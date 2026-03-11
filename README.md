# Pythofy Downloader

Download .mp3 songs with metadata from a Spotify playlist of a max of 100 songs.

## Installation
Download the latest installer from [Releases](link) and run it.

## Build from source

### Requirements
- Python 3.x
- PyInstaller: `pip install pyinstaller`
- NSIS 3.x to create the setup

### Steps
1. Build the exe: `pyinstaller --onefile --noconsole youtube_downloader_gui.py`
2. Download `yt-dlp.exe` and place it in `dist/pythofy_tools/`
3. Download `ffmpeg.exe` and place it in `dist/pythofy_tools/`
4. Compile the setup with NSIS: right click `PythofySetup.nsi` → Compile

## License
MIT
