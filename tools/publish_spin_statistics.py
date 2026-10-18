"""Publish only approved statistics files over current main; preserve all player content.

Default is a read-only plan. --apply fast-forwards main without staging local work.
"""
import argparse
import base64
import json
import subprocess
from pathlib import Path
from enable_daas_statistics import api, ROOT, REPO

FILES = [
    'static/machine-statistics.js', 'tools/inject_daas_statistics.py',
    'worker/src/machine-stats.js', 'worker/stats.wrangler.jsonc',
    'worker/migrations/0005_all_machine_spins.sql', 'docs/daas-statistics.md',
]

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--apply',action='store_true');args=parser.parse_args()
    head=api('git/ref/heads/main')['object']['sha']
    files={name:(ROOT/name).read_text(encoding='utf-8') for name in FILES}
    workflow='.github/workflows/deploy-pages.yml'
    original=base64.b64decode(api(f'contents/{workflow}?ref={head}')['content']).decode('utf-8')
    if 'run: python tools/inject_daas_statistics.py' not in original:
        raise RuntimeError('Inspect changed deployment workflow before publishing')
    files[workflow]=original.replace('name: Preserve DAAS first-party statistics','name: Preserve per-machine reel spin statistics')
    print('Base:',head);print('Paths:',*files,sep='\n')
    if not args.apply:return
    tree=api('git/trees',{
        'base_tree':api(f'git/commits/{head}')['tree']['sha'],
        'tree':[{'path':name,'mode':'100644','type':'blob','content':content} for name,content in files.items()]})
    commit=api('git/commits',{'message':'Add subtle per-machine reel spin counters', 'tree':tree['sha'],'parents':[head]})
    subprocess.run(['gh','api',f'{REPO}/git/refs/heads/main','--method','PATCH','--input','-'],
        input=json.dumps({'sha':commit['sha'],'force':False}),text=True,encoding='utf-8',capture_output=True,check=True)
    print('Published source commit:',commit['sha'])

if __name__=='__main__':main()
