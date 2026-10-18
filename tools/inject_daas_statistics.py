"""Keep DAAS tracking present even when an older desktop republishes its page.

Run immediately before uploading the Pages artifact. Only this machine changes.
"""
from pathlib import Path
import hashlib
import re
import shutil

def inject(root: Path):
    site=root/'public/crispy-bits/doug-anthony-allstars'
    page=site/'index.html'
    if not page.is_file():return
    source=root/'static/machine-statistics.js'
    digest=hashlib.sha256(source.read_bytes()).hexdigest()[:12]
    html=page.read_text(encoding='utf-8')
    html=re.sub(r'<script defer src="assets/machine-statistics\.js\?v=[a-f0-9]+"></script>','',html)
    if html.count('</body>')!=1:raise ValueError('Unexpected DAAS page structure')
    (site/'assets').mkdir(exist_ok=True)
    shutil.copyfile(source,site/'assets/machine-statistics.js')
    page.write_text(html.replace('</body>',f'<script defer src="assets/machine-statistics.js?v={digest}"></script></body>'),encoding='utf-8')

if __name__=='__main__':inject(Path(__file__).resolve().parents[1])
