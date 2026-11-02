"""Closed-history support hypotheses, never new production BUY rules."""
from .trend_reversal import closed,finite

def assess(coin,now_ms):
    out=dict(status='N/A',support=None,broken_support=None,breakdown='UNVERIFIED',pullback={'ready':False},confirmed={'ready':False},approved_buy=False)
    price=coin.get('price')
    if coin.get('stale',True) or not finite(price) or price<=0:return dict(out,reason='STALE_QUOTE')
    try:rows=closed(coin.get('raw',{}).get('4h'),'4h',now_ms)
    except (ValueError,TypeError,KeyError) as e:return dict(out,reason=str(e))
    old=coin.get('frames',{}).get('4h',{}).get('support')
    lows=[]
    # Only confirmed pivot lows: both right candles have already closed.
    for i in range(2,len(rows)-2):
        if rows[i]['low']<price and rows[i]['low']<=min(r['low'] for r in rows[i-2:i+3]):lows.append((rows[i]['low'],rows[i]['timestamp']))
    # Two separate historic touches (>= 3 candles apart) reduce single-wick noise.
    zones=[]
    atr=coin.get('frames',{}).get('4h',{}).get('atr')
    tolerance=atr*.25 if finite(atr) and atr>0 else price*.003
    for value,stamp in lows:
        touches=[(v,t) for v,t in lows if abs(v-value)<=tolerance]
        if len(touches)>=2 and max(t for v,t in touches)-min(t for v,t in touches)>=3*14400000:
            zones.append(dict(price=min(v for v,t in touches),touches=len(touches),confirmed_at=max(t for v,t in touches)+3*14400000))
    support=max((z for z in zones if z['price']<price),key=lambda z:z['price'],default=None)
    if support is not None:support['timeframe']='4h'
    if support is None:
        try:
            daily=closed(coin.get('raw',{}).get('1d'),'1d',now_ms)
            pivots=[(daily[i]['low'],daily[i]['timestamp']) for i in range(2,len(daily)-2) if daily[i]['low']<price and daily[i]['low']<=min(r['low'] for r in daily[i-2:i+3])]
            zones=[]
            for value,stamp in pivots:
                touches=[(v,t) for v,t in pivots if abs(v-value)<=tolerance]
                if len(touches)>=2 and max(t for v,t in touches)-min(t for v,t in touches)>=3*86400000:
                    zones.append(dict(price=min(v for v,t in touches),touches=len(touches),confirmed_at=max(t for v,t in touches)+3*86400000,timeframe='1d'))
            support=max(zones,key=lambda z:z['price'],default=None)
        except (ValueError,TypeError,KeyError):pass
    lost=finite(old) and old>=price
    recent=rows[-2:];below=lost and all(r['close']<old for r in recent)
    prior=rows[-22:-2];avg=sum(r['volume'] for r in prior)/len(prior)
    sell=sum(r['volume'] for r in recent if r['close']<r['open'])
    buy=sum(r['volume'] for r in recent if r['close']>r['open'])
    expansion=avg>0 and sum(r['volume'] for r in recent)/2>avg*1.1
    resistance=max(r['high'] for r in rows[-22:-2])
    stabilized=bool(support and all(r['close']>=support['price'] for r in recent) and buy>sell and expansion)
    confirmed=bool(all(r['close']>resistance for r in recent) and buy>sell and expansion)
    out.update(status='AVAILABLE',support=support,broken_support=old if lost else None,
        breakdown='CONFIRMED_2_CLOSED_BARS' if below else 'INTRABAR_OR_UNCONFIRMED' if lost else 'NOT_BROKEN',
        volume_proxy='selling' if expansion and sell>buy else 'buying' if expansion and buy>sell else 'unconfirmed',
        pullback=dict(ready=stabilized,zone=support['price'] if support else None,invalidation=support['price'] if support else None,condition='stabilization + closed candle buying-volume proxy; broader market still required'),
        confirmed=dict(ready=confirmed,level=resistance,condition='two closed 4h bars above fixed resistance + volume; daily and market filters still required'),
        reason='Historic zone is a hypothesis, not guaranteed support; fees and broader market gates unchanged')
    return out
