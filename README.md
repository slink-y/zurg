# Zurgbot

A Discord bot to help me streamline downloads to my Raspberry Pi and organize my music hoarding obsession.

## Features:
- Simple downloading from a provided URL of one of these services
    - **MEGA** (using `mega-get` CLI tool)
    - **ffsend** ([send.vis.ee](https://send.vis.ee) and [send.richy.sh](https://send.richy.sh), using `ffsend` CLI tool)
    - **Direct URL download** (using `wget`?)
- A streamlined user experience to minimize manual input for use on my phone
- Optional note for each download to keep track of from where & why I downloaded something
- Animated download progress information
- Automatic unarchiving, management of archives, and other file organization features
- A detailed log is saved after each download for archival purposes, and a brief log is sent via webhook to a dedicated channel

## Proposed flow
- The interaction starts when either a URL is sent to a specific channel in my server OR a URL is submitted using a slash command provided by the bot as a user app, so I can use start a download anywhere
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