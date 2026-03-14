# Pythofy Downloader
Download .mp3 songs with metadata from a Spotify playlist.

> **Disclaimer:** This tool is intended for personal and educational use only.
> Download only content you own or have the right to download.
> The author is not responsible for any misuse of this software.
> Downloading copyrighted content without authorization may violate YouTube's
> and Spotify's Terms of Service and applicable copyright laws.

## Installation
Download the latest installer from [Releases](link) and run it.

## Build from source
### Requirements
- Python 3.x
- PyInstaller: `pip install pyinstaller`
- NSIS 3.x to create the setup

### Steps
1. Build the exe: `pyinstaller --onefile --noconsole Pythofy.py`
2. Download `yt-dlp.exe` and place it in `dist/pythofy_tools/`
3. Download `ffmpeg.exe` and place it in `dist/pythofy_tools/`

## License
MIT
