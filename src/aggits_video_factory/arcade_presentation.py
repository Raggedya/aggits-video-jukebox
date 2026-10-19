"""Opt-in decoration only; never changes machine configuration or publication."""
import hashlib
import html
from pathlib import Path
import re


def add_arcade_presentation(document: str, assets: Path) -> str:
    """Install dormant, early-head presentation resources in Channel Master output.

    Callers must restrict this to Channel Master. URLs, metadata, machine.json,
    controls and the main runtime are deliberately untouched.
    """
    if '</head>' not in document:
        raise ValueError('Machine HTML head is missing; presentation was not installed.')
    # Reinstall only our own generated tags. A previously generated/published
    # machine may already contain an older content-hashed presentation reference.
    document = re.sub(
        r'<script src="assets/arcade-presentation\.js(?:\?[^"<>]*)?"></script>\s*'
        r'|<link rel="stylesheet" href="assets/arcade-presentation\.css(?:\?[^"<>]*)?">\s*',
        '', document,
    )
    resources = []
    for filename in ("arcade-presentation.js", "arcade-presentation.css"):
        digest = hashlib.sha256((assets / filename).read_bytes()).hexdigest()[:16]
        url = f"assets/{filename}?v={digest}"
        resources.append(f'<script src="{url}"></script>' if filename.endswith('.js')
                         else f'<link rel="stylesheet" href="{url}">')
    return document.replace('</head>', '\n'.join(resources) + '\n</head>', 1)


def theatrical_share_url(standalone_url: str) -> str:
    """A fixed sibling entry document, not a duplicate runtime or catalogue."""
    if not re.fullmatch(r'https://raggedya\.github\.io/aggits-video-jukebox/crispy-bits/[a-z0-9]+(?:-[a-z0-9]+)*/', standalone_url):
        raise ValueError('Theatrical sharing requires a verified canonical machine URL.')
    return standalone_url + 'theatre.html'


def _head_meta(document: str, attribute: str, key: str, value: str | None) -> str:
    pattern = rf'<meta\b(?=[^>]*\b{attribute}=[\"\']{re.escape(key)}[\"\'])[^>]*>\s*'
    document = re.sub(pattern, '', document, flags=re.I)
    if value is not None:
        document = document.replace('</head>', f'<meta {attribute}="{key}" content="{html.escape(value, quote=True)}">\n</head>', 1)
    return document


def arcade_share_documents(document: str, assets: Path, standalone_url: str, *, local_preview=False) -> tuple[str, str]:
    """Called ONLY after Arcade Active/primary/permission/listing validation.

    Emit two entry documents sharing assets and the single machine.json. No
    template, artwork, body, configuration, runtime or social image is replaced.
    The original canonical remains standalone; the new entry has static theatre
    state plus canonical/og:url suitable for crawlers that do not execute JS.
    Local preview overrides only the live DOM Share target, never public metadata.
    """
    share_url = theatrical_share_url(standalone_url)
    if document.count('</head>') != 1 or len(re.findall(r'<html\b', document, re.I)) != 1:
        raise ValueError('Theatrical sharing requires one complete generated HTML document.')
    document = _head_meta(document, 'name', 'crispy-arcade-theatre-url', share_url)
    document = _head_meta(document, 'name', 'crispy-arcade-local-preview', 'true' if local_preview else None)
    # Only registry-approved Arcade entries call this renderer. Keep the return
    # control separate from the established four-button row and accessible footer.
    document = re.sub(r'<nav data-arcade-return[^>]*>.*?</nav>\s*', '', document, flags=re.S)
    if '<footer class="channel-master-footer-mark"' in document:
        nav = ('<nav data-arcade-return aria-label="Comedy Arcade navigation">'
               '<a href="https://raggedya.github.io/aggits-video-jukebox/crispy-bits/comedy-arcade/">'
               '← BACK TO COMEDY ARCADE</a></nav>\n')
        document = document.replace('<footer class="channel-master-footer-mark"', nav + '<footer class="channel-master-footer-mark"', 1)
        for filename in ('arcade-navigation.css', 'arcade-navigation.js'):
            digest = hashlib.sha256((assets / filename).read_bytes()).hexdigest()[:16]
            document = re.sub(rf'<(?:link|script)\b[^>]*(?:href|src)="assets/{re.escape(filename)}(?:\?[^"<>]*)?"[^>]*>(?:</script>)?\s*', '', document)
            url = f'assets/{filename}?v={digest}'
            tag = f'<script defer src="{url}"></script>' if filename.endswith('.js') else f'<link rel="stylesheet" href="{url}">'
            document = document.replace('</head>', tag + '\n</head>', 1)
    # Preview snapshots can predate current tracking. Use the same current
    # first-party adapter, now also recognizing the fixed theatrical filename.
    if (assets / 'machine-statistics.js').is_file():
        digest = hashlib.sha256((assets / 'machine-statistics.js').read_bytes()).hexdigest()[:12]
        document = re.sub(r'<script defer src="assets/machine-statistics\.js(?:\?[^"<>]*)?"></script>', '', document)
        document = document.replace('</body>', f'<script defer src="assets/machine-statistics.js?v={digest}"></script></body>')
    standalone = add_arcade_presentation(document, assets)
    theatre = re.sub(r'<link\b(?=[^>]*\brel=[\"\']canonical[\"\'])[^>]*>\s*', '', document, flags=re.I)
    theatre = theatre.replace('</head>', f'<link rel="canonical" href="{share_url}">\n</head>', 1)
    theatre = _head_meta(theatre, 'property', 'og:url', share_url)
    theatre = re.sub(r'<html\b([^>]*)>', lambda m: '<html' + m[1] + ' data-arcade-share-page="true" data-arcade-presentation="theatre">', theatre, count=1, flags=re.I)
    return standalone, add_arcade_presentation(theatre, assets)
