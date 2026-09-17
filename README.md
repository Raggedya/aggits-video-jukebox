# CRISPY BITS Video Jukebox Factory

A standalone Windows desktop application that turns a public YouTube channel, up to 15 individually chosen videos, or both into a CRISPY BITS video-first discovery experience. Its text-based cylindrical selector reuses the proven Music Machine single-reel engine, followed by a cinematic 16:9 YouTube stage, customer information and customer-themed environment.

## Factory workflow

1. Open **Settings** once and save a YouTube Data API v3 key.
2. Enter a jukebox title and ticker text (up to 1,000 characters), then supply a channel URL, up to 15 individual video URLs, or both.
3. Press **Analyse + Review Videos**. Explicit videos are included first; duplicates are removed and the channel fills the remaining places up to 30 public, embeddable videos.
4. Review the resolved list with thumbnails and default-on inclusion checkboxes, then build using only the videos you keep checked.
5. Preview privately, then publish or unpublish from the Library.
6. After a successful publication, the separate delivery Worker emails the live link and titled QR card.

Published jukeboxes can be reopened with **Edit Videos**. Reviewed changes remain private and the existing live version stays untouched until **Update + Republish** is pressed.

The public machine uses YouTube's official embedded player. After the reel confirms a winner, the machine pauses briefly and reveals the matched video without autoplaying it. **Play Video** activates the selected official player, while **Re-spin** closes the stage before the existing reel sequence begins again.

## Local development

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
$env:PYTHONPATH = "$PWD\src"
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe desktop\video_jukebox_factory.py
```

Build the standalone EXE with `desktop\build.ps1`.

## Separate services

- GitHub Pages: `https://raggedya.github.io/aggits-video-jukebox/crispy-bits/`
- Cloudflare Worker: `aggits-video-jukebox`
- D1: `aggits-video-jukebox-production`

The Worker requires the `RESEND_API_KEY` secret and a verified `REPORT_FROM_EMAIL` sender before automatic email delivery can succeed.
