"""True-time research observations. All outputs public-market only, no delivery."""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from v11 import shadow_pair as pair
from v11.runtime import market_status
from v11.strategy import decide
from scripts.fundamental_sources_shadow import run as collect
from scripts.v111_shadow import write_json

ROOT=Path(__file__).resolve().parents[1]

def scheduled_phase(now):
    local=now.astimezone(pair.BL);minute=local.hour*60+local.minute
    for phase,start in [('morning',420),('evening',1200)]:
        if start<=minute<=start+90:return phase
    return ''


def run(phase,output='shadow-output/temporal-current',reference=None):
    started=datetime.now(timezone.utc)
    phase=scheduled_phase(started) if phase=='auto' else phase
    if not phase:return 0
    pair.slot(started,phase) # real clock, no synthetic override in CLI
    out=Path(output).resolve()
    if not out.is_relative_to(ROOT/'shadow-output'):raise ValueError('Isolated output required')
    code=collect(out,False,report_phase=phase) # scheduled research never calls AI
    snap=json.loads((out/'market_snapshot.json').read_text());fund=json.loads((out/'fundamentals.json').read_text())
    now=datetime.now(timezone.utc);risk=market_status(snap,{})
    evaluations={s:dict(action=decide(snap['coins'][s],held=False,approved=False,market_complete=snap['complete'],risk_normal=risk['state']=='NORMAL')['action']) for s in pair.SYMBOLS}
    summary=json.loads((out/'summary.json').read_text());summary['phase']=phase
    if code:
        result=dict(verified_temporal_pair=False,status='N/A',reason='Incomplete current market snapshot')
    elif phase=='morning':
        saved=pair.checkpoint(snap,evaluations,now,fund)
        pair.save_once(out/'checkpoints/morning.json',saved)
        result=dict(verified_temporal_pair=False,status='AWAITING_EVENING',morning_at=saved['observed_at'])
    elif not reference or not Path(reference).is_file():
        result=dict(verified_temporal_pair=False,status='N/A',reason='Morning observation missing; independent evening observation retained')
    else:
        path=Path(reference).resolve()
        if not path.is_relative_to(ROOT/'shadow-output') or path.stat().st_size>20_000_000:raise ValueError('Invalid public reference path')
        try:
            morning=json.loads(path.read_text())
            if not isinstance(morning,dict):raise ValueError('Invalid checkpoint object')
            result=pair.compare(morning,snap,evaluations,now,fund)
        except (ValueError,KeyError,TypeError) as exc:
            result=dict(verified_temporal_pair=False,status='N/A',reason=str(exc))
            code=2 # checksum/commit/reused-data failures remain visible job failures
    write_json(out/'comparison.json',result)
    text=pair.report(result) if result.get('verified_temporal_pair') else 'SHADOW POROVNANIE: '+result.get('status','N/A')+' — '+result.get('reason','Čaká na skutočný večerný zber.')
    (out/'comparison.txt').write_text(text+'\n')
    if phase=='evening':
        with (out/'evening.txt').open('a') as f:f.write('\n'+text+'\n')
    summary['temporal_status']=result.get('status','COMPARED');summary['verified_temporal_pair']=result.get('verified_temporal_pair',False)
    write_json(out/'summary.json',summary)
    return code

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--phase',choices=['auto','morning','evening'],default='auto');p.add_argument('--reference');p.add_argument('--slot',action='store_true')
    args=p.parse_args()
    if args.slot:
        now=datetime.now(timezone.utc);print('phase='+scheduled_phase(now));print('day='+now.astimezone(pair.BL).date().isoformat())
    else:raise SystemExit(run(args.phase,reference=args.reference))
