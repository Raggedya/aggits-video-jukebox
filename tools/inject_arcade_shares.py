"""Preserve approved theatrical links in Pages output after Desktop republishes.

The published, registry-validated Arcade manifest is the only authority. No
registry records, permissions, private files, network calls or catalogues change.
"""
import json
from pathlib import Path
import re
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from aggits_video_factory.arcade_presentation import arcade_share_documents

BASE='https://raggedya.github.io/aggits-video-jukebox/crispy-bits/'
ASSETS=('arcade-presentation.css','comedy-arcade/assets/theatre.webp',
        'arcade-stage/assets/foreground-curtains-v1.webp',
        'arcade-stage/assets/amber-spotlights-v1.webp',
        'arcade-stage/assets/lower-hanging-curtains-v2.webp')

def inject(root: Path):
    public=root/'public/crispy-bits'
    gallery=public/'comedy-arcade/index.html'
    if not gallery.is_file():return
    matches=re.findall(r'<script id="arcade-data" type="application/json">(.*?)</script>',
                       gallery.read_text(encoding='utf-8'),re.S)
    if len(matches)!=1:raise ValueError('Expected exactly one published Arcade manifest.')
    manifest=json.loads(matches[0])
    if manifest.get('schemaVersion')!=1 or not isinstance(manifest.get('comedians'),list):
        raise ValueError('Unsupported public Arcade manifest.')
    eligible={}
    for record in manifest['comedians']:
        if record.get('status')!='active':continue
        url=record.get('destinationUrl','')
        match=re.fullmatch(re.escape(BASE)+r'([a-z0-9]+(?:-[a-z0-9]+)*)/',url)
        if not match or not record.get('primaryMachineId'):
            raise ValueError('Unsafe or missing approved primary destination.')
        slug=match[1]
        if slug in eligible:raise ValueError('Duplicate approved destination.')
        eligible[slug]=url
    # Prepare every entry before changing output. A failed Pages build preserves
    # the last successful deployment; it must never silently drop one entry.
    writes={};source=root/'static/arcade-presentation.js'
    for slug,url in eligible.items():
        folder=public/slug
        if not folder.is_dir():
            # Deliberate standalone unpublish: do not resurrect missing machines.
            continue
        page=folder/'index.html';config=folder/'machine.json';assets=folder/'assets'
        if not page.is_file() or not config.is_file():raise ValueError('Incomplete published machine: '+slug)
        data=json.loads(config.read_text(encoding='utf-8'))
        document=page.read_text(encoding='utf-8')
        if data.get('slug')!=slug or data.get('projectType')!='channel_master' or 'data-project-type="channel_master"' not in document:
            raise ValueError('Approved machine identity mismatch: '+slug)
        canonical=re.findall(r'<link rel="canonical" href="([^"]+)">',document)
        if canonical!=[url]:raise ValueError('Standalone canonical mismatch: '+slug)
        if any(not (assets/name).is_file() for name in ASSETS):
            raise ValueError('Approved theatrical resources missing: '+slug)
        script=source.read_bytes()
        # The renderer hashes resources in assets. Point only this JS lookup at
        # the approved shared source, without changing any published artwork.
        class Resources:
            def __truediv__(self,name):return source if name=='arcade-presentation.js' else assets/name
        standalone,theatre=arcade_share_documents(document,Resources(),url)
        writes[page]=standalone.encode('utf-8')
        writes[folder/'theatre.html']=theatre.encode('utf-8')
        writes[assets/'arcade-presentation.js']=script
    for path,payload in writes.items():path.write_bytes(payload)
    # Remove only our explicitly marked aliases for records no longer listed.
    # Do not touch standalone pages, catalogues, assets or unrelated HTML.
    for page in public.glob('*/theatre.html'):
        if page.parent.name not in eligible and 'data-arcade-share-page="true"' in page.read_text(encoding='utf-8'):
            page.unlink()

if __name__=='__main__':inject(ROOT)
