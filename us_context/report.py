"""Short, attributed US context. No AI, forecasts or trading decisions."""
import concurrent.futures
import json
import math
import os
import time
import urllib.parse
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from zoneinfo import ZoneInfo
from . import macro as fundamentals

# Provider IDs for the six production watchlist symbols. collect() follows
# main.PORTFOLIO; the FET provider alias is independent of its ticker symbol.
COINS = dict(AAVE='aave', TAO='bittensor', FET='fetch-ai', SOL='solana',
             ONDO='ondo-finance', RENDER='render-token')

UTC = timezone.utc
BRATISLAVA = ZoneInfo('Europe/Bratislava')
NEW_YORK = ZoneInfo('America/New_York')
OPENING_MINUTES = 30
QUOTE_MAX_AGE = 20 * 60  # Public equity feeds can be delayed; never call them live.
CRYPTO_MAX_AGE = 15 * 60
MAX_CLOCK_SKEW = 60
QUOTES = {
    '^IXIC': ('Nasdaq Composite', 'index'),
    '^GSPC': ('S&P 500', 'index'),
    'NQ=F': ('Nasdaq-100 futures', 'future'),
    'ES=F': ('S&P 500 futures', 'future'),
}
MACRO_SOURCES = [s for s in fundamentals.SOURCES if s['id'] in ('fed', 'bls_calendar', 'bea')]


def number(value, positive=False):
    if isinstance(value, bool):
        return None
    try:
        out = float(value)
        return out if math.isfinite(out) and (not positive or out > 0) else None
    except (TypeError, ValueError, OverflowError):
        return None


def stamp(value):
    try:
        if isinstance(value, (float, int)) and not isinstance(value, bool):
            return datetime.fromtimestamp(value, UTC)
        out = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return out.astimezone(UTC) if out.tzinfo else None
    except (ValueError, TypeError, OverflowError, OSError):
        return None


def fresh(at, now, max_age):
    return at is not None and -MAX_CLOCK_SKEW <= (now - at).total_seconds() <= max_age


@lru_cache(maxsize=4)
def calendar(year):
    import exchange_calendars
    # XNYS cash holiday/early-close sessions also apply to Nasdaq's regular US
    # equity session. This does NOT describe CME futures trading hours or halts.
    return exchange_calendars.get_calendar('XNYS', start=f'{year-1}-01-01', end=f'{year+1}-12-31')


def session(now, get_calendar=calendar):
    if now.tzinfo is None:
        raise ValueError('US session requires an aware timestamp')
    ny = now.astimezone(NEW_YORK)
    result = dict(phase='N/A',ny=ny,open=None,close=None,calendar='XNYS',reason='kalendár nedostupný')
    try:
        import pandas as pd
        cal = get_calendar(ny.year)
        day = pd.Timestamp(ny.date())
        if not cal.is_session(day):
            result.update(phase='CLOSED',reason='víkend / burzový sviatok')
            return result
        opening = cal.session_open(day).to_pydatetime()
        closing = cal.session_close(day).to_pydatetime()
        phase = ('PREOPEN' if now < opening else 'OPENING' if now < opening+timedelta(minutes=OPENING_MINUTES)
                 else 'AFTER OPEN' if now < closing else 'CLOSED')
        result.update(phase=phase,open=opening,close=closing,reason='riadna akciová seansa' if now < closing else 'po závere seansy')
    except Exception:
        pass  # Unknown calendar must never imply an open market.
    return result


def parse_quote(payload, symbol, now, market):
    missing = dict(symbol=symbol,name=QUOTES[symbol][0],kind=QUOTES[symbol][1],price=None,change=None,at=None,status='N/A',source='Yahoo Finance')
    try:
        chart = payload['chart']
        if chart.get('error'):
            return missing
        meta = chart['result'][0]['meta']
        expected = 'FUTURE' if missing['kind']=='future' else 'INDEX'
        if meta.get('symbol') != symbol or meta.get('instrumentType') != expected or meta.get('currency') != 'USD':
            return missing
        price = number(meta.get('regularMarketPrice'), positive=True)
        previous = number(meta.get('chartPreviousClose'), positive=True)
        at = stamp(meta.get('regularMarketTime'))
        # Do not use chart candle timestamps as quote-update timestamps.
        if price is None or at is None or (at-now).total_seconds()>MAX_CLOCK_SKEW:
            return missing
        status = 'oneskorený zdroj'
        if missing['kind']=='index' and market['phase']=='PREOPEN':
            # Previous cash-session quote is useful, but never today's premarket index.
            if not (now-timedelta(days=7) <= at < market['open']):
                return missing
            cal = calendar(at.astimezone(NEW_YORK).year)
            import pandas as pd
            day = pd.Timestamp(at.astimezone(NEW_YORK).date())
            if not cal.is_session(day):
                return missing
            close = cal.session_close(day).to_pydatetime()
            # Only the most recent completed session, near its close.
            latest = cal.date_to_session(pd.Timestamp(market['ny'].date()), direction='previous')
            latest = cal.previous_session(latest)  # Today is a trading day in PREOPEN.
            if day != latest or abs((at-close).total_seconds())>20*60:
                return missing
            status = 'posledná uzavretá seansa'
        elif not fresh(at,now,QUOTE_MAX_AGE):
            return missing
        elif missing['kind']=='index' and market['phase'] not in ('OPENING','AFTER OPEN'):
            return missing
        elif missing['kind']=='index' and at<market['open']:
            return missing
        # chartPreviousClose on a 1d chart is the feed's prior-session reference.
        return dict(missing,price=price,change=number((price/previous-1)*100) if previous else None,at=at,status=status)
    except (KeyError, IndexError, TypeError, ValueError, OverflowError, AttributeError):
        return missing


def crypto_snapshot(tickers, metadata, global_payload, now, watched=None):
    def rows_by(rows, key):
        return {r[key]:r for r in rows if isinstance(r,dict) and isinstance(r.get(key),str)} if isinstance(rows,list) else {}
    ticker_map = rows_by(tickers,'symbol')
    meta_map = rows_by(metadata,'id')
    coins = {}
    for symbol, coin_id in {'BTC':'bitcoin', **(COINS if watched is None else watched)}.items():
        t = ticker_map.get(symbol+'USDT',{})
        end = stamp(number(t.get('closeTime'))/1000) if number(t.get('closeTime')) is not None else None
        begin = stamp(number(t.get('openTime'))/1000) if number(t.get('openTime')) is not None else None
        valid = fresh(end,now,CRYPTO_MAX_AGE) and begin is not None and abs((end-begin).total_seconds()-86400)<300
        price = number(t.get('lastPrice'),positive=True) if valid else None
        change = number(t.get('priceChangePercent')) if valid and price else None
        if price is not None:
            coins[symbol] = dict(price=price,change=change,at=end,source='Binance USDT',start=begin)
        else:
            m = meta_map.get(coin_id,{})
            at = stamp(m.get('last_updated'))
            valid = fresh(at,now,CRYPTO_MAX_AGE)
            coins[symbol] = dict(price=number(m.get('current_price'),True) if valid else None,
                change=number(m.get('price_change_percentage_24h')) if valid and number(m.get('current_price'),True) else None,
                at=at if valid else None,source='CoinGecko USD',start=at-timedelta(days=1) if valid else None)
    g = global_payload.get('data',{}) if isinstance(global_payload,dict) else {}
    if not isinstance(g,dict):
        g = {}
    at = stamp(g.get('updated_at'))
    valid = fresh(at,now,CRYPTO_MAX_AGE)
    caps = g.get('total_market_cap')
    shares = g.get('market_cap_percentage')
    cap = number(caps.get('usd'),True) if valid and isinstance(caps,dict) else None
    dominance = number(shares.get('btc')) if valid and cap and isinstance(shares,dict) else None
    if dominance is not None and not 0<=dominance<=100:
        dominance = None
    return dict(coins=coins,global_at=at if valid else None,cap=cap,
                cap_change=number(g.get('market_cap_change_percentage_24h_usd')) if cap else None,dominance=dominance)


def divergences(crypto):
    btc = crypto['coins']['BTC']
    out = []
    if btc['change'] is None or btc['at'] is None:
        return out
    cap = crypto['cap_change']
    if cap is not None and crypto['global_at'] is not None and abs((btc['at']-crypto['global_at']).total_seconds())<=900:
        if btc['change']*cap<0 and abs(btc['change']-cap)>=1:
            out.append(f"BTC {btc['change']:+.2f}% vs kryptotrh {cap:+.2f}% (24h)")
    opposite = []
    for s,d in crypto['coins'].items():
        if s=='BTC' or d['change'] is None or d['at'] is None:
            continue
        if abs((btc['at']-d['at']).total_seconds())<=900 and btc['change']*d['change']<0 and abs(btc['change']-d['change'])>=1:
            opposite.append(s)
    if opposite:
        out.append('opačný 24h smer voči BTC: '+', '.join(opposite))
    return out


def macro_events(payloads, now):
    result = []; seen = set();day = now.astimezone(NEW_YORK).date()
    midnight = now.astimezone(NEW_YORK).replace(hour=0,minute=0,second=0,microsecond=0).astimezone(UTC)
    for source in MACRO_SOURCES:
        raw = payloads.get(source['id'])
        if not isinstance(raw,bytes):
            continue
        try:
            events = (fundamentals.parse_calendar(raw,source,midnight) if source.get('format')=='ics'
                      else fundamentals.parse_feed(raw,source,now))
        except Exception:
            continue
        for e in events:
            if not set(e['categories']) & {'Fed','CPI','PCE','employment','GDP'}:
                continue
            at = stamp(e.get('event_at') or e.get('published_at'))
            if at is None or at.astimezone(NEW_YORK).date()!=day:
                continue
            if not e['scheduled'] and at>now:
                continue
            key = (e['title'].casefold(),at)
            if key not in seen:
                seen.add(key);result.append(dict(e,at=at))
    return sorted(result,key=lambda e:e['at'])[:3]


def collect(api, now):
    """One bounded attempt/source, parallel; no candle histories or AI requests."""
    jobs = {}
    def get(url, headers=None):
        return api.http_json(url,headers=headers,timeout=6,retries=1)
    def equity(symbol):
        last_code=None
        for host in ('query1.finance.yahoo.com','query2.finance.yahoo.com'):
            url='https://'+host+'/v8/finance/chart/'+urllib.parse.quote(symbol,safe='')+'?interval=1m&range=1d'
            try:
                value=get(url,{'User-Agent':'CryptoBotUS/11.1 public-data reader'})
                chart=value.get('chart',{})
                if chart.get('result') and not chart.get('error'):return value
            except Exception as exc:
                last_code=getattr(exc,'code',None) or getattr(getattr(exc,'response',None),'status_code',None)
        error=ValueError('US quote providers unavailable')
        error.code=last_code
        raise error
    for symbol in QUOTES:
        jobs[symbol] = lambda symbol=symbol:equity(symbol)
    # Bulk endpoint: one delisted/unsupported symbol must not reject the entire
    # batch. Only the watched symbols are retained by crypto_snapshot().
    jobs['tickers']=lambda:get('https://data-api.binance.vision/api/v3/ticker/24hr')
    watched={s:COINS.get(s,coin_id) for s,coin_id in api.PORTFOLIO.items()}
    headers=api.coingecko_headers()
    jobs['global']=lambda:get('https://api.coingecko.com/api/v3/global',headers)
    ids=','.join(['bitcoin',*watched.values()])
    jobs['metadata']=lambda:get('https://api.coingecko.com/api/v3/coins/markets?'+urllib.parse.urlencode({'vs_currency':'usd','ids':ids,'price_change_percentage':'24h'}),headers)
    # Reuse bounded (8s, no retries), size-limited official-feed fetching with
    # redirect-domain validation, not the broad 72h fundamentals collector.
    for source in MACRO_SOURCES:
        jobs[source['id']]=lambda source=source:fundamentals.fetch(source)
    payloads={};statuses={}
    def one(item):
        key,fn=item
        try:
            return key,fn(),'FETCH_OK'
        except Exception as exc:
            code=getattr(exc,'code',None)
            return key,None,type(exc).__name__+(f':{code}' if isinstance(code,int) else '')
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(jobs)) as pool:
        for key,value,status in pool.map(one,jobs.items()):
            payloads[key]=value;statuses[key]=status
    market=session(now)
    return dict(market=market,quotes={s:parse_quote(payloads[s],s,now,market) for s in QUOTES},
                crypto=crypto_snapshot(payloads.get('tickers'),payloads.get('metadata'),payloads.get('global'),now,watched),
                macro=macro_events(payloads,now),sources=statuses)


def refresh(data, now):
    """A slow fetch must not leave a PREOPEN heading after the opening bell."""
    data['market']=session(now)
    for q in data['quotes'].values():
        previous=q['status']=='posledná uzavretá seansa'
        valid=(data['market']['phase']=='PREOPEN' if previous else fresh(q['at'],now,QUOTE_MAX_AGE))
        if q['kind']=='index' and not previous:
            valid=valid and data['market']['phase'] in ('OPENING','AFTER OPEN')
            valid=valid and q['at'] is not None and q['at']>=data['market']['open']
        if not valid:
            q.update(price=None,change=None,at=None,status='N/A')
    for d in data['crypto']['coins'].values():
        if not fresh(d['at'],now,CRYPTO_MAX_AGE):
            d.update(price=None,change=None,at=None,start=None)
    if not fresh(data['crypto']['global_at'],now,CRYPTO_MAX_AGE):
        data['crypto'].update(global_at=None,cap=None,cap_change=None,dominance=None)
    return data


def pct(value):
    return 'N/A' if value is None else f'{value:+.2f}%'


def local_time(at):
    return 'N/A' if at is None else at.astimezone(BRATISLAVA).strftime('%d.%m. %H:%M:%S')


def target_time(slot):
    try:
        date = str(slot).rsplit('_',2)[-2]
        return datetime.fromisoformat(date+'T15:00:00').replace(tzinfo=BRATISLAVA)
    except (ValueError, IndexError):
        return None


def render(data, now, slot, previous=None, collected_seconds=0):
    market=data['market'];crypto=data['crypto'];target=target_time(slot)
    late=max(0,(now-target).total_seconds()) if target else None
    lines=['🇺🇸 USA prehľad | '+market['phase'],
           f"Plán 15:00 Bratislava; zostavené {now.astimezone(BRATISLAVA):%d.%m.%Y %H:%M:%S} | NY {now.astimezone(NEW_YORK):%H:%M:%S}"]
    if market['open']:
        lines.append(f"Akcie: otvorenie {market['open'].astimezone(BRATISLAVA):%H:%M}, záver {market['close'].astimezone(BRATISLAVA):%H:%M} Bratislava (XNYS).")
    else:
        lines.append('Akcie: '+market['reason']+'; otvorenie N/A.')
    if late is not None and late>=60:
        lines.append(f"Meškanie pri zostavení {late/60:.1f} min; zber {collected_seconds:.1f}s; Actions nemá časovú garanciu.")
    for symbol in QUOTES:
        q=data['quotes'][symbol]
        if q['price'] is None:
            lines.append(q['name']+': N/A (Yahoo Finance).')
        else:
            lines.append(f"{q['name']}: {q['price']:,.2f}; {pct(q['change'])} vs predch. záver; {local_time(q['at'])} BL, {q['status']} [Yahoo Finance].")
    btc=crypto['coins']['BTC']
    currency='USDT' if btc['source']=='Binance USDT' else 'USD'
    price='N/A' if btc['price'] is None else f"{btc['price']:,.0f} {currency}"
    lines.append(f"BTC {price} | 24h {pct(btc['change'])}; {local_time(btc['at'])} BL [{btc['source']}].")
    cap='N/A' if crypto['cap'] is None else f"${crypto['cap']/1e12:.2f}T"
    dom='N/A' if crypto['dominance'] is None else f"{crypto['dominance']:.2f}%"
    delta='N/A'
    if previous and crypto['dominance'] is not None:
        at=stamp(previous.get('at'));old=number(previous.get('dominance'))
        if at and old is not None and 18*3600<=(now-at).total_seconds()<=30*3600:
            delta=f"{crypto['dominance']-old:+.2f} p. b. od {local_time(at)} BL"
    lines.append(f"Kryptotrh {cap} | 24h {pct(crypto['cap_change'])}; BTC dominancia {dom} ({delta}); {local_time(crypto['global_at'])} BL [CoinGecko].")
    alts=[(s,d) for s,d in crypto['coins'].items() if s!='BTC']
    for i in range(0,len(alts),5):
        lines.append('Altcoiny 24h: '+' | '.join(s+' '+pct(d['change']) for s,d in alts[i:i+5]))
    valid=[d for _,d in alts if d['change'] is not None]
    if valid:
        ats=[d['at'] for d in valid]
        lines.append('Alt dáta: '+', '.join(sorted({d['source'] for d in valid}))+f"; aktualizácie {local_time(min(ats))}–{local_time(max(ats))} BL.")
        changes=sorted(d['change'] for d in valid)
        middle=len(changes)//2
        median=changes[middle] if len(changes)%2 else (changes[middle-1]+changes[middle])/2
        relative='N/A' if btc['change'] is None else f"{median-btc['change']:+.2f} p. b. vs BTC"
        lines.append(f"Alt šírka 24h: {sum(d['change']>0 for d in valid)}/{len(valid)} rastie; medián {median:+.2f}% ({relative}).")
    for text in divergences(crypto):
        lines.append('⚠️ Divergencia: '+text+'. Nejde o dôkaz toku kapitálu.')
    usable=[q for q in data['quotes'].values() if q['price'] is not None and q['change'] is not None and q['status']!='posledná uzavretá seansa']
    down=[s for s,d in alts if d['change'] is not None and d['change']<0]
    if usable and all(q['change']<0 for q in usable) and down:
        lines.append('Súbeh oslabenia US dát a 24h strát: '+', '.join(down)+'. Rozdielne intervaly; príčina ani ďalší smer nepotvrdené.')
    elif not usable:
        lines.append('Aktuálny vplyv USA na altcoiny: N/A — chýbajú aktuálne US kotácie.')
    if market['phase']=='PREOPEN':
        lines.append('Futures sú predbežný kontext; dnešná reakcia akcií ešte nie je dostupná. NQ ≠ Nasdaq Composite.')
    lines.append('Makro dnes (New York; BLS/Fed/BEA):')
    for event in data['macro']:
        label=('plán kalendára; výsledok N/A' if event['scheduled'] else
               'čas aktualizácie' if event.get('timestamp_kind')=='updated' else 'čas publikácie')
        lines.append(f"{event['at'].astimezone(NEW_YORK):%H:%M} NY / {event['at'].astimezone(BRATISLAVA):%H:%M} BL | {event['title'][:110]} ({label}) — {event['url']}")
    if not data['macro']:
        lines.append('N/A — overená dnešná udalosť s časom z BLS/Fed/BEA nedostupná.')
    lines.append('Krátky scenár: súbežné potvrdené oslabenie akcií a šírky altcoinov zvyšuje opatrnosť; opačný vývoj tento scenár oslabí. Bez aktuálnych dát je smer N/A.')
    lines.append('Pokyn: nepotvrdené nové vstupy WAIT; skutočná držba N/A v analytickom pilote, existujúce ochranné hranice musí posúdiť používateľ. USA kontext sám nevytvára BUY/SELL; bot neobchoduje.')
    return '\n'.join(lines)


def run(api, slot):
    from v11.reporting import require_live_snapshot
    require_live_snapshot({})
    state=api.load_state()
    from v11.delivery import already_attempted, send_once
    if state.get('last_us_slot')==slot or state.get('last_main_slot')==slot or already_attempted(state,slot):
        return
    started=datetime.now(UTC);timer=time.monotonic()
    data=collect(api,started)
    ready=datetime.now(UTC);seconds=time.monotonic()-timer
    refresh(data,ready)
    message=render(data,ready,slot,state.get('us_market_previous'),seconds)
    print('US_OUTLOOK_READY '+json.dumps(dict(slot=slot,at=ready.isoformat(),collect_seconds=round(seconds,3))))
    if not send_once(api,state,message,slot):
        return
    sent=datetime.now(UTC)
    target=target_time(slot)
    job=stamp(os.getenv('BOT_JOB_STARTED_AT'))
    timing=dict(slot=slot,target_at=target.isoformat() if target else None,
        job_first_step_at=job.isoformat() if job else None,outlook_started_at=started.isoformat(),
        ready_at=ready.isoformat(),sent_at=sent.isoformat(),collect_seconds=round(seconds,3),
        schedule_to_job_seconds=round((job-target).total_seconds(),3) if job and target else None,
        job_to_outlook_seconds=round((started-job).total_seconds(),3) if job else None,
        send_seconds=round((sent-ready).total_seconds(),3),
        delay_seconds=round((sent-target).total_seconds(),3) if target else None)
    # Public-safe timing only. No portfolio, chat ID, credentials or request bodies.
    print('US_OUTLOOK_TIMING '+json.dumps(timing,sort_keys=True))
    print('US_OUTLOOK_SOURCES '+json.dumps(data['sources'],sort_keys=True))
    state['us_outlook_timing']=timing
    if data['crypto']['dominance'] is not None:
        state['us_market_previous']=dict(at=data['crypto']['global_at'].isoformat(),dominance=data['crypto']['dominance'])
    state.update(last_main_slot=slot,last_us_slot=slot,last_run=api.iso_now(),last_us_outlook=api.iso_now(),bot_version=api.VERSION)
    api.save_state(state)


class PublicUSAPI:
    """Read-only public market adapter; no bot state, broker, AI or Telegram."""
    PORTFOLIO=COINS
    @staticmethod
    def coingecko_headers():return {'Accept':'application/json','User-Agent':'CryptoBotUS/11.1'}
    def http_json(self,url,headers=None,timeout=6,retries=1):
        import requests
        parsed=urllib.parse.urlsplit(url)
        known={('data-api.binance.vision','/api/v3/ticker/24hr'),
               ('api.coingecko.com','/api/v3/global'),('api.coingecko.com','/api/v3/coins/markets')}
        chart=(parsed.hostname in ('query1.finance.yahoo.com','query2.finance.yahoo.com') and
               parsed.path.startswith('/v8/finance/chart/') and urllib.parse.unquote(parsed.path.rsplit('/',1)[-1]) in QUOTES)
        if parsed.scheme!='https' or parsed.username or parsed.password or parsed.port not in (None,443) or not (chart or (parsed.hostname,parsed.path) in known):
            raise ValueError('US adapter destination refused')
        response=requests.get(url,headers=headers,timeout=min(timeout,8),allow_redirects=False)
        response.raise_for_status()
        if not 200<=response.status_code<300:raise ValueError('US redirect refused')
        return response.json()
