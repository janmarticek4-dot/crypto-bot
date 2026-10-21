"""Frozen strategy matrix, ablations, robustness and past-only walk-forward."""
import hashlib
import importlib.metadata
import json
from pathlib import Path
import warnings
import numpy as np
import pandas as pd
from data import ROOT,DATA,load,alt_features,market_daily,global_history
from regime import classify,SPECS
from sim import Dataset,simulate

warnings.filterwarnings('ignore',category=FutureWarning)
OUT=ROOT/'docs/phase3';OUT.mkdir(exist_ok=True)
DESIGN=json.loads(Path(__file__).with_name('design.json').read_text())
ENTRIES=DESIGN['entry_types'];EXITS=DESIGN['exit_types']
PERIODS=[(str(y),f'{y}-01-01',f'{y+1}-01-01') for y in range(2021,2026)]+[('2026_seen','2026-01-01','2026-10-01'),('2026_short_holdout','2026-10-01','2026-10-21')]


def save(name,data):
    (OUT/name).write_text(json.dumps(data,indent=2,allow_nan=False)+'\n')


def select_model(rows):
    """Accept training metrics only; no test-period fields or prices."""
    eligible=[r for r in rows if r['trades']>=5 and r['max_drawdown_pct']<=20
              and r['return_pct']>0 and r['profit_factor'] is not None and r['profit_factor']>=1]
    return max(eligible,key=lambda r:(r['return_pct']-.5*r['max_drawdown_pct'],r['entry'],r['exit'])) if eligible else None


def prepare():
    hourly={s:load(s,'1h') for s in DESIGN['symbols']}
    daily={s:load(s,'1d') for s in DESIGN['symbols']}
    feat={s:alt_features(load(s,'4h'),daily[s]) for s in DESIGN['symbols']}
    market=market_daily(load('BTC','1d'),daily,global_history(OUT/'global_first_vintage.csv'))
    regimes={name:classify(market,groups=groups) for name,groups in SPECS.items()}
    regimes['raw']=classify(market,confirmation=1,dwell=1)
    for name,kwargs in {'confirm2':{'confirmation':2},'confirm5':{'confirmation':5},'dwell3':{'dwell':3},'dwell10':{'dwell':10},'band0':{'band':0},'band4':{'band':.04},'vol4':{'atr_guard':.04},'vol8':{'atr_guard':.08}}.items():regimes[name]=classify(market,**kwargs)
    ds=Dataset(hourly,feat,regimes)
    return ds,market,regimes


def run():
    save('manifest.json',{'status':'running'})
    ds,market,regimes=prepare()
    manifest={'status':'running','design':DESIGN,'design_sha256':hashlib.sha256(Path(__file__).with_name('design.json').read_bytes()).hexdigest(),'source_files':{},'code_sha256':{},'dependencies':{p:importlib.metadata.version(p) for p in ('freqtrade','ccxt','numpy','pandas','TA-Lib','matplotlib')}}
    for p in sorted(Path(__file__).parent.glob('*.py')):manifest['code_sha256'][p.name]=hashlib.sha256(p.read_bytes()).hexdigest()
    for s in DESIGN['symbols']+['BTC','ETH']:
        for tf in ('1h','4h','1d'):
            p=DATA/f'{s}_USDT-{tf}.feather';f=load(s,tf)
            manifest['source_files'][p.name]={'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'rows':len(f),'first':str(f.date.min()),'last':str(f.date.max()),'missing_intervals':int((f.date.diff()>pd.Timedelta(tf)).sum())}
    save('manifest.json',manifest)
    quality=[]
    for name,r in regimes.items():
        x=r[['date','available_at','close','raw_regime','regime','alt_breadth','breadth_count','adx','atr_pct']].copy()
        x['past30_peak_drawdown_pct']=(x.close/x.close.rolling(30).max()-1)*100
        x['future7_return_pct']=(x.close.shift(-7)/x.close-1)*100  # DIAGNOSTIC ONLY.
        x['future30_return_pct']=(x.close.shift(-30)/x.close-1)*100
        x.to_csv(OUT/f'regimes_{name}.csv.gz',index=False,compression={'method':'gzip','mtime':0})
        for label,start,end in PERIODS:
            sub=x[(x.available_at>=pd.Timestamp(start,tz='UTC'))&(x.available_at<pd.Timestamp(end,tz='UTC'))].copy()
            # Forward diagnostic labels must mature WITHIN the selected window.
            for horizon in (7,30):sub.loc[sub.available_at+pd.Timedelta(days=horizon)>=pd.Timestamp(end,tz='UTC'),f'future{horizon}_return_pct']=np.nan
            for state in (-1,0,1):
                group=sub[sub.regime==state]
                quality.append(dict(spec=name,period=label,regime=state,days=len(group),switches=int(sub.regime.diff().fillna(0).ne(0).sum()),raw_switches=int(sub.raw_regime.diff().fillna(0).ne(0).sum()),mean_forward7_pct=float(group.future7_return_pct.mean()) if group.future7_return_pct.notna().any() else None,mean_forward30_pct=float(group.future30_return_pct.mean()) if group.future30_return_pct.notna().any() else None))
    pd.DataFrame(quality).to_csv(OUT/'regime_quality.csv',index=False)
    records=[];trades=[]
    def evaluate(category,period,entry,exit_type,**kw):
        name,start,end=period
        m,t,c=simulate(ds,entry,exit_type,start,end,**kw)
        ident=category+':'+name+':'+entry+':'+exit_type+':'+str(len(records))
        records.append(dict(id=ident,category=category,period=name,entry=entry,exit=exit_type,settings=json.dumps(kw,sort_keys=True),**m))
        if category=='main':trades.extend(dict(run=ident,period=name,entry_type=entry,exit_type=exit_type,**x) for x in t)
        return m,t,c
    for period in PERIODS:
        evaluate('baseline',period,'hold','fixed')
        evaluate('baseline_fully_allocated',period,'hold','fixed',hold_at_start=True)
        for entry in ENTRIES:
            for exit_type in EXITS:evaluate('main',period,entry,exit_type)
        print('Main:',period[0],flush=True)
    for period in PERIODS[:-1]:
        for entry in ENTRIES:
            for name in SPECS:
                if name=='full':continue
                evaluate('ablation',period,entry,'hybrid',regime=name)
            evaluate('ablation',period,entry,'hybrid',regime_filter=False)
        print('Ablations:',period[0],flush=True)
    sensitivity=[('raw',dict(regime='raw')),('confirm2',dict(regime='confirm2')),('confirm5',dict(regime='confirm5')),('dwell3',dict(regime='dwell3')),('dwell10',dict(regime='dwell10')),('band0',dict(regime='band0')),('band4',dict(regime='band4')),('vol4',dict(regime='vol4')),('vol8',dict(regime='vol8')),('regime_lag3',dict(regime_delay_days=3)),('regime_lag7',dict(regime_delay_days=7)),('stop15',dict(stop=.15)),('stop25',dict(stop=.25)),('atr2',dict(atr_multiple=2)),('atr4',dict(atr_multiple=4)),('trail15',dict(trailing=.15)),('trail25',dict(trailing=.25)),('high_cost',dict(spread=.002,slip=.003)),('extreme_cost',dict(spread=.005,slip=.005))]
    for period in PERIODS[:-1]:
        for name,kw in sensitivity:
            # Changing ATR/trailing parameters must exercise that exit, not hybrid.
            exit_type='atr' if name.startswith('atr') else 'trailing' if name.startswith('trail') else 'hybrid'
            evaluate('sensitivity_'+name,period,'pullback',exit_type,**kw)
        for entry in ENTRIES:
            for delay in (0,4,12):evaluate('manual_delay',period,entry,'hybrid',delay=delay)
        print('Robustness:',period[0],flush=True)
    # Keep all full-run candidate results before selecting walk-forward models.
    save('results.json',records);pd.DataFrame(records).to_csv(OUT/'results.csv',index=False)
    pd.DataFrame(trades).to_csv(OUT/'trades.csv.gz',index=False,compression={'method':'gzip','mtime':0})
    folds=[];training=[];wf_curves=[];wf_trades=[];wealth=8500.
    for start in pd.date_range('2022-01-01','2026-07-01',freq='6MS'):
        start=start.tz_localize('UTC');train_start=start-pd.DateOffset(months=6)
        end=min(start+pd.DateOffset(months=6),pd.Timestamp('2026-10-01',tz='UTC'))
        ts,te=train_start.strftime('%Y-%m-%d'),start.strftime('%Y-%m-%d')
        candidates=[]
        for entry in ENTRIES:
            for exit_type in EXITS:
                m,_,_=simulate(ds,entry,exit_type,ts,te)
                row=dict(fold=te,train_start=ts,train_end=te,entry=entry,exit=exit_type,**m)
                ok=m['trades']>=5 and m['max_drawdown_pct']<=20 and m['return_pct']>0 and m['profit_factor'] is not None and m['profit_factor']>=1
                row['eligible']=ok;row['score']=m['return_pct']-.5*m['max_drawdown_pct'];training.append(row)
                candidates.append(row)
        chosen=select_model(candidates)
        if chosen:
            m,t,curve=simulate(ds,chosen['entry'],chosen['exit'],te,end.strftime('%Y-%m-%d'),initial=wealth,keep_curve=True)
            strategy=chosen['entry']+'/'+chosen['exit']
            wf_trades.extend(dict(test_start=te,strategy=strategy,**trade) for trade in t)
        else:
            length=int((end-start).total_seconds()/3600);curve=np.full(length,wealth)
            m=dict(return_pct=0.,max_drawdown_pct=0.,trades=0,profit_factor=None,fees=0.,final_equity=wealth,mean_exposure_pct=0.)
            strategy='CASH'
        baseline,_,_=simulate(ds,'hold','fixed',te,end.strftime('%Y-%m-%d'),initial=wealth)
        folds.append(dict(test_start=te,test_end=end.strftime('%Y-%m-%d'),train_start=ts,train_end=te,chosen=strategy,train_score=chosen['score'] if chosen else None,starting_equity=wealth,hold_return_pct=baseline['return_pct'],**m))
        wf_curves.extend(zip(pd.date_range(start,end,freq='1h',inclusive='left')+pd.Timedelta('1h'),curve))
        wealth=m['final_equity']
        print('Walk forward:',te,strategy,round(m['return_pct'],2),flush=True)
    pd.DataFrame(training).to_csv(OUT/'walk_forward_training.csv',index=False)
    pd.DataFrame(folds).to_csv(OUT/'walk_forward.csv',index=False)
    pd.DataFrame(wf_curves,columns=['time','equity']).to_csv(OUT/'walk_forward_curve.csv.gz',index=False,compression={'method':'gzip','mtime':0})
    pd.DataFrame(wf_trades).to_csv(OUT/'walk_forward_trades.csv',index=False)
    curves=np.array([x[1] for x in wf_curves]);peak=np.maximum.accumulate(np.r_[8500,curves])[1:]
    hold,_,hold_curve=simulate(ds,'hold','fixed','2022-01-01','2026-10-01',keep_curve=True)
    pd.DataFrame({'time':[x[0] for x in wf_curves],'equity':hold_curve}).to_csv(OUT/'walk_forward_hold_curve.csv.gz',index=False,compression={'method':'gzip','mtime':0})
    wins=sum(t['pnl'] for t in wf_trades if t['pnl']>0);losses=-sum(t['pnl'] for t in wf_trades if t['pnl']<0)
    save('walk_forward_summary.json',dict(return_pct=(wealth/8500-1)*100,max_drawdown_pct=float(np.max(1-curves/peak)*100),profit_factor=wins/losses if losses else None,trades=len(wf_trades),fees=sum(t['fees'] for t in wf_trades),spread_slippage=sum(t['friction'] for t in wf_trades),folds=len(folds),cash_folds=sum(x['chosen']=='CASH' for x in folds),hold_continuous=hold))
    # Same predeclared selector, trained strictly before the short holdout.
    candidates=[]
    for entry in ENTRIES:
        for exit_type in EXITS:
            m,_,_=simulate(ds,entry,exit_type,'2026-04-01','2026-10-01')
            candidates.append(dict(entry=entry,exit=exit_type,**m))
    pd.DataFrame(candidates).to_csv(OUT/'final_holdout_training.csv',index=False)
    chosen=select_model(candidates)
    if chosen:
        final,_,_=simulate(ds,chosen['entry'],chosen['exit'],'2026-10-01','2026-10-21',initial=wealth)
        selected=chosen['entry']+'/'+chosen['exit']
    else:
        final=dict(return_pct=0.,max_drawdown_pct=0.,trades=0,profit_factor=None,final_equity=wealth)
        selected='CASH'
    save('final_policy.json',dict(train_start='2026-04-01',train_end='2026-10-01',test_start='2026-10-01',test_end_exclusive='2026-10-21',chosen=selected,metrics=final))
    manifest['status']='complete'
    manifest['artifacts_sha256']={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(OUT.iterdir()) if p.suffix in ('.csv','.gz','.json') and p.name.startswith(('regimes_','regime_quality.','results.','trades.','walk_forward','final_'))}
    save('manifest.json',manifest)
    print('COMPLETE',len(records),'matrix runs,',len(training),'walk-forward training runs,',len(folds),'test folds',flush=True)

if __name__=='__main__':run()
