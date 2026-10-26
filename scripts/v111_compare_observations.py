"""Audit two archived LIVE shadow observations, not a simulated07:00/20:00 pair.

No network, credentials, orders or production state. Strict slot protocol in
v11.shadow_pair remains unchanged. Evidence is compressed public market data.
"""
import argparse
from datetime import datetime,timezone
import gzip
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
import sys
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from v11.shadow_pair import SYMBOLS,fresh,fingerprint,save_once,digest

MIN_SECONDS=15*60


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_bundle(folder):
    folder=Path(folder).resolve()
    if not folder.is_relative_to((ROOT/'shadow-output').resolve()):raise ValueError('Only isolated shadow inputs allowed')
    summary=json.loads((folder/'summary.json').read_text())
    snap=json.loads((folder/'market_snapshot.json').read_text())
    report=(folder/'morning.txt').read_text()
    at=datetime.fromisoformat(summary['collected_at'])
    if at.tzinfo is None:raise ValueError('Timezone missing')
    if snap.get('synthetic') or snap.get('data_mode')=='synthetic':raise ValueError('Synthetic data refused')
    if summary.get('status')!='CURRENT_MARKET_DATA' or not summary.get('protected_files_unchanged'):
        raise ValueError('Unverified/incomplete shadow observation')
    for flag in ('telegram_enabled','production_state_loaded','real_positions_loaded','state_written','orders_enabled'):
        if summary.get(flag) is not False:raise ValueError('Missing or invalid shadow isolation evidence')
    fresh(snap,at)
    if abs(at.timestamp()-snap['at'])>120:raise ValueError('Collector timestamp mismatch')
    if at>datetime.now(timezone.utc):raise ValueError('Future observation refused')
    actions={}
    for symbol in SYMBOLS:
        coin=snap['coins'][symbol]
        age=coin.get('age_seconds')
        if not isinstance(age,(int,float)) or not math.isfinite(age) or not -60<=age<=900:
            raise ValueError('Quote freshness unproven: '+symbol)
        matches=re.findall(r'^'+symbol+r': (BUY NOW|BUY PULLBACK|WAIT|HOLD|REDUCE|SELL)\b',report,re.M)
        if len(matches)!=1:raise ValueError('Original recommendation ambiguous/missing: '+symbol)
        actions[symbol]=matches[0]
    return dict(snapshot=snap,summary=summary,observed_at=at.isoformat(),actions=actions,
                source_hashes={n:sha(folder/n) for n in ('market_snapshot.json','summary.json','morning.txt')},
                original_report=report,fingerprint=fingerprint(snap))


def latest_closed(coin,tf,observed_at):
    step={'1h':3600,'4h':14400}[tf]
    bars=coin.get('raw',{}).get(tf,[])
    if not bars:return None
    dates=[float(r['timestamp'])/1000+step for r in bars]
    if not all(math.isfinite(x) for x in dates) or max(dates)>observed_at+1:
        raise ValueError('Future or invalid closed candle in evidence')
    return max(dates)


def compare(first,second):
    a=datetime.fromisoformat(first['observed_at']);b=datetime.fromisoformat(second['observed_at'])
    elapsed=(b-a).total_seconds()
    if elapsed<MIN_SECONDS:raise ValueError('Observations must be at least15minutes apart')
    if first['fingerprint']!=fingerprint(first['snapshot']) or second['fingerprint']!=fingerprint(second['snapshot']):
        raise ValueError('Source fingerprint mismatch')
    if first['fingerprint']==second['fingerprint']:raise ValueError('Reused source observations')
    rows=[]
    for s in SYMBOLS:
        old=first['snapshot']['coins'][s];new=second['snapshot']['coins'][s]
        ac=latest_closed(old,'1h',first['snapshot']['at']);bc=latest_closed(new,'1h',second['snapshot']['at'])
        ma=old.get('metadata_at');mb=new.get('metadata_at')
        metadata_advanced=bool(ma and mb and datetime.fromisoformat(mb.replace('Z','+00:00'))>datetime.fromisoformat(ma.replace('Z','+00:00')))
        if not (ac is not None and bc is not None and bc>ac) and not metadata_advanced:
            raise ValueError('No independently advanced provider timestamp: '+s)
        def delta(key):
            x,y=old.get(key),new.get(key)
            return (y/x-1)*100 if isinstance(x,(int,float)) and isinstance(y,(int,float)) and math.isfinite(x) and math.isfinite(y) and x>0 else None
        def trend(coin):
            t=coin.get('frames',{}).get('4h',{})
            return {k:t.get(k) for k in ('ema20','ema50','ema200','higher_structure','support_broken','adx')}
        rows.append(dict(symbol=s,price_first=old['price'],price_second=new['price'],price_pct=delta('price'),
            market_cap_pct=delta('market_cap'),volume24h_pct=delta('volume_24h'),
            action_first=first['actions'][s],action_second=second['actions'][s],
            trend_first=trend(old),trend_second=trend(new),trend_changed=trend(old)!=trend(new),
            source_proof=dict(first_closed_1h=ac,second_closed_1h=bc,metadata_advanced=metadata_advanced,
                              first_metadata_at=ma,second_metadata_at=mb,
                              first_closed_4h=latest_closed(old,'4h',first['snapshot']['at']),
                              second_closed_4h=latest_closed(new,'4h',second['snapshot']['at']))))
    a_global=first['snapshot'].get('global_data',{});b_global=second['snapshot'].get('global_data',{})
    def market_delta(key):
        a,b=a_global.get(key),b_global.get(key)
        return (b/a-1)*100 if isinstance(a,(int,float)) and isinstance(b,(int,float)) and a>0 else None
    dom_a,dom_b=a_global.get('dominance'),b_global.get('dominance')
    market=dict(first=a_global,second=b_global,cap_pct=market_delta('cap'),volume_pct=market_delta('volume'),
                btc_dominance_pp=dom_b-dom_a if dom_a is not None and dom_b is not None else None)
    return dict(test='two_real_observations',verified=True,morning_evening_slot_test=False,
        first_at=first['observed_at'],second_at=second['observed_at'],elapsed_seconds=elapsed,
        first_fingerprint=first['fingerprint'],second_fingerprint=second['fingerprint'],market=market,rows=rows,
        interpretation='Real separate collection times, not synthetic07/20. Marketcap is not net capital flow; volume compares rolling24h windows. Same4h candle may legitimately imply unchanged4h trend/actions. No forecast accuracy or trading profitability claim.')


def markdown(result):
    tz=ZoneInfo('Europe/Bratislava')
    first=datetime.fromisoformat(result['first_at']).astimezone(tz)
    second=datetime.fromisoformat(result['second_at']).astimezone(tz)
    lines=['# Skutočný SHADOW test dvoch pozorovaní',
        f'Prvý zber: {first:%d.%m.%Y %H:%M:%S} Bratislava. Druhý: {second:%d.%m.%Y %H:%M:%S} Bratislava.',
        f"Odstup {result['elapsed_seconds']/60:.2f} min. Nejde o celý07:00→20:00 test.",
        '', '| Minca | Cena | Kapitalizácia | Objem24h | Odporúčanie | Trend4h zmenený |',
        '|---|---:|---:|---:|---|---|']
    def fmt(x):return 'N/A' if x is None else f'{x:+.2f}%'
    for r in result['rows']:
        lines.append('| '+' | '.join([r['symbol'],fmt(r['price_pct']),fmt(r['market_cap_pct']),fmt(r['volume24h_pct']),
            r['action_first']+' → '+r['action_second'],'áno' if r['trend_changed'] else 'nie'])+' |')
    market=result.get('market',{})
    lines+=['',f"Celý kryptotrh: kapitalizácia {fmt(market.get('cap_pct'))}; objem24h {fmt(market.get('volume_pct'))}; BTC dominancia rozdiel {market.get('btc_dominance_pp') if market.get('btc_dominance_pp') is not None else 'N/A'} p.b.",'',result['interpretation'],'','Pôvodné odporúčania sú extrahované z uložených pôvodných reportov; neboli spätne prepísané.']
    return '\n\n'.join(lines[:3])+'\n\n'+'\n'.join(lines[3:])+'\n'


def run(first_dir,second_dir,out):
    out=Path(out).resolve()
    if not out.is_relative_to((ROOT/'shadow-output').resolve()):raise ValueError('Only isolated shadow outputs allowed')
    out.mkdir(parents=True,exist_ok=True)
    first=load_bundle(first_dir);second=load_bundle(second_dir)
    # Freeze the first BEFORE comparison; no overwrite on failed/repeated attempts.
    save_once(out/'first_checkpoint.json',dict(first,sha256=digest(first)))
    result=compare(first,second)
    rules=ROOT/'v11/strategy.py'
    prior=subprocess.check_output(['git','show','993e4f6:v11/strategy.py'],cwd=ROOT)
    if hashlib.sha256(prior).hexdigest()!=sha(rules):raise ValueError('Decision rules changed since original capture')
    result['unchanged_strategy_sha256']=sha(rules)
    result['source_hashes']={'first':first['source_hashes'],'second':second['source_hashes']}
    save_once(out/'second_checkpoint.json',dict(second,sha256=digest(second)))
    save_once(out/'comparison.json',result)
    (out/'REPORT.md').write_text(markdown(result))
    for name,value in [('first',first),('second',second)]:
        raw=json.dumps(value,ensure_ascii=False,sort_keys=True,allow_nan=False).encode()
        with (out/(name+'.json.gz')).open('xb') as target:target.write(gzip.compress(raw,mtime=0))
    print(markdown(result))
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--first',required=True);p.add_argument('--second',required=True);p.add_argument('--output',required=True)
    a=p.parse_args();run(a.first,a.second,a.output)
