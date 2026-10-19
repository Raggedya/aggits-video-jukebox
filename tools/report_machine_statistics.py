"""Authenticated, aggregate-only report. Read-only; never publishes raw events."""
import argparse
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
import json
import re
import shutil
import subprocess
from pathlib import Path

import requests

ARCADE='https://raggedya.github.io/aggits-video-jukebox/crispy-bits/comedy-arcade/'
EVENTS=('page_view','spin','play_click','share_click','spotify_click','cta_click','cta2_click','contact_click','membership_click')

def arcade_slugs(html):
    class Manifest(HTMLParser):
        active=False
        data=''
        def handle_starttag(self,tag,attrs):
            if tag=='script' and dict(attrs).get('id')=='arcade-data':self.active=True
        def handle_data(self,data):
            if self.active:self.data+=data
        def handle_endtag(self,tag):
            if tag=='script':self.active=False
    parser=Manifest();parser.feed(html)
    records=json.loads(parser.data)['comedians']
    slugs=['comedy-arcade']
    for item in records:
        if item['status']!='active':continue
        match=re.fullmatch(r'https://raggedya\.github\.io/aggits-video-jukebox/crispy-bits/([a-z0-9]+(?:-[a-z0-9]+)*)/',item['destinationUrl'])
        if not match:raise ValueError('Unsafe or unexpected public Arcade destination.')
        if match[1] not in slugs:slugs.append(match[1])
    return slugs

def summarize(rows,slugs):
    machines={slug:{name:0 for name in EVENTS} for slug in slugs if slug!='comedy-arcade'}
    landing=0
    for row in rows:
        if row['slug']=='comedy-arcade' and row['event_name']=='page_view':landing+=row['events']
        elif row['slug'] in machines and row['event_name'] in EVENTS:
            machines[row['slug']][row['event_name']]+=row['events']
    totals={name:sum(m[name] for m in machines.values()) for name in EVENTS}
    return {'gallery_page_views':landing,'machine_page_views':totals['page_view'],
            'combined_page_views':landing+totals['page_view'],
            'machine_totals':totals,'primary_cta_clicks':totals['cta_click']+totals['spotify_click'],
            'recorded_action_clicks':sum(totals[e] for e in EVENTS if e.endswith('_click')),
            'per_machine':machines,
            'notes':['Page views are not unique people. No cross-machine unique-visitor estimate is available.',
                     'Play/Share/CTA clicks do not confirm playback, sharing, listening or sales.',
                     'Missing historical coverage is not proof of zero historical usage.']}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--hours',type=int,default=36)
    parser.add_argument('--wrangler',default=shutil.which('wrangler'))
    args=parser.parse_args()
    if not 1<=args.hours<=8760:parser.error('--hours must be between 1 and 8760')
    if not args.wrangler:parser.error('Supply the installed Wrangler executable or wrangler.js with --wrangler')
    response=requests.get(ARCADE,timeout=20);response.raise_for_status()
    slugs=arcade_slugs(response.text)
    end=datetime.now(timezone.utc).replace(microsecond=0);start=end-timedelta(hours=args.hours)
    # Slugs are strictly validated by arcade_slugs, never arbitrary SQL input.
    selection=','.join("'"+slug+"'" for slug in slugs)
    sql=(f"SELECT slug,event_name,COUNT(*) AS events,COUNT(DISTINCT session_id) AS tab_sessions "
         f"FROM machine_statistics WHERE slug IN ({selection}) AND received_at>={int(start.timestamp())} "
         f"AND received_at<{int(end.timestamp())} GROUP BY slug,event_name")
    command=(['node',args.wrangler] if args.wrangler.endswith('.js') else [args.wrangler])
    command+=['d1','execute','aggits-video-jukebox-production','--remote','--config',
              str(Path(__file__).resolve().parents[1]/'worker/stats.wrangler.jsonc'),'--json','--command',sql]
    result=subprocess.run(command,capture_output=True,text=True,encoding='utf-8',check=True)
    data=json.loads(result.stdout)
    if not data or not data[0].get('success'):raise RuntimeError('Authenticated report failed.')
    report=summarize(data[0]['results'],slugs)
    report.update(window_start_utc=start.isoformat(),window_end_utc=end.isoformat(),
                  scope='Current public Comedy Arcade active listings plus its landing page',
                  per_metric_tab_sessions=data[0]['results'])
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()
