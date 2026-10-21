"""Hourly manual-execution research engine. No broker/Telegram imports.
A closed 4H signal can fill at its availability time + manual delay. Stops
observed from hourly lows are acted upon only after that hour closes + delay.
Trailing thresholds use prior completed highs, never a same-hour high/low order.
"""
import math
import numpy as np
import pandas as pd


class Dataset:
    def __init__(self,hourly,features,regimes,start='2020-01-01',end='2026-10-21'):
        self.index=pd.date_range(start,end,freq='1h',tz='UTC',inclusive='left')
        self.symbols=list(hourly);self.coins={};self.regimes={}
        left=pd.DataFrame({'time':self.index})
        for symbol,h in hourly.items():
            raw=h.set_index('date').reindex(self.index)
            feat=features[symbol].sort_values('available_at')
            cols=['available_at','atr','pullback','breakout','retest','momentum','strong_neutral']
            merged=pd.merge_asof(left,feat[cols],left_on='time',right_on='available_at',direction='backward')
            # Pulses only at the actual close of a new 4H candle.
            pulse=(merged['time']==merged['available_at']).to_numpy()
            self.coins[symbol]={c:raw[c].to_numpy(dtype=float) for c in ('open','high','low','close')}
            for c in ('pullback','breakout','retest','momentum','strong_neutral'):
                self.coins[symbol][c]=merged[c].fillna(False).to_numpy(dtype=bool)&pulse
            self.coins[symbol]['atr']=merged['atr'].to_numpy(dtype=float)
        self.any_signal={entry:np.logical_or.reduce([c[entry] for c in self.coins.values()]) for entry in ('pullback','breakout','retest','momentum')}
        for name,r in regimes.items():
            merged=pd.merge_asof(left,r[['available_at','regime']],left_on='time',right_on='available_at',direction='backward')
            self.regimes[name]=merged['regime'].fillna(0).to_numpy(dtype=np.int8)


def simulate(ds,entry,exit_type,start,end,regime='full',delay=1,stop=.20,atr_multiple=3.,trailing=.20,
             fee=.01,spread=.001,slip=.001,initial=8500.,stake_fraction=1000/8500,cooldown=24,
             regime_delay_days=0,keep_curve=False,regime_filter=True,hold_at_start=False):
    a=ds.index.searchsorted(pd.Timestamp(start,tz='UTC'));b=ds.index.searchsorted(pd.Timestamp(end,tz='UTC'))
    n=b-a
    if n<=0:raise ValueError('Empty simulation period')
    labels=ds.regimes[regime]
    hold_universe={s for s,c in ds.coins.items() if np.isfinite(c['open'][a])} if hold_at_start else set(ds.coins)
    if entry=='hold' and hold_at_start and hold_universe:stake_fraction=1/len(hold_universe)
    cash=initial;positions={};buys={};sells={};last_exit={};last_quote={};has_bought=set()
    trades=[];equities=[];exposures=[];stale_count=0;cancelled=0;fees_total=0.;friction=0.
    def label(i):return int(labels[max(0,i-regime_delay_days*24)])
    def close(symbol,mid,i,reason):
        nonlocal cash,fees_total,friction
        p=positions.pop(symbol)
        price=mid*(1-spread-slip);commission=p['qty']*price*fee
        credit=p['qty']*price-commission;cash+=credit;fees_total+=commission;friction+=p['qty']*(mid-price)
        trades.append(dict(symbol=symbol,signal_at=str(ds.index[p['signal']]),entry_at=str(ds.index[p['i']]),exit_at=str(ds.index[i]+(pd.Timedelta('1h') if reason=='scheduled_end' else pd.Timedelta(0))),entry_mid=p['mid'],exit_mid=mid,
            debit=p['debit'],credit=credit,pnl=credit-p['debit'],return_pct=(credit/p['debit']-1)*100,
            fees=p['fee']+commission,friction=p['friction']+p['qty']*(mid-price),reason=reason,
            initial_stop_pct=p['initial_stop_pct'],stop_mid=p['stop'] if np.isfinite(p['stop']) else None,
            holding_hours=i-p['i']+(1 if reason=='scheduled_end' else 0),
            entry_regime=p['regime'],exit_regime=label(i),trigger_at=str(ds.index[0]+pd.Timedelta(hours=sells[symbol][0])) if symbol in sells else None))
        last_exit[symbol]=i;sells.pop(symbol,None);buys.pop(symbol,None)
    def execute_sells(i):
        for s,(trigger,due,reason) in list(sells.items()):
            op=ds.coins[s]['open'][i]
            if due<=i and np.isfinite(op):close(s,op,i,reason)
    for i in range(a,b):
        regime_now=label(i)
        if entry!='hold' and not positions and not buys and not ds.any_signal[entry][i]:
            equities.append(cash);exposures.append(0.);continue
        # Known at hour OPEN: daily regime and gaps below old protective level.
        for s,p in list(positions.items()):
            op=ds.coins[s]['open'][i]
            if s in sells:continue
            if entry!='hold' and exit_type in ('regime','hybrid') and regime_now==-1:
                sells[s]=(i,i+delay,'bear_regime')
            elif np.isfinite(op) and exit_type!='regime' and op<=p['stop']:
                sells[s]=(i,i+delay,'stop_gap')
        execute_sells(i)
        for s,c in ds.coins.items():
            if entry=='hold' and s not in hold_universe:continue
            if s in positions or s in buys or i-last_exit.get(s,-100000)<cooldown:continue
            signal=entry=='hold' and s not in has_bought and np.isfinite(c['open'][i]) or entry!='hold' and c[entry][i]
            if not signal:continue
            if entry=='hold':allowed=True
            elif not regime_filter:allowed=True
            else:allowed=regime_now==1 or (regime_now==0 and entry in ('breakout','retest') and c['strong_neutral'][i])
            if allowed:buys[s]=(i,i+delay,regime_now,c['atr'][i],bool(c['strong_neutral'][i]))
        for s,(signal,due,signal_regime,atr,strong) in list(buys.items()):
            if i<due:continue
            c=ds.coins[s];op=c['open'][i]
            allowed=entry=='hold' or not regime_filter or regime_now==1 or (regime_now==0 and entry in ('breakout','retest') and strong)
            if not allowed or i-signal>24:
                buys.pop(s);cancelled+=1;continue
            if not np.isfinite(op):continue
            # A hold signal may wait for the actual historical listing.
            if entry!='hold' and (not np.isfinite(atr) or atr<=0):buys.pop(s);cancelled+=1;continue
            equity=cash
            invested=0.
            for other,p in positions.items():
                mark=ds.coins[other]['open'][i]
                if not np.isfinite(mark):mark=last_quote.get(other,p['mid'])
                invested+=p['qty']*mark*(1-spread-slip)*(1-fee)
            equity+=invested
            cap=1. if entry=='hold' or not regime_filter else .70 if regime_now==1 else .25 if regime_now==0 else 0.
            debit=min(initial*stake_fraction,cash,max(0.,cap*equity-invested))
            if debit<50:buys.pop(s);cancelled+=1;continue
            price=op*(1+spread+slip);qty=debit/(1+fee)/price
            commission=qty*price*fee;impact=qty*(price-op)
            threshold=op*(1-stop)
            if exit_type=='trailing':threshold=op*(1-trailing)
            if exit_type=='atr':threshold=max(1e-9,op-atr_multiple*atr)
            if exit_type=='regime':threshold=-np.inf
            if entry=='hold':threshold=-np.inf
            cash-=debit;fees_total+=commission;friction+=impact
            positions[s]=dict(qty=qty,mid=op,stop=threshold,initial_stop_pct=(1-threshold/op)*100 if np.isfinite(threshold) else None,peak=op,i=i,signal=signal,debit=debit,fee=commission,friction=impact,regime=regime_now)
            has_bought.add(s);buys.pop(s)
        # Known only after hour CLOSE: hourly low/high. Never fill at that low.
        for s,p in list(positions.items()):
            c=ds.coins[s]
            if not np.isfinite(c['close'][i]):stale_count+=1;continue
            last_quote[s]=c['close'][i]
            if entry!='hold' and s not in sells and c['low'][i]<=p['stop']:
                sells[s]=(i+1,i+1+delay,'stop_observed')
            # Threshold raised by THIS completed high applies to the NEXT hour.
            if exit_type=='trailing' and entry!='hold':
                p['peak']=max(p['peak'],c['high'][i]);p['stop']=max(p['stop'],p['peak']*(1-trailing))
        equity=cash;invested=0.
        for s,p in positions.items():
            mark=last_quote.get(s,p['mid'])
            invested+=p['qty']*mark*(1-spread-slip)*(1-fee)
        equities.append(equity+invested);exposures.append(invested/(equity+invested) if equity+invested else 0.)
    # Ex-ante scheduled boundary liquidation, not an executable forecast signal.
    # Mark at the last actual quote, with explicit staleness if exchange is absent.
    for s,p in list(positions.items()):
        if not np.isfinite(ds.coins[s]['close'][b-1]):raise ValueError('Cannot liquidate at a stale boundary quote')
        close(s,ds.coins[s]['close'][b-1],b-1,'scheduled_end')
    equities[-1]=cash
    curve=np.array(equities);peak=np.maximum.accumulate(np.r_[initial,curve])[1:]
    drawdown=np.max(1-curve/peak)*100
    pnls=[t['pnl'] for t in trades];wins=[x for x in pnls if x>0];losses=[x for x in pnls if x<0]
    metrics=dict(return_pct=(cash/initial-1)*100,max_drawdown_pct=float(drawdown),trades=len(trades),
        profit_factor=sum(wins)/-sum(losses) if losses else None,win_rate=len(wins)/len(trades) if trades else None,
        fees=fees_total,spread_slippage=friction,mean_exposure_pct=float(np.mean(exposures)*100),
        average_win=float(np.mean(wins)) if wins else None,average_loss=float(np.mean(losses)) if losses else None,
        stale_position_hours=stale_count,cancelled_entries=cancelled,final_equity=cash)
    return metrics,trades,curve if keep_curve else None
