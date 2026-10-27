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


def comparable_morning(previous,snapshot,now):
    """Refuse legacy/identical/unverifiable references; never call one sample two observations."""
    from datetime import datetime
    from v11.shadow_pair import fingerprint,BL
    if not previous:return None
    context=previous.get('_context',{})
    try:
        at=datetime.fromisoformat(context['at'])
        hours=(now-at).total_seconds()/3600
        valid=at.tzinfo is not None and at.astimezone(BL).date()==now.astimezone(BL).date() and 8<=hours<=16
        return previous if valid and context.get('fingerprint') and context['fingerprint']!=fingerprint(snapshot) else None
    except (KeyError,TypeError,ValueError):return None


def manual_request_key():
    if os.getenv('V111_MANUAL_ANALYSIS','false').lower()!='true':return None
    run_id=os.getenv('GITHUB_RUN_ID','')
    if os.getenv('GITHUB_EVENT_NAME')!='workflow_dispatch' or os.getenv('GITHUB_REF')!='refs/heads/main' or not run_id.isdigit():
        raise ValueError('Explicit main-branch workflow_dispatch with run ID required')
    return 'github-run-'+run_id # deliberately independent of GITHUB_RUN_ATTEMPT


def run():
    manual_key=manual_request_key()
    if os.getenv('V111_INTEGRATION_ENABLED','false').lower()!='true':
        if manual_key:raise RuntimeError('Manual V11.1 requires approved integration enabled')
        return pilot.run()
    def invoke():return pilot.run(manual_key=manual_key) if manual_key else pilot.run()
    original_read=pilot.PublicJournal.read
    original_render=pilot.render
    original_remember=pilot.forecast_audit.remember
    def strict_read(journal):
        value=original_read(journal)
        if not value.get('slots'):raise RuntimeError('Existing delivery journal missing/empty; refusing a reset')
        return value
    try:
        pilot.PublicJournal.read=strict_read
        # Evaluate prior delivered forecasts only; do not create/promote a V11 model.
        pilot.forecast_audit.remember=lambda *args,**kwargs: None
        if not manual_key and pilot.phase(pilot.datetime.now(pilot.timezone.utc)) not in ('morning','evening'):return invoke()
        state=latest_public_rule_state() # fail closed, no reset or legacy-state write
        fear=legacy.get_fear_greed() # same existing read-only provider
        def enrich(snap,fund,now,kind,previous=None):
            previous=comparable_morning(previous,snap,now) if kind=='evening' else None
            text,quotes,evaluations=integration.render(legacy,snap,fund,now,kind,state,previous,fear)
            directory=os.getenv('V111_DIAGNOSTICS_DIR')
            if directory:
                # Public data only; private inventory is loaded later by the existing sender.
                from v11.state_policy import require_public_data
                from v11.fundamental_analysis import analyze
                details,_,_=integration.render_detailed(legacy,snap,fund,now,kind,state,previous,fear)
                files={'analysis_details.txt':details,'risk_diagnostics.json':{s:integration.risk_breakdown(legacy,e) for s,e in evaluations.items()},
                    'fundamental_evidence.json':analyze(fund,now),'market_snapshot.json':snap}
                target=Path(directory);target.mkdir(parents=True,exist_ok=True)
                for name,value in files.items():
                    require_public_data(value)
                    (target/name).write_text(value if isinstance(value,str) else json.dumps(value,ensure_ascii=False,allow_nan=False))
            return text,quotes
        pilot.render=enrich
        return invoke() # same canonical slot and CAS-before-send owner
    finally:
        pilot.render=original_render
        pilot.PublicJournal.read=original_read
        pilot.forecast_audit.remember=original_remember

if __name__=='__main__':raise SystemExit(run())
