"""Frozen, causal prediction experiment. Not imported by production delivery.
Every feature is an origin-time observation. No class probabilities are emitted.
"""
import hashlib
from bisect import bisect_right
import json
import math
from datetime import datetime, timezone
import numpy as np
from .prediction_shadow import COINS, HORIZONS, STEP, valid
from .state_policy import require_public_data

VERSION='research-v2-20261028'
MODELS=('flat','trend','legacy_v1','regime_momentum','ridge_technical',
        'ridge_technical_matched','ridge_macro','ridge_macro_project')
MIN_TRAIN=400
RIDGE=50.0
WINDOW=1200
BOOTSTRAPS=400
MACRO=('yield_2y','yield_10y','cpi','pce','unemployment','payrolls','dxy','etf_flow')
PROJECT=('tvl','fees','revenue')

def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()

def finite(value):
    return type(value) in (int,float) and math.isfinite(value)

def ema_array(values,period):
    result=np.full(len(values),np.nan)
    if len(values)<period:return result
    result[period-1]=np.mean(values[:period])
    for i in range(period,len(values)):
        result[i]=result[i-1]+2/(period+1)*(values[i]-result[i-1])
    return result

def prepare(rows,btc):
    if not valid(rows) or not valid(btc):raise ValueError('NO_DATA: invalid, gapped or incomplete OHLCV')
    index={r['timestamp']:r for r in btc}
    aligned=[index.get(r['timestamp']) for r in rows]
    if any(r is None for r in aligned):raise ValueError('NO_DATA: BTC clock mismatch')
    c=np.array([r['close'] for r in rows]);b=np.array([r['close'] for r in aligned])
    high=np.array([r['high'] for r in rows]);low=np.array([r['low'] for r in rows]);vol=np.array([r['volume'] for r in rows])
    ret=np.r_[np.nan,np.diff(np.log(c))];br=np.r_[np.nan,np.diff(np.log(b))]
    n=len(rows);sigma=np.full(n,np.nan);bsigma=np.full(n,np.nan)
    volume=np.full(n,np.nan);rsi=np.full(n,np.nan);atr=np.full(n,np.nan);adx=np.full(n,np.nan)
    gains=np.maximum(np.diff(c),0);losses=np.maximum(-np.diff(c),0)
    up=np.mean(gains[:14]);down=np.mean(losses[:14])
    trs=np.maximum(high[1:]-low[1:],np.maximum(abs(high[1:]-c[:-1]),abs(low[1:]-c[:-1])))
    plus=np.maximum(high[1:]-high[:-1],0);minus=np.maximum(low[:-1]-low[1:],0)
    pu=np.where(plus>minus,plus,0);md=np.where(minus>plus,minus,0)
    tr=np.mean(trs[:14]);pp=np.mean(pu[:14]);mm=np.mean(md[:14]);dx=[]
    for i in range(14,n):
        if i>14:
            up=(13*up+gains[i-1])/14;down=(13*down+losses[i-1])/14
            tr=(13*tr+trs[i-1])/14;pp=(13*pp+pu[i-1])/14;mm=(13*mm+md[i-1])/14
        rsi[i]=100-100/(1+up/down) if down else (100 if up else 50)
        atr[i]=tr;dx.append(100*abs(pp-mm)/(pp+mm) if pp+mm else 0)
        if len(dx)==14:adx[i]=np.mean(dx)
        elif len(dx)>14:adx[i]=(13*adx[i-1]+dx[-1])/14
    e={p:ema_array(c,p) for p in (20,50,100,200)}
    be50=ema_array(b,50);be200=ema_array(b,200)
    macd=ema_array(c,12)-ema_array(c,26)
    signal=np.r_[np.full(25,np.nan),ema_array(macd[25:],9)]
    hist=macd-signal
    features=np.full((n,10),np.nan)
    for i in range(120,n):
        sigma[i]=np.std(ret[i-119:i+1]);bsigma[i]=np.std(br[i-119:i+1])
        v=np.mean(vol[i-20:i]);volume[i]=vol[i]/v if v>0 else np.nan
        if sigma[i]<=0 or not np.isfinite(volume[i]):continue
        s=sigma[i]
        features[i]=[(np.log(c[i]/c[i-6]))/(s*math.sqrt(6)),
            np.log(c[i]/c[i-20])/(s*math.sqrt(20)),(c[i]/e[50][i]-1)/(s*math.sqrt(50)),
            hist[i]/c[i]/s,(rsi[i]-50)/50,np.log(max(volume[i],1e-8)),
            (np.log(c[i]/c[i-42])-np.log(b[i]/b[i-42]))/(s*math.sqrt(42)),
            (b[i]/be50[i]-1)/(max(bsigma[i],1e-8)*math.sqrt(50)),
            (rsi[i]-rsi[i-5])/100,hist[i]/c[i]/s-hist[i-1]/c[i-1]/s]
    return dict(rows=rows,close=c,btc=b,ret=ret,sigma=sigma,btc_sigma=bsigma,
        features=features,ema=e,btc_ema50=be50,btc_ema200=be200,macd_hist=hist,
        adx=adx,atr=atr,rsi=rsi,volume_ratio=volume)

def direction(log_return,threshold):
    return 'RAST' if log_return>threshold else 'POKLES' if log_return < -threshold else 'DO STRANY'

def regime(data,i,vol_limit):
    # BTC trend is a market proxy, not total capitalization or observed order flow.
    b=data['btc'];s=data['btc_sigma'][i]
    if s>vol_limit:
        return 'CRISIS_PROXY' if np.log(b[i]/b[i-6]) < -2*s*math.sqrt(6) else 'HIGH_VOLATILITY'
    if b[i]>data['btc_ema50'][i]>data['btc_ema200'][i]:return 'BULL'
    if b[i]<data['btc_ema50'][i]<data['btc_ema200'][i]:return 'BEAR'
    return 'SIDEWAYS'

def label_data(data,h,end):
    # end is exclusive. Endpoint close must be <= the origin of the prediction.
    stop=end-h
    idx=np.arange(220,max(220,stop),dtype=int)
    if not len(idx):return idx,np.array([])
    mask=np.all(np.isfinite(data['features'][idx]),axis=1)&(data['sigma'][idx]>0)
    idx=idx[mask]
    y=np.log(data['close'][idx+h]/data['close'][idx])/(data['sigma'][idx]*math.sqrt(h))
    return idx,y

def fit_predict(x,y,current):
    if len(y)<80:return None
    mean=np.mean(x,axis=0);std=np.std(x,axis=0);std=np.where(std>1e-8,std,1.)
    z=np.clip((x-mean)/std,-5,5);z=np.c_[np.ones(len(z)),z]
    target=np.clip(y,-5,5)
    penalty=np.eye(z.shape[1])*RIDGE;penalty[0,0]=1e-6
    beta=np.linalg.solve(z.T@z+penalty,z.T@target)
    return float(np.r_[1.,np.clip((current-mean)/std,-5,5)]@beta)

def validate_vintage(item):
    required={'symbol','feature','value','available_at','published_at','retrieved_at','source_url','vintage_id'}
    if not isinstance(item,dict) or set(item)!=required:raise ValueError('Invalid point-in-time schema')
    if item['symbol'] not in ('*',*COINS) or item['feature'] not in (*MACRO,*PROJECT):raise ValueError('Unknown vintage field')
    if not finite(item['value']) or not all(finite(item[k]) for k in ('available_at','retrieved_at')) or (item['published_at'] is not None and not finite(item['published_at'])):raise ValueError('Invalid point-in-time value')
    if item['available_at']<0 or item['retrieved_at']<0 or (item['published_at'] is not None and not 0<=item['published_at']<=item['available_at']) or item['retrieved_at']>item['available_at']:raise ValueError('Vintage was not available at claimed time')
    if not isinstance(item['source_url'],str) or not item['source_url'].startswith('https://') or not isinstance(item['vintage_id'],str) or not item['vintage_id']:raise ValueError('Missing archival provenance')
    require_public_data(item)
    return item

class VintageIndex:
    def __init__(self,vintages):
        self.rows={}
        for v in vintages:self.rows.setdefault((v['symbol'],v['feature']),[]).append(v)
        self.times={}
        for key,items in self.rows.items():
            items.sort(key=lambda r:r['available_at']);self.times[key]=[r['available_at'] for r in items]

    def latest(self,symbol,name,at):
        key=(symbol,name);times=self.times.get(key,[]);i=bisect_right(times,at)-1
        if i<0:return None
        item=self.rows[key][i]
        return item if at-item['available_at']<=7*86400000 else None


def pit_features(vintages,symbol,at,project=False):
    names=(*MACRO,*PROJECT) if project else MACRO
    index=vintages if isinstance(vintages,VintageIndex) else VintageIndex(vintages)
    values=[];found=[]
    for name in names:
        entry=index.latest(symbol if name in PROJECT else '*',name,at)
        values.extend([entry['value'] if entry else 0.,float(entry is not None)]);found.append(entry is not None)
    # Missing individual covariates are explicitly masked; no macro/project group
    # is manufactured. Restrict every ablation to shared eligible observations.
    if not any(found[:len(MACRO)]) or (project and not any(found[len(MACRO):])):return None
    return np.array(values)

def point_models(data,i,h,vol_limit,vintages=(),symbol='SOL'):
    c=data['close'];s=data['sigma'][i]*math.sqrt(h)
    if not np.isfinite(s) or s<=0 or not np.all(np.isfinite(data['features'][i])):return {}
    trend=(c[i]/c[i-20]-1)*h/20
    legacy_sigma=np.std(data['ret'][i-119:i+1])*math.sqrt(h) # exact V1 last 120 returns, including current
    old=max(-.95,-legacy_sigma,min(legacy_sigma,trend))
    agree=int(c[i]>data['ema'][50][i] and data['macd_hist'][i]>0)-int(c[i]<data['ema'][50][i] and data['macd_hist'][i]<0)
    old=old if agree and old*agree>0 else 0.
    mode=regime(data,i,vol_limit)
    # One fixed shrinkage hypothesis, not tuned on the evaluation tail.
    momentum=np.log(c[i]/c[i-6])/6*h
    adaptive=.1*np.clip(momentum,-s,s)
    if mode in ('SIDEWAYS','HIGH_VOLATILITY','CRISIS_PROXY'):adaptive=0.
    out=dict(flat=0.,trend=float(np.log1p(max(-.95,trend))),legacy_v1=float(np.log1p(old)),regime_momentum=float(adaptive))
    idx,y=label_data(data,h,i+1);idx=idx[-WINDOW:];y=y[-WINDOW:]
    if len(idx):
        q=fit_predict(data['features'][idx],y,data['features'][i])
        if q is not None:out['ridge_technical']=float(np.clip(q,-3,3)*s)
    # Controlled ablation: identical historical training rows and test origins.
    # The all-data technical model above remains a separate forecasting candidate.
    current=data['pit_full'][i] if 'pit_full' in data else pit_features(vintages,symbol,data['rows'][i]['timestamp']+STEP,True)
    if current is None:return out
    shared=[];targets=[];technical=[]
    for j,target in zip(idx,y):
        f=data['pit_full'][j] if 'pit_full' in data else pit_features(vintages,symbol,data['rows'][j]['timestamp']+STEP,True)
        if f is not None:
            shared.append(f);technical.append(data['features'][j]);targets.append(target)
    if len(targets)<80:return out
    technical=np.array(technical);shared=np.array(shared);targets=np.array(targets)
    for name,columns in [('ridge_technical_matched',0),('ridge_macro',2*len(MACRO)),('ridge_macro_project',2*(len(MACRO)+len(PROJECT)))]:
        x=np.c_[technical,shared[:,:columns]] if columns else technical
        now=np.r_[data['features'][i],current[:columns]] if columns else data['features'][i]
        q=fit_predict(x,targets,now)
        if q is not None:out[name]=float(np.clip(q,-3,3)*s)
    return out

def wilson(success,n):
    if not n:return None
    z=1.95996398454;p=success/n;den=1+z*z/n
    mid=(p+z*z/(2*n))/den;half=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/den
    return [max(0.,mid-half),min(1.,mid+half)]

def uncertainty(values,median=False):
    if len(values)<5:return None
    rng=np.random.default_rng(27810)
    # Circular moving-block bootstrap retains short-range serial dependence.
    n=len(values);block=max(1,int(math.ceil(n**(1/3))))
    starts=rng.integers(0,n,size=(BOOTSTRAPS,math.ceil(n/block)))
    indexes=((starts[:,:,None]+np.arange(block))%n).reshape(BOOTSTRAPS,-1)[:,:n]
    draws=np.asarray(values)[indexes]
    stats=np.median(draws,axis=1) if median else np.mean(draws,axis=1)
    return [float(v) for v in np.quantile(stats,[.025,.975])]

def metrics(records):
    if not records:return dict(n=0,status='NO_DATA')
    errors=[r['abs_error_pct'] for r in records];hits=sum(r['direction_correct'] for r in records);inside=sum(r['inside'] for r in records)
    classes=('RAST','POKLES','DO STRANY')
    recalls=[sum(r['direction_correct'] and r['actual_direction']==c for r in records)/sum(r['actual_direction']==c for r in records) for c in classes if any(r['actual_direction']==c for r in records)]
    return dict(n=len(records),direction_accuracy=hits/len(records),balanced_direction_accuracy=float(np.mean(recalls)),direction_ci95=wilson(hits,len(records)),
        direction_block_ci95=uncertainty([int(r['direction_correct']) for r in records]),
        mae_pct=float(np.mean(errors)),mae_ci95=uncertainty(errors),median_error_pct=float(np.median(errors)),median_ci95=uncertainty(errors,True),
        band_coverage=inside/len(records),band_ci95=wilson(inside,len(records)),mean_band_width_pct=float(np.mean([r['width_pct'] for r in records])),
        confusion={a:{b:sum(r['actual_direction']==a and r['predicted_direction']==b for r in records) for b in ('RAST','POKLES','DO STRANY')} for a in ('RAST','POKLES','DO STRANY')},
        original_v1_band_coverage=(sum(r['original_v1_band_inside'] for r in records)/len(records) if all('original_v1_band_inside' in r for r in records) else None),
        probability_calibration='N/A: no probability model',ci_note='Wilson proportions + moving-block bootstrap for mean/median/differences; ceil(n^(1/3)) circular blocks, 400 fixed-seed draws. Approximate, especially for small n.')

def experiment(rows,btc,symbol,vintages=()):
    data=prepare(rows,btc);n=len(rows);train_end=int(n*.6);validation_end=int(n*.8)
    if train_end<MIN_TRAIN+100:raise ValueError('NO_DATA: insufficient chronological training history')
    vintages=[validate_vintage(v) for v in vintages]
    index=VintageIndex(vintages)
    data['pit_full']=[pit_features(index,symbol,r['timestamp']+STEP,True) for r in rows]
    vol_values=data['btc_sigma'][220:train_end];vol_values=vol_values[np.isfinite(vol_values)]
    vol_limit=float(np.quantile(vol_values,.75));result={};all_records=[];live={}
    for label,h in HORIZONS.items():
        idx,y=label_data(data,h,train_end)
        threshold=float(np.quantile(np.abs(y),1/3)) if len(y) else None
        if threshold is None:continue
        calibration={m:[] for m in MODELS}
        # Forward-origin training residuals; no in-sample residual calibration.
        for i in range(MIN_TRAIN,train_end-h,h):
            past_vol=data['btc_sigma'][220:i+1];past_vol=past_vol[np.isfinite(past_vol)]
            past_limit=float(np.quantile(past_vol,.75))
            points=point_models(data,i,h,past_limit,vintages,symbol)
            scale=data['sigma'][i]*math.sqrt(h);actual=float(np.log(data['close'][i+h]/data['close'][i]))
            for m,q in points.items():calibration[m].append((actual-q)/scale)
        offsets={m:tuple(float(v) for v in np.quantile(e,[.1,.9])) for m,e in calibration.items() if len(e)>=8}
        records=[]
        for part,begin,end in [('validation',train_end,validation_end),('test',validation_end,n)]:
            for i in range(begin,end-h,h):
                points=point_models(data,i,h,vol_limit,vintages,symbol)
                p=data['close'][i];actual=data['close'][i+h];scale=data['sigma'][i]*math.sqrt(h)
                tolerance=threshold*scale;actual_class=direction(float(np.log(actual/p)),tolerance)
                for m,q in points.items():
                    if m not in offsets:continue
                    lo,hi=offsets[m];low=p*math.exp(q+lo*scale);high=p*math.exp(q+hi*scale);point=p*math.exp(q)
                    extra={}
                    if m=='legacy_v1':
                        old_returns=data['close'][h:i+1]/data['close'][:i+1-h]-1
                        old_low=p*(1+float(np.quantile(old_returns,.1)));old_high=p*(1+float(np.quantile(old_returns,.9)))
                        extra=dict(original_v1_band_inside=bool(old_low<=actual<=old_high))
                    records.append(dict(**extra,symbol=symbol,horizon=label,model=m,part=part,origin=rows[i]['timestamp']+STEP,due=rows[i+h]['timestamp']+STEP,
                        regime=regime(data,i,vol_limit),price=float(p),actual=float(actual),point=point,low=low,high=high,
                        predicted_direction=direction(q,tolerance),actual_direction=actual_class,direction_correct=direction(q,tolerance)==actual_class,
                        abs_error_pct=abs(point-actual)/p*100,inside=bool(low<=actual<=high),width_pct=(high-low)/p*100,tolerance_pct=math.expm1(tolerance)*100))
        by_model={m:{part:metrics([r for r in records if r['model']==m and r['part']==part]) for part in ('validation','test')} for m in MODELS}
        # Candidate selection is frozen on validation MAE. Never choose on test.
        eligible=[m for m in MODELS[:5] if by_model[m]['validation']['n']>=8]
        selected=min(eligible,key=lambda m:by_model[m]['validation']['mae_pct']) if eligible else None
        regimes={mode:{m:metrics([r for r in records if r['part']=='test' and r['regime']==mode and r['model']==m]) for m in MODELS[:5]} for mode in ('BULL','BEAR','SIDEWAYS','HIGH_VOLATILITY','CRISIS_PROXY')}
        paired={}
        for m in MODELS[1:]:
            for base in ('flat','trend'):
                a={r['origin']:r for r in records if r['part']=='test' and r['model']==m};b={r['origin']:r for r in records if r['part']=='test' and r['model']==base}
                common=sorted(set(a)&set(b));differences=[a[t]['abs_error_pct']-b[t]['abs_error_pct'] for t in common]
                paired[m+'_minus_'+base]=dict(n=len(common),mae_difference_pct=float(np.mean(differences)) if differences else None,ci95=uncertainty(differences))
        shared=set.intersection(*[{r['origin'] for r in records if r['part']=='test' and r['model']==m} for m in ('ridge_technical_matched','ridge_macro','ridge_macro_project')])
        ablation={m:metrics([r for r in records if r['part']=='test' and r['model']==m and r['origin'] in shared]) for m in ('ridge_technical_matched','ridge_macro','ridge_macro_project')}
        result[label]=dict(models=by_model,selected_on_validation=selected,selection_metric='validation endpoint MAE; min 8 nonoverlapping observations',regimes=regimes,paired=paired,
            ablation=dict(training_policy='identical PIT-eligible training rows for all three variants',status='AVAILABLE' if shared else 'NO_POINT_IN_TIME_HISTORY',matched_origins=len(shared),models=ablation),
            tolerance_factor=threshold,calibration_counts={m:len(v) for m,v in calibration.items()},interval_method='10/90% normalized forward-error quantiles from training only, frozen; not a probability forecast')
        points=point_models(data,n-1,h,vol_limit,vintages,symbol);scale=data['sigma'][-1]*math.sqrt(h)
        if selected and selected in points and selected in offsets:
            q=points[selected];lo,hi=offsets[selected];p=data['close'][-1]
            live[label]=dict(model=selected,point=float(p*math.exp(q)),low=float(p*math.exp(q+lo*scale)),high=float(p*math.exp(q+hi*scale)),price=float(p),
                log_return=q,trend_log_return=points['trend'],input_features=[float(v) for v in data['features'][-1]],volatility_4h=float(data['sigma'][-1]),direction=direction(q,threshold*scale),tolerance_pct=math.expm1(threshold*scale)*100,confidence='NÍZKA',probabilities=None,
                alt_up=float(p*math.exp(q+hi*scale)),alt_down=float(p*math.exp(q+lo*scale)),regime=regime(data,n-1,vol_limit))
        all_records.extend(records)
    if not result:raise ValueError('NO_DATA: no eligible training horizons')
    return dict(version=VERSION,status='RESEARCH_ONLY',independent_validation=False,source_start=rows[0]['timestamp'],source_end=rows[-1]['timestamp'],
        split_train=rows[train_end]['timestamp'],split_test=rows[validation_end]['timestamp'],volatility_limit=vol_limit,
        results=result,live=live,input_digest=digest(rows),btc_digest=digest(btc),vintage_digest=digest(vintages),records=all_records)
