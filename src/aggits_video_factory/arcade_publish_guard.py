"""Pages isolation for a confirmed Arcade publication; no application imports."""
import json
import os
from pathlib import Path
import re
import subprocess

GUARD_MARKER = 'arcade-publish-isolation-v1'
ARCADE_PATH = 'public/crispy-bits/comedy-arcade/'
NEW_ASSETS = ('arcade-presentation.js', 'arcade-presentation.css', 'arcade-navigation.js',
              'arcade-navigation.css', 'comedy-arcade/assets/theatre.webp',
              'arcade-stage/assets/foreground-curtains-v1.webp',
              'arcade-stage/assets/amber-spotlights-v1.webp',
              'arcade-stage/assets/lower-hanging-curtains-v2.webp')

def is_arcade_only(changes, metadata, manifest, parent):
    if (metadata.get('schemaVersion') != 1 or metadata.get('baseRevision') != parent
            or not re.fullmatch(r'[a-f0-9-]{36}', metadata.get('publicationId', ''))):
        return False
    active = set()
    for row in manifest.get('comedians', []):
        if row.get('status') == 'active':
            match = re.fullmatch(r'https://raggedya.github.io/aggits-video-jukebox/crispy-bits/([a-z0-9-]+)/', row.get('destinationUrl', ''))
            if not match:return False
            active.add(match[1])
    aliases = set(metadata.get('newTheatricalFiles', []))
    allowed = {f'public/crispy-bits/{slug}/{name}' for slug in active
               for name in ('theatre.html', *(f'assets/{a}' for a in NEW_ASSETS))}
    if not aliases <= allowed:return False
    paths = {p for status, p in changes}
    if not {ARCADE_PATH+'index.html', ARCADE_PATH+'publication.json'} <= paths:return False
    return all((status in {'A', 'M'} and p.startswith(ARCADE_PATH) and '..' not in p.split('/'))
               or (status == 'A' and p in aliases) for status, p in changes)

def main():
    def git(*args):return subprocess.check_output(['git', *args]).decode().strip()
    parent = git('rev-parse', 'HEAD^')
    raw = subprocess.check_output(['git', 'diff-tree', '--no-commit-id', '--name-status', '-r', '-z', 'HEAD']).decode().split('\0')
    changes = list(zip(raw[0::2], raw[1::2]))
    try:
        metadata=json.loads(Path(ARCADE_PATH+'publication.json').read_text(encoding='utf-8'))
        document=Path(ARCADE_PATH+'index.html').read_text(encoding='utf-8')
        manifest=json.loads(re.search(r'<script id="arcade-data" type="application/json">(.*?)</script>',document,re.S)[1])
        isolated=is_arcade_only(changes,metadata,manifest,parent)
    except (OSError, ValueError, TypeError, KeyError):isolated=False
    with open(os.environ['GITHUB_OUTPUT'],'a',encoding='utf-8') as stream:
        stream.write('arcade_only='+str(isolated).lower()+'\n')

if __name__ == '__main__':main()
