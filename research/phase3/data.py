"""Closed-bar features only; independent phase-3 data directory."""
from pathlib import Path
import numpy as np
import pandas as pd
import talib.abstract as ta

ROOT=Path(__file__).resolve().parents[2]
DATA=ROOT/'backtesting/user_data/phase3/binance'


def load(symbol, timeframe):
    f=pd.read_feather(DATA/f'{symbol}_USDT-{timeframe}.feather').sort_values('date')
    if f['date'].duplicated().any():raise ValueError('Duplicate candle timestamp')
    if f['date'].dt.tz is None:raise ValueError('Missing timezone')
    if not np.isfinite(f[['open','high','low','close','volume']].to_numpy()).all():raise ValueError('Nonfinite candle')
    if (f['volume']<0).any():raise ValueError('Negative volume')
    if (f[['open','high','low','close']]<=0).any().any():raise ValueError('Nonpositive OHLC')
    if (f['high']<f[['open','close','low']].max(axis=1)).any() or (f['low']>f[['open','close']].min(axis=1)).any():raise ValueError('Invalid OHLC bounds')
    return f.reset_index(drop=True)


def daily_features(f):
    f=f.copy()
    f['ema50']=ta.EMA(f,timeperiod=50);f['ema200']=ta.EMA(f,timeperiod=200)
    f['momentum30']=f['close'].pct_change(30)
    f['momentum5']=f['close'].pct_change(5)
    f['ema50_slope']=f['ema50'].pct_change(5)
    f['adx']=ta.ADX(f);f['atr_pct']=ta.ATR(f)/f['close']
    quote=f['volume']*f['close']
    f['relative_volume']=quote/quote.shift(1).rolling(20).mean()
    f['return1']=f['close'].pct_change()
    f['available_at']=f['date']+pd.Timedelta('1D')
    return f


def retests(f):
    """A breakout level must have existed before the retest bar opened."""
    out=np.zeros(len(f),dtype=bool);level=None;expiry=-1
    rows=f[['close','open','low','resistance','atr','hist','rvol']].to_numpy()
    for i,(close,op,low,res,atr,hist,rvol) in enumerate(rows):
        if level is not None:
            if i>expiry or close<level-.5*atr:level=None
            elif low<=level*1.01 and close>=level and close>op and rvol>=1:
                out[i]=True;level=None
        # New breakout is recorded after evaluating the previous level.
        if np.isfinite(res) and close>res and (i==0 or rows[i-1,0]<=f['resistance'].iloc[i-1]):
            level=res;expiry=i+12
    return out


def alt_features(f, daily):
    f=f.copy()
    for p in (20,50,200):f[f'ema{p}']=ta.EMA(f,timeperiod=p)
    f['rsi']=ta.RSI(f);f['adx']=ta.ADX(f);f['atr']=ta.ATR(f)
    f['hist']=ta.MACD(f)['macdhist']
    f['rvol']=f['volume']/f['volume'].shift(1).rolling(20).mean()
    f['resistance']=f['high'].shift(1).rolling(20).max()
    f['available_at']=f['date']+pd.Timedelta('4h')
    d=daily_features(daily)[['available_at','ema200']].rename(columns={'ema200':'daily200'})
    f=pd.merge_asof(f,d,left_on='available_at',right_on='available_at',direction='backward')
    f['warm']=f['ema200'].notna()&f['daily200'].notna()
    f['pullback']=(f['low']<=f['ema20'])&(f['close']>f['ema20'])&(f['ema20']>f['ema50'])&f['rsi'].between(40,65)&(f['hist']>f['hist'].shift(1))&(f['close']>f['daily200'])
    f['breakout']=(f['close']>f['resistance'])&(f['close'].shift(1)<=f['resistance'].shift(1))&(f['rvol']>=1.5)&(f['adx']>=20)&(f['close']>f['ema200'])
    f['retest']=retests(f)&(f['close']>f['daily200'])
    f['momentum']=(f['ema20']>f['ema50'])&(f['ema50']>f['ema200'])&f['rsi'].between(50,68)&(f['hist']>0)&(f['rvol']>=1.2)&((f['close']-f['ema20'])<=2*f['atr'])
    f['strong_neutral']=(f['rvol']>=1.8)&(f['adx']>=25)&(f['close']>f['daily200'])&f['rsi'].between(50,68)
    for key in ('pullback','breakout','retest','momentum'):f[key]=f[key]&f['warm']&(f['volume']>0)
    return f


def global_history(path):
    """Optional first-vintage input, never a backfill of today's global values."""
    path=Path(path)
    if not path.exists():return None
    f=pd.read_csv(path,parse_dates=['date','available_at'])
    required={'date','available_at','total_cap_usd','btc_dominance_pct','source_url','vintage_type'}
    if not required.issubset(f):raise ValueError('Global history lacks provenance')
    if f['date'].dt.tz is None or f['available_at'].dt.tz is None:raise ValueError('Global history timezone missing')
    if f['date'].duplicated().any() or not f['vintage_type'].eq('first_release').all():raise ValueError('Revised global data is not first-vintage data')
    if (f['available_at']<f['date']+pd.Timedelta('1D')).any():raise ValueError('Global daily value available before day closed')
    if not f.source_url.str.startswith('https://').all():raise ValueError('Global source missing')
    if (f.total_cap_usd<=0).any() or not f.btc_dominance_pct.between(0,100).all():raise ValueError('Invalid global series')
    f=f.sort_values('date').reset_index(drop=True)
    if not f.available_at.is_monotonic_increasing or f.available_at.duplicated().any():raise ValueError('Noncausal global publication order')
    if not np.isfinite(f[['total_cap_usd','btc_dominance_pct']].to_numpy()).all():raise ValueError('Nonfinite global series')
    if not f.date.diff().dropna().eq(pd.Timedelta('1D')).all():raise ValueError('Global daily observations must be contiguous')
    return f


def market_daily(btc,alts,global_frame=None):
    f=daily_features(btc)
    strengths=[]
    for symbol,d in alts.items():
        x=d.set_index('date')['close'].reindex(pd.DatetimeIndex(f['date']))
        relative=x.pct_change(30,fill_method=None).to_numpy()-f['momentum30'].to_numpy()
        strengths.append(relative)
    rs=np.array(strengths).T
    counts=np.isfinite(rs).sum(axis=1)
    f['alt_breadth']=np.divide((rs>0).sum(axis=1),counts,out=np.full(len(f),np.nan),where=counts>=2)
    f['breadth_count']=counts
    f['cap_momentum30']=np.nan;f['dominance_change30']=np.nan
    if global_frame is not None:
        g=global_frame.copy();g['cap_momentum30']=g['total_cap_usd'].pct_change(30,fill_method=None)
        g['dominance_change30']=g['btc_dominance_pct'].diff(30)
        f=f.drop(columns=['cap_momentum30','dominance_change30'])
        f=pd.merge_asof(f,g[['available_at','cap_momentum30','dominance_change30']],on='available_at',direction='backward')
    return f
