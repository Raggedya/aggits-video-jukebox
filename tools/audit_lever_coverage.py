"""Read-only published source/HTTP coverage inventory; never changes machines."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from collections import Counter
import json
from pathlib import Path
import re
import subprocess
import requests

def inventory(ref='origin/main',live=False):
    def git(*args):return subprocess.run(['git',*args],capture_output=True,check=True).stdout
    names=git('ls-tree','-r','--name-only',ref,'public').decode().splitlines()
    pages=[p for p in names if re.fullmatch(r'public/(?:crispy-bits/)?[a-z0-9-]+/index\.html',p)]
    def inspect(p):
        source=git('show',ref+':'+p).decode('utf-8')
        kind=re.search(r'data-project-type="([^"]+)"',source)
        shell=bool(re.search(r'class="[^"]*\bmusic-machine\b',source))
        gallery='class="machine-stack"' in source
        if not shell and not gallery:return None
        url='https://raggedya.github.io/aggits-video-jukebox/'+p.removeprefix('public/').removesuffix('index.html')
        status=None;runtime='';tracker=False
        html=source
        if live:
            response=requests.get(url,timeout=25);status=response.status_code;response.raise_for_status();html=response.text
            runtime_match=re.search(r'src="(assets/(?:video-machine|trivia-machine)\.js[^"<>]*)"',html)
            if runtime_match:
                r=requests.get(url+runtime_match[1],timeout=25);r.raise_for_status();runtime=r.text
        else:
            runtime_path=p.removesuffix('index.html')+('assets/trivia-machine.js' if 'data-project-type="trivia"' in html else 'assets/video-machine.js')
            if runtime_path in names:runtime=git('show',ref+':'+runtime_path).decode('utf-8')
        tracker='assets/machine-statistics.js' in html
        config_path=p.removesuffix('index.html')+'machine.json'
        category=kind[1] if kind else 'arcade_gallery' if gallery else 'legacy_reel'
        if config_path in names:category=json.loads(git('show',ref+':'+config_path)).get('projectType',category)
        return {'slug':p.split('/')[-2],'type':category,'url':url,
                'httpStatus':status,'hasCollector':tracker,'hasCanonicalAcceptedTelemetry':'accepted-spin' in runtime,
                'hasSpinState':"'SPINNING'" in runtime or '"SPINNING"' in runtime,
                'hasLever':bool(re.search(r'class="[^"]*\blever\b',html)),
                'hasRespin':'data-action="spin-again"' in html}
    with ThreadPoolExecutor(max_workers=4) as pool:rows=[r for r in pool.map(inspect,pages) if r]
    return {'ref':ref,'sourceCommit':git('rev-parse',ref).decode().strip(),'liveReadOnly':live,
            'categories':dict(Counter(r['type'] for r in rows)),'machines':rows,
            'notes':['Collector presence is not proof of historical coverage or every historical action.',
                     'Trivia has a real lever/reel; Next Question does not spin, while its lever/Re-spin do.']}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--live',action='store_true');p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    result=inventory(live=args.live);args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({'categories':result['categories'],'machines':len(result['machines'])}))
