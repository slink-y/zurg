# Project Notes

## Proposed flow
- The interaction starts when either a URL is sent
    - To a specific channel in my server via a simple /download command
    - A URL is submitted using a slash command provided by the bot as a user app, so I can start a download anywhere (but it still directs to a progress message in the download channel)
- The download type is automatically identified from the provided URL, so the appropriate tool is used
    - `MEGAcmd`, `ffsend`, or `wget`
- All files will be downloaded and stored on my connected SSD `/mnt/transformer/`
- A directory can be created for each download in `/mnt/transformer/tmp`
- As the download begins, the user can select the destination folder
    - Predefined paths for commonly used directories should be shown, to minimize typing on my phone
    - A custom path in `/mnt/transformer` can also be provided
- As the download occurs, the status message should be updated to reflect progress
- The user can submit a note to be associated with the download history item, either while downloading or after it is completed
- After the download completes, archives should be automatically expanded. The archive should be stored in a new folder under `/mnt/transformer/storage/archives/`
- A log item should be generated, containing as much information about the download as possible
    - Time of download
    - Type of download
    - Archive name
    - Folder name
    - Destination path
    - Size of archive/folder and number of files
    - Any provided note
- The full log item should be appended to some type of history database/file. It should also be saved within the archive folder if one is created. An abbreviated version formatted for a Discord message should be sent to a #history channel via webhook

## Considerations

- I don't know if this is an issue, but the status message should be updated an appropriate interval so as not to overload the Pi
- Directories I commonly download to are `music/`, `shared/`, `media/`, `downloads/`

## Embed layout

Author: Identified service (MEGA, ffsend)
Author image: service icon
Title: Indentified file or folder name
    - need to figure out how to indentify that with megacmd and ffsend
Title URL: original download URL from command
Description: something like this

    ⏳ Downloading...

    [▓▓▓▓░░░░░░] - 40%

    40 MB of 100
    16 MB/s

    📁 (destination path)
    📒 (notes if added)

- the status line could update from
    - "🔎 Starting download..."
    - "⏳ Downloading..." (<50% complete)
    - "⌛ Downloading..." (>50%)
    - "📦 Extracting files..."
    - "⏸️ Waiting for destination..."
    - "➡️ Moving to destination..."
    - "✅ Download complete."
- The progress bar will update with download percentage
- The download speed should be updated if the download tool provides it
- The destination line should show "📁 Select a destination" until one is added in the dropdown, and then show that path
- The notes line should only show when a note is added

### Buttons

- A destination dropdown with common selection or a custom option (need to decide how to submit custom selection)
- "Add notes" should change to "Edit notes" after its submitted
- "Cancel" to cancel the download

### Download progress

**mega-get**
- one line updates with progress in this format:

`
TRANSFERRING ||#############################.........||(112/147 MB:  76.12 %)
`


**ffsend download**
- one line updates with progress, percentage, speed, and time remaining:

`
Download & Decrypt 21.26 MB / 23.95 MB [===============>-] 88.75 % 5.14 MB/s 1s
`
`ffsend info` to fetch details, example:
ID:         b087066715
Name:       my-file.txt
Size:       12 KiB
MIME:       text/plain
Downloads:  0 of 10
Expiry:     18h2m (64928s)

**wget**
- detailed progress message with file name, percentage, size completed (but not total?), speed, and time remaining.

```
--2025-09-29 20:54:43--  https://ash-speed.hetzner.com/100MB.bin
Resolving ash-speed.hetzner.com (ash-speed.hetzner.com)... 5.161.7.195, 2a01:4ff:ef::fa57:1
Connecting to ash-speed.hetzner.com (ash-speed.hetzner.com)|5.161.7.195|:443... connected.
HTTP request sent, awaiting response... 200 OK
Length: 104857600 (100M) [application/octet-stream]
Saving to: ‘100MB.bin.2’

100MB.bin.2          30%[=====>              ]  30.40M  6.68MB/s    eta 14s    
```
and when completed it updates to:
```
100MB.bin.2         100%[===================>] 100.00M  5.08MB/s    in 23s     

2025-09-29 20:55:07 (4.37 MB/s) - ‘100MB.bin.2’ saved [104857600/104857600]
```

## File Structure

/mnt/transformer/
├── tmp/                         # Temporary download location
│   └── {download_id}/           # Unique folder per download
│       ├── archive.zip          # Original archive (if applicable)
│       └── extracted/           # Extracted contents
│
├── storage/                     # Permanent storage
│   ├── archives/                # Archived original files
│   |   └── {download_id}/
│   |       ├── archive.zip
|   |       └── {download_id}.json
|   |
|   └──logs/                     # Logging system
|      ├── downloads.json        # Main download history
|      ├── errors.log            # Error logs
|      └── {download_id}.json     # Individual download logs
│
├── music/                       # Common destinations
├── media/
├── shared/
└── downloads/

log file example:
```
{
  "id": "dl_20250129_143022_abc123",
  "timestamp": "2025-01-29T14:30:22Z",
  "url": "https://mega.nz/file/...",
  "service": "MEGA",
  "file_name": "example.zip",
  "destination": "/mnt/transformer/music/",
  "final_path": "/mnt/transformer/music/example/",
  "size_bytes": 104857600,
  "archive_size_bytes": 104857600,
  "file_count": 15,
  "download_duration": 23.5,
  "note": "Music album from friend",
  "status": "completed"
}
```

