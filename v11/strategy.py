"""Experimental rules. No return target is a promise; no calibrated probability."""
import os
from .portfolio import BUY_FEE, SELL_FEE
from .indicators import scenarios


def costs(entry, target, stop=None, spread=None):
    if spread is None:
        raw = os.getenv('SPREAD_ESTIMATE')
        spread = float(raw) if raw else None
    s = spread if spread is not None else 0.
    if not 0 <= s < 1:
        raise ValueError('SPREAD_ESTIMATE musí byť v [0,1).')
    factor = (1-SELL_FEE)*(1-s)/((1+BUY_FEE)*(1+s))
    net = target/entry*factor-1
    loss = 1-stop/entry*factor if stop else None
    return dict(gross=target/entry-1, net=net, spread=spread, break_even=entry/factor,
                buy_fee=BUY_FEE, sell_fee=SELL_FEE, net_rr=net/loss if loss and loss>0 else None,
                estimated=spread is not None)


def reentry_edge(sale_price, buy_price, spread=None):
    s = spread or 0.
    return sale_price*(1-SELL_FEE)*(1-s)/(buy_price*(1+BUY_FEE)*(1+s))-1


def decide(data, held=False, sold=None, market_complete=True, approved=False, risk_normal=True):
    t = data.get('frames',{}).get('4h',{})
    daily = data.get('frames',{}).get('1d',{})
    price = data.get('price')
    result = dict(action='HOLD' if held else 'WAIT', reasons=[], confidence='nízka', forecasts=[], held=held, data_complete=False)
    if not price or not t or t.get('ema200') is None or data.get('stale'):
        result['reasons'] = ['Neúplné alebo zastarané dáta; nevytvárajú nový obchodný signál.']
        return result
    result['data_complete'] = True
    checks = dict(trend=price>t['ema50'] and t['ema20']>t['ema50'],
                  broad=daily.get('ema200') is not None and price>daily['ema200'],
                  momentum=t['macd_hist'] is not None and t['macd_hist']>0 and 40<=t['rsi14']<=68,
                  volume=t['relative_volume'] is not None and t['relative_volume']>=1.1,
                  structure=t['higher_structure'] or t['retest'],
                  strength=t['adx'] is not None and t['adx']>=20)
    score = sum(checks.values())
    result.update(score=score, confidence='stredná' if score>=4 else 'nízka', reasons=[{'trend':'rastový trend 4H','broad':'denný trend nad EMA200','momentum':'potvrdené momentum','volume':'zvýšený objem','structure':'vyššie maximá/minimá alebo retest','strength':'ADX potvrdzuje silu trendu'}[k] for k,v in checks.items() if v])
    stop = min(t['support'],price)-1.5*t['atr']
    tp1 = t['resistance'] if t['resistance']>price else price+1.5*(price-stop)
    tp2 = price+3*(price-stop)
    economics = costs(price,tp1,stop)
    result.update(entry=price,stop=stop,tp1=tp1,tp2=tp2,economics=economics,
                  forecasts=scenarios(price,t['atr'],daily.get('candles',0)))
    # A risk-point count alone cannot cause a sell. Independent closed-candle
    # structure, volume and broader weakness are required.
    severe = bool(t['support_broken'] and t['relative_volume'] and t['relative_volume']>=1.5
                  and daily.get('ema50') and price<daily['ema50'] and t['macd_hist']<0)
    result['sale_kind'] = None
    if held and severe and market_complete:
        result.update(action='REDUCE',sale_kind='ochranný',reasons=['Potvrdený support breakdown, predajný objem, slabý denný trend.'])
    elif not held and score>=5 and checks['broad'] and market_complete and risk_normal and approved and economics['estimated'] and economics['net']>=float(os.getenv('MIN_NET_EDGE','.03')) and (economics['net_rr'] or 0)>=1.5:
        result['action'] = 'BUY NOW'
        if sold:
            edge = reentry_edge(sold,price,economics['spread'])
            result['reentry_edge'] = edge
            result['action'] = 'BUY PULLBACK' if edge>=float(os.getenv('MIN_NET_EDGE','.03')) and (t['retest'] or t['bullish_divergence']) else 'WAIT'
    if result['action'].startswith('BUY') and os.getenv('V11_RULES_VALIDATED','false').lower()!='true':
        result['action']='WAIT'
        result['reasons'].append('Nové aktívne pravidlá čakajú na historickú validáciu.')
    if not approved:
        result['reasons'].append('Dostupnosť na eToro nebola používateľom overená; nový nákup zablokovaný.')
    if not economics['estimated']:
        result['reasons'].append('Spread neznámy: čisté výnosy sú optimistická hranica; nový nákup zablokovaný.')
    if not risk_normal:
        result['reasons'].append('Zvýšené trhové riziko; nový nákup zablokovaný.')
    if not market_complete:
        result['reasons'].append('Neúplné trhové pokrytie; zlepšenie rizika nepotvrdené.')
    return result
