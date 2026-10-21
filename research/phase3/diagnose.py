"""Post-hoc diagnostics only. Forward returns here never enter signal generation."""
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd
from data import ROOT,load

OUT=ROOT/'docs/phase3'

def analyze():
    r=pd.read_csv(OUT/'results.csv');t=pd.read_csv(OUT/'trades.csv.gz')
    main=r[r.category=='main'];seen=main[main.period!='2026_short_holdout']
    base=r[r.category=='baseline'].set_index('period')
    rows=[]
    for (entry,exit_type),g in seen.groupby(['entry','exit']):
        h=g.period.map(base.return_pct);d=g.period.map(base.max_drawdown_pct)
        rows.append(dict(entry=entry,exit=exit_type,periods=len(g),positive_periods=int((g.return_pct>0).sum()),
            beat_hold_periods=int((g.return_pct.to_numpy()>h.to_numpy()).sum()),
            median_hold_alpha_pp=float(np.median(g.return_pct.to_numpy()-h.to_numpy())),
            median_dd_reduction_pp=float(np.median(d.to_numpy()-g.max_drawdown_pct.to_numpy())),
            worst_return_pct=float(g.return_pct.min()),max_drawdown_pct=float(g.max_drawdown_pct.max()),
            trades=int(g.trades.sum()),mean_exposure_pct=float(g.mean_exposure_pct.mean())))
    pd.DataFrame(rows).to_csv(OUT/'strategy_stability.csv',index=False)
    # Paired feature ablation: same period, entry, exit, costs, capital.
    ab=[]
    for _,x in r[r.category=='ablation'].iterrows():
        full=main[(main.period==x.period)&(main.entry==x.entry)&(main.exit==x.exit)].iloc[0]
        setting=json.loads(x.settings);name=setting.get('regime','no_entry_regime_filter')
        ab.append(dict(period=x.period,entry=x.entry,spec=name,return_pct=x.return_pct,max_drawdown_pct=x.max_drawdown_pct,
            delta_return_pp=x.return_pct-full.return_pct,delta_drawdown_pp=x.max_drawdown_pct-full.max_drawdown_pct,trades=x.trades))
    pd.DataFrame(ab).to_csv(OUT/'ablation_pairs.csv',index=False)
    sr=[]
    for _,x in r[r.category.str.startswith('sensitivity_')|r.category.eq('manual_delay')].iterrows():
        full=main[(main.period==x.period)&(main.entry==x.entry)&(main.exit==x.exit)].iloc[0]
        sr.append(dict(variant=x.category.removeprefix('sensitivity_'),settings=x.settings,period=x.period,entry=x.entry,exit=x.exit,
            return_pct=x.return_pct,max_drawdown_pct=x.max_drawdown_pct,trades=x.trades,
            delta_return_pp=x.return_pct-full.return_pct,delta_drawdown_pp=x.max_drawdown_pct-full.max_drawdown_pct))
    pd.DataFrame(sr).to_csv(OUT/'robustness_pairs.csv',index=False)
    # Simulated trades pooled across overlapping alternatives; never add as a portfolio.
    hourly={s:load(s,'1h').set_index('date') for s in t.symbol.unique()}
    diagnostics=[]
    for _,x in t.iterrows():
        end=pd.Timestamp('2026-10-21' if x.period=='2026_short_holdout' else '2026-10-01' if x.period=='2026_seen' else f'{int(x.period)+1}-01-01',tz='UTC')
        at=pd.Timestamp(x.exit_at);future=at+pd.Timedelta('7D');f=hourly[x.symbol]
        forward=None;lower=None;complete=False
        if x.reason!='scheduled_end' and future<end and future in f.index:
            forward=(float(f.loc[future,'close'])/x.exit_mid-1)*100
            window=f.loc[(f.index>=at)&(f.index<future)]
            complete=len(window)==168
            if complete:lower=float(window.low.min())/x.exit_mid
        # Sale and re-buy frictions: quantity is preserved only below this ratio.
        breakeven=.998*.99/(1.002*1.01)
        diagnostics.append(dict(run=x.run,period=x.period,symbol=x.symbol,entry=x.entry_type,exit=x.exit_type,
            reason=x.reason,pnl=x.pnl,return_pct=x.return_pct,fees=x.fees,friction=x.friction,holding_hours=x.holding_hours,
            initial_stop_pct=x.initial_stop_pct,forward7_pct=forward,complete_forward7_hours=complete,
            min_low7_to_exit=lower,rebound_without_cost_recovery=bool(forward>0 and lower>breakeven) if forward is not None and lower is not None else None))
    diag=pd.DataFrame(diagnostics);diag.to_csv(OUT/'trade_diagnostics.csv.gz',index=False,compression={'method':'gzip','mtime':0})
    grouped=[]
    for (exit_type,reason),g in diag[diag.period!='2026_short_holdout'].groupby(['exit','reason']):
        mature=g[g.forward7_pct.notna()];complete=mature[mature.complete_forward7_hours]
        grouped.append(dict(exit=exit_type,reason=reason,trades=len(g),losing_trades=int((g.pnl<0).sum()),
            mean_net_return_pct=g.return_pct.mean(),median_holding_hours=g.holding_hours.median(),
            median_initial_stop_pct=g.initial_stop_pct.median() if g.initial_stop_pct.notna().any() else None,
            mean_cost_usd=(g.fees+g.friction).mean(),mature7=len(mature),rebounded7=int((mature.forward7_pct>0).sum()),
            complete7=len(complete),rebound_without_cost_recovery=int(complete.rebound_without_cost_recovery.eq(True).sum())))
    pd.DataFrame(grouped).to_csv(OUT/'exit_diagnostics.csv',index=False)
    coin=[]
    for (period,entry,exit_type,symbol),g in t.groupby(['period','entry_type','exit_type','symbol']):
        wins=g[g.pnl>0].pnl.sum();losses=-g[g.pnl<0].pnl.sum()
        coin.append(dict(period=period,entry=entry,exit=exit_type,symbol=symbol,trades=len(g),pnl_usd=g.pnl.sum(),fees_usd=g.fees.sum(),friction_usd=g.friction.sum(),profit_factor=wins/losses if losses else None,average_win=g[g.pnl>0].pnl.mean(),average_loss=g[g.pnl<0].pnl.mean()))
    pd.DataFrame(coin).to_csv(OUT/'coin_contributions.csv',index=False)
    # Per-coin contributions share the original cash-constrained wallet.
    regime=pd.read_csv(OUT/'regimes_full.csv.gz',parse_dates=['date','available_at'])
    shifts=regime.regime.ne(regime.regime.shift());bear=regime[shifts&regime.regime.eq(-1)]
    bear[['date','available_at','close','past30_peak_drawdown_pct']].to_csv(OUT/'bear_transitions.csv',index=False)
    curve=pd.read_csv(OUT/'walk_forward_curve.csv.gz',parse_dates=['time']).set_index('time').equity
    day=curve.resample('1D',closed='right',label='right').last().dropna();goals=[]
    for n in (90,180):
        changes=(day/day.shift(n)-1)*100;changes=changes.dropna()
        goals.append(dict(window_days=n,overlapping_windows=len(changes),windows_at_least_100_pct=int((changes>=100).sum()),median_return_pct=changes.median(),worst_return_pct=changes.min()))
    (OUT/'goal_windows.json').write_text(json.dumps(goals,indent=2,allow_nan=False)+'\n')
    print('Diagnostics complete:',len(diag),'simulated alternative trades')

if __name__=='__main__':analyze()
