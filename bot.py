import os
import discord
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv
from discord import Interaction
import asyncio
import subprocess
import re
import time
import json
import uuid
import shutil
from datetime import datetime
from typing import Optional, Dict, Any
from urllib.parse import urlparse

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
DOWNLOAD_CHANNEL_ID = int(os.getenv("DOWNLOAD_CHANNEL_ID"))
GUILD_ID = discord.Object(id=int(os.getenv("GUILD_ID")))

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# Global variables
downloads = {}  # download_id -> DownloadManager
last_downloads = {}  # user_id -> download_id (for /note command)

# Helper function to format URLs for Discord embeds
def format_url(url: str) -> str:
    if not url:
        return url
    
    # If URL already has a scheme, return as-is
    parsed = urlparse(url)
    if parsed.scheme in ['http', 'https']:
        return url
    
    # If no scheme, assume https
    if not parsed.scheme:
        return f"https://{url}"
    
    # For other schemes, convert to https
    return f"https://{parsed.netloc or url}"

def get_service_icon(service: str) -> str:
    """Get the icon URL for a service"""
    icons = {
        "MEGA": "https://github.com/slink-y/zurg/blob/main/assets/icons/mega.png?raw=true",
        "ffsend": "https://github.com/slink-y/zurg/blob/main/assets/icons/ffsend.png?raw=true",
        "Direct Download": "https://github.com/slink-y/zurg/blob/main/assets/icons/direct.png?raw=true"
    }
    return icons.get(service, "https://github.com/slink-y/zurg/blob/main/assets/icons/direct.png?raw=true")


def _parse_size_to_mb(size_str: str) -> float:
    """Parse a size string like '21.26 MB', '12 KiB', '1.5 GB' into MB (float)."""
    try:
        parts = size_str.strip().split()
        if not parts:
            return 0.0
        value = float(parts[0].replace(',', '.'))
        unit = parts[1].lower() if len(parts) > 1 else 'mb'
        if unit in ('b', 'bytes'):
            return value / (1024 * 1024)
        if unit in ('kb', 'kib'):
            return value / 1024
        if unit in ('mb', 'mib'):
            return value
        if unit in ('gb', 'gib'):
            return value * 1024
    except Exception:
        return 0.0
    return 0.0

def generate_download_id():
    """Generate a unique download ID"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    unique_id = str(uuid.uuid4())[:8]
    return f"dl_{timestamp}_{unique_id}"

class DownloadHistory:
    """Manage download history and logging"""
    def __init__(self):
        self.history_file = "/mnt/transformer/logs/downloads.json"
        self.ensure_logs_directory()
    
    def ensure_logs_directory(self):
        """Ensure logs directory exists"""
        os.makedirs("/mnt/transformer/logs", exist_ok=True)
        os.makedirs("/mnt/transformer/tmp", exist_ok=True)
        os.makedirs("/mnt/transformer/storage/archives", exist_ok=True)
        
        # Initialize downloads.json if it doesn't exist
        if not os.path.exists(self.history_file):
            with open(self.history_file, 'w') as f:
                json.dump({"downloads": []}, f, indent=2)
    
    def add_download(self, log_data):
        """Add a download to the history"""
        with open(self.history_file, 'r') as f:
            data = json.load(f)
        
        data["downloads"].append(log_data)
        
        with open(self.history_file, 'w') as f:
            json.dump(data, f, indent=2)
    
    def save_individual_log(self, download_id, log_data):
        """Save individual log file"""
        individual_log_path = f"/mnt/transformer/logs/{download_id}.json"
        with open(individual_log_path, 'w') as f:
            json.dump(log_data, f, indent=2)
    
    def save_archive_log(self, download_id, log_data):
        """Save log with archive"""
        archive_dir = f"/mnt/transformer/storage/archives/{download_id}"
        os.makedirs(archive_dir, exist_ok=True)
        
        archive_log_path = f"{archive_dir}/download_log.json"
        with open(archive_log_path, 'w') as f:
            json.dump(log_data, f, indent=2)

class DownloadManager:
    def __init__(self, message: discord.Message, url: str):
        self.message = message
        self.url = format_url(url)
        self.download_id = generate_download_id()
        self.destination = None
        self.note = None
        self.download_task = None
        self.is_cancelled = False
        self.progress = 0
        self.total_size = 0
        self.downloaded_size = 0
        self.speed = 0
        self.status = "🔎 Starting download..."
        self.file_name = "Unknown"
        self.service = "Unknown"
        self.temp_dir = f"/mnt/transformer/tmp/{self.download_id}"
        self.archive_dir = f"/mnt/transformer/storage/archives/{self.download_id}"
        self.download_start_time = None
        self.download_duration = 0
        self.archive_size = 0
        self.file_count = 0
        self.has_archive_file = False  # Track if we actually saved an archive file
        self.history = DownloadHistory()
        
        # Track this as the user's last download for /note command
        last_downloads[message.author.id] = self.download_id
        
        # Ensure temp directory exists
        os.makedirs(self.temp_dir, exist_ok=True)
        
    async def start_download(self):
        """Start the download process and update status"""
        try:
            # Identify the service and file info
            await self._identify_source()
            
            # Start the actual download
            self.download_task = asyncio.create_task(self._perform_download())
            
            # Start status updates
            await self._update_status_loop()
            
        except Exception as e:
            await self._update_embed(f"❌ Error: {str(e)}")
    
    async def _identify_source(self):
        if "mega.nz" in self.url or "mega.co.nz" in self.url:
            self.service = "MEGA"
            self.file_name = "MEGA File"  # Will be updated during download
        elif "send.vis.ee" in self.url or "ffsend" in self.url:
            self.service = "ffsend"
            self.file_name = "ffsend File"  # Will be updated after download
        else:
            self.service = "Direct Download"
            self.file_name = "File"
        
        await self._update_embed()
    
    def _unwrap_nested_directories(self, base_path):
        """
        Unwrap unnecessary nested directories like /media/mousebits/actualfolderhere
        Returns the path to the actual content directory
        """
        try:
            # Get all items in the base directory
            items = os.listdir(base_path)
            if not items:
                return base_path
            
            # If there's only one item and it's a directory, check if it needs unwrapping
            if len(items) == 1:
                single_item = os.path.join(base_path, items[0])
                if os.path.isdir(single_item):
                    # Check if this directory contains only one subdirectory
                    sub_items = os.listdir(single_item)
                    if len(sub_items) == 1 and os.path.isdir(os.path.join(single_item, sub_items[0])):
                        # This looks like a nested structure, unwrap it
                        actual_content_dir = os.path.join(single_item, sub_items[0])
                        print(f"Unwrapping nested directory: {single_item} -> {actual_content_dir}")
                        
                        # Move the actual content up one level
                        temp_unwrap_dir = os.path.join(base_path, "unwrapped")
                        shutil.move(actual_content_dir, temp_unwrap_dir)
                        
                        # Remove the empty nested directories
                        shutil.rmtree(single_item)
                        
                        # Move the content back to the base level
                        shutil.move(temp_unwrap_dir, os.path.join(base_path, sub_items[0]))
                        
                        return os.path.join(base_path, sub_items[0])
            
            return base_path
        except Exception as e:
            print(f"Error unwrapping directories: {e}")
            return base_path
    
    async def _perform_download(self):
        """Perform the actual download using ffsend"""
        self.status = "⏳ Downloading..."
        self.download_start_time = time.time()
        await self._update_embed()
        
        try:
            if self.service == "ffsend":
                await self._download_with_ffsend()
            elif self.service == "MEGA":
                await self._download_with_mega()
            else:
                await self._download_with_wget()
                
        except Exception as e:
            self.status = f"❌ Download failed: {str(e)}"
            await self._update_embed()
            return
        
        if not self.is_cancelled:
            self.status = "📦 Extracting files..."
            await self._update_embed()
            await self._extract_files()
            
            # Check if destination was already selected during download
            if self.destination:
                self.status = "➡️ Moving to destination..."
                await self._update_embed()
                await self._complete_download()
            else:
                self.status = "⏸️ Waiting for destination..."
                await self._update_embed()
    
    async def _download_with_ffsend(self):
        """Download using ffsend with progress parsing"""
        try:
            # Run ffsend download command
            process = await asyncio.create_subprocess_exec(
                "ffsend", "download", "-y", self.url, "--output", self.temp_dir,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                stdin=asyncio.subprocess.PIPE
            )
            # Stream output and parse progress as it arrives so the embed can be updated
            buffer = ""
            ansi_re = re.compile(r'\x1b\[[0-9;]*[A-Za-z]')
            full_prog_re = re.compile(r'([\d\.,]+)\s*(B|KB|KIB|MB|MIB|GB|GIB)?\s*/\s*([\d\.,]+)\s*(B|KB|KIB|MB|MIB|GB|GIB)?.*?([\d\.,]+)\s*%', re.IGNORECASE)
            pct_only_re = re.compile(r'([\d\.,]+)\s*%.*?([\d\.,]+)\s*(B|KB|KIB|MB|MIB|GB|GIB)?/s', re.IGNORECASE)
            speed_re = re.compile(r'([\d\.,]+)\s*(B|KB|KIB|MB|MIB|GB|GIB)?/s', re.IGNORECASE)

            while True:
                chunk = await process.stdout.read(1024)
                if not chunk:
                    break
                try:
                    text = chunk.decode(errors='ignore')
                except Exception:
                    text = chunk.decode('utf-8', errors='ignore')

                # Strip ANSI sequences
                clean = ansi_re.sub('', text)
                clean = clean.replace('\x1b[K', '')

                # Append to buffer
                buffer += clean

                # Look for the last full progress match
                full_matches = list(full_prog_re.finditer(buffer))
                if full_matches:
                    m = full_matches[-1]
                    try:
                        downloaded_raw = f"{m.group(1)} {m.group(2) or 'MB'}"
                        total_raw = f"{m.group(3)} {m.group(4) or 'MB'}"
                        perc_raw = m.group(5)
                        self.downloaded_size = _parse_size_to_mb(downloaded_raw)
                        self.total_size = _parse_size_to_mb(total_raw)
                        self.progress = float(perc_raw.replace(',', '.'))
                    except Exception:
                        pass

                    # speed
                    sm = speed_re.search(buffer)
                    if sm:
                        try:
                            speed_val = float(sm.group(1).replace(',', '.'))
                            speed_unit = (sm.group(2) or 'MB').upper()
                            if speed_unit in ('B',):
                                self.speed = speed_val / (1024 * 1024)
                            elif speed_unit in ('KB', 'KIB'):
                                self.speed = speed_val / 1024
                            elif speed_unit in ('MB', 'MIB'):
                                self.speed = speed_val
                            elif speed_unit in ('GB', 'GIB'):
                                self.speed = speed_val * 1024
                        except Exception:
                            pass

                    try:
                        await self._update_embed()
                    except Exception:
                        pass

                    # Truncate buffer up to the matched end to avoid repeated parsing
                    buffer = buffer[m.end():]
                    continue

                # Otherwise, try percent-only
                pct_matches = list(pct_only_re.finditer(buffer))
                if pct_matches:
                    m = pct_matches[-1]
                    try:
                        self.progress = float(m.group(1).replace(',', '.'))
                        speed_val = float(m.group(2).replace(',', '.'))
                        speed_unit = (m.group(3) or 'MB').upper()
                        if speed_unit in ('B',):
                            self.speed = speed_val / (1024 * 1024)
                        elif speed_unit in ('KB', 'KIB'):
                            self.speed = speed_val / 1024
                        elif speed_unit in ('MB', 'MIB'):
                            self.speed = speed_val
                        elif speed_unit in ('GB', 'GIB'):
                            self.speed = speed_val * 1024
                    except Exception:
                        pass

                    try:
                        await self._update_embed()
                    except Exception:
                        pass

                    buffer = buffer[m.end():]

                # Prevent buffer growth
                if len(buffer) > 8192:
                    buffer = buffer[-8192:]
            # Wait for process to exit and get return code
            returncode = await process.wait()

            if returncode == 0:
                self.download_duration = time.time() - self.download_start_time
                print(f"Download completed in {self.download_duration:.2f} seconds")
                # ffsend with -y flag auto-extracts, so we need to handle this differently
                # First, try to unwrap any unnecessary nested directories
                unwrapped_path = self._unwrap_nested_directories(self.temp_dir)
                
                # Calculate total size of extracted files and determine file name
                total_size_bytes = 0
                file_count = 0
                
                # Get the top-level directory name as the file name
                temp_contents = os.listdir(unwrapped_path)
                if temp_contents:
                    # Use the first directory as the file name, or first file if no directories
                    top_level_item = temp_contents[0]
                    if os.path.isdir(os.path.join(unwrapped_path, top_level_item)):
                        self.file_name = top_level_item
                    else:
                        # If it's a file, use the filename without extension
                        self.file_name = os.path.splitext(top_level_item)[0]
                
                for root, dirs, files in os.walk(unwrapped_path):
                    for file in files:
                        file_path = os.path.join(root, file)
                        if os.path.isfile(file_path):
                            file_size = os.path.getsize(file_path)
                            total_size_bytes += file_size
                            file_count += 1
                
                self.archive_size = total_size_bytes
                self.file_count = file_count
                
                # Update total_size if we got it from ffsend info, otherwise use calculated size
                if self.total_size == 0:
                    self.total_size = total_size_bytes / (1024 * 1024)
                
                print(f"Downloaded and extracted: {self.file_name} ({file_count} files, {total_size_bytes} bytes)")
            else:
                raise Exception("ffsend download failed")
                
        except Exception as e:
            raise Exception(f"ffsend download error: {str(e)}")
    
    async def _download_with_mega(self):
        """Download using mega-get"""
        try:
            # Run mega-get command
            process = await asyncio.create_subprocess_exec(
                "mega-get", self.url, self.temp_dir,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                stdin=asyncio.subprocess.PIPE
            )
            
            # Stream output and parse progress as it arrives
            buffer = ""
            ansi_re = re.compile(r'\x1b\[[0-9;]*[A-Za-z]')
            # MEGA progress format: TRANSFERRING ||#############################.........||(112/147 MB:  76.12 %)
            mega_prog_re = re.compile(r'TRANSFERRING.*?\((\d+)/(\d+)\s*MB:\s*(\d+\.\d+)\s*%\s*\)', re.IGNORECASE)
            
            while True:
                chunk = await process.stdout.read(1024)
                if not chunk:
                    break
                try:
                    text = chunk.decode(errors='ignore')
                except Exception:
                    text = chunk.decode('utf-8', errors='ignore')
                
                # Strip ANSI sequences and clean up the text
                clean = ansi_re.sub('', text)
                clean = clean.replace('\x1b[K', '')
                clean = clean.replace('\x00', '')  # Remove null characters
                clean = clean.replace('\r', '')  # Remove carriage returns
                
                # Append to buffer
                buffer += clean
                
                # Look for MEGA progress in the buffer (handle overwriting lines)
                matches = list(mega_prog_re.finditer(buffer))
                if matches:
                    m = matches[-1]  # Get the last (most recent) match
                    try:
                        downloaded_mb = float(m.group(1))
                        total_mb = float(m.group(2))
                        progress_pct = float(m.group(3))
                        
                        print(f"MEGA progress: {downloaded_mb}/{total_mb} MB ({progress_pct}%)")
                        
                        self.downloaded_size = downloaded_mb
                        self.total_size = total_mb
                        self.progress = progress_pct
                        
                        # Update embed with progress
                        await self._update_embed()
                    except Exception as e:
                        print(f"MEGA progress parsing error: {e}")
                        pass
                    
                    # Keep only the last part of the buffer to avoid memory issues
                    buffer = buffer[-1024:]
                
                # Prevent buffer growth
                if len(buffer) > 8192:
                    buffer = buffer[-8192:]
            
            # Wait for process to exit
            returncode = await process.wait()
            
            if returncode == 0:
                self.download_duration = time.time() - self.download_start_time
                print(f"MEGA download completed in {self.download_duration:.2f} seconds")
                
                # Discover actual file name and size after download
                for file in os.listdir(self.temp_dir):
                    file_path = os.path.join(self.temp_dir, file)
                    if os.path.isfile(file_path):
                        self.file_name = file
                        self.archive_size = os.path.getsize(file_path)
                        print(f"Downloaded file: {file} ({self.archive_size} bytes)")
                        break
                    elif os.path.isdir(file_path):
                        # If it's a directory, use the directory name
                        self.file_name = file
                        # Calculate total size of directory
                        total_size_bytes = 0
                        file_count = 0
                        for root, dirs, files in os.walk(file_path):
                            for f in files:
                                total_size_bytes += os.path.getsize(os.path.join(root, f))
                                file_count += 1
                        self.archive_size = total_size_bytes
                        self.file_count = file_count
                        print(f"Downloaded directory: {file} ({file_count} files, {total_size_bytes} bytes)")
                        break
            else:
                raise Exception("mega-get download failed")
                
        except Exception as e:
            raise Exception(f"MEGA download error: {str(e)}")
    
    async def _download_with_wget(self):
        """Download using wget (placeholder for now)"""
        # TODO: Implement wget download
        await asyncio.sleep(1)  # Placeholder
    
    async def _extract_files(self):
        """Extract downloaded files"""
        try:
            extracted_dir = os.path.join(self.temp_dir, "extracted")
            os.makedirs(extracted_dir, exist_ok=True)
            
            # Find archive files and extract them
            archive_files_found = False
            for file in os.listdir(self.temp_dir):
                file_path = os.path.join(self.temp_dir, file)
                if os.path.isfile(file_path) and file.endswith(('.zip', '.rar', '.7z', '.tar', '.gz')):
                    archive_files_found = True
                    # Extract using appropriate tool
                    if file.endswith('.zip'):
                        result = await asyncio.create_subprocess_exec(
                            "unzip", file_path, "-d", extracted_dir
                        )
                        await result.wait()
                    elif file.endswith('.tar.gz') or file.endswith('.tgz'):
                        result = await asyncio.create_subprocess_exec(
                            "tar", "-xzf", file_path, "-C", extracted_dir
                        )
                        await result.wait()
                    # Add more extraction methods as needed
            
            # Only count extracted files if we actually extracted something
            if archive_files_found:
                self.file_count = sum(len(files) for _, _, files in os.walk(extracted_dir))
            # If no archive files found (e.g., ffsend auto-extracted), keep the existing file_count
            
        except Exception as e:
            print(f"Extraction error: {e}")
            # Continue even if extraction fails
    
    async def _update_status_loop(self):
        """Continuously update the status embed"""
        while not self.is_cancelled and self.download_task and not self.download_task.done():
            # Update embed periodically to reflect any progress parsed by the download tasks
            try:
                await self._update_embed()
            except Exception:
                pass
            await asyncio.sleep(1)  # Update every second
    
    async def _update_embed(self, error_message: str = None):
        """Update the Discord embed with current status"""
        if error_message:
            description = f"❌ {error_message}"
        else:
            # Create progress bar
            filled = int(self.progress / 10)
            progress_bar = "▓" * filled + "░" * (10 - filled)
            
            # Format sizes
            if self.total_size > 0:
                if self.total_size >= 1024 * 1024:  # GB
                    size_info = f"{self.downloaded_size/1024:.1f} GB of {self.total_size/1024:.1f} GB"
                else:  # MB
                    size_info = f"{self.downloaded_size:.1f} MB of {self.total_size:.1f} MB"
            else:
                size_info = f"{self.downloaded_size:.1f} MB of ?"
            
            # Speed info (only for ffsend and direct downloads, not MEGA)
            if self.service != "MEGA":
                speed_info = f"{self.speed:.2f} MB/s" if self.speed > 0 else "0.00 MB/s"
                
                # Grey out speed info after completion
                if self.status == "✅ Download complete.":
                    speed_info = f"-# {speed_info}"
            else:
                speed_info = None
            
            # Destination info
            dest_info = f"📁 {self.destination}" if self.destination else "📁 Select a destination"
            
            # Notes info - only show if note exists
            note_info = f"📒 {self.note}" if self.note else ""
            
            # Build description parts
            description_parts = [
                f"{self.status}\n\n",
                f"[{progress_bar}] - **{self.progress}%**\n\n",
                f"{size_info}"
            ]
            
            # Add speed info only if available (not for MEGA)
            if speed_info is not None:
                description_parts.append(f"\n{speed_info}")
            
            description_parts.extend(["\n\n", f"{dest_info}"])
            
            description = "".join(description_parts)
            
            # Show notes line after submitted
            if note_info:
                description += f"\n{note_info}"
        
        embed = discord.Embed(
            title=self.file_name,
            url=self.url,
            description=description,
            color=discord.Color.blue() if not error_message else discord.Color.red()
        )
        embed.set_author(name=self.service, icon_url=get_service_icon(self.service))
        
        try:
            await self.message.edit(embed=embed)
            print(f"Embed updated: {self.file_name} - {self.progress}%")
        except discord.NotFound:
            # Message was deleted
            pass
    
    def set_destination(self, destination: str):
        """Set the download destination"""
        self.destination = destination
        # Update the embed to show the selected destination
        asyncio.create_task(self._update_embed())
        
        # If download is already complete and waiting for destination, complete it now
        if self.status == "⏸⚠️ Waiting for destination...":
            self.status = "➡️ Moving to destination..."
            asyncio.create_task(self._update_embed())
            # Complete the download process
            asyncio.create_task(self._complete_download())
    
    def set_note(self, note: str):
        """Set a note for the download"""
        self.note = note
        asyncio.create_task(self._update_embed())
        
        # If download is complete, save the note to logs
        if self.status == "✅ Download complete.":
            asyncio.create_task(self._save_note_to_logs())
    
    async def update_view_after_completion(self):
        """Update the view to hide cancel button and destination dropdown after completion"""
        try:
            # Create a new view with only the note button
            view = CompletedDownloadView(self)
            
            # Update the message with the new view
            await self.message.edit(view=view)
        except Exception as e:
            print(f"Error updating view after completion: {e}")
    
    async def _save_note_to_logs(self):
        """Save note to logs after download completion"""
        try:
            # Read the current log data
            individual_log_path = f"/mnt/transformer/logs/{self.download_id}.json"
            if os.path.exists(individual_log_path):
                with open(individual_log_path, 'r') as f:
                    log_data = json.load(f)
                
                # Update the note
                log_data["note"] = self.note
                
                # Save back to individual log
                with open(individual_log_path, 'w') as f:
                    json.dump(log_data, f, indent=2)
                
                # Update main downloads log
                self.history.add_download(log_data)
                
                # Update archive log if it exists
                archive_log_path = f"/mnt/transformer/storage/archives/{self.download_id}/download_log.json"
                if os.path.exists(archive_log_path):
                    with open(archive_log_path, 'w') as f:
                        json.dump(log_data, f, indent=2)
                
                print(f"Note saved to logs: {self.note}")
        except Exception as e:
            print(f"Error saving note to logs: {e}")
    
    async def _complete_download(self):
        """Complete the download process"""
        try:
            # Move files to final destination
            if self.destination:
                final_path = f"/mnt/transformer/{self.destination}"
                os.makedirs(final_path, exist_ok=True)
                
                # Move files - handle different extraction scenarios
                extracted_dir = os.path.join(self.temp_dir, "extracted")
                if os.path.exists(extracted_dir) and os.listdir(extracted_dir):
                    # Files were extracted to extracted directory (normal extraction)
                    for item in os.listdir(extracted_dir):
                        src = os.path.join(extracted_dir, item)
                        dst = os.path.join(final_path, item)
                        if os.path.isdir(src):
                            shutil.copytree(src, dst)
                        else:
                            shutil.copy2(src, dst)
                else:
                    # No extracted directory or empty - check if ffsend auto-extracted or files are direct
                    # For ffsend, files are already extracted to temp_dir
                    # For other services, move files directly
                    for item in os.listdir(self.temp_dir):
                        if item in ["extracted", "unwrapped"]:  # Skip empty directories
                            continue
                        src = os.path.join(self.temp_dir, item)
                        dst = os.path.join(final_path, item)
                        if os.path.isdir(src):
                            # Directory (likely from ffsend auto-extraction)
                            shutil.copytree(src, dst)
                        elif os.path.isfile(src):
                            # Single file
                            shutil.copy2(src, dst)
                
                # Archive original files (if any exist)
                os.makedirs(self.archive_dir, exist_ok=True)
                archive_files_found = False
                for file in os.listdir(self.temp_dir):
                    file_path = os.path.join(self.temp_dir, file)
                    if os.path.isfile(file_path) and file.endswith(('.zip', '.rar', '.7z', '.tar', '.gz')):
                        shutil.copy2(file_path, self.archive_dir)
                        archive_files_found = True
                        self.has_archive_file = True
                
                # If no archive files found (e.g., ffsend auto-extracted), create a note about it
                if not archive_files_found:
                    archive_note_path = os.path.join(self.archive_dir, "no_archive_note.txt")
                    with open(archive_note_path, 'w') as f:
                        f.write(f"Downloaded via {self.service} - files were auto-extracted\n")
                        f.write(f"Original URL: {self.url}\n")
                        f.write(f"Downloaded on: {datetime.now().isoformat()}\n")
                
                # Create log data
                log_data = {
                    "id": self.download_id,
                    "timestamp": datetime.now().isoformat(),
                    "url": self.url,
                    "service": self.service,
                    "file_name": self.file_name,
                    "destination": f"/mnt/transformer/{self.destination}",
                    "final_path": final_path,
                    "size_bytes": int(self.archive_size),  # Convert to integer bytes
                    "file_count": self.file_count,
                    "download_duration": self.download_duration,
                    "note": self.note,
                    "status": "completed"
                }
                
                # Only include archive_size_bytes if we actually saved an archive file
                if self.has_archive_file:
                    log_data["archive_size_bytes"] = int(self.archive_size)
                
                # Save logs to all locations
                self.history.add_download(log_data)
                self.history.save_individual_log(self.download_id, log_data)
                self.history.save_archive_log(self.download_id, log_data)
                
                # Clean up temp directory
                shutil.rmtree(self.temp_dir, ignore_errors=True)
            
            self.status = "✅ Download complete."
            await self._update_embed()
            
            # Update the view to hide cancel button and destination dropdown
            await self.update_view_after_completion()
            
        except Exception as e:
            self.status = f"❌ Error completing download: {str(e)}"
            await self._update_embed()
    
    def cancel(self):
        """Cancel the download"""
        self.is_cancelled = True
        if self.download_task:
            self.download_task.cancel()


class DestinationDropdown(discord.ui.Select):
    def __init__(self, download_manager: DownloadManager):
        self.download_manager = download_manager
        options = [
            discord.SelectOption(label="music/"),
            discord.SelectOption(label="media/"),
            discord.SelectOption(label="shared/"),
            discord.SelectOption(label="downloads/"),
            discord.SelectOption(label="test/"),
        ]
        super().__init__(
            placeholder="Choose a destination...",
            min_values=1,
            max_values=1,
            options=options,
            row=0
        )

    async def callback(self, interaction: discord.Interaction):
        destination = self.values[0]
        self.download_manager.set_destination(destination)
        await interaction.response.defer()

class DownloadView(discord.ui.View):
    def __init__(self, download_manager: DownloadManager):
        super().__init__()
        self.download_manager = download_manager
        self.add_item(DestinationDropdown(download_manager))

    @discord.ui.button(label="Add Note", style=discord.ButtonStyle.primary, row=1)
    async def add_note_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(NoteModal(self.download_manager))

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.danger, row=1)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.download_manager.cancel()
        await interaction.response.edit_message(content="❌ Download cancelled.", view=None)


class CompletedDownloadView(discord.ui.View):
    def __init__(self, download_manager: DownloadManager):
        super().__init__()
        self.download_manager = download_manager
        # Add the note button with correct initial text
        self.add_item(NoteButton(download_manager))

class NoteButton(discord.ui.Button):
    def __init__(self, download_manager: DownloadManager):
        self.download_manager = download_manager
        super().__init__(
            label="Edit Note" if download_manager.note else "Add Note",
            style=discord.ButtonStyle.primary,
            row=0
        )
    
    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(NoteModal(self.download_manager))


class NoteModal(discord.ui.Modal, title="Add a Note"):
    def __init__(self, download_manager: DownloadManager):
        super().__init__()
        self.download_manager = download_manager
        self.note = discord.ui.TextInput(label="Note", style=discord.TextStyle.paragraph)
        self.add_item(self.note)
    
    async def on_submit(self, interaction: discord.Interaction):
        self.download_manager.set_note(self.note.value)
        
        # Update the button text if we're in a CompletedDownloadView
        if hasattr(interaction.message, 'view') and isinstance(interaction.message.view, CompletedDownloadView):
            # Update the existing button text
            for item in interaction.message.view.children:
                if isinstance(item, NoteButton):
                    item.label = "Edit Note" if self.download_manager.note else "Add Note"
                    break
            await interaction.message.edit(view=interaction.message.view)
        
        await interaction.response.defer()


@bot.tree.command(name="download", description="Start download from URL")
@app_commands.describe(url="The URL to download from")
async def download(interaction: discord.Interaction, url: str):
    # Format the URL to ensure it's valid for Discord embeds
    formatted_url = format_url(url)
    # Create initial embed
    description = (
        "🔎 Starting download...\n\n"
        "[░░░░░░░░░░] - **0%**\n\n"
        "0 MB of ?\n"
        "0 MB/s\n\n"
        "📁 *No destination selected*"
    )

    embed = discord.Embed(
        title="Unknown File",
        url=formatted_url,
        description=description,
        color=discord.Color.blue()
    )
    embed.set_author(name="Identifying source...", icon_url=get_service_icon("Direct Download"))

    # Send the initial message
    await interaction.response.send_message(embed=embed)
    message = await interaction.original_response()

    # Create download manager and start the download
    download_manager = DownloadManager(message, formatted_url)
    view = DownloadView(download_manager)
    
    # Update the message with the view
    await message.edit(embed=embed, view=view)
    
    # Start the download process
    asyncio.create_task(download_manager.start_download())

@bot.tree.command(name="test", description="Test command to verify bot is working")
@app_commands.guilds(GUILD_ID)
async def test_command(interaction: discord.Interaction):
    """Simple test command"""
    await interaction.response.send_message("✅ Bot is working!", ephemeral=True)

@bot.tree.command(name="lastlog", description="Show the last download log")
async def last_log(interaction: discord.Interaction):
    try:
        # Read the downloads log file
        downloads_file = "/mnt/transformer/logs/downloads.json"
        if not os.path.exists(downloads_file):
            await interaction.response.send_message("❌ No download logs found.", ephemeral=True)
            return
        
        with open(downloads_file, 'r') as f:
            data = json.load(f)
        
        downloads = data.get("downloads", [])
        if not downloads:
            await interaction.response.send_message("❌ No downloads found in logs.", ephemeral=True)
            return
        
        # Get the last download
        last_download = downloads[-1]
        
        # Format the log data
        service_emoji = {
            "MEGA": "🔴",
            "ffsend": "✉️", 
            "Direct Download": "🔗"
        }
        
        service_icon = service_emoji.get(last_download.get("service", ""), "📁")
        
        # Format timestamp
        timestamp = last_download.get("timestamp", "")
        if timestamp:
            try:
                dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                formatted_time = dt.strftime("%Y-%m-%d %H:%M:%S")
            except:
                formatted_time = timestamp
        else:
            formatted_time = "Unknown"
        
        # Format file size
        size_bytes = last_download.get("size_bytes", 0)
        if size_bytes >= 1024 * 1024 * 1024:  # GB
            size_str = f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"
        elif size_bytes >= 1024 * 1024:  # MB
            size_str = f"{size_bytes / (1024 * 1024):.1f} MB"
        elif size_bytes >= 1024:  # KB
            size_str = f"{size_bytes / 1024:.1f} KB"
        else:
            size_str = f"{size_bytes} bytes"
        
        # Format duration
        duration = last_download.get("download_duration", 0)
        if duration >= 60:
            duration_str = f"{duration/60:.1f} minutes"
        else:
            duration_str = f"{duration:.1f} seconds"
        
        # Create description with all the info
        description_lines = [
            f"🌐 **Service:** {last_download.get('service', 'Unknown')}",
            f"📊 **Size:** {size_str}",
            f"📂 **Destination:** `{last_download.get('destination', 'Unknown')}`",
            f"📈 **Files:** {last_download.get('file_count', 0)}",
            f"⏱️ **Duration:** {duration_str}",
            f"🕒 **Downloaded:** {formatted_time}"
        ]
        
        # Add note if exists
        note = last_download.get("note")
        if note:
            description_lines.append(f"📝 **Note:** {note}")
        
        # Add URL if exists
        url = last_download.get("url")
        if url:
            description_lines.append(f"🔗 **URL:** {url}")
        
        # Create embed
        embed = discord.Embed(
            title=f"{service_icon} {last_download.get('file_name', 'Unknown File')}",
            description="\n".join(description_lines),
            color=discord.Color.blue(),
            timestamp=datetime.now()
        )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
        
    except Exception as e:
        await interaction.response.send_message(
            f"❌ Error retrieving last log: {str(e)}",
            ephemeral=True
        )

@bot.tree.command(name="note", description="Add or edit a note for your last download")
@app_commands.describe(content="The note content to add or edit")
async def note_command(interaction: discord.Interaction, content: str):
    try:
        user_id = interaction.user.id
        
        # Check if user has a recent download
        if user_id not in last_downloads:
            await interaction.response.send_message(
                "❌ No recent download found to add a note to. Start a download first!",
                ephemeral=True
            )
            return
        
        download_id = last_downloads[user_id]
        
        # Check if the download still exists
        if download_id not in downloads:
            await interaction.response.send_message(
                "❌ Your last download is no longer active. Start a new download first!",
                ephemeral=True
            )
            return
        
        download_manager = downloads[download_id]
        
        # Set the note
        download_manager.set_note(content)
        
        # Update the embed to show the new note
        await download_manager._update_embed()
        
        await interaction.response.send_message(
            f"✅ Note {'updated' if download_manager.note else 'added'} successfully!",
            ephemeral=True
        )
        
    except Exception as e:
        await interaction.response.send_message(
            f"❌ Error adding note: {str(e)}",
            ephemeral=True
        )

@bot.tree.command(name="refresh", description="Force refresh bot commands")
async def refresh_commands(interaction: discord.Interaction):
    try:
        # Clear all commands
        bot.tree.clear_commands(guild=None)
        
        # Sync commands globally
        synced = await bot.tree.sync()
        
        await interaction.response.send_message(
            "🔄 Commands refreshed.",
            ephemeral=True
        )
    except Exception as e:
        await interaction.response.send_message(
            f"❌ Error refreshing commands: {str(e)}",
            ephemeral=True
        )

@bot.event
async def on_connect():
    print("Connected to Discord")

@bot.event
async def on_ready():
    print("Logged in as {bot.user}")
    #try:
       # Sync commands globally (to all servers the bot is in)
       #synced = await bot.tree.sync()
       #print(f"✅ Synced {len(synced)} commands globally")
    #except Exception as e:
        #print(f"❌ Error syncing commands: {e}")

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return
    
    if message.content == "!test":
        await message.channel.send("✅ Bot is responding to messages")

if __name__ == "__main__":
    print("Starting bot...")
    bot.run(TOKEN)