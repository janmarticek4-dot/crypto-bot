"""Whitelisted PUBLIC production diagnostics. No holdings or Telegram text exports."""
import json,sys,zipfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from v11.prediction_research import prepare
from v11.state_policy import require_public_data

def audit(archive,context):
    with zipfile.ZipFile(archive) as z:
        def read(name):
            found=[i for i in z.infolist() if i.filename.split('/')[-1]==name]
            if len(found)!=1 or found[0].file_size>25000000:raise ValueError('Missing or oversized public diagnostics')
            return json.loads(z.read(found[0]))
        model=read('v112_analysis.json');snap=read('market_snapshot.json')
    diagnostics=model.get('prediction_diagnostics',{})
    allowed={'prediction_error','prediction_reason','public_store','package_created','records','paper_saved','paper_error','snapshot_age_ms','coin_errors','report_contract','package_source'}
    out=dict(context,at=model.get('observation',{}).get('at'),snapshot_at=snap.get('at'),prediction_diagnostics={k:v for k,v in diagnostics.items() if k in allowed},
             predictions={s:len(v) for s,v in model.get('experimental_predictions',{}).items()},coins={})
    import datetime
    at=datetime.datetime.fromisoformat(out['at']).timestamp()
    out['snapshot_clock_delta_ms']=int(at*1000)-snap.get('at',0)*1000
    btc=snap['coins'].get('BTC',{}).get('raw',{}).get('4h',[])
    for symbol in ('BTC','SOL','TAO','FET','AAVE','ONDO','RENDER'):
        c=snap['coins'].get(symbol,{});rows=c.get('raw',{}).get('4h',[])
        record=dict(stale=c.get('stale'),bars=len(rows),first=rows[0]['timestamp'] if rows else None,last=rows[-1]['timestamp'] if rows else None)
        try:prepare(rows,btc);record['preparation']='OK'
        except (ValueError,KeyError) as exc:record['preparation']=str(exc)[:180]
        out['coins'][symbol]=record
    require_public_data(out);return out

if __name__=='__main__':
    value=audit(sys.argv[1],json.loads(Path(sys.argv[2]).read_text()));Path('production-audit').mkdir(exist_ok=True)
    Path('production-audit/report.json').write_text(json.dumps(value,indent=2,ensure_ascii=False))
    print('::notice title=Actual production prediction audit::'+json.dumps(value,ensure_ascii=False,separators=(',',':')))
