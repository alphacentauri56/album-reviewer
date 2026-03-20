*This temporary README was written by AI*

# Album Reviewer GUI

A small PyQt5 GUI for searching albums via the Spotify Web API, viewing album metadata and cover art, rating tracks, writing comments, and saving a structured review (Markdown + cover image + Instagram text). This repository provides a GUI wrapper for personal album reviews.

## Features
- Search Spotify for albums and load album metadata and tracks
- Display album cover and extract prominent colours
- Rate individual tracks and give an overall album score
- Add comments across multiple pages (tabbed UI)
- Save a review as a Markdown file, save cover art, and export an Instagram-friendly text file
- Optional tabbed layout for large albums

## Requirements
- Python 3.9+ (3.10 or 3.11 recommended)
- Windows (tested on Windows 10/11 for screenshot behavior)
- The GUI uses PyQt5
- Additional Python packages: requests, python-dotenv, pillow, numpy
- A Spotify Developer account client credentials (CLIENT_ID and CLIENT_SECRET)

## Installing dependencies
Create and activate a virtual environment, then install dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

If you don't have a `requirements.txt`, install manually:

```powershell
pip install pyqt5 requests python-dotenv pillow numpy
```

## Environment variables
Create a `.env` file in the same folder as the script with the following contents:

```
CLIENT_ID=your_spotify_client_id
CLIENT_SECRET=your_spotify_client_secret
```

The script reads credentials via `python-dotenv`.

## Running the GUI
From the repository root run:

```powershell
python album_reviewer_GUI.py
```

or if you use the original file name in this workspace:

```powershell
python "Personal\Spotify API\Get Albums GUI copy.py"
```

Notes:
- The application will request a token from Spotify using the Client Credentials flow. No user login is performed.
- When saving a review the script takes screenshots using PIL's ImageGrab. On Windows this captures the entire screen region enclosing the window. Make sure the window is visible and not covered by other windows.

## Common issues & troubleshooting
- Auth errors (401): verify `CLIENT_ID` and `CLIENT_SECRET` are correct, and your system clock is accurate.
- Rate limiting (429): Spotify may return 429 responses; if you see failures when searching or loading albums, wait and retry.
- Screenshot blank or partial: ensure the window is fully on-screen and not obscured by another window. Try increasing the margin value passed to the screenshot function.
- Module import errors: ensure the virtualenv is activated and `pip install` completed successfully.

## Development notes
- The core API wrappers are in the script and use requests directly. They could be hardened with retries, token expiry handling, and better error messages. Consider extracting API logic to a separate module for unit testing.
- Colour extraction is handled by the `colour_temp` module (expected to be available in the same environment). If you don't have it, you may need to stub or remove colour extraction code.

## License
This repository contains user code and may reference third-party code. Check individual files for attribution and license comments.

---