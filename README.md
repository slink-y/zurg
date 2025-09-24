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