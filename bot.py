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
from typing import Optional, Dict, Any

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
DOWNLOAD_CHANNEL_ID = int(os.getenv("DOWNLOAD_CHANNEL_ID"))
GUILD_ID = discord.Object(id=int(os.getenv("GUILD_ID")))

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

class DownloadManager:
    def __init__(self, message: discord.Message, url: str):
        self.message = message
        self.url = url
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
            # You would use megacmd here to get file info
            self.file_name = "MEGA File"
        elif "ffsend" in self.url:
            self.service = "ffsend"
            self.file_name = "ffsend File"
        else:
            self.service = "Direct Download"
            self.file_name = "File"
        
        await self._update_embed()
    
    async def _perform_download(self):
        self.status = "⏳ Downloading..."
        await self._update_embed()
        
        # Simulate download progress (replace with actual download logic)
        for i in range(101):
            if self.is_cancelled:
                return
            
            self.progress = i
            self.downloaded_size = int((i / 100) * 100)  # Simulate 100MB total
            self.total_size = 100
            self.speed = 5 + (i % 10)  # Simulate varying speed
            
            await asyncio.sleep(0.1)  # Simulate download time
        
        if not self.is_cancelled:
            self.status = "📦 Extracting files..."
            await self._update_embed()
            await asyncio.sleep(2)  # Simulate extraction
            
            self.status = "⏸️ Waiting for destination selection..."
            await self._update_embed()
    
    async def _update_status_loop(self):
        """Continuously update the status embed"""
        while not self.is_cancelled and self.download_task and not self.download_task.done():
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
                size_info = f"{self.downloaded_size} MB of {self.total_size} MB"
            else:
                size_info = f"{self.downloaded_size} MB of ?"
            
            speed_info = f"{self.speed} MB/s" if self.speed > 0 else "0 MB/s"
            
            # Destination info
            dest_info = f"📁 {self.destination}" if self.destination else "📁 *(no destination yet)*"
            
            # Notes info
            note_info = f"📒 {self.note}" if self.note else "📒 *(no notes yet)*"
            
            description = (
                f"{self.status}\n\n"
                f"[{progress_bar}] - **{self.progress}%**\n\n"
                f"{size_info}\n"
                f"{speed_info}\n\n"
                f"{dest_info}\n"
                f"{note_info}"
            )
        
        embed = discord.Embed(
            title=self.file_name,
            description=description,
            color=discord.Color.blue() if not error_message else discord.Color.red()
        )
        embed.set_author(name=self.service)
        embed.add_field(name="URL", value=self.url, inline=False)
        
        try:
            await self.message.edit(embed=embed)
        except discord.NotFound:
            # Message was deleted
            pass
    
    def set_destination(self, destination: str):
        """Set the download destination"""
        self.destination = destination
        if self.status == "☑️ Download finished, waiting for destination selection...":
            self.status = "➡️ Moving to destination..."
            asyncio.create_task(self._update_embed())
            # Simulate moving files
            asyncio.create_task(self._complete_download())
    
    def set_note(self, note: str):
        """Set a note for the download"""
        self.note = note
        asyncio.create_task(self._update_embed())
    
    async def _complete_download(self):
        """Complete the download process"""
        await asyncio.sleep(2)  # Simulate moving files
        self.status = "✅ Download complete."
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
        await interaction.response.send_message(
            f"Files will be saved to `{destination}`", ephemeral=True
        )

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


class NoteModal(discord.ui.Modal, title="Add a Note"):
    def __init__(self, download_manager: DownloadManager):
        super().__init__()
        self.download_manager = download_manager
        self.note = discord.ui.TextInput(label="Note", style=discord.TextStyle.paragraph)
        self.add_item(self.note)
    
    async def on_submit(self, interaction: discord.Interaction):
        self.download_manager.set_note(self.note.value)
        await interaction.response.send_message(f"📝 Note saved: {self.note.value}", ephemeral=True)


@bot.tree.command(name="download", description="Start download from URL")
@app_commands.describe(url="The URL to download from")
@app_commands.guilds(GUILD_ID)
async def download(interaction: discord.Interaction, url: str):
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
        description=description,
        color=discord.Color.blue()
    )
    embed.set_author(name="Identifying source...")
    embed.add_field(name="URL", value=url, inline=False)

    # Send the initial message
    await interaction.response.send_message(embed=embed)
    message = await interaction.original_response()

    # Create download manager and start the download
    download_manager = DownloadManager(message, url)
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

@bot.tree.command(name="refresh", description="Force refresh bot commands")
@app_commands.guilds(GUILD_ID)
async def refresh_commands(interaction: discord.Interaction):
    try:
        # Clear all commands
        bot.tree.clear_commands(guild=None)
        bot.tree.clear_commands(guild=GUILD_ID)
        
        # Sync to guild
        await bot.tree.sync(guild=GUILD_ID)
        
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
    try:
       synced = await bot.tree.sync(guild=GUILD_ID)
       print(f"✅ Synced {len(synced)} commands to guild {GUILD_ID.id}")
    except Exception as e:
        print(f"❌ Error syncing commands: {e}")

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return
    
    if message.content == "!test":
        await message.channel.send("✅ Bot is responding to messages")

if __name__ == "__main__":
    print("Starting bot...")
    bot.run(TOKEN)