"""Closed OHLCV only. A missing warm-up is missing data, never a zero."""
import math
import statistics


def ema(xs, period):
    if len(xs) < period:
        return None
    v = sum(xs[:period]) / period
    for x in xs[period:]:
        v += 2 / (period + 1) * (x - v)
    return v


def rsi(xs, period=14):
    if len(xs) <= period:
        return None
    ds = [b-a for a, b in zip(xs, xs[1:])]
    up = sum(max(d, 0) for d in ds[:period])/period
    down = sum(max(-d, 0) for d in ds[:period])/period
    for d in ds[period:]:
        up = (up*(period-1)+max(d, 0))/period
        down = (down*(period-1)+max(-d, 0))/period
    return 100-100/(1+up/down) if down else (100 if up else 50)


def summary(rows):
    if len(rows) < 35:
        return {}
    cs = [r['close'] for r in rows]
    trs, plus, minus = [], [], []
    for a, b in zip(rows, rows[1:]):
        trs.append(max(b['high']-b['low'], abs(b['high']-a['close']), abs(b['low']-a['close'])))
        u, d = b['high']-a['high'], a['low']-b['low']
        plus.append(u if u > d and u > 0 else 0)
        minus.append(d if d > u and d > 0 else 0)
    tr, p, m = (sum(x[:14])/14 for x in (trs, plus, minus))
    dx = []
    for i in range(13, len(trs)):
        if i > 13:
            tr, p, m = ((v*13+x[i])/14 for v, x in ((tr, trs), (p, plus), (m, minus)))
        total = p+m
        dx.append(100*abs(p-m)/total if total else 0)
    adx = sum(dx[:14])/14 if len(dx) >= 14 else None
    if adx is not None:
        for d in dx[14:]:
            adx = (adx*13+d)/14
    # MACD signal uses a sequence of past MACD values, never future data.
    macds = [ema(cs[:i], 12)-ema(cs[:i], 26) for i in range(26, len(cs)+1)]
    signal = ema(macds, 9)
    center, std = statistics.mean(cs[-20:]), statistics.pstdev(cs[-20:])
    volumes = [r.get('volume') for r in rows]
    has_volume = all(v is not None and v >= 0 for v in volumes[-21:])
    prior_volume = statistics.mean(volumes[-21:-1]) if has_volume else 0
    recent = rows[-20:]
    total_volume = sum(r['volume'] for r in recent) if has_volume else 0
    # Explicitly a rolling VWAP, not a daily/session VWAP.
    vwap = sum((r['high']+r['low']+r['close'])/3*r['volume'] for r in recent)/total_volume if total_volume else None
    old_rsi = rsi(cs[:-5])
    support = min(r['low'] for r in rows[-21:-1])
    resistance = max(r['high'] for r in rows[-21:-1])
    previous_support = min(r['low'] for r in rows[-22:-2])
    previous_resistance = max(r['high'] for r in rows[-22:-2])
    rsi_now = rsi(cs)
    return dict(price=cs[-1], **{f'ema{p}':ema(cs, p) for p in (20, 50, 100, 200)},
                rsi14=rsi_now, macd_hist=macds[-1]-signal if signal is not None else None,
                atr=tr, adx=adx, bb_lower=center-2*std, bb_upper=center+2*std,
                relative_volume=volumes[-1]/prior_volume if prior_volume else None,
                vwap20=vwap, support=support, resistance=resistance,
                breakout=cs[-1] > resistance,
                retest=cs[-2] > previous_resistance and rows[-1]['low'] <= previous_resistance*1.01 and cs[-1] >= previous_resistance,
                higher_structure=min(cs[-5:]) > min(cs[-10:-5]) and max(cs[-5:]) > max(cs[-10:-5]),
                bullish_divergence=cs[-1] < cs[-6] and old_rsi is not None and rsi_now > old_rsi,
                bearish_divergence=cs[-1] > cs[-6] and old_rsi is not None and rsi_now < old_rsi,
                support_broken=cs[-1] < support and cs[-2] < previous_support,
                returns=[b/a-1 for a, b in zip(cs[-61:-1], cs[-60:])], candles=len(rows))


def correlation(a, b):
    if len(a) != len(b) or len(a) < 20:
        return None
    ma, mb = statistics.mean(a), statistics.mean(b)
    denom = math.sqrt(sum((x-ma)**2 for x in a)*sum((y-mb)**2 for y in b))
    return sum((x-ma)*(y-mb) for x, y in zip(a, b))/denom if denom else None


def scenarios(price, atr4h, daily_count):
    """Volatility envelopes, NOT probabilities or calibrated forecasts."""
    if not price or not atr4h:
        return []
    return [dict(horizon=label, low=max(0, price-atr4h*math.sqrt(hours/4)),
                 high=price+atr4h*math.sqrt(hours/4), probability_up=None,
                 probability_down=None, probability_correction=None, confidence='nekalibrovaný scenár')
            for label, hours, needed in [('24h',24,0), ('48–72h',72,0), ('7–14 dní',336,30), ('30 dní',720,90)]
            if daily_count >= needed]
