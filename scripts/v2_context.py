"""Public-only enrichment; failures never block the approved primary analysis."""
import hashlib,json,os,subprocess
from pathlib import Path
from v11 import event_lifecycle,prediction_runtime as runtime
from v11.fundamental_analysis import analyze
from scripts.public_prediction_store import PublicPredictionStore
ROOT=Path(__file__).resolve().parents[1]

def enrich(snapshot,fund,now,model,persist=True,store=None):
    model['_current_fundamentals']=fund;model['project_evidence']=analyze(fund,now)['evidence']
    model['experimental_predictions']={};model['prediction_diagnostics']={};state=None
    try:
        store=store or PublicPredictionStore()
        state=store.read()
    except Exception as exc:
        model['prediction_diagnostics']['public_store']=type(exc).__name__
        if isinstance(getattr(exc,'code',None),int):model['prediction_diagnostics']['public_store_http_status']=exc.code
    value=state.get('runtime_package') if state else None
    model['prediction_diagnostics']['package_source']='public-journal' if value is not None else 'bundled-frozen'
    if value is None:
        try:value=json.loads((ROOT/'v11/frozen_prediction_package.json').read_text())
        except (OSError,ValueError):value=None
    try:
        if value is None:raise ValueError('No approved research package')
        model['prediction_diagnostics']['package_created']=value.get('created')
        forecasts=runtime.predict(snapshot,value,int(now.timestamp()*1000),model['prediction_diagnostics'])
        model['experimental_predictions']=forecasts
        code=hashlib.sha256((ROOT/'v11/prediction_runtime.py').read_bytes()).hexdigest()
        rows=runtime.records(forecasts,int(now.timestamp()*1000),os.getenv('GITHUB_RUN_ID') or now.isoformat(),code)
        model['prediction_diagnostics'].update(package_created=value['created'],records=len(rows),paper_saved=False)
        if persist and rows:
            try:store.append(rows,int(now.timestamp()*1000));model['prediction_diagnostics']['paper_saved']=True
            except Exception as exc:model['prediction_diagnostics']['paper_error']=type(exc).__name__
        if state:
            totals=state.get('totals',{});n=sum(t['n'] for t in totals.values())
            model['paper_weekly']=f'{n} vyhodnotených papierových prognóz; vzorka je malá alebo prekrývajúca sa, nejde o kalibrovanú úspešnosť.' if n else 'Zatiaľ 0 dozretých prognóz; úspešnosť N/A.'
    except Exception as exc:
        model['prediction_diagnostics']['prediction_error']=type(exc).__name__
        if isinstance(exc,ValueError):model['prediction_diagnostics']['prediction_reason']=str(exc)[:180]
    details=model['prediction_diagnostics']
    available=runtime.current_predictions(model,int(now.timestamp()*1000))
    details['available_predictions']={s:len(v) for s,v in available.items()}
    details['missing_predictions']={s:{h:details.get('coin_errors',{}).get(s) or details.get('horizon_errors',{}).get(s,{}).get(h) or
        ('INFERENCE_FAILED_SEE_PREDICTION_REASON' if details.get('prediction_error') else 'MODEL_OUTPUT_UNAVAILABLE')
        for h in runtime.HORIZONS if h not in available[s]} for s in runtime.COINS if len(available[s])<len(runtime.HORIZONS)}
    return model
