# AGGITS Video Jukebox Factory

A standalone Windows desktop application that turns a public YouTube channel into an AGGITS single-reel video discovery jukebox. This repository and deployment are deliberately independent of the existing Cosmic Aquarium applications.

## Factory workflow

1. Open **Settings** once and save a YouTube Data API v3 key.
2. Enter a jukebox title, ticker text (up to 500 characters), and the channel's main YouTube URL.
3. Press **Create Jukebox**. The Factory selects up to 30 public, embeddable uploads.
4. Preview privately, then publish or unpublish from the Library.
5. After a successful publication, the separate delivery Worker emails the live link and titled QR card.

The public machine uses YouTube's official embedded player. Landing on a reel winner does not autoplay video. **Play Video** mechanically opens the shutters; the visitor then presses YouTube's own play control.

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

- GitHub Pages: `https://raggedya.github.io/aggits-video-jukebox/`
- Cloudflare Worker: `aggits-video-jukebox`
- D1: `aggits-video-jukebox-production`

The Worker requires the `RESEND_API_KEY` secret and a verified `REPORT_FROM_EMAIL` sender before automatic email delivery can succeed.
