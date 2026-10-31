"""Read-only health check; runs AFTER analysis, never sends or resets attempts."""
import base64,json,os,sys,urllib.request
from pathlib import Path
from datetime import datetime,timezone
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from v11.production_schedule import phase,target

def assess(now,state):
    kind=phase(now)
    if not kind:return 'NOT_DUE'
    if (now-target(now,kind)).total_seconds()<900:return 'NOT_DUE'
    row=state.get('slots',{}).get(now.astimezone(target(now,kind).tzinfo).date().isoformat()+'-'+kind,{})
    status=row.get('status')
    return 'SENT' if status=='sent' else 'UNCERTAIN' if status in ('attempting','uncertain') else 'MISSING_SAFE_TO_COLLECT'

def run():
    now=datetime.now(timezone.utc)
    if not phase(now):return 0
    req=urllib.request.Request('https://api.github.com/repos/'+os.environ['GITHUB_REPOSITORY']+'/contents/trial-public/v111-delivery.json?ref=main',headers={'Authorization':'Bearer '+os.environ['GH_TOKEN'],'Accept':'application/vnd.github+json','User-Agent':'crypto-bot-delivery-health'})
    try:
        with urllib.request.urlopen(req,timeout=15) as response:raw=json.load(response)
        status=assess(now,json.loads(base64.b64decode(raw['content'])))
    except Exception:status='UNAVAILABLE'
    print('::'+('notice' if status in ('SENT','NOT_DUE') else 'error')+'::ANALYSIS_DELIVERY_HEALTH='+status+'; ambiguous attempts never resent')
    return 0 if status in ('SENT','NOT_DUE') else 1

if __name__=='__main__':raise SystemExit(run())
