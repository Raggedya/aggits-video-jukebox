"""Keep per-machine spin totals on published players, including older EXE builds.

Historical filename retained for existing deployment workflows. No network calls.
"""
from pathlib import Path
import hashlib
import re
import shutil

def inject(root: Path):
    public=root/'public'
    for page in sorted(set(public.glob('*/index.html')) | set(public.glob('crispy-bits/*/index.html'))):
        if not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*',page.parent.name) or len(page.parent.name)>100:continue
        html=page.read_text(encoding='utf-8')
        machine = re.search(r'class="[^"]*\bmusic-machine\b',html)
        gallery = page.parent.name == 'comedy-arcade' and re.search(r'<main\b[^>]*class="[^"]*\bmachine-stack\b',html)
        if not machine and not gallery:continue
        inject_site(root,page.parent)

def inject_site(root: Path, site: Path):
    page=site/'index.html'
    if not page.is_file():return
    source=root/'static/machine-statistics.js'
    digest=hashlib.sha256(source.read_bytes()).hexdigest()[:12]
    html=page.read_text(encoding='utf-8')
    html=re.sub(r'<script defer src="assets/machine-statistics\.js\?v=[a-f0-9]+"></script>','',html)
    if html.count('</body>')!=1:raise ValueError(f'Unexpected machine page structure: {site.name}')
    (site/'assets').mkdir(exist_ok=True)
    shutil.copyfile(source,site/'assets/machine-statistics.js')
    page.write_text(html.replace('</body>',f'<script defer src="assets/machine-statistics.js?v={digest}"></script></body>'),encoding='utf-8')

if __name__=='__main__':inject(Path(__file__).resolve().parents[1])
