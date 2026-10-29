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
    allowed={'prediction_error','prediction_reason','public_store','package_created','records','paper_saved','paper_error','snapshot_age_ms','coin_errors','report_contract','package_source','package_attempts'}
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
    package=Path('production-runtime-package.json')
    if package.exists():
        from v11.prediction_runtime import predict
        details={}
        try:
            replay=predict(snap,json.loads(package.read_text()),int(at*1000),details)
            out['historical_replay']=dict(counts={s:len(v) for s,v in replay.items()},diagnostics=details,stored_as_paper=False,independent_validation=False)
        except (ValueError,KeyError) as exc:out['historical_replay']=dict(error=type(exc).__name__,reason=str(exc)[:180],stored_as_paper=False)
    count=sum(out['predictions'].values())
    labeled=diagnostics.get('report_contract',{}).get('technical_fallback_labeled') is True
    out['quality']='COMPLETE_V2' if count==18 else 'DEGRADED_EXPLICIT_TECHNICAL_FALLBACK' if labeled else 'DEGRADED_NO_VERIFIED_FALLBACK'
    receipt=context.get('receipt') or {}
    if context.get('audit_trigger')=='workflow_run':
        validation=receipt.get('report_validation') or {}
        checks=dict(delivery_confirmed=receipt.get('status')=='sent',same_run=validation.get('workflow_run')==str(context['run_id']),source_matches=validation.get('source')==context.get('source')==context.get('expected_source'),verdict_first=validation.get('verdict_first') is True,urls_absent=validation.get('urls_absent') is True,version=validation.get('format_version')=='verdict-v1',predictions_or_explicit_fallback=validation.get('v2_count')==18 or validation.get('technical_fallback_labeled') is True)
        replay=out.get('historical_replay',{}).get('counts',{})
        if sum(replay.values())==18 and count<18:checks['model_availability_matches_replay']=False
        out['scheduled_delivery_checks']=checks
    require_public_data(out);return out

if __name__=='__main__':
    value=audit(sys.argv[1],json.loads(Path(sys.argv[2]).read_text()));Path('production-audit').mkdir(exist_ok=True)
    Path('production-audit/report.json').write_text(json.dumps(value,indent=2,ensure_ascii=False))
    print('::notice title=Actual production prediction audit::'+json.dumps(value,ensure_ascii=False,separators=(',',':')))
    if 'scheduled_delivery_checks' in value and not all(value['scheduled_delivery_checks'].values()):raise SystemExit('Production delivery verification failed; see whitelisted report')
