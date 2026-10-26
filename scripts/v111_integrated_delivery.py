"""Prepared, opt-in delivery adapter. Not wired into the production workflow.

Uses the existing pilot slot journal and one sender; never touches bot_state.json.
"""
import base64
import json
import os
from pathlib import Path
import sys
import urllib.request
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import main as legacy
from scripts import v111_trial as pilot
from v11 import integration


def latest_public_rule_state():
    repo=os.environ['GITHUB_REPOSITORY']
    import re
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',repo):raise ValueError('Invalid repository')
    request=urllib.request.Request('https://api.github.com/repos/'+repo+'/contents/bot_state.json?ref=main',headers={
        'Authorization':'Bearer '+os.environ['GH_TOKEN'],'Accept':'application/vnd.github+json','User-Agent':'crypto-bot-integration'})
    with urllib.request.urlopen(request,timeout=15) as response:
        raw=response.read(6_000_001)
    if len(raw)>6_000_000:raise ValueError('Oversized public rule state')
    encoded=''.join(json.loads(raw)['content'].splitlines())
    state=json.loads(base64.b64decode(encoded,validate=True))
    if not state:raise ValueError('Unexpected empty public rule state')
    selected=integration.rule_state(state)
    if not selected:raise ValueError('No supported public rule-cache fields')
    return selected


def run():
    if os.getenv('V111_INTEGRATION_ENABLED','false').lower()!='true':return pilot.run()
    original_read=pilot.PublicJournal.read
    original_render=pilot.render
    def strict_read(journal):
        value=original_read(journal)
        if not value.get('slots'):raise RuntimeError('Existing delivery journal missing/empty; refusing a reset')
        return value
    try:
        pilot.PublicJournal.read=strict_read
        if pilot.phase(pilot.datetime.now(pilot.timezone.utc)) not in ('morning','evening'):return pilot.run()
        state=latest_public_rule_state() # fail closed, no reset or legacy-state write
        fear=legacy.get_fear_greed() # same existing read-only provider
        def enrich(snap,fund,now,kind,previous=None):
            text,quotes,_=integration.render(legacy,snap,fund,now,kind,state,previous,fear)
            return text,quotes
        pilot.render=enrich
        return pilot.run() # same canonical slot and CAS-before-send owner
    finally:
        pilot.render=original_render
        pilot.PublicJournal.read=original_read

if __name__=='__main__':raise SystemExit(run())
