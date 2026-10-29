"""Bounded inference only; package selected/trained by the separate research job.
No broker, private inventory, Telegram, model selection or online fitting here.
"""
import math
from . import prediction_research as r
from .prediction_shadow import HORIZONS,STEP,COINS
from .state_policy import require_public_data

SCHEMA='v2-runtime-package-1'

def package(results,created):
    out=dict(schema=SCHEMA,version=r.VERSION,created=created,coins={})
    for symbol,result in results.items():
        if symbol not in COINS or result.get('status')!='RESEARCH_ONLY':continue
        out['coins'][symbol]=dict(asof=result['source_end']+STEP,input_digest=result['input_digest'],btc_digest=result['btc_digest'],states={label:f['runtime_state'] for label,f in result['live'].items()})
    validate(out);return out

def validate(value):
    if not isinstance(value,dict) or set(value)!={'schema','version','created','coins'} or value['schema']!=SCHEMA or value['version']!=r.VERSION:raise ValueError('Invalid runtime package')
    if not r.finite(value['created']) or not isinstance(value['coins'],dict) or set(value['coins'])-set(COINS):raise ValueError('Invalid package clock/coins')
    for symbol,item in value['coins'].items():
        if set(item)!={'asof','input_digest','btc_digest','states'} or not r.finite(item['asof']) or item['asof']>value['created']:raise ValueError('Invalid package observation')
        if not all(isinstance(item[k],str) and len(item[k])==64 for k in ('input_digest','btc_digest')):raise ValueError('Invalid package provenance')
        for label,state in item['states'].items():
            if label not in HORIZONS or set(state)!={'model','volatility_limit','tolerance_factor','offsets','ridge'}:raise ValueError('Invalid state schema')
            if state['model'] not in r.MODELS[:5] or not all(r.finite(state[k]) and state[k]>=0 for k in ('volatility_limit','tolerance_factor')):raise ValueError('Invalid model/threshold')
            if len(state['offsets'])!=2 or not all(r.finite(v) for v in state['offsets']) or state['offsets'][0]>state['offsets'][1]:raise ValueError('Invalid model interval')
            fit=state['ridge']
            if state['model']=='ridge_technical':
                if not isinstance(fit,dict) or set(fit)!={'mean','std','beta'} or [len(fit[k]) for k in ('mean','std','beta')]!=[10,10,11]:raise ValueError('Invalid ridge state')
                if not all(r.finite(v) for a in fit.values() for v in a) or min(fit['std'])<=0:raise ValueError('Invalid coefficients')
            elif fit is not None:raise ValueError('Unexpected fitted state')
    require_public_data(value);return value

def predict(snapshot,value,now_ms,diagnostics=None):
    validate(value)
    if not 0<=now_ms-value['created']<=48*3600000:raise ValueError('Runtime package stale/future')
    stamp=snapshot.get('at')
    if not r.finite(stamp):raise ValueError('Invalid snapshot clock')
    # Both clocks use integer milliseconds. Truncating only now made valid
    # microsecond snapshots appear up to 0.999 ms in the future in production.
    age=now_ms-int(stamp*1000)
    if diagnostics is not None:diagnostics.update(snapshot_age_ms=age,coin_errors={})
    if not 0<=age<=900000:raise ValueError('Snapshot stale/future')
    def reject(symbol,reason):
        if diagnostics is not None:diagnostics['coin_errors'][symbol]=reason
    btc=snapshot['coins'].get('BTC',{});out={}
    for symbol in COINS:
        coin=snapshot['coins'].get(symbol,{});item=value['coins'].get(symbol)
        out[symbol]={}
        if not item:reject(symbol,'MODEL_STATE_MISSING');continue
        if coin.get('stale',True) or not r.finite(coin.get('price')) or coin['price']<=0:reject(symbol,'CURRENT_COIN_QUOTE_MISSING_OR_STALE');continue
        if btc.get('stale',True):reject(symbol,'CURRENT_BTC_QUOTE_MISSING_OR_STALE');continue
        try:data=r.prepare(coin['raw']['4h'],btc['raw']['4h'])
        except (ValueError,KeyError) as exc:reject(symbol,'INVALID_OR_UNALIGNED_CLOSED_CANDLES: '+str(exc)[:100]);continue
        i=len(data['rows'])-1
        if not r.np.all(r.np.isfinite(data['features'][i])):reject(symbol,'INVALID_OR_UNWARMED_FEATURES');continue
        source_close=data['rows'][-1]['timestamp']+STEP
        if not 0<=now_ms-source_close<=STEP:reject(symbol,'LAST_CLOSED_CANDLE_STALE_OR_FUTURE');continue
        if item['asof']>source_close:reject(symbol,'PACKAGE_AHEAD_OF_SNAPSHOT');continue
        if now_ms-item['asof']>48*3600000:reject(symbol,'MODEL_OBSERVATION_EXPIRED');continue
        for label,state in item['states'].items():
            h=HORIZONS[label];scale=float(data['sigma'][i])*math.sqrt(h)
            if not math.isfinite(scale) or scale<=0:reject(symbol,'NO_FINITE_VOLATILITY');continue
            kind=state['model'];points=r.point_models(data,i,h,state['volatility_limit'],fit_models=False)
            if kind=='ridge_technical':q=float(r.np.clip(r.predict_state(state['ridge'],data['features'][i]),-3,3)*scale)
            else:q=points.get(kind)
            if q is None or not math.isfinite(q):reject(symbol,'MODEL_OUTPUT_MISSING');continue
            p=coin['price'];lo,hi=state['offsets'];tolerance=state['tolerance_factor']*scale
            out[symbol][label]=dict(model=kind,price=p,point=p*math.exp(q),low=p*math.exp(q+lo*scale),high=p*math.exp(q+hi*scale),
                direction=r.direction(q,tolerance),confidence='NÍZKA',probabilities=None,low_pct=math.expm1(q+lo*scale)*100,high_pct=math.expm1(q+hi*scale)*100,
                input_features=data['features'][i].tolist(),volatility_4h=float(data['sigma'][i]),regime=r.regime(data,i,state['volatility_limit']),
                tolerance_log=tolerance,trend_price=p*math.exp(points['trend']),source_close=source_close,input_digest=r.digest(coin['raw']['4h']),btc_digest=r.digest(btc['raw']['4h']))
    require_public_data(out);return out

def records(predictions,now_ms,run_id,code_digest):
    out=[]
    for s,forecasts in predictions.items():
        for label,f in forecasts.items():
            hours=HORIZONS[label]*4;due=math.ceil((now_ms+hours*3600000)/60000)*60000
            out.append(dict(id=f'{r.VERSION}:report-{run_id}:{s}:{hours}',symbol=s,created=now_ms,due=due,price=f['price'],point=f['point'],low=f['low'],high=f['high'],
                direction=f['direction'],continuation=f['trend_price'],model_version=r.VERSION,model=f['model'],source_digest=f['input_digest'],btc_digest=f['btc_digest'],
                requested_hours=hours,tolerance_log=f['tolerance_log'],source_cutoff=now_ms,source_close=f['source_close'],source_mode='FORWARD_PAPER',
                inputs=dict(features=f['input_features'],volatility_4h=f['volatility_4h'],regime=f['regime'],model_code_digest=code_digest,vintage_digest=r.digest([]))))
    return out
