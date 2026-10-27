"""One frozen exit-only research experiment. No production imports with side effects beyond main definitions.
Local public OHLCV only; never reads/writes bot_state, credentials, Telegram or holdings.
"""
import argparse,copy,csv,hashlib,json,sys
from datetime import datetime,timezone,timedelta
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import main as legacy

SYMBOLS=('AAVE','TAO','FET','SOL','ONDO','RENDER')
PERIODS=(('development_seen','2025-06-01','2026-01-01'),('test_seen_H1','2026-01-01','2026-07-01'),('test_seen_H2','2026-07-01','2026-10-21'))
VARIANTS=((.01,.0025),(.012,.0025),(.012,.005))


def alternative(coin,prior,btc,at,event=None):
    """Correlated price indicators form ONE family, not independent votes.
    Cross-asset evidence is distinct input but not statistically independent.
    Event is external verified evidence, never inferred from candles/headlines.
    """
    if not coin or not coin.get('valid'):return 'HOLD','data_unavailable'
    if event:
        age=at-event.get('known_at',float('inf'))
        if 0<=age<=3600 and event.get('verified') and event.get('severity')=='severe' and event.get('direct_exposure') and event.get('primary_url','').startswith('https://'):
            return 'SELL','extraordinary_protective'
    p=coin['price'];t=coin['technical'];support=prior['structure']['support_prev'] if prior else None
    structural=bool(prior and support and prior['price']<support*.995 and p<support*.995)
    weak=bool(t.get('ema50') and t.get('ema200') and p<t['ema50'] and p<t['ema200'] and coin['score']['score']<=3.5)
    liquidity=coin['structure']['sell_pressure']
    market=bool(btc and btc['structure']['support_broken'] and (btc['technical'].get('macd') or {}).get('histogram',0)<0)
    # Price weakness and structure are deliberately ONE family, never two votes.
    price_family=structural and weak
    if price_family and liquidity and market:return 'SELL','protective_structure_volume_market'
    if price_family and (liquidity or market):return 'REDUCE','protective_two_families'
    return 'HOLD','ordinary_or_unconfirmed_correction'


def reentry(c,previous):
    def good(x):
        if not x or not x.get('valid'):return False
        t=x['technical'];p=x['price']
        return bool(t.get('ema20') and t.get('ema50') and p>t['ema20'] and p>t['ema50'] and (t.get('macd') or {}).get('histogram',0)>0 and not x['structure']['support_broken'])
    return good(c) and good(previous)


def feature(rows):
    price=rows[-1]['close'];t=legacy.technical_summary(rows,price)
    return dict(valid=True,price=price,technical=t,score=legacy.calculate_technical_score(t),structure=legacy.compute_structure(rows,price))


def load(directory):
    import pandas as pd
    frames={};coverage=[]
    for s in ('BTC',*SYMBOLS):
        p=Path(directory)/(s+'_USDT-4h.feather')
        if not p.exists():raise ValueError('NO_DATA '+s)
        d=pd.read_feather(p).sort_values('date');ts=[int(v.timestamp()) for v in d['date']]
        if len(set(ts))!=len(ts) or any(b-a!=14400 for a,b in zip(ts,ts[1:])):raise ValueError('Non-contiguous/duplicate OHLCV '+s)
        rows=[dict(timestamp=t*1000,open=float(r.open),high=float(r.high),low=float(r.low),close=float(r.close),volume=float(r.volume)) for t,r in zip(ts,d.itertuples())]
        if any(not all(__import__('math').isfinite(r[k]) and r[k]>0 for k in ('open','high','low','close')) or not __import__('math').isfinite(r['volume']) or r['volume']<0 or not r['low']<=min(r['open'],r['close'])<=max(r['open'],r['close'])<=r['high'] for r in rows):raise ValueError('Invalid OHLCV '+s)
        frames[s]={r['timestamp']//1000:r for r in rows}
        coverage.append(dict(symbol=s,first=d.iloc[0]['date'].isoformat(),last=d.iloc[-1]['date'].isoformat(),rows=len(rows),sha256=hashlib.sha256(p.read_bytes()).hexdigest(),source='existing Binance spot OHLCV via CCXT/Freqtrade; independently unverified download'))
    return frames,coverage


def prepare(frames,start,end):
    start=int(datetime.fromisoformat(start).replace(tzinfo=timezone.utc).timestamp());end=int(datetime.fromisoformat(end).replace(tzinfo=timezone.utc).timestamp())
    common=sorted(set.intersection(*(set(d) for d in frames.values())))
    times=[t for t in common if start-14400<=t<end]
    result={}
    histories={s:sorted(d) for s,d in frames.items()}
    for n,t in enumerate(times):
        values={}
        for s,d in frames.items():
            import bisect
            i=bisect.bisect_right(histories[s],t)
            keys=histories[s][max(0,i-300):i]
            if len(keys)<300:raise ValueError('NO_DATA warmup '+s)
            values[s]=feature([d[k] for k in keys])
        result[t]=values
    return result


def native_signals(features,times):
    state={};out={}
    for t in times:
        at=datetime.fromtimestamp(t+14400,timezone.utc)
        class Clock(datetime):
            @classmethod
            def now(cls,tz=None):return at.astimezone(tz) if tz else at.replace(tzinfo=None)
        values=features[t]
        def data(s):
            v=values[s];return dict(symbol=s,price_usd=v['price'],technical_4h=v['technical'],technical_score_calc=v['score'],structure=v['structure'],change_24h=v['structure']['change_24h_candles'])
        ctx=dict(btc_data=data('BTC'),portfolio_data={s:data(s) for s in SYMBOLS},fear={},global_change=None,btc_change_24h=values['BTC']['structure']['change_24h_candles'])
        with patch.object(legacy,'datetime',Clock):mm,safety,ev=legacy.evaluate_all(ctx,state,None)
        state['safety']=dict(safety,as_of=at.isoformat())
        state['last_actions']={s:dict(action=e['action'],ts=at.isoformat()) for s,e in ev.items()}
        out[t]={s:e['action'] for s,e in ev.items()}
    return out


def cost_value(units,price,fee,friction):return units*price*(1-friction)*(1-fee)


def simulate(frames,features,times,native,method,fee,friction,delay=1):
    # Equal independent sleeves, no transfers/rebalancing. Initial positions purchased
    # at first open. All marks valued net of liquidation on the same convention.
    books={s:dict(cash=0.,units=1000/(frames[s][times[0]]['open']*(1+friction)*(1+fee)),initial=1000,reduced=False) for s in SYMBOLS}
    curves={s:[] for s in SYMBOLS};orders=[]
    for i,t in enumerate(times):
        for s,b in books.items():
            action='HOLD';why='hold_baseline'
            if method!='HOLD' and i>=delay:
                sigt=times[i-delay];c=features[sigt][s];prior=features.get(sigt-14400,{}).get(s)
                if method=='V10.6_technical':action=native[sigt][s];why='legacy_points'
                else:action,why=alternative(c,prior,features[sigt]['BTC'],sigt+14400)
                target=0 if action=='SELL' else .5 if action=='REDUCE' else 1 if reentry(c,prior) else None
                price=frames[s][t]['open']
                equity=b['cash']+cost_value(b['units'],price,fee,friction)
                exposure=cost_value(b['units'],price,fee,friction)/equity if equity>0 else 0
                # REDUCE is a 50% exposure cap; never repeated halving or buying up to 50%.
                if target is not None and target<exposure-1e-8 and (target==0 or not b['reduced']):
                    sell=b['units'] if target==0 else max(0,b['units']-target*equity/(price*(1-friction)*(1-fee)))
                    b['units']-=sell;b['cash']+=cost_value(sell,price,fee,friction);b['reduced']=True
                    orders.append(dict(symbol=s,time=t,signal_time=sigt+14400,side='SELL' if target==0 else 'REDUCE',price=price,units=sell,reason=why))
                elif target==1 and b['cash']>1e-6:
                    units=b['cash']/(price*(1+friction)*(1+fee));b['units']+=units;b['cash']=0;b['reduced']=False
                    orders.append(dict(symbol=s,time=t,signal_time=sigt+14400,side='BUY',price=price,units=units,reason='common_reentry'))
            curves[s].append(b['cash']+cost_value(b['units'],frames[s][t]['close'],fee,friction))
    rows=[]
    def metrics(values,capital):
        peak=capital;dd=0
        for v in values:peak=max(peak,v);dd=max(dd,(peak-v)/peak*100)
        return dict(net_return_pct=(values[-1]/capital-1)*100,max_drawdown_pct=dd)
    for s in SYMBOLS:
        trades=[o for o in orders if o['symbol']==s];sells=[o for o in trades if o['side']=='SELL'];rebuys=[];mature=0;premature=0;missed=[];captured=0;correction_eligible=0
        for o in sells:
            at=o['time'];future=[k for k in times if at<k<=at+14*86400]
            end=at+14*86400
            if end<=times[-1]:
                mature+=1;last=max(k for k in times if k<=end)
                premature+=frames[s][last]['close']>o['price']
            if at+7*86400<=times[-1]:
                correction_eligible+=1
                captured+=min(frames[s][k]['low'] for k in times if at<k<=at+7*86400)<=o['price']*.9
            nxt=next((a for a in trades if a['side']=='BUY' and a['time']>at),None)
            segment=[k for k in future if not nxt or k<nxt['time']]
            missed.append(max([0]+[(frames[s][k]['high']/o['price']-1)*100 for k in segment]))
            if nxt:
                netratio=o['price']*(1-friction)*(1-fee)/(nxt['price']*(1+friction)*(1+fee))
                rebuys.append(netratio>1)
        rows.append(dict(symbol=s,**metrics(curves[s],1000),orders=len(trades)+2,active_orders=len(trades),full_sells=len(sells),reductions=sum(o['side']=='REDUCE' for o in trades),premature_sells_14d=premature,mature_sells_14d=mature,missed_rally_max_14d_pct=max(missed,default=0),profitable_reentries=sum(rebuys),reentries=len(rebuys),corrections_captured_7d=captured,correction_eligible_sells=correction_eligible))
    portfolio=[sum(curves[s][i] for s in SYMBOLS) for i in range(len(times))]
    rows.append(dict(symbol='PORTFOLIO',**metrics(portfolio,6000),orders=sum(r['orders'] for r in rows),active_orders=len(orders),full_sells=sum(r['full_sells'] for r in rows),reductions=sum(r['reductions'] for r in rows),premature_sells_14d=sum(r['premature_sells_14d'] for r in rows),mature_sells_14d=sum(r['mature_sells_14d'] for r in rows),missed_rally_max_14d_pct=max(r['missed_rally_max_14d_pct'] for r in rows),profitable_reentries=sum(r['profitable_reentries'] for r in rows),reentries=sum(r['reentries'] for r in rows),corrections_captured_7d=sum(r['corrections_captured_7d'] for r in rows),correction_eligible_sells=sum(r['correction_eligible_sells'] for r in rows)))
    return rows,orders


def run(directory,out):
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    frames,coverage=load(directory);(out/'coverage.json').write_text(json.dumps(coverage,indent=2))
    allrows=[];allorders=[]
    for name,start,end in PERIODS:
        print('Preparing',name,flush=True)
        fs=prepare(frames,start,end);startts=int(datetime.fromisoformat(start).replace(tzinfo=timezone.utc).timestamp());times=[t for t in sorted(fs) if t>=startts]
        if not times:raise ValueError('NO_DATA period')
        native=native_signals(fs,times)
        for fee,friction in VARIANTS:
            for delay in (1,2):
                for method in ('V10.6_technical','Alternative','HOLD'):
                    rows,orders=simulate(frames,fs,times,native,method,fee,friction,delay)
                    metadata=dict(period=name,start=start,end_exclusive=end,method=method,fee=fee,friction=friction,execution_delay_bars=delay)
                    allrows.extend(dict(metadata,**r) for r in rows)
                    if fee==.01 and friction==.0025 and delay==1:allorders.extend(dict(metadata,**r) for r in orders)
        print('Finished',name,flush=True)
    (out/'results.json').write_text(json.dumps(allrows,indent=2));(out/'orders.json').write_text(json.dumps(allorders,indent=2))
    with (out/'results.csv').open('w') as f:
        writer=csv.DictWriter(f,fieldnames=list(allrows[0]));writer.writeheader();writer.writerows(allrows)
    return allrows

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--data',required=True);p.add_argument('--out',required=True);a=p.parse_args();run(a.data,a.out)
