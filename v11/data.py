"""Run-scoped snapshots, independent price/metadata paths, closed candles."""
import time
import urllib.parse
from .indicators import summary, correlation

COINS = dict(SOL='solana',TAO='bittensor',ONDO='ondo-finance',RENDER='render-token',AAVE='aave',FET='fetch-ai',HYPE='hyperliquid',SUI='sui',LINK='chainlink',APT='aptos')
MARKET = dict(BTC='bitcoin',ETH='ethereum')
PRIMARY = ('SOL','TAO','ONDO','RENDER','AAVE','FET')
INTERVAL_MS = {'1h':3600000,'4h':14400000,'1d':86400000,'1w':604800000}


def candles(api, symbol, interval):
    query = urllib.parse.urlencode(dict(symbol=symbol+'USDT',interval=interval,limit=1000 if interval=="1h" else 300))
    rows = api.http_json('https://data-api.binance.vision/api/v3/klines?'+query,retries=2,timeout=15)
    now = time.time()*1000
    out = []
    for row in rows:
        if not isinstance(row,list) or len(row)<7 or float(row[6])>=now:
            continue
        vals = [api.safe_float(row[i]) for i in (1,2,3,4,5)]
        if any(v is None for v in vals) or min(vals[:4])<=0 or vals[4]<0:
            continue
        if vals[1]<max(vals[0],vals[3]) or vals[2]>min(vals[0],vals[3]):
            continue
        out.append(dict(timestamp=int(row[0]),open=vals[0],high=vals[1],low=vals[2],close=vals[3],volume=vals[4]))
    out.sort(key=lambda x:x['timestamp'])
    if len(out)<35:
        raise ValueError('Málo uzavretých sviečok.')
    if len({r['timestamp'] for r in out})!=len(out):
        raise ValueError('Duplicitné sviečky.')
    step=INTERVAL_MS[interval]
    if any(b['timestamp']-a['timestamp']!=step for a,b in zip(out,out[1:])):
        raise ValueError('Medzery v OHLCV histórii.')
    if now-(out[-1]['timestamp']+step)>step:
        raise ValueError('Zastarané sviečky.')
    return out


def collect(api, full=True):
    symbols={**MARKET,**(COINS if full else {s:COINS[s] for s in PRIMARY})}
    errors=[]
    metadata={}
    try:
        rows=api.coingecko_markets(list(symbols.values()))
        metadata={r['id']:r for r in rows}
    except Exception as exc:
        errors.append('CoinGecko metadata: '+type(exc).__name__)
    tickers={}
    try:
        query=urllib.parse.urlencode({'symbols':__import__('json').dumps([s+'USDT' for s in symbols],separators=(',',':'))})
        rows=api.http_json('https://data-api.binance.vision/api/v3/ticker/24hr?'+query,retries=2,timeout=15)
        tickers={r['symbol']:r for r in rows}
    except Exception as exc:
        errors.append('Binance tickers: '+type(exc).__name__)
    global_data={}
    try:
        raw=api.http_json('https://api.coingecko.com/api/v3/global',timeout=8,retries=1)['data']
        stamp=api.safe_float(raw.get('updated_at'))
        if stamp and -60<=time.time()-stamp<=900:
            global_data=dict(at=stamp,cap=api.safe_float(raw.get('total_market_cap',{}).get('usd')),
                volume=api.safe_float(raw.get('total_volume',{}).get('usd')),
                dominance=api.safe_float(raw.get('market_cap_percentage',{}).get('btc')),
                change=api.safe_float(raw.get('market_cap_change_percentage_24h_usd')),source='CoinGecko')
    except Exception as exc:errors.append('Global: '+type(exc).__name__)
    result={}
    for symbol, coin_id in symbols.items():
        meta=metadata.get(coin_id,{})
        ticker=tickers.get(symbol+'USDT',{})
        ticker_price=api.safe_float(ticker.get('lastPrice'))
        use_ticker=ticker_price is not None and ticker_price>0
        price=ticker_price if use_ticker else api.safe_float(meta.get('current_price'))
        if price is not None and price<=0:price=None
        stamp=api.safe_float(ticker.get('closeTime')) if use_ticker else None
        meta_stamp=api.parse_timestamp(meta.get('last_updated')) if meta.get('last_updated') else None
        age=time.time()-stamp/1000 if stamp else time.time()-meta_stamp.timestamp() if meta_stamp else None
        data=dict(price=price,frames={},raw={},market_cap=meta.get('market_cap'),volume_24h=meta.get('total_volume'),
                  market_cap_change_24h=meta.get('market_cap_change_percentage_24h'),
                  total_supply=meta.get('total_supply'),max_supply=meta.get('max_supply'),circulating_supply=meta.get('circulating_supply'),change_24h=api.safe_float(ticker.get('priceChangePercent')) if use_ticker else meta.get('price_change_percentage_24h'),
                  stale=age is None or age>900 or age < -60,price_source='Binance' if stamp else 'CoinGecko',age_seconds=age,
                  metadata_at=meta.get('last_updated'),errors=[])
        if not meta_stamp or not -60<=time.time()-meta_stamp.timestamp()<=900:
            for key in ('market_cap','volume_24h','market_cap_change_24h','circulating_supply','total_supply','max_supply'):
                data[key]=None
        intervals=('1h','4h','1d','1w') if full else ('4h',)
        for interval in intervals:
            try:
                rows=candles(api,symbol,interval)
                data['raw'][interval]=rows
                data['frames'][interval]=summary(rows)
            except Exception as exc:
                data['errors'].append(interval+': '+type(exc).__name__)
        data['volume_to_cap']=data['volume_24h']/data['market_cap'] if data['volume_24h'] is not None and data['market_cap'] else None
        result[symbol]=data
        print(f"Data {symbol}: price={'OK' if price else 'missing'}, frames={','.join(data['frames'])}")
    btc=result['BTC']
    for sym,data in result.items():
        a,b=data['raw'].get('4h',[]),btc['raw'].get('4h',[])
        if len(a)>=61 and len(b)>=61 and [r['timestamp'] for r in a[-61:]]==[r['timestamp'] for r in b[-61:]]:
            data['btc_correlation']=correlation(data['frames']['4h']['returns'],btc['frames']['4h']['returns'])
            data['relative_strength_btc_7d']=(a[-1]['close']/a[-43]['close'])/(b[-1]['close']/b[-43]['close'])-1
        else:
            data['btc_correlation']=None
            data['relative_strength_btc_7d']=None
    alt_values=[d['relative_strength_btc_7d'] for s,d in result.items() if s in PRIMARY and d['relative_strength_btc_7d'] is not None]
    center=__import__('statistics').median(alt_values) if alt_values else None
    for d in result.values():
        d['relative_strength_alt_median_7d']=d['relative_strength_btc_7d']-center if center is not None and d['relative_strength_btc_7d'] is not None else None
    complete=all(result[s]['price'] and not result[s]['stale'] and result[s]['frames'].get('4h',{}).get('ema200') is not None for s in (*PRIMARY,'BTC','ETH'))
    return dict(coins=result,complete=complete,errors=errors,global_data=global_data,at=time.time())
