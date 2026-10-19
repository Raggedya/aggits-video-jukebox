"""Keep per-machine spin totals on published players, including older EXE builds.

Historical filename retained for existing deployment workflows. No network calls.
"""
from pathlib import Path
import hashlib
import re
import shutil

def instrument_runtime(script: str):
    """Telemetry-only upgrade for known old players; retain their own engine/imports.

    Fail closed on unexpected source instead of replacing a customer's runtime.
    """
    if "spinTelemetry='accepted-v1'" in script:
        return script
    def once(old, new):
        nonlocal script
        if script.count(old) != 1:
            raise ValueError('Unsupported published reel telemetry anchor: ' + old[:65])
        script = script.replace(old, new, 1)
    once('if (machine) {', """if (machine) {
  machine.dataset.spinTelemetry='accepted-v1';
  const spinIntents=new WeakSet();
  function trustedSpinIntent(event,action='lever') {
    if(!event?.isTrusted || event.type==='pointercancel')return null;
    const intent={action};spinIntents.add(intent);return intent;
  }""")
    once('async function spin() {', """async function spin() {
    const input=arguments[0];
    const intent=spinIntents.has(input)?input:trustedSpinIntent(input,'respin');
    if(intent)spinIntents.delete(intent);""")
    once("setState('SPINNING', 'The reel is selecting a video.');",
         "setState('SPINNING', 'The reel is selecting a video.');\n    if(intent)machine.dispatchEvent(new CustomEvent('crispy-bits:accepted-spin',{bubbles:true,detail:{action:intent.action}}));")
    if 'function animateLeverAndSpin() {' in script:
        once('function animateLeverAndSpin() {', "function animateLeverAndSpin() {\n    const event=arguments[0],intent=trustedSpinIntent(event);")
        start=script.index('function animateLeverAndSpin() {')
        end=script.index('function onLeverDown(event)',start)
        part=script[start:end]
        if 'void spin();' not in part:raise ValueError('Unknown lever scheduling path.')
        script=script[:start]+part.replace('void spin();','void spin(intent);')+script[end:]
        once('if (leverTriggered) { void spin(); resetLever(true); }',
             'if (leverTriggered) { void spin(trustedSpinIntent(event)); resetLever(true); }')
        script=script.replace('animateLeverAndSpin();','animateLeverAndSpin(event);')
    script=script.replace('event.preventDefault();\n        spin();','event.preventDefault();\n        spin(event);')
    return script

def inject(root: Path):
    public=root/'public'
    pages=set(public.glob('*/index.html')) | set(public.glob('crispy-bits/*/index.html'))
    pages |= set(public.glob('*/theatre.html')) | set(public.glob('crispy-bits/*/theatre.html'))
    for page in sorted(pages):
        if not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*',page.parent.name) or len(page.parent.name)>100:continue
        html=page.read_text(encoding='utf-8')
        if page.name=='theatre.html' and 'data-arcade-share-page="true"' not in html:continue
        machine = re.search(r'class="[^"]*\bmusic-machine\b',html)
        gallery = page.parent.name == 'comedy-arcade' and re.search(r'<main\b[^>]*class="[^"]*\bmachine-stack\b',html)
        if not machine and not gallery:continue
        inject_page(root,page)

def inject_site(root: Path, site: Path):
    inject_page(root,site/'index.html')


def inject_page(root: Path, page: Path):
    site=page.parent
    if not page.is_file():return
    source=root/'static/machine-statistics.js'
    digest=hashlib.sha256(source.read_bytes()).hexdigest()[:12]
    html=page.read_text(encoding='utf-8')
    runtime=site/'assets/video-machine.js'
    if re.search(r'class="[^\"]*\bmusic-machine\b',html) and runtime.is_file():
        patched=instrument_runtime(runtime.read_text(encoding='utf-8'))
        runtime.write_text(patched,encoding='utf-8')
        runtime_hash=hashlib.sha256(runtime.read_bytes()).hexdigest()[:12]
        html=re.sub(r'(src="assets/video-machine\.js)(?:\?[^"<>]*)?"',
                    lambda m:m[1]+'?v='+runtime_hash+'"',html)
    html=re.sub(r'<script defer src="assets/machine-statistics\.js\?v=[a-f0-9]+"></script>','',html)
    if html.count('</body>')!=1:raise ValueError(f'Unexpected machine page structure: {site.name}')
    (site/'assets').mkdir(exist_ok=True)
    shutil.copyfile(source,site/'assets/machine-statistics.js')
    page.write_text(html.replace('</body>',f'<script defer src="assets/machine-statistics.js?v={digest}"></script></body>'),encoding='utf-8')

if __name__=='__main__':inject(Path(__file__).resolve().parents[1])
