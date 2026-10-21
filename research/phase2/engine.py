"""Offline research only. No API writes, Telegram, broker, or production imports.
Signals are computed at closed 4H bars, fills at the NEXT bar open. Daily
indicators are available only after the daily bar closes. No model fitting.
"""
import hashlib
import json
import math
from pathlib import Path
import numpy as np
import pandas as pd
import talib.abstract as ta

ROOT=Path(__file__).resolve().parents[2]
DATA=ROOT/'backtesting/user_data/data/binance'
DESIGN=json.loads((Path(__file__).parent/'design.json').read_text())
STRATEGIES=DESIGN['strategies']
HOURLY={}


def load(symbol,tf):
    p=DATA/f'{symbol}_USDT-{tf}.feather'
    frame=pd.read_feather(p).sort_values('date').drop_duplicates('date').reset_index(drop=True)
    if frame.empty:raise ValueError(f'No data: {symbol} {tf}')
    if frame['date'].dt.tz is None:raise ValueError('Timezone missing')
    if not np.isfinite(frame[['open','high','low','close','volume']].to_numpy()).all():raise ValueError('Nonfinite OHLCV')
    if (frame[['open','high','low','close']]<=0).any().any():raise ValueError('Invalid prices')
    step={'1h':'1h','4h':'4h','1d':'1d'}[tf]
    if tf!='1h' and not frame['date'].diff().dropna().eq(pd.Timedelta(step)).all():raise ValueError(f'Gaps in {symbol} {tf}')
    return frame


def features(symbol):
    f=load(symbol,'4h')
    d=load(symbol,'1d')
    d['daily50']=ta.EMA(d,timeperiod=50);d['daily200']=ta.EMA(d,timeperiod=200)
    d['daily_bear2']=(d['close']<d['daily200'])&(d['close'].shift(1)<d['daily200'].shift(1))
    d['available_at']=d['date']+pd.Timedelta('1d')
    for n in (20,50,100,200):f[f'ema{n}']=ta.EMA(f,timeperiod=n)
    f['rsi']=ta.RSI(f);f['adx']=ta.ADX(f);f['atr']=ta.ATR(f);f['hist']=ta.MACD(f)['macdhist']
    f['rvol']=f['volume']/f['volume'].shift(1).rolling(20).mean()
    f['support']=f['low'].shift(1).rolling(20).min()
    f['resistance']=f['high'].shift(1).rolling(20).max()
    f['broken']=(f['close']<f['support'])&(f['close'].shift(1)<f['support'].shift(1))
    f['higher']=(f['close'].rolling(5).min()>f['close'].shift(5).rolling(5).min())&(f['close'].rolling(5).max()>f['close'].shift(5).rolling(5).max())
    f['decision_at']=f['date']+pd.Timedelta('4h')
    f=pd.merge_asof(f,d[['available_at','daily50','daily200','daily_bear2']],left_on='decision_at',right_on='available_at',direction='backward')
    f['b_trend']=(f['close']>f['ema200'])&(f['ema20']>f['ema50'])&(f['hist']>0)&(f['close']>f['daily200'])
    f['c_pullback']=(f['close']>f['daily200'])&f['rsi'].between(40,60)&(f['rsi'].shift(1)<40)&(f['hist']>0)&(f['rvol']>=1.1)
    f['d_breakout']=(f['close']>f['resistance'])&(f['close'].shift(1)<=f['resistance'].shift(1))&(f['rvol']>=1.5)&(f['close']>f['daily200'])&(f['adx']>=20)
    f['e_exit']=f['broken']&(f['rvol']>=1.5)&(f['close']<f['daily50'])&(f['hist']<0)
    f['f_trend']=(f['close']>f['ema50'])&(f['ema20']>f['ema50'])
    f['f_daily']=f['close']>f['daily200']
    f['f_momentum']=(f['hist']>0)&f['rsi'].between(40,68)
    f['f_volume']=f['rvol']>=1.1;f['f_structure']=f['higher'];f['f_strength']=f['adx']>=20
    f['score']=sum(f[c].astype(int) for c in ('f_trend','f_daily','f_momentum','f_volume','f_structure','f_strength'))
    f['warm']=f['ema200'].notna()&f['daily200'].notna()
    f['retest']=(f['close'].shift(1)>f['resistance'].shift(1))&(f['low']<=f['resistance'].shift(1)*1.01)&(f['close']>=f['resistance'].shift(1))
    return f.set_index('date')


def with_cost_signals(f,fee=.01,spread=.001,slip=.001):
    f=f.copy()
    factor=(1-fee)*(1-spread-slip)/((1+fee)*(1+spread+slip))
    f['net_gain']=f['resistance']/f['close']*factor-1
    f['net_loss']=1-(f['support']-1.5*f['atr'])/f['close']*factor
    f['net_rr']=f['net_gain']/f['net_loss']
    f['gate_score']=f['score']>=5
    f['gate_gain']=f['net_gain']>=DESIGN['min_net_edge']
    f['gate_rr']=f['net_rr']>=DESIGN['min_net_rr']
    f['gate_volume']=f['volume']>0
    f['f_combined']=f['gate_score']&f['gate_gain']&f['gate_rr']&f['gate_volume']&f['warm']
    return f


def simulate(frames,strategy,start,end,fee=.01,spread=.001,slip=.001,initial=8500,stake=1000):
    start,end=pd.Timestamp(start,tz='UTC'),pd.Timestamp(end,tz='UTC')
    index=pd.date_range(start,end,freq='4h',inclusive='left')
    full={s:with_cost_signals(f,fee,spread,slip) for s,f in frames.items()}
    data={s:f.reindex(index) for s,f in full.items()}
    # Lag decisions one row: a signal computed from this bar cannot fill at its open.
    entries={'A_hold':None,'B_trend':'b_trend','C_pullback':'c_pullback','D_breakout':'d_breakout','E_protective':'b_trend','F_combined_reentry':'f_combined'}
    signals={s:(f[entries[strategy]] & ~f['daily_bear2'].fillna(False)).shift(1).reindex(index).fillna(False).to_numpy(dtype=bool) if entries[strategy] else np.ones(len(index),dtype=bool) for s,f in full.items()}
    base_exit={s:f['daily_bear2'].shift(1).reindex(index).fillna(False).to_numpy(dtype=bool) for s,f in full.items()}
    protection={s:f['e_exit'].shift(1).reindex(index).fillna(False).to_numpy(dtype=bool) for s,f in full.items()}
    warm={s:f['warm'].shift(1).reindex(index).fillna(False).to_numpy(dtype=bool) for s,f in full.items()}
    retest={s:f['retest'].shift(1).reindex(index).fillna(False).to_numpy(dtype=bool) for s,f in full.items()}
    arrays={s:{c:f[c].to_numpy() for c in ('open','high','low','close')} for s,f in data.items()}
    hours=pd.date_range(start,end,freq='1h',inclusive='left')
    hourly={s:{c:HOURLY[s][c].reindex(hours).to_numpy().reshape(-1,4) for c in ('open','low')} for s,f in frames.items()}
    positions={};cash=initial;trades=[];marks=[];lastsale={};has_bought=set();fees=0.;friction=0.
    def close(s,mid,ts,why):
        nonlocal cash,fees,friction
        p=positions.pop(s)
        price=mid*(1-spread-slip)
        commission=p['qty']*price*fee
        net=p['qty']*price-commission
        cash+=net;fees+=commission;friction+=p['qty']*(mid-price)
        pnl=net-p['debit']
        trades.append(dict(symbol=s,entry_at=str(p['at']),exit_at=str(ts),entry_mid=p['mid'],exit_mid=mid,entry_price=p['price'],exit_price=price,qty=p['qty'],cash_debit=p['debit'],net_credit=net,pnl=pnl,return_pct=pnl/p['debit']*100,fees=p['fee']+commission,friction=p['friction']+p['qty']*(mid-price),reason=why))
        lastsale[s]=mid
    for i,ts in enumerate(index):
        # All simultaneous exits free cash before entries; entry ordering is fixed
        # design symbol order and is included in the manifest (no hindsight rank).
        just_closed=set()
        for s,p in list(positions.items()):
            o=arrays[s]['open'][i]
            if not np.isfinite(o):continue
            if strategy!='A_hold' and (base_exit[s][i] or (strategy in ('E_protective','F_combined_reentry') and protection[s][i])):
                close(s,o,ts,'protective' if protection[s][i] and strategy in ('E_protective','F_combined_reentry') else 'daily_bear2')
                just_closed.add(s)
        for s in data:
            o=arrays[s]['open'][i]
            if s in positions or s in just_closed or not np.isfinite(o) or cash<10:continue
            if ts<HOURLY[s].index.min().ceil('4h'):continue
            if strategy=='A_hold':
                enter=s not in has_bought
            else:
                enter=signals[s][i] and warm[s][i]
            if strategy=='F_combined_reentry' and s in lastsale:
                edge=lastsale[s]*(1-fee)*(1-spread-slip)/(o*(1+fee)*(1+spread+slip))-1
                enter=enter and edge>=DESIGN['min_net_edge'] and retest[s][i]
            if not enter:continue
            debit=min(stake,cash)
            price=o*(1+spread+slip);qty=debit/(1+fee)/price
            commission=qty*price*fee;impact=qty*(price-o)
            cash-=debit;fees+=commission;friction+=impact
            positions[s]=dict(qty=qty,price=price,mid=o,debit=debit,fee=commission,friction=impact,at=ts)
            has_bought.add(s)
        # Stops use 1H low to avoid assuming the order of 4H intrabar movements.
        # Market gaps fill at the worse of hourly open and stop. Hold has no stop.
        for s,p in list(positions.items()):
            if strategy=='A_hold':continue
            stop=p['mid']*(1-DESIGN['hard_stop'])
            lows=hourly[s]['low'][i]
            if not np.isfinite(lows).all() or not np.isfinite(hourly[s]['open'][i]).all():raise ValueError('Missing required 1H detail while invested')
            hit=np.flatnonzero(lows<=stop)
            if len(hit):
                j=hit[0];close(s,min(stop,hourly[s]['open'][i,j]),ts+pd.Timedelta(hours=int(j)),'hard_stop')
        equity=cash
        for s,p in positions.items():
            c=arrays[s]['close'][i]
            if not np.isfinite(c):raise ValueError('Missing close while invested')
            equity+=p['qty']*c*(1-spread-slip)*(1-fee)
        marks.append(equity)
    for s,p in list(positions.items()):
        close(s,arrays[s]['close'][-1],end,'end_of_period')
    if marks:marks[-1]=cash
    curve=pd.Series(marks,index=index,dtype=float)
    peak=curve.cummax().clip(lower=initial)
    dd=(1-curve/peak).max()
    wins=[t['pnl'] for t in trades if t['pnl']>0];losses=[t['pnl'] for t in trades if t['pnl']<0]
    daily=curve.resample('1d').last();rs=daily.pct_change().dropna()
    # Include first day's return relative to the initial wallet.
    if len(daily):rs=pd.concat([pd.Series([daily.iloc[0]/initial-1],index=[daily.index[0]]),rs])
    std=rs.std();downside=math.sqrt((rs.clip(upper=0)**2).mean()) if len(rs) else 0
    metrics=dict(return_pct=(cash/initial-1)*100,max_drawdown_pct=float(dd*100),trades=len(trades),wins=len(wins),losses=len(losses),win_rate=len(wins)/len(trades) if trades else None,
                 avg_win=float(np.mean(wins)) if wins else None,avg_loss=float(np.mean(losses)) if losses else None,
                 profit_factor=sum(wins)/-sum(losses) if losses else None,fees=fees,spread_slippage_cost=friction,
                 sharpe=float(math.sqrt(365)*rs.mean()/std) if std and np.isfinite(std) else None,
                 sortino=float(math.sqrt(365)*rs.mean()/downside) if downside else None,final_equity=cash)
    return metrics,trades,curve
