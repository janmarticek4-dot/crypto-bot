"""Causal analytical evidence groups, NOT an approved trading strategy.
Price structure/EMA are one group. Volume is candle-body activity, not taker flow.
No fitting, broker, private inventory, network or mutable global state.
"""
import copy,math
from datetime import datetime,timedelta,timezone
from .indicators import ema
from .fundamentals import timestamp
from .state_policy import require_public_data

COINS=('SOL','TAO','FET','AAVE','ONDO','RENDER')
LABELS={'CORRECTION':'KOREKCIA','RECOVERY_FAILED':'ODRAZ ZLYHÁVA','RECOVERY_ATTEMPT':'POKUS O OBRAT','REVERSAL_CONFIRMING':'OBRAT SA POTVRDZUJE','UPTREND_CONFIRMED':'RASTOVÝ TREND POTVRDENÝ'}
VERSION='reversal-evidence-v1'
STEPS={'4h':14400000,'1d':86400000}

def finite(x):return type(x) in (float,int) and math.isfinite(x)
def change(a,b):return (a/b-1)*100 if finite(a) and finite(b) and b>0 else None

def closed(rows,tf,now_ms):
    step=STEPS[tf]
    if not isinstance(rows,list):raise ValueError('MISSING_CANDLES')
    selected=[]
    for row in rows:
        if not isinstance(row,dict) or not all(finite(row.get(k)) for k in ('timestamp','open','high','low','close','volume')):raise ValueError('INVALID_CANDLE')
        if row['timestamp']+step>now_ms:continue
        if row['timestamp']%step or min(row[k] for k in ('open','high','low','close'))<=0 or row['volume']<0 or not row['low']<=min(row['open'],row['close'])<=max(row['open'],row['close'])<=row['high']:raise ValueError('INVALID_CANDLE')
        selected.append(row)
    minimum=220 if tf=='4h' else 55
    if len(selected)<minimum:raise ValueError('INSUFFICIENT_CLOSED_HISTORY')
    if any(b['timestamp']-a['timestamp']!=step for a,b in zip(selected,selected[1:])):raise ValueError('GAPPED_OR_DUPLICATE_HISTORY')
    if not 0<=now_ms-selected[-1]['timestamp']-step<=step:raise ValueError('STALE_CLOSED_HISTORY')
    return selected

def structure(rows):
    bounds=[(min(r['low'] for r in rows[i:i+4]),max(r['high'] for r in rows[i:i+4])) for i in (len(rows)-12,len(rows)-8,len(rows)-4)]
    return all(b[0]>a[0] and b[1]>a[1] for a,b in zip(bounds,bounds[1:]))

def frame(rows):
    cs=[r['close'] for r in rows];last=cs[-1]
    e20,e50,e200=(ema(cs,p) for p in (20,50,200))
    higher=structure(rows)
    sustained=all(cs[-n]>ema(cs[:-n+1] if n>1 else cs,20) for n in (1,2))
    bull=bool(higher and sustained and last>e50 and e20>e50)
    resistance=max(r['high'] for r in rows[-22:-2])
    support=min(r['low'] for r in rows[-21:-1])
    two_above=all(c>resistance for c in cs[-2:])
    recent=rows[-3:];prior=rows[-23:-3]
    usual=sum(r['volume'] for r in prior)/len(prior)
    # This is a signed candle-volume proxy, never measured net order flow.
    up=sum(r['volume'] for r in recent if r['close']>r['open'])
    down=sum(r['volume'] for r in recent if r['close']<r['open'])
    volume_ratio=sum(r['volume'] for r in recent)/3/usual if usual>0 else None
    buy_volume=volume_ratio is not None and volume_ratio>=1.1 and up>down and cs[-1]>cs[-4]
    sell_volume=volume_ratio is not None and volume_ratio>=1.1 and down>up and cs[-1]<cs[-4]
    breakout=two_above and buy_volume
    # The resistance is fixed before both confirmation candles, never computed
    # with the candles that are being tested against it.
    retest=bool(rows[-2]['close']>resistance and rows[-1]['low']<=resistance*1.01 and rows[-1]['close']>=resistance and buy_volume)
    return dict(bull=bull,higher_structure=higher,sustained=sustained,ema20=e20,ema50=e50,ema200=e200,
        close=last,source_close=rows[-1]['timestamp'],support=support,resistance=resistance,
        rebound=last>cs[-4],breakout=breakout,retest=retest,buy_volume=buy_volume,sell_volume=sell_volume,
        volume_ratio=volume_ratio,volume_scope='signed candle-body activity proxy; not taker flow or net capital flow')

def profile(coin,now_ms):
    if coin.get('stale',True) or not finite(coin.get('price')) or coin['price']<=0:return dict(status='INSUFFICIENT',reason='STALE_OR_MISSING_QUOTE')
    try:
        four=frame(closed(coin.get('raw',{}).get('4h'),'4h',now_ms))
        daily=frame(closed(coin.get('raw',{}).get('1d'),'1d',now_ms))
        four['source_close']+=STEPS['4h'];daily['source_close']+=STEPS['1d']
    except (ValueError,TypeError,KeyError) as exc:return dict(status='INSUFFICIENT',reason=str(exc))
    bull=four['bull'] and daily['bull']
    setup='BUY CONFIRMED' if four['breakout'] and daily['bull'] else 'BUY PULLBACK' if four['retest'] and daily['bull'] else None
    state='UPTREND_CONFIRMED' if bull and four['buy_volume'] else 'REVERSAL_CONFIRMING' if four['bull'] and four['buy_volume'] else 'RECOVERY_ATTEMPT' if four['rebound'] else 'CORRECTION'
    return dict(status='AVAILABLE',state=state,four=four,daily=daily,technical_candidate=setup,
        entry_level=four['resistance'],support=four['support'] if four['support']<coin['price'] else None,
        invalidation=four['support'] if four['support']<coin['price'] else None,
        confirmation='two closed 4h candles above fixed prior resistance plus directional volume and daily structure',
        approved_action=None)

def legacy_reference(record,kind):
    if record.get('status')!='sent':return None
    q=record.get('quotes',{});ctx=q.get('_context',{})
    if not timestamp(ctx.get('at')) or not isinstance(ctx.get('fingerprint'),str):return None
    return dict(schema='public-analysis-v112',at=ctx['at'],fingerprint=ctx['fingerprint'],kind=kind,
        coins={s:copy.deepcopy(q[s]) for s in COINS if isinstance(q.get(s),dict)},global_data={},metrics={},economics={},event_ids=[],legacy_partial=True)

def references(journal,now):
    rows=list(journal.get('analysis_history_v112',[]))
    latest=journal.get('last_analysis_v112')
    if isinstance(latest,dict):rows.append(latest)
    for key,record in journal.get('slots',{}).items():
        kind=key.rsplit('-',1)[-1]
        if kind in ('morning','evening'):
            item=legacy_reference(record,kind)
            if item:rows.append(item)
    valid=[];seen=set()
    for row in rows:
        if not isinstance(row,dict) or row.get('schema')!='public-analysis-v112':continue
        at=timestamp(row.get('at'));fp=row.get('fingerprint')
        if not at or not timedelta(0)<now-at<=timedelta(days=7) or not isinstance(fp,str) or len(fp)!=64:continue
        key=(row['at'],fp)
        if key in seen:continue
        seen.add(key);valid.append(row)
    valid.sort(key=lambda r:(timestamp(r['at']).timestamp(),not bool(r.get('legacy_partial'))))
    return {kind:next((r for r in reversed(valid) if kind=='latest' or r.get('kind')==kind),None) for kind in ('latest','morning','evening')}

def remember(journal,observation,kind):
    # Only called after sent; never copy portfolio or modify bot_state.json.
    value=copy.deepcopy(observation);value['kind']=kind
    require_public_data(value)
    rows=[r for r in journal.get('analysis_history_v112',[]) if r.get('at')!=value.get('at')]
    rows.append(value);rows.sort(key=lambda r:r['at'])
    scheduled=[r for r in rows if r.get('kind') in ('morning','evening')][-14:]
    other=[r for r in rows if r.get('kind') not in ('morning','evening')][-16:]
    journal['analysis_history_v112']=sorted(scheduled+other,key=lambda r:r['at'])[-30:]

def comparisons(refs,current,profiles):
    out={}
    for name,old in refs.items():
        if not old or old.get('fingerprint')==current.get('fingerprint'):
            out[name]=dict(status='N/A',reason='MISSING_OR_IDENTICAL_REFERENCE');continue
        old_coins=old.get('coins',{});g=current.get('global_data',{});og=old.get('global_data',{})
        coins={s:dict(price_pct=change(current.get('coins',{}).get(s,{}).get('price'),old_coins.get(s,{}).get('price')),
            trend_before=old.get('reversal',{}).get('coins',{}).get(s),trend_now=profiles.get(s,{}).get('state')) for s in COINS}
        out[name]=dict(status='COMPARED',at=old['at'],cap_pct=change(g.get('cap'),og.get('cap')),
            rolling_volume_pct=change(g.get('volume'),og.get('volume')),coins=coins,
            previous_state=old.get('reversal',{}).get('state'),legacy_partial=bool(old.get('legacy_partial')))
    return out

def analyze(snapshot,fund,now,refs,current):
    ms=int(now.timestamp()*1000);age=now.timestamp()-snapshot.get('at',0)
    profiles={s:profile(snapshot.get('coins',{}).get(s,{}),ms) for s in ('BTC',*COINS)}
    compared=comparisons(refs,current,profiles);prior=compared.get('latest',{})
    valid=[s for s in COINS if profiles[s]['status']=='AVAILABLE']
    btc=profiles['BTC'];btc_ok=btc['status']=='AVAILABLE'
    cap_now=snapshot.get('global_data',{});cap_at=cap_now.get('at')
    cap_valid=finite(cap_now.get('cap')) and cap_now['cap']>0 and finite(cap_at) and 0<=now.timestamp()-cap_at<=900
    cap_delta=prior.get('cap_pct') if prior.get('status')=='COMPARED' and cap_valid else None
    breadth_up=sum(snapshot['coins'][s].get('change_24h',0)>0 for s in valid if finite(snapshot['coins'][s].get('change_24h')))
    trend_up=sum(profiles[s]['four']['bull'] for s in valid)
    stronger=sum(snapshot['coins'][s].get('relative_strength_btc_7d',0)>0 for s in valid if finite(snapshot['coins'][s].get('relative_strength_btc_7d')))
    buys=sum(profiles[s]['four']['buy_volume'] for s in valid)
    groups=dict(btc_structure=bool(btc_ok and btc['four']['bull'] and btc['daily']['bull']),
        capitalization=cap_delta is not None and cap_delta>=.1,
        directional_volume=bool(btc_ok and btc['four']['buy_volume'] and buys>=3),
        breadth=len(valid)==6 and trend_up>=4)
    previous=(refs.get('latest') or {}).get('reversal',{})
    new_closed=btc_ok and finite(previous.get('source_close')) and btc['four']['source_close']>previous['source_close']
    stable=bool(new_closed and previous.get('state') in ('REVERSAL_CONFIRMING','UPTREND_CONFIRMED') and all(previous.get('groups',{}).get(k) for k in groups))
    releases=[]
    for e in fund.get('event_lifecycle',{}).get('releases',[]):
        if not isinstance(e,dict):continue
        at=timestamp(e.get('published_at'))
        if e.get('status') in ('RELEASED','REACTION') and at and timedelta(0)<=now-at<=timedelta(hours=72):
            releases.append(dict(at=at.isoformat(),url=e.get('url'),status=e['status'],directional_impact='UNVERIFIED_WITHOUT_COMPARABLE_EXPECTATION_AND_REACTION'))
    sufficient=btc_ok and len(valid)==6 and 0<=age<=900
    moves=[c.get('price_pct') for c in prior.get('coins',{}).values() if finite(c.get('price_pct'))]
    old_btc=(refs.get('latest') or {}).get('coins',{}).get('BTC',{}).get('price')
    btc_change=change(snapshot['coins'].get('BTC',{}).get('price'),old_btc)
    falling=sum(v<0 for v in moves)
    deterioration=bool(cap_valid and finite(cap_delta) and cap_delta<=-.1 and finite(btc_change) and btc_change<0 and len(moves)==6 and falling>=4)
    pressure_known=btc_ok and finite(btc['four']['volume_ratio'])
    weak_buying=pressure_known and not btc['four']['buy_volume'] and buys<=2
    selling=bool(btc_ok and (btc['four']['sell_volume'] or sum(profiles[s]['four']['sell_volume'] for s in valid)>=3))
    prior_at=timestamp((refs.get('latest') or {}).get('at'))
    separated=bool(prior_at and timedelta(hours=1)<=now-prior_at<=timedelta(hours=36))
    closed_level_lost=bool(btc_ok and not btc['four']['bull'] and snapshot['coins']['BTC']['price']<min(btc['four']['close'],btc['four']['ema20']) and trend_up<=2)
    failed=bool(deterioration and separated and previous.get('state') in ('RECOVERY_ATTEMPT','REVERSAL_CONFIRMING','RECOVERY_FAILED') and
        not groups['btc_structure'] and (selling or weak_buying or closed_level_lost))
    # A positive trailing 12h candle change cannot override newer broad losses.
    recovery=bool(btc_ok and btc['four']['rebound'] and not deterioration and
        (groups['capitalization'] or prior.get('status')=='COMPARED' and sum(v>0 for v in moves)>=4 and finite(btc_change) and btc_change>0 and cap_valid and finite(cap_delta) and cap_delta>=0))
    state=None
    if sufficient:
        if failed:state='RECOVERY_FAILED'
        elif deterioration:state='CORRECTION'
        elif all(groups.values()) and stable:state='UPTREND_CONFIRMED'
        elif btc['four']['bull'] and groups['capitalization'] and groups['directional_volume'] and groups['breadth']:state='REVERSAL_CONFIRMING'
        elif recovery:state='RECOVERY_ATTEMPT'
        elif not btc['four']['rebound'] and (finite(cap_delta) and cap_delta<0 or finite(cap_now.get('change')) and cap_now['change']<0):state='CORRECTION'
    failure_evidence=dict(broad_deterioration=deterioration,btc_since_reference_pct=btc_change,cap_since_reference_pct=cap_delta,
        alts_lower_since_reference=falling,known_alt_comparisons=len(moves),selling_proxy=selling,weak_buying_proxy=weak_buying,closed_level_lost=closed_level_lost,
        prior_recovery=previous.get('state'),separated_observations=separated)
    missing=[name for name,value in groups.items() if not value]
    if not stable:missing.append('multi_analysis_stability')
    old_state=previous.get('state');order=['CORRECTION','RECOVERY_FAILED','RECOVERY_ATTEMPT','REVERSAL_CONFIRMING','UPTREND_CONFIRMED']
    proximity='bližšie k technickému potvrdeniu' if state in order and old_state in order and order.index(state)>order.index(old_state) else 'ďalej od technického potvrdenia' if state in order and old_state in order and order.index(state)<order.index(old_state) else 'zmenu vzdialenosti nemožno potvrdiť'
    out=dict(version=VERSION,state=state,failure_evidence=failure_evidence,quality='AVAILABLE' if sufficient else 'INSUFFICIENT',groups=groups,missing=missing,stable=stable,
        source_close=btc['four']['source_close'] if btc_ok else None,coins=profiles,comparisons=compared,
        breadth=dict(covered=len(valid),rising_24h=breadth_up,change_24h_covered=sum(finite(snapshot['coins'][s].get('change_24h')) for s in valid),confirmed_4h=trend_up,stronger_than_btc_7d=stronger,relative_strength_covered=sum(finite(snapshot['coins'][s].get('relative_strength_btc_7d')) for s in valid)),
        proximity=proximity,macro=dict(verified_releases=releases,impact='not a cause or a trade trigger'),
        activation='ANALYTICAL_ONLY_NO_NEW_BUY_SELL',parameters='fixed explanatory heuristics, not return-optimized or independently validated')
    require_public_data(out);return out

def attach(model,snapshot,fund,now,journal):
    refs=references(journal,now)
    try:
        result=analyze(snapshot,fund,now,refs,model['observation'])
    except (KeyError,TypeError,ValueError,OverflowError) as exc:
        result=dict(version=VERSION,state=None,quality='INSUFFICIENT',error=type(exc).__name__,activation='ANALYTICAL_ONLY_NO_NEW_BUY_SELL')
    model['trend_reversal']=result
    model['observation']['reversal']=dict(state=result.get('state'),groups=result.get('groups',{}),source_close=result.get('source_close'),
        coins={s:p.get('state') for s,p in result.get('coins',{}).items() if s in COINS})
    return result
