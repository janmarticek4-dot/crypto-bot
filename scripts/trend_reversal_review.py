"""Causal historical classifier diagnostics, not strategy optimization/backtesting.
Public OHLCV only, no state write or Telegram. Future bars are outcome labels only.
"""
import sys,json,math
from pathlib import Path
from datetime import datetime,timezone
from collections import Counter
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from v11 import trend_reversal as tr
from scripts.prediction_research import download_history
from scripts.v111_shadow import ShadowAPI

OUT=Path('shadow-output/reversal-review')

def daily(rows):
    buckets={}
    for row in rows:buckets.setdefault(row['timestamp']//86400000,[]).append(row)
    out=[]
    for day,items in sorted(buckets.items()):
        if len(items)!=6 or items[0]['timestamp']!=day*86400000 or any(b['timestamp']-a['timestamp']!=14400000 for a,b in zip(items,items[1:])):continue
        out.append(dict(timestamp=day*86400000,open=items[0]['open'],high=max(r['high'] for r in items),low=min(r['low'] for r in items),close=items[-1]['close'],volume=sum(r['volume'] for r in items)))
    return out

def coin(rows):
    return dict(price=rows[-1]['close'],stale=False,raw={'4h':rows[-300:],'1d':daily(rows)[-300:]})

def evaluate(rows):
    by_year={};examples={};prefix_proofs=[]
    for i in range(360,len(rows)-18,6):
        at=rows[i]['timestamp']+tr.STEPS['4h']
        # At most 1800 past 4h candles; no future rows reach feature generation.
        prefix=rows[max(0,i-1799):i+1]
        p=tr.profile(coin(prefix),at);year=datetime.fromtimestamp(at/1000,timezone.utc).year
        counts=by_year.setdefault(str(year),Counter());counts['observations']+=1
        if p['status']!='AVAILABLE':counts['insufficient']+=1;continue
        state=p['state'];counts[state]+=1
        f24=(rows[i+6]['close']/rows[i]['close']-1)*100
        f72=(rows[i+18]['close']/rows[i]['close']-1)*100
        high=(max(r['high'] for r in rows[i+1:i+19])/rows[i]['close']-1)*100
        low=(min(r['low'] for r in rows[i+1:i+19])/rows[i]['close']-1)*100
        category='false_rebound' if state=='RECOVERY_ATTEMPT' and f24<0 else 'confirmed_followthrough' if state=='UPTREND_CONFIRMED' and f72>0 else 'continuing_decline' if state=='CORRECTION' and f72<0 else None
        if category:
            counts[category]+=1
            examples.setdefault(category,dict(at=datetime.fromtimestamp(at/1000,timezone.utc).isoformat(),state=state,price=rows[i]['close'],next_24h_pct=f24,next_72h_pct=f72,max_72h_pct=high,min_72h_pct=low))
        if high>=10 and state in ('CORRECTION','RECOVERY_ATTEMPT'):counts['large_rise_not_confirmed_at_origin']+=1
        if low<=-10:counts['future_deep_drop']+=1
        if len(prefix_proofs)<3:
            # Appended, not-yet-closed bars are ignored at the SAME origin clock.
            other=coin(prefix)
            other['raw']['4h']+=rows[i+1:i+4]
            assert tr.profile(other,at)==p,'Future candle changed origin classification'
            prefix_proofs.append(at)
    return dict(years={k:dict(v) for k,v in by_year.items()},examples=examples,prefix_invariance_checks=len(prefix_proofs))

def run():
    OUT.mkdir(parents=True,exist_ok=True);results={};api=ShadowAPI();cutoff=int(datetime.now(timezone.utc).timestamp()*1000)
    for symbol in tr.COINS:
        path=Path('shadow-output/prediction-inputs')/(symbol+'.json')
        try:
            rows=json.loads(path.read_text()) if path.exists() else download_history(api,symbol,cutoff)
            tr.closed(rows,'4h',rows[-1]['timestamp']+tr.STEPS['4h'])
            results[symbol]=dict(status='DIAGNOSTIC_ONLY',source='Binance public USDT 4h OHLCV; UTC daily bars resampled from six closed 4h bars',
                first=datetime.fromtimestamp(rows[0]['timestamp']/1000,timezone.utc).isoformat(),last=datetime.fromtimestamp((rows[-1]['timestamp']+tr.STEPS['4h'])/1000,timezone.utc).isoformat(),bars=len(rows),input_digest=__import__('hashlib').sha256(json.dumps(rows,sort_keys=True).encode()).hexdigest(),**evaluate(rows))
        except (OSError,ValueError,KeyError,TypeError) as exc:results[symbol]=dict(status='NO_DATA',error=type(exc).__name__)
    report=dict(version=tr.VERSION,parameters_optimized=False,new_trading_rules_activated=False,independent_validation=False,
        historical_global_cap='NO_DATA',historical_macro_vintages='NO_DATA',scope='Asset technical classifier only. Full multi-market detector cannot be historically validated without point-in-time cap/analysis/macro observations. 2024–2026 already examined; overlapping outcomes are not independent. No strategy returns or predictive advantage claimed.',results=results)
    from v11.state_policy import require_public_data
    require_public_data(report);(OUT/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    lines=['# Reversal classifier diagnostics — not a trading backtest',report['scope'],'', '| Coin | Year | Samples | Correction | Recovery | Confirming | Uptrend | False rebounds (24h<0) |','|---|---|---:|---:|---:|---:|---:|---:|']
    for s,result in results.items():
        for year,c in result.get('years',{}).items():lines.append('| '+' | '.join(map(str,[s,year,c.get('observations',0),*(c.get(k,0) for k in tr.LABELS),c.get('false_rebound',0)]))+' |')
        if result['status']=='NO_DATA':lines.append('| '+s+' | NO_DATA | | | | | | |')
    (OUT/'REPORT.md').write_text('\n'.join(lines))
    print('::notice title=Reversal historical diagnostics::'+json.dumps(dict(status={s:r['status'] for s,r in results.items()},independent_validation=False,new_trading_rules_activated=False)))
    return report

if __name__=='__main__':run()
