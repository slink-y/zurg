# Project Notes

## Proposed flow
- The interaction starts when either a URL is sent
    - To a specific channel in my server via a simple slash command
    - A URL is submitted using a slash command provided by the bot as a user app, so I can use start a download anywhere
- The download type is automatically identified from the provided URL, so the appropriate tool is used
    - `mega`, `ffsend`, or `wget`
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
    - "☑️ Download finished, waiting for destination selection..."
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


