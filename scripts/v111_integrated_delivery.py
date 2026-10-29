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
        if manual_key or os.getenv('V112_ANALYTICS_ENABLED','false').lower()=='true':raise RuntimeError('Approved V11.1 integration must remain enabled')
        return pilot.run()
    def invoke():return pilot.run(manual_key=manual_key) if manual_key else pilot.run()
    original_read=pilot.PublicJournal.read
    original_render=pilot.render
    original_personalize=pilot.personalize
    original_metadata=pilot.delivery_metadata
    original_usa=pilot.usa_prepare
    v112=os.getenv('V112_ANALYTICS_ENABLED','false').lower()=='true'
    holder={}
    original_remember=pilot.forecast_audit.remember
    def strict_read(journal):
        value=original_read(journal)
        if not value.get('slots'):raise RuntimeError('Existing delivery journal missing/empty; refusing a reset')
        holder['journal']=value
        return value
    try:
        pilot.PublicJournal.read=strict_read
        # Evaluate prior delivered forecasts only; do not create/promote a V11 model.
        pilot.forecast_audit.remember=lambda *args,**kwargs: None
        if not manual_key and pilot.phase(pilot.datetime.now(pilot.timezone.utc)) not in (('morning','evening','usa') if v112 else ('morning','evening')):return invoke()
        state=latest_public_rule_state() # fail closed, no reset or legacy-state write
        fear=legacy.get_fear_greed() # same existing read-only provider
        def enrich(snap,fund,now,kind,previous=None):
            display=os.getenv('V2_REPORT_ENABLED','false').lower()=='true'
            if display:
                from v11 import event_lifecycle
                fund=event_lifecycle.collect(fund,now,snap)
            previous=previous if v112 else comparable_morning(previous,snap,now) if kind=='evening' else None
            text,quotes,evaluations=integration.render(legacy,snap,fund,now,kind,state,previous,fear)
            if v112:
                from v11 import analyst
                model=analyst.prepare(snap,fund,now,quotes,evaluations,previous)
                if display:
                    from scripts.v2_context import enrich as add_predictions
                    try:add_predictions(snap,fund,now,model)
                    except Exception as exc:model.update(experimental_predictions={},prediction_diagnostics={'prediction_error':type(exc).__name__})
                from v11 import trend_reversal
                trend_reversal.attach(model,snap,fund,now,holder.get('journal',{}))
                from v11 import event_notices
                model['event_notices']=event_notices.plan(fund,holder.get('journal',{}),now)
                model['observation']['event_notices_pending']=model['event_notices']
                holder['model']=model
                if display:
                    from v11.integrated_report import render
                    text=render(model,snap,now,kind)
                    from v11.report_verdict import contract
                    from v11.prediction_runtime import current_predictions
                    model.setdefault('prediction_diagnostics',{})['report_contract']=contract(text,sum(len(v) for v in current_predictions(model,int(now.timestamp()*1000)).values()))
                    from v11.reversal_report import guard
                    _,model['report_consistency']=guard(text,analyst.final_text(model,snap,now,kind),model,snap)
                else:text=analyst.final_text(model,snap,now,kind)
                quotes['_v112_observation']=model['observation']
            directory=os.getenv('V111_DIAGNOSTICS_DIR')
            if directory:
                # Public data only; private inventory is loaded later by the existing sender.
                from v11.state_policy import require_public_data
                from v11.fundamental_analysis import analyze
                details,_,_=integration.render_detailed(legacy,snap,fund,now,kind,state,previous,fear)
                files={'analysis_details.txt':details,'risk_diagnostics.json':{s:integration.risk_breakdown(legacy,e) for s,e in evaluations.items()},
                    'fundamental_evidence.json':analyze(fund,now),'market_snapshot.json':snap}
                if v112:files['v112_analysis.json']=holder['model']
                target=Path(directory);target.mkdir(parents=True,exist_ok=True)
                for name,value in files.items():
                    require_public_data(value)
                    (target/name).write_text(value if isinstance(value,str) else json.dumps(value,ensure_ascii=False,allow_nan=False))
            return text,quotes
        if v112:
            def usa_prepare(context,snap,fund,now,previous):
                from v11 import analyst
                from v11.us_brief import render as brief
                _,quotes,evaluations=integration.render(legacy,snap,fund,now,'usa',state,previous,fear)
                model=analyst.prepare(snap,fund,now,quotes,evaluations,previous)
                from v11 import event_notices
                model['event_notices']=event_notices.plan(fund,holder.get('journal',{}),now,limit=1)
                context['_event_plan']=model['event_notices']
                holder.update(model=model,us_context=context,us_fund=fund)
                # Only public evidence, never final personalized text, enters artifacts.
                directory=os.getenv('V111_DIAGNOSTICS_DIR')
                if directory:
                    from v11.state_policy import require_public_data
                    require_public_data(model)
                    target=Path(directory);target.mkdir(parents=True,exist_ok=True)
                    (target/'v112_analysis.json').write_text(json.dumps(model,ensure_ascii=False,allow_nan=False))
                return brief(context,model,snap,fund,now)
            pilot.usa_prepare=usa_prepare
        pilot.render=enrich
        if v112:
            from v11 import analyst
            def private_render(inventory,snap,now,kind):
                if kind=='usa':
                    from v11.us_brief import render as brief
                    return brief(holder['us_context'],holder['model'],snap,holder['us_fund'],now,inventory)
                if os.getenv('V2_REPORT_ENABLED','false').lower()=='true':
                    from v11.integrated_report import render
                    # Private storage is read after the attempting CAS. Recheck
                    # forecast freshness at final rendering, not the old clock
                    # from before those bounded network requests.
                    delivery_now=pilot.datetime.now(pilot.timezone.utc)
                    return render(holder['model'],snap,delivery_now,kind,inventory)
                return analyst.final_text(holder['model'],snap,now,kind,inventory)
            pilot.personalize=private_render
        if v112 and os.getenv('V2_REPORT_ENABLED','false').lower()=='true':
            def metadata(text):
                import subprocess
                from v11.report_verdict import contract
                # Count what the final rendered text actually contains, not a
                # possibly expired in-memory model. No private text is persisted.
                import re
                result=contract(text,len(re.findall(r'(?:24h|72h|14d) (?:RAST|POKLES|DO STRANY)(?=\s|[.;]|$)',text)))
                try:source=subprocess.check_output(['git','rev-parse','HEAD'],text=True,stderr=subprocess.DEVNULL).strip()
                except (OSError,subprocess.SubprocessError):source=None
                if 'trend_reversal' in holder.get('model',{}):
                    from v11.compact_main import LABELS
                    actual_state=next((s for s,label in LABELS.items() if '🌐 TRH: '+label in text.splitlines()),None)
                    result.update(trend_reversal_state=actual_state,reversal_consistency_checked=True)
                result.update(workflow_run=os.getenv('GITHUB_RUN_ID'),source=source)
                return result
            pilot.delivery_metadata=metadata
        return invoke() # same canonical slot and CAS-before-send owner
    finally:
        pilot.render=original_render
        pilot.personalize=original_personalize
        pilot.delivery_metadata=original_metadata
        pilot.usa_prepare=original_usa
        pilot.PublicJournal.read=original_read
        pilot.forecast_audit.remember=original_remember

if __name__=='__main__':raise SystemExit(run())
