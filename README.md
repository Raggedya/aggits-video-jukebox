# CRISPY BITS DESKTOP

A standalone Windows desktop application for creating and managing CRISPY BITS BUSINESS, MUSIC, TOURISM, BANJO and CHANNEL MASTER projects. The six-tab desktop also includes BULK UPLOAD, an internal campaign workflow that creates ordinary Channel Master projects while reusing the proven YouTube, Library, publication, QR, delivery and recovery infrastructure.

## Factory workflow

1. Open **Settings** once and save a YouTube Data API v3 key, Delivery Email and provisioned delivery credential.
2. Choose **BUSINESS**, **MUSIC** or **TOURISM**, enter a title and Bio / Story, then supply a channel URL, up to 15 individual video URLs, or both.
3. Business projects may configure a Shop URL. Music projects configure one Primary Call to Action and Destination URL. Tourism projects may configure distinct More Info and Stay URLs.
4. Press **Analyse + Review Videos**. Explicit videos are included first; duplicates are removed and the channel fills the remaining places up to 30 public, embeddable videos.
5. Review the resolved list, then build using only the videos you keep checked.
6. Preview privately, then publish or unpublish from the Library.
7. After a verified publication, the separate delivery Worker emails the live link and titled QR card.

Published jukeboxes can be reopened with **Edit Videos**. Reviewed changes remain private and the existing live version stays untouched until **Update + Republish** is pressed.

## Bulk Upload campaign factory

**BULK UPLOAD** is an operator-only orchestration tab, not a public project type. It can import/export a UTF-8 campaign CSV, validate and approve up to 20 prospects, build each approved row as a normal `channel_master` project with up to 50 videos, require a second approval before bulk publication, and package verified publications as individual QR codes, one internal A4 QR sheet, individual 1080×1350 prospect cards, ZIP files, a manifest and final campaign CSV.

The desktop ships with a `CandidateResearchService` boundary but no prospect-research provider. Until an authorised provider is configured, use verified CSV input; the application does not scrape or invent prospects. Campaign data is stored separately under the application data root and never enters public machine output. Prospect outreach remains manual.

One operator campaign email uses the authenticated `/api/campaign-deliveries` Worker route. The Worker fixes the recipient from `OWNER_EMAIL`, constructs the subject/body, allowlists campaign attachments and applies HMAC replay protection and delivery idempotency. Deploying that source route is a separate production operation.

The public machine uses YouTube's official embedded player. After the reel confirms a winner, the machine pauses briefly and reveals the matched video without autoplaying it. **Play Video** activates the selected official player, while **Re-spin** closes the stage before the existing reel sequence begins again.

## Local development

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
$env:PYTHONPATH = "$PWD\src"
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe desktop\video_jukebox_factory.py
```

Build a development EXE with `desktop\build.ps1`.

Create the clean, tested, versioned release candidate with:

```powershell
.\desktop\release-build.ps1
```

The release command uses Python 3.12.10, installs the exact versions in `requirements-release.txt`, runs Python and Worker tests, validates JavaScript and Python syntax, embeds Windows version metadata, smoke-tests the packaged executable, and creates the release manifest.

## Separate services

- GitHub Pages: `https://raggedya.github.io/aggits-video-jukebox/crispy-bits/`
- Cloudflare Worker: `aggits-video-jukebox`
- D1: `aggits-video-jukebox-production`

The Worker requires the `RESEND_API_KEY` secret and a verified `REPORT_FROM_EMAIL` sender before automatic email delivery can succeed.

## Delivery hardening (Milestone 6)

Recipient-selectable delivery uses HMAC-SHA256 authentication. The canonical signed bytes are:

```text
{unix_timestamp}\n{nonce}\nPOST\n/api/deliveries\n{exact UTF-8 request body bytes}
```

The desktop sends the hexadecimal signature in `X-Crispy-Signature`, with `X-Crispy-Timestamp` and `X-Crispy-Nonce`. The Worker allows a five-minute clock window and records nonces in D1 for replay protection. Delivery identity is `(slug, publication revision, normalized recipient)`; a deterministic SHA-256 digest of that tuple is supplied to Resend as its idempotency key.

Before production use:

1. Generate one strong random shared secret outside source control.
2. Configure it on the Worker as the Cloudflare secret `DELIVERY_HMAC_SECRET`.
3. Apply Worker D1 migration `0002_delivery_security.sql`.
4. Store the same secret on the authorised Windows desktop with `python tools/provision_delivery_secret.py` (DPAPI), or provision `CRISPY_BITS_DELIVERY_SECRET` securely in its launch environment.
5. Deploy the reviewed Worker only after explicit production approval.
6. `ALLOW_LEGACY_DELIVERY=true` is retained temporarily so the approved v2.3.0 rollback application can still deliver to fixed `OWNER_EMAIL`. This compatibility path ignores caller-selected recipients and should be removed after v2.3.0 retirement; set it to `false` then. Authenticated current-desktop requests always use the signed recipient.

Persistent desktop diagnostics are written under `%LOCALAPPDATA%\CRISPY BITS\Video Jukebox Factory\logs\` with bounded rotation. Publication pushes that outlive Pages verification are retained as recoverable `Verification Pending` operations and can be reconciled with **Check Live Status** without another Git push.
