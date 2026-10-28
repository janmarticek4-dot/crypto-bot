"""Research only. No delivery imports, trading rules, fitting, or production state.
Bands are empirical historical ENDPOINT-return scenarios, not confidence intervals.
"""
import math
import statistics
from .indicators import summary
from .state_policy import require_public_data

COINS=('SOL','TAO','FET','AAVE','ONDO','RENDER')
HORIZONS={'24 h':6,'48–72 h':18,'7–14 dní':84} # 4h closed bars; endpoints 24/72/336h
STEP=14400000

def valid(rows):
    if len(rows)<220:return False
    try:
        return all(all(type(r[k]) in (int,float) and math.isfinite(r[k]) for k in ('timestamp','open','high','low','close','volume')) and min(r[k] for k in ('open','high','low','close'))>0 and r['volume']>=0 and r['low']<=min(r['open'],r['close'])<=max(r['open'],r['close'])<=r['high'] for r in rows) and all(b['timestamp']-a['timestamp']==STEP for a,b in zip(rows,rows[1:]))
    except (KeyError,TypeError):return False

def quantile(values,q):
    x=sorted(values);i=(len(x)-1)*q;lo=int(i)
    return x[lo]+(x[min(lo+1,len(x)-1)]-x[lo])*(i-lo)

def forecast(rows,h):
    if not valid(rows) or h not in HORIZONS.values():return {'status':'NO_DATA'}
    cs=[r['close'] for r in rows];p=cs[-1];t=summary(rows)
    # Every outcome in the reference distribution is fully observed before origin.
    returns=[cs[i]/cs[i-h]-1 for i in range(h,len(cs))]
    if len(returns)<120:return {'status':'NO_DATA'}
    trend=(p>t['ema50'] and t['macd_hist']>0)-(p<t['ema50'] and t['macd_hist']<0)
    # Heuristic point forecast; fixed cap and lookback declared before evaluation.
    sigma=statistics.pstdev([math.log(b/a) for a,b in zip(cs[-121:-1],cs[-120:])])*math.sqrt(h)
    drift=max(-.95,-sigma,min(sigma,(p/cs[-21]-1)*h/20))
    point=p*(1+drift) if trend and drift*trend>0 else p
    low=p*(1+quantile(returns,.1));high=p*(1+quantile(returns,.9))
    return dict(status='EXPERIMENTAL',price=p,point=point,low=low,high=high,
        low_pct=(low/p-1)*100,high_pct=(high/p-1)*100,direction='RAST' if point>p else 'POKLES' if point<p else 'DO STRANY',
        confidence='NÍZKA',probabilities=None,reference_outcomes=len(returns),
        reason='zhoda trendu a momenta' if trend else 'trend a momentum bez zhody',
        support=t['support'] if t['support']<p else None,resistance=t['resistance'] if t['resistance']>p else None,
        invalidates='nové uzavretie pod podporou/nad rezistenciou alebo nová významná overená udalosť; zber zopakovať',
        band_method='10.–90. percentil minulých prekrývajúcich sa koncových výnosov; nekalibrované, nie maximum/minimum počas horizontu')

def evaluate(rows):
    """Frozen specification, chronological research split; not untouched evidence.
    Fixed origins every six bars; overlapping labels are explicitly not independent.
    """
    if not valid(rows):return {'status':'NO_DATA'}
    split=int(len(rows)*.7);out={}
    for label,h in HORIZONS.items():
        records=[]
        for i in range(220,len(rows)-h,6):
            f=forecast(rows[:i+1],h)
            if f['status']=='NO_DATA':continue
            p=f['price'];actual=rows[i+h]['close'];flat=p
            continuation=p*(1+max(-.95,(p/rows[i-20]['close']-1)*h/20))
            records.append(dict(origin=rows[i]['timestamp'],due=rows[i+h]['timestamp'],part='development' if i+h<split else 'test' if i>=split else 'purged',
                actual=actual,price=p,point=f['point'],flat=flat,continuation=continuation,inside=f['low']<=actual<=f['high']))
        out[label]={}
        for part in ('development','test'):
            r=[x for x in records if x['part']==part]
            metrics={}
            for model in ('point','flat','continuation'):
                metrics[model]=dict(mae_pct=statistics.mean(abs(x[model]-x['actual'])/x['price']*100 for x in r) if r else None,
                    direction_accuracy=statistics.mean((x[model]>x['price'])-(x[model]<x['price']) == (x['actual']>x['price'])-(x['actual']<x['price']) for x in r) if r else None)
            out[label][part]=dict(n=len(r),band_endpoint_coverage=statistics.mean(x['inside'] for x in r) if r else None,models=metrics)
    return dict(status='RESEARCH_ONLY',start=rows[0]['timestamp'],end=rows[-1]['timestamp'],split=rows[split]['timestamp'],results=out,independent_validation=False)

def coin_view(coin,btc=None):
    rows=coin.get('raw',{}).get('4h',[])
    if coin.get('stale',True) or type(coin.get('price')) not in (int,float) or not math.isfinite(coin['price']) or coin['price']<=0 or not valid(rows):return dict(status='NO_DATA',action='WAIT',forecasts={})
    t=summary(rows);prior=summary(rows[:-1]);p=coin['price'];volume=t.get('relative_volume')
    momentum=t['macd_hist']>prior['macd_hist'];structure=t['higher_structure']
    rebound=momentum and structure
    volume_confirmed=volume is not None and volume>=1.2
    broken=bool(t['support_broken'])
    # Correlated EMA/momentum/structure count as ONE technical evidence family.
    independent_evidence=['structure'] if broken else []
    if broken and volume_confirmed and rows[-1]['close']<rows[-1]['open']:independent_evidence.append('sell_volume_proxy')
    risk='zvýšené technické riziko' if len(independent_evidence)>=2 else 'hlbší pokles nepotvrdený'
    forecasts={label:forecast(rows,h) for label,h in HORIZONS.items()}
    rs=coin.get('relative_strength_btc_7d')
    support=t['support'] if t['support']<p else None;resistance=t['resistance'] if t['resistance']>p else None
    economics={}
    if support and resistance and support-t['atr']>0:
        for fee in (.01,.012):
            factor=(1-fee)*(1-.0025)/((1+fee)*(1+.0025))
            gain=resistance/support*factor-1;loss=1-(support-t['atr'])/support*factor
            economics[str(fee)]=dict(net_rr=gain/loss if loss>0 else None,net_target_pct=gain*100,fee_per_side=fee,adverse_fill_per_side=.0025)
    # Ranking is ordinal evidence groups, explicitly not a trained probability score.
    return dict(status='EXPERIMENTAL',action='WAIT',reversal='predbežný obrat' if rebound else 'obrat nepotvrdený',
        volume_ratio=volume,relative_strength_btc_7d=rs,trend='rastový' if p>t['ema50'] else 'slabý',risk=risk,
        rank_groups=[bool(rebound),bool(volume_confirmed),bool(rs is not None and rs>0)],
        zone=[support,min(p,support+t['atr'])] if support else None,economics=economics,
        invalidates=support,targets=[x for x in (resistance,coin.get('frames',{}).get('1d',{}).get('resistance')) if isinstance(x,(int,float)) and x>p],
        confirmation=f'uzavretie 4h nad {resistance:.4g} a objem aspoň 1,2× minulý priemer' if resistance else 'najprv vytvoriť overiteľnú rezistenciu a nový retest',
        forecasts=forecasts,independent_risk_evidence=independent_evidence,
        unavailable=['orderbook','likvidácie','kalibrovaná pravdepodobnosť'],technical={tf:coin.get('frames',{}).get(tf,{}) for tf in ('1h','4h','1d')})

def journal_update(journal,records,observations,now_ms):
    """Caller persists a separate PUBLIC file. No state or delivery side effects.
    Exact-horizon close only; missing historical quote is never replaced by now.
    """
    allowed={'id','symbol','created','due','price','point','low','high','direction','continuation','result'}
    def clean(r):
        if not isinstance(r,dict) or set(r)-allowed:raise ValueError('Non-public journal fields')
        if r.get('symbol') not in COINS:raise ValueError('Unknown symbol')
        if not isinstance(r.get('id'),str) or not all(type(r.get(k)) in (int,float) and math.isfinite(r[k]) for k in ('created','due','price','point','low','high')):raise ValueError('Invalid public prediction')
        if not 0<r['low']<=r['high'] or min(r['price'],r['point'])<=0 or r['due']<=r['created']:raise ValueError('Invalid forecast horizon or bounds')
        if 'continuation' in r and (type(r['continuation']) not in (int,float) or not math.isfinite(r['continuation']) or r['continuation']<=0):raise ValueError('Invalid baseline')
        require_public_data(r);return dict(r)
    items={r['id']:clean(r) for r in journal}
    for item in records:
        c=clean(item);items.setdefault(c['id'],c)
    for r in items.values():
        actual=observations.get((r['symbol'],r['due']))
        if not r.get('result') and r['due']<=now_ms and actual is not None and math.isfinite(actual) and actual>0:
            r['result']=dict(actual=actual,inside=r['low']<=actual<=r['high'],absolute_error_pct=abs(r['point']-actual)/r['price']*100,
                flat_error_pct=abs(r['price']-actual)/r['price']*100,
                continuation_error_pct=abs(r['continuation']-actual)/r['price']*100 if r.get('continuation') else None,
                actual_return_pct=(actual/r['price']-1)*100,
                predicted_return_pct=(r['point']/r['price']-1)*100,
                direction_correct=((r['point']>r['price'])-(r['point']<r['price']))==((actual>r['price'])-(actual<r['price'])))
    return sorted(items.values(),key=lambda r:r['created'])[-600:]
