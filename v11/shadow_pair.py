"""Immutable public-market morning checkpoint; no portfolio or production state."""
from datetime import datetime,timezone,timedelta
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile
from zoneinfo import ZoneInfo

BL=ZoneInfo('Europe/Bratislava')
SYMBOLS=('AAVE','TAO','FET','SOL','ONDO','RENDER')
SCHEMA='v111-shadow-morning-v1'


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def fingerprint(snapshot):
    # Source observations, excluding collector time and derived quote age.
    return digest({s:{k:d.get(k) for k in ('price','change_24h','metadata_at','market_cap','volume_24h','raw')}
                   for s,d in snapshot['coins'].items() if s in ('BTC','ETH',*SYMBOLS)})


def slot(now,phase):
    if now.tzinfo is None:raise ValueError('Timezone required')
    local=now.astimezone(BL);minutes=local.hour*60+local.minute
    start=7*60 if phase=='morning' else 20*60
    if not start<=minutes<=start+90:raise ValueError('Outside real '+phase+' observation window (Bratislava)')
    return local.date().isoformat()


def fresh(snapshot,now):
    age=now.timestamp()-snapshot['at']
    if not 0<=age<=900:raise ValueError('Snapshot collection timestamp stale or future')
    for symbol in SYMBOLS:
        coin=snapshot['coins'].get(symbol,{})
        if coin.get('stale',True) or not coin.get('price') or not coin.get('frames',{}).get('4h',{}).get('ema200'):
            raise ValueError('Incomplete current market data: '+symbol)


def checkpoint(snapshot,evaluations,now):
    day=slot(now,'morning');fresh(snapshot,now)
    if datetime.fromtimestamp(snapshot['at'],BL).date().isoformat()!=day:raise ValueError('Wrong snapshot date')
    result=dict(schema=SCHEMA,phase='morning',date=day,observed_at=now.astimezone(timezone.utc).isoformat(),
                snapshot=snapshot,evaluations=evaluations,fingerprint=fingerprint(snapshot),
                positions='UNKNOWN; no real portfolio loaded',github_commit=os.getenv('GITHUB_SHA'),
                github_branch=os.getenv('GITHUB_REF_NAME'))
    result['sha256']=digest(result)
    return result


def save_once(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with path.with_suffix('.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if path.exists():raise ValueError('Morning checkpoint already exists; never overwrite')
        with tempfile.NamedTemporaryFile(mode='w',dir=path.parent,delete=False) as f:
            json.dump(value,f,ensure_ascii=False,indent=2,allow_nan=False);f.write('\n');f.flush();os.fsync(f.fileno());tmp=f.name
        os.replace(tmp,path)


def compare(morning,snapshot,evaluations,now):
    day=slot(now,'evening');fresh(snapshot,now)
    data={k:v for k,v in morning.items() if k!='sha256'}
    if (morning.get('schema')!=SCHEMA or morning.get('phase')!='morning') or digest(data)!=morning.get('sha256'):raise ValueError('Invalid checkpoint schema/checksum')
    if os.getenv('GITHUB_SHA') and morning.get('github_commit')!=os.getenv('GITHUB_SHA'):raise ValueError('Morning belongs to another commit')
    if os.getenv('GITHUB_REF_NAME') and morning.get('github_branch')!=os.getenv('GITHUB_REF_NAME'):raise ValueError('Morning belongs to another branch')
    start=datetime.fromisoformat(morning['observed_at'])
    slot(start,'morning');fresh(morning['snapshot'],start)
    if morning['date']!=day or start.astimezone(BL).date().isoformat()!=day:raise ValueError('Not same Bratislava day')
    if not timedelta(hours=8)<=now-start<=timedelta(hours=16):raise ValueError('Not independent morning/evening observations')
    if snapshot['at']-morning['snapshot']['at']<8*3600:raise ValueError('Snapshot timestamps too close')
    if morning['fingerprint']!=fingerprint(morning['snapshot']):raise ValueError('Invalid morning source fingerprint')
    if fingerprint(snapshot)==morning['fingerprint']:raise ValueError('Reused market observations')
    rows=[]
    for symbol in SYMBOLS:
        old=morning['snapshot']['coins'][symbol];new=snapshot['coins'][symbol]
        def delta(key):
            a,b=old.get(key),new.get(key)
            return (b/a-1)*100 if isinstance(a,(int,float)) and a>0 and isinstance(b,(int,float)) and math.isfinite(a) and math.isfinite(b) and not old.get('stale') and not new.get('stale') else None
        def trend(d):
            t=d.get('frames',{}).get('4h',{})
            return dict(ema20=t.get('ema20'),ema50=t.get('ema50'),higher_structure=t.get('higher_structure'),support_broken=t.get('support_broken'),adx=t.get('adx'))
        rows.append(dict(symbol=symbol,price_pct=delta('price'),market_cap_pct=delta('market_cap'),volume24h_pct=delta('volume_24h'),
            morning_action=morning['evaluations'][symbol]['action'],evening_action=evaluations[symbol]['action'],
            morning_trend=trend(old),evening_trend=trend(new),morning_price=old.get('price'),evening_price=new.get('price')))
    return dict(verified_temporal_pair=True,morning_at=morning['observed_at'],evening_at=now.isoformat(),
                hours=(now-start).total_seconds()/3600,rows=rows,
                note='Observed changes; volume compares rolling24h windows, marketcap is not net flow. Recommendations are not executed trades. Forecasts remain pending until horizon ends.')


def report(result):
    lines=['SKUTOČNÉ SHADOW POROVNANIE',f"Ráno {result['morning_at']}; večer {result['evening_at']}; odstup {result['hours']:.2f}h."]
    def fmt(x):return 'N/A' if x is None else f'{x:+.2f}%'
    for r in result['rows']:
        lines.append(f"{r['symbol']}: cena {fmt(r['price_pct'])}; kapitalizácia {fmt(r['market_cap_pct'])}; objem24h {fmt(r['volume24h_pct'])}; {r['morning_action']} → {r['evening_action']}.")
        lines.append(f"Trend ráno {r['morning_trend']}; večer {r['evening_trend']}.")
    return '\n'.join(lines+[result['note']])
