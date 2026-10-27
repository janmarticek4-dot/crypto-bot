"""Real-data integration preview/pair, using the production V10.6 rule functions."""
import argparse
import json
import os
from datetime import datetime,timezone
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import main as legacy
from v11 import integration,shadow_pair
from scripts.fundamental_sources_shadow import run as collect
from scripts.v111_shadow import write_json,protected_hashes

ROOT=Path(__file__).resolve().parents[1]

def run(phase='preview',reference=None):
    now=datetime.now(timezone.utc)
    if phase!='preview':shadow_pair.slot(now,phase)
    before=protected_hashes();out=ROOT/'shadow-output/integration';out.mkdir(parents=True,exist_ok=True)
    state_origin='checkout public cache (not guaranteed latest main)'
    if os.getenv('INTEGRATION_READ_MAIN_STATE','false')=='true':
        from scripts.v111_integrated_delivery import latest_public_rule_state
        state=latest_public_rule_state();state_origin='latest main public cache (read-only)'
    else:state=integration.read_rule_state(ROOT/'bot_state.json')
    code=collect(out,False,report_phase=phase)
    snapshot=json.loads((out/'market_snapshot.json').read_text());fund=json.loads((out/'fundamentals.json').read_text())
    now=datetime.now(timezone.utc)
    kind='morning' if phase=='morning' else 'evening'
    previous=None;morning=None;reference_error=False
    if reference:
        try:
            p=Path(reference).resolve()
            if not p.is_relative_to(ROOT/'shadow-output') or p.stat().st_size>20_000_000:raise ValueError('Invalid public reference')
            morning=json.loads(p.read_text())
            if not isinstance(morning,dict):raise ValueError('Invalid reference object')
        except (ValueError,OSError,TypeError):reference_error=True
    fear=legacy.get_fear_greed()
    text,quotes,evaluations=integration.render(legacy,snapshot,fund,now,kind,state,fear=fear)
    # Signal values are outputs of the original function, not V11 strategy decisions.
    _,_,_,baseline=integration.evaluate(legacy,snapshot,state,fear)
    assert evaluations==baseline
    pair=dict(status='N/A',verified_temporal_pair=False,reason='Preview or missing real morning observation')
    if phase=='evening' and reference_error:
        pair=dict(status='N/A',verified_temporal_pair=False,reason='Invalid or unreadable morning reference');code=2
    if not code and phase=='morning':
        checkpoint=shadow_pair.checkpoint(snapshot,{s:dict(action=e['action']) for s,e in evaluations.items()},now,fund)
        shadow_pair.save_once(out/'checkpoints/morning.json',checkpoint)
        pair=dict(status='AWAITING_EVENING',verified_temporal_pair=False)
    elif not code and phase=='evening' and morning:
        try:
            pair=shadow_pair.compare(morning,snapshot,{s:dict(action=e['action']) for s,e in evaluations.items()},now,fund)
            pair['status']='COMPARED'
            old=morning['snapshot']['coins']
            previous={s:dict(price=old[s].get('price'),market_cap=old[s].get('market_cap'),volume_24h=old[s].get('volume_24h'),action=morning['evaluations'][s]['action'],rule_engine='v10.6-original') for s in shadow_pair.SYMBOLS}
            text,quotes,_=integration.render(legacy,snapshot,fund,now,kind,state,previous,fear)
        except (ValueError,TypeError,KeyError):
            pair=dict(status='N/A',verified_temporal_pair=False,reason='Reference refused: checksum/time/source mismatch');code=2
    detailed,_,_=integration.render_detailed(legacy,snapshot,fund,now,kind,state,previous,fear)
    (out/'analysis_details.txt').write_text(detailed)
    text='SHADOW — SKUTOČNÝ ZBER, BEZ ODOSLANIA.\nV10.6 kontext: '+state_origin+'; nejde o potvrdenú osobnú držbu.\n'+text
    (out/(kind+'.txt')).write_text(text)
    from v11.fundamental_analysis import analyze
    displayed=[e for e in analyze(fund,now)['evidence'] if e['title'] in text]
    write_json(out/'analysis_validation.json',dict(renderer='v10.6-native-with-v11-enrichment',rendered_evidence=len(displayed),source_urls_present=all(e['url'] in text for e in displayed),meaning_and_impact_present=not displayed or all(t in text for t in ('Význam:','Dopad:','Overiť:'))))
    write_json(out/'comparison.json',pair)
    (out/'comparison.txt').write_text(shadow_pair.report(pair) if pair.get('verified_temporal_pair') else 'Porovnanie N/A — '+pair.get('reason','čaká na večer'))
    write_json(out/'risk_diagnostics.json',{s:integration.risk_breakdown(legacy,e) for s,e in evaluations.items()})
    write_json(out/'legacy_rule_audit.json',dict(identical_evaluations=True,rule_engine='main.py V10.6 unchanged',new_fundamentals_affect_signals=False,
        legacy_cache=state_origin,source_commit=os.getenv('SHADOW_SOURCE_SHA')))
    summary=json.loads((out/'summary.json').read_text());summary.update(phase=phase,verified_temporal_pair=pair.get('verified_temporal_pair',False),state_written=False,rule_engine='v10.6-original')
    write_json(out/'summary.json',summary)
    if before!=protected_hashes():raise RuntimeError('Protected production files changed')
    return code

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--phase',choices=['preview','morning','evening'],default='preview');p.add_argument('--reference');p.add_argument('--reference-if-present',action='store_true');args=p.parse_args()
    if args.reference_if_present and (ROOT/'shadow-output/reference/checkpoints/morning.json').is_file():args.reference=str(ROOT/'shadow-output/reference/checkpoints/morning.json')
    raise SystemExit(run(args.phase,args.reference))
