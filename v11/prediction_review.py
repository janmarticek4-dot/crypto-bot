"""Public forecast comparison from immutable first-seen paper rows; no journal writes."""
import math
from .prediction_shadow import COINS,HORIZONS
from .prediction_research import direction,finite,VERSION

def review(state,current,now_ms):
    rows=[r for r in state.get('predictions',[]) if r.get('model_version')==VERSION and r.get('source_mode')=='FORWARD_PAPER' and finite(r.get('created')) and r['created']<now_ms]
    output={};total=0
    for s in COINS:
        output[s]={}
        for h,bars in HORIZONS.items():
            matches=sorted([r for r in rows if r['symbol']==s and r.get('requested_hours')==bars*4],key=lambda r:r['created'])
            done=[r for r in matches if r.get('result') and r['due']<=now_ms and r['result'].get('evaluated_at',now_ms+1)<=now_ms]
            hits=flat=trend=trend_n=0;errors=[]
            for r in done:
                a=r['result'];tol=r['tolerance_log'];actual=a['actual_direction']
                hits+=int(a['direction_correct']);flat+=int(direction(0,tol)==actual)
                if finite(r.get('continuation')) and r['continuation']>0:
                    trend+=int(direction(math.log(r['continuation']/r['price']),tol)==actual);trend_n+=1
                errors.append(a['abs_error_pct'])
            previous=matches[-1] if matches else None
            prev={k:previous.get(k) for k in ('created','due','point','low','high','direction','result')} if previous else None
            f=current.get(s,{}).get(h)
            latest={k:f.get(k) for k in ('generated_at','point','low','high','direction')} if f else None
            output[s][h]=dict(previous=prev,current=latest,matured=len(done),direction_hits=hits,flat_direction_hits=flat,trend_direction_hits=trend,trend_baseline_n=trend_n,
                mean_absolute_error_pct=sum(errors)/len(errors) if errors else None,calibrated_probability=None)
            total+=len(done)
    return dict(coins=output,matured=total,scope='bounded retained forward-paper records; overlapping observations are not independent',independent_validation=False)
