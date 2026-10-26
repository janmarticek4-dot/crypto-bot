"""GitHub-only operational checks. No Telegram or private data/credentials."""
import base64
from datetime import datetime,timezone
import json
import os
from zoneinfo import ZoneInfo
import urllib.request


def expected(now):
    local=now.astimezone(ZoneInfo('Europe/Bratislava'));minute=local.hour*60+local.minute
    for label,end in [('morning',525),('usa',1005),('evening',1305)]:
        if label=='usa' and local.date().isoformat()<'2026-10-27':continue
        if end<=minute<=end+45:return local.date().isoformat()+'-'+label
    return None


def assess(now,state):
    slot=expected(now)
    if not slot:return 'NOT_DUE'
    record=state.get('slots',{}).get(slot,{})
    return 'SENT' if record.get('status')=='sent' else 'UNCERTAIN' if record.get('status') in ('attempting','uncertain') else 'MISSING'


def run():
    now=datetime.now(timezone.utc)
    if not expected(now):return 0
    repo=os.environ['GITHUB_REPOSITORY']
    req=urllib.request.Request('https://api.github.com/repos/'+repo+'/contents/trial-public/v111-delivery.json?ref=main',
        headers={'Authorization':'Bearer '+os.environ['GH_TOKEN'],'Accept':'application/vnd.github+json','User-Agent':'crypto-bot-delivery-health'})
    try:
        with urllib.request.urlopen(req,timeout=15) as r:response=json.load(r)
        status=assess(now,json.loads(base64.b64decode(response['content'])))
    except Exception:status='UNAVAILABLE'
    level='notice' if status=='SENT' else 'error'
    print('::'+level+'::ANALYSIS_DELIVERY_HEALTH='+status+'; automatic resend disabled')
    return 0 if status=='SENT' else 1

if __name__=='__main__':raise SystemExit(run())
