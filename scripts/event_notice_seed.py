"""Whitelisted migration from an actual SENT old-format public diagnostics artifact."""
import json,sys,zipfile
from pathlib import Path
from datetime import datetime
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from v11 import event_notices as notices
from v11.state_policy import require_public_data

APPROVED_OLD={'68805b3a5b6331251ad3deb6dd4eaebac6244df0','8bed9b1839c55d249b1eca1df7b6eef9c22ea491'}
def build(archive,context,reference=None):
    if context['status']!='sent' or context['source'] not in APPROVED_OLD:raise ValueError('Unverified old-format sent receipt')
    with zipfile.ZipFile(archive) as z:
        matches=[i for i in z.infolist() if i.filename.split('/')[-1]=='v112_analysis.json']
        if len(matches)!=1 or matches[0].file_size>25000000:raise ValueError('Missing/big public diagnostic')
        model=json.loads(z.read(matches[0]))
        snapshots=[i for i in z.infolist() if i.filename.split('/')[-1]=='market_snapshot.json']
        snap=json.loads(z.read(snapshots[0])) if len(snapshots)==1 and snapshots[0].file_size<=25000000 else None
    now=datetime.fromisoformat(context['at'])
    if model['observation']['at']!=context['at']:raise ValueError('Observation does not match actual sent receipt')
    fund=model.get('_current_fundamentals',{})
    # Both approved old renderers unconditionally displayed these release rows
    # and all available ETF lines. No inference from publication date alone.
    releases=[r for r in fund.get('event_lifecycle',{}).get('releases',[]) if r.get('status')!='SUPERSEDED'][:2]
    selected=[]
    for release in releases:
        item=notices.release_notice(release,now)
        if item:selected.append(item)
    critical=[e for e in model.get('evidence',[]) if set(e.get('categories',[]))&{'hack','geopolitics','regulation'}][:2]
    rendered_ids={'news:'+e['id'] for e in critical}
    for row in notices.candidates(fund,now):
        if row['kind']=='flow' or row['id'] in rendered_ids:selected.append(row)
    journal={};notices.commit(journal,{'selected':selected},now)
    result=dict(provenance=context,records=journal[notices.KEY])
    if reference is not None and snap is not None:
        from v11 import trend_reversal
        original=model.get('trend_reversal',{}).get('state')
        corrected=trend_reversal.attach(model,snap,fund,now,reference)
        result['original_report_replay']=dict(original_state=original,corrected_state=corrected.get('state'),evidence=corrected.get('failure_evidence'),independent_validation=False)
    require_public_data(result);return result

if __name__=='__main__':
    reference=Path('event-seed-reference.json')
    value=build(sys.argv[1],json.loads(Path(sys.argv[2]).read_text()),json.loads(reference.read_text()) if reference.exists() else None)
    Path('v11/event_notice_seed.json').write_text(json.dumps(value,ensure_ascii=False,indent=2))
    print('::notice title=Verified previously announced event seed::'+json.dumps(value,ensure_ascii=False))
