"""Narrow DAAS tracking publication; never rebuild or republish other machines.

Default is read-only review; --apply creates one fast-forward main commit.
The current working tree, including all Football edits, is never staged.
"""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[1]
REPO='repos/Raggedya/aggits-video-jukebox'
def api(path, body=None):
    args=['gh','api',f'{REPO}/{path}']
    if body is not None:
        args += ['--method','POST','--input','-']
    result=subprocess.run(args,input=json.dumps(body) if body is not None else None,
        capture_output=True,text=True,encoding='utf-8',check=True)
    return json.loads(result.stdout)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--apply',action='store_true');args=parser.parse_args()
    head=api('git/ref/heads/main')['object']['sha']
    prefix='public/crispy-bits/doug-anthony-allstars/'
    response=api(f'contents/{prefix}index.html?ref={head}')
    html=base64.b64decode(response['content']).decode('utf-8')
    script=(ROOT/'static/machine-statistics.js').read_text(encoding='utf-8')
    digest=hashlib.sha256(script.encode()).hexdigest()[:12]
    tag=f'<script defer src="assets/machine-statistics.js?v={digest}"></script>'
    if 'machine-statistics.js' in html:
        raise RuntimeError('Tracking already present; inspect before replacing.')
    if html.count('</body>')!=1:raise RuntimeError('Unexpected live HTML structure')
    changed=html.replace('</body>',tag+'</body>')
    assert changed.replace(tag,'')==html
    files={prefix+'index.html':changed,prefix+'assets/machine-statistics.js':script}
    for name in ['worker/src/machine-stats.js','worker/stats.wrangler.jsonc',
                 'worker/migrations/0004_machine_statistics.sql','docs/daas-statistics.md',
                 'static/machine-statistics.js','tools/inject_daas_statistics.py']:
        files[name]=(ROOT/name).read_text(encoding='utf-8')
    workflow_path='.github/workflows/deploy-pages.yml'
    response=api(f'contents/{workflow_path}?ref={head}')
    workflow=base64.b64decode(response['content']).decode('utf-8')
    marker='      - uses: actions/upload-pages-artifact@v3'
    if workflow.count(marker)!=1:raise RuntimeError('Inspect changed Pages workflow before proceeding')
    workflow=workflow.replace('      - "public/**"','      - "public/**"\n      - "static/machine-statistics.js"\n      - "tools/inject_daas_statistics.py"')
    files[workflow_path]=workflow.replace(marker,'      - name: Preserve DAAS first-party statistics\n        run: python tools/inject_daas_statistics.py\n'+marker)
    print('Base commit:',head)
    print('Only these paths:',*files,sep='\n')
    if not args.apply:return
    tree=api('git/trees',{'base_tree':api(f'git/commits/{head}')['tree']['sha'],
        'tree':[{'path':name,'mode':'100644','type':'blob','content':content} for name,content in files.items()]})
    commit=api('git/commits',{'message':'Record first-party statistics for Doug Anthony All Stars only',
        'tree':tree['sha'],'parents':[head]})
    # Non-force update refuses concurrent main changes rather than overwriting.
    args=['gh','api',f'{REPO}/git/refs/heads/main','--method','PATCH','--input','-']
    subprocess.run(args,input=json.dumps({'sha':commit['sha'],'force':False}),text=True,
        encoding='utf-8',capture_output=True,check=True)
    print('Published source commit:',commit['sha'])
if __name__=='__main__':main()
