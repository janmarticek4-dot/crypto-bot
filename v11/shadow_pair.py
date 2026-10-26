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


def checkpoint(snapshot,evaluations,now,fundamentals=None):
    day=slot(now,'morning');fresh(snapshot,now)
    if datetime.fromtimestamp(snapshot['at'],BL).date().isoformat()!=day:raise ValueError('Wrong snapshot date')
    result=dict(schema=SCHEMA,phase='morning',date=day,observed_at=now.astimezone(timezone.utc).isoformat(),
                snapshot=snapshot,evaluations=evaluations,fingerprint=fingerprint(snapshot),
                positions='UNKNOWN; no real portfolio loaded',github_commit=os.getenv('SHADOW_SOURCE_SHA') or os.getenv('GITHUB_SHA'),
                github_branch=os.getenv('SHADOW_SOURCE_BRANCH') or os.getenv('GITHUB_REF_NAME'))
    if fundamentals is not None:result['fundamentals']=fundamentals
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


def compare(morning,snapshot,evaluations,now,fundamentals=None):
    day=slot(now,'evening');fresh(snapshot,now)
    data={k:v for k,v in morning.items() if k!='sha256'}
    if (morning.get('schema')!=SCHEMA or morning.get('phase')!='morning') or digest(data)!=morning.get('sha256'):raise ValueError('Invalid checkpoint schema/checksum')
    source_sha=os.getenv('SHADOW_SOURCE_SHA') or os.getenv('GITHUB_SHA')
    source_branch=os.getenv('SHADOW_SOURCE_BRANCH') or os.getenv('GITHUB_REF_NAME')
    if source_sha and morning.get('github_commit')!=source_sha:raise ValueError('Morning belongs to another commit')
    if source_branch and morning.get('github_branch')!=source_branch:raise ValueError('Morning belongs to another branch')
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
                global_changes={k:((snapshot.get('global_data',{}).get(k)/morning['snapshot'].get('global_data',{})[k]-1)*100 if snapshot.get('global_data',{}).get(k) is not None and morning['snapshot'].get('global_data',{}).get(k) else None) for k in ('cap','volume')},
                fundamentals=compare_fundamentals(morning.get('fundamentals'),fundamentals,start,now),
                note='Observed changes; volume compares rolling24h windows, marketcap is not net flow. Recommendations are not executed trades. Forecasts remain pending until horizon ends.')


def report(result):
    lines=['SKUTOČNÉ SHADOW POROVNANIE',f"Ráno {result['morning_at']}; večer {result['evening_at']}; odstup {result['hours']:.2f}h."]
    def fmt(x):return 'N/A' if x is None else f'{x:+.2f}%'
    for r in result['rows']:
        lines.append(f"{r['symbol']}: cena {fmt(r['price_pct'])}; kapitalizácia {fmt(r['market_cap_pct'])}; objem24h {fmt(r['volume24h_pct'])}; {r['morning_action']} → {r['evening_action']}.")
        lines.append(f"Trend ráno {r['morning_trend']}; večer {r['evening_trend']}.")
    f=result.get('fundamentals',{})
    lines.append('Fundamenty: '+('N/A — '+f.get('reason','chýbajúce fundamentálne pozorovanie') if f.get('status')!='COMPARED' else f"nové publikované udalosti {len(f['new'])}, nezmenené skupiny {f['unchanged']}, aktualizované publikácie {len(f['updated'])}. Nezobrazená udalosť nie je vyriešená udalosť."))
    for e in f.get('new',[]):lines.append('Nová publikácia: '+e['title']+'; '+e['url'])
    for m in f.get('metrics',[]):lines.append(m['metric']+': '+fmt(m['change_pct'])+'; '+m['period_status']+'; obdobia '+str(m['morning'].get('period'))+' → '+str(m['evening'].get('period')))
    return '\n'.join(lines+[result['note']])


def compare_fundamentals(old,new,start,now):
    if old is None or new is None:return dict(status='N/A',reason='Missing fundamental snapshot')
    from .fundamental_analysis import analyze
    from .event_groups import same_event
    a=analyze(old,start);b=analyze(new,now)
    if not b['source_ok'] and not any(b['coverage'].values()):return dict(status='N/A',reason='No available current fundamental coverage')
    changed=[];added=[];unchanged=0;matched=set()
    for current in b['evidence']:
        match=next((e for e in a['evidence'] if same_event(e,current)),None)
        if match is None:added.append(current)
        else:
            matched.add(match['id'])
            if set(current.get('member_ids',[]))!=set(match.get('member_ids',[])):changed.append(current)
            else:unchanged+=1
    return dict(status='COMPARED',new=added,updated=changed,unchanged=unchanged,
                not_observed_now=[e for e in a['evidence'] if e['id'] not in matched],
                morning_coverage=a['coverage'],evening_coverage=b['coverage'],metrics=metric_changes(old,new),
                note='Missing coverage or an expired article is not evidence that a risk ended.')


def metric_changes(old,new):
    def flatten(f):
        rows={s+'/TVL':dict(value=m.get('value'),period=m.get('at')) for s,m in f.get('metrics',{}).items()}
        for symbol,values in f.get('project_economics',{}).get('observations',{}).items():
            rows.update({symbol+'/'+kind:dict(value=m.get('value'),period=m.get('period')) for kind,m in values.items()})
        return rows
    a,b=flatten(old),flatten(new);rows=[]
    for key in sorted(set(a)|set(b)):
        before,after=a.get(key,{}),b.get(key,{})
        x,y=before.get('value'),after.get('value')
        change=(y/x-1)*100 if type(x) in (float,int) and type(y) in (float,int) and math.isfinite(x) and math.isfinite(y) and x>0 else None
        same=before.get('period') is not None and before.get('period')==after.get('period')
        rows.append(dict(metric=key,morning=before,evening=after,change_pct=change,
                         period_status='SAME_PERIOD_UNCHANGED' if same and x==y else 'SAME_PERIOD_REVISION' if same else 'DIFFERENT_PERIODS' if change is not None else 'N/A'))
    return rows
