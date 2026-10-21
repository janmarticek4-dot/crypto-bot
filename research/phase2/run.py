import gzip
import hashlib
import importlib.metadata
import json
import warnings
from pathlib import Path
import pandas as pd
from engine import ROOT, DATA, DESIGN, STRATEGIES, HOURLY, features, load, simulate, with_cost_signals

warnings.filterwarnings('ignore',category=FutureWarning)
OUT=ROOT/'docs/phase2'
OUT.mkdir(exist_ok=True)


def main():
    (OUT/'manifest.json').write_text(json.dumps({'status':'running'})+'\n')
    frames={s:features(s) for s in DESIGN['symbols']}
    for s,f in frames.items():HOURLY[s]=load(s,'1h').set_index('date')
    manifest={'status':'running','design':DESIGN,'files':{},'code_sha256':hashlib.sha256(Path(__file__).with_name('engine.py').read_bytes()).hexdigest()}
    manifest['dependencies']={p:importlib.metadata.version(p) for p in ('freqtrade','ccxt','pandas','numpy','TA-Lib')}
    for s in frames:
        for tf in ('1h','4h','1d'):
            p=DATA/f'{s}_USDT-{tf}.feather';f=load(s,tf)
            manifest['files'][p.name]={'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'rows':len(f),'first':str(f['date'].min()),'last':str(f['date'].max())}
    (OUT/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    periods=[('train_2024','2024-01-01','2025-01-01'),('seen_2025','2025-01-01','2026-01-01'),('holdout_2026','2026-01-01','2026-10-01')]
    modes=[('etoro',.01,.001,.001),('no_etoro_fee',0,.001,.001),('frictionless',0,0,0)]
    records=[];all_trades=[];gate_counts=[]
    logs=[]
    for symbol,raw in frames.items():
        f=with_cost_signals(raw)
        cols=['close','score','warm','f_trend','f_daily','f_momentum','f_volume','f_structure','f_strength','net_gain','net_loss','net_rr','gate_score','gate_gain','gate_rr','gate_volume','f_combined']
        out=f.loc[(f.index>=pd.Timestamp('2024-01-01',tz='UTC'))&(f.index<pd.Timestamp('2026-10-01',tz='UTC')),cols].copy()
        out.insert(0,'symbol',symbol)
        out['blockers']=[';'.join(c for c in ('warm','gate_score','gate_gain','gate_rr','gate_volume') if not bool(row[c])) for _,row in out.iterrows()]
        logs.append(out.reset_index())
        for label,start,end in periods:
            sub=out.loc[(out.index>=pd.Timestamp(start,tz='UTC'))&(out.index<pd.Timestamp(end,tz='UTC'))]
            gate_counts.append(dict(symbol=symbol,period=label,rows=len(sub),warm=int(sub['warm'].sum()),score=int(sub['gate_score'].sum()),gain=int(sub['gate_gain'].sum()),rr=int(sub['gate_rr'].sum()),all_pass=int(sub['f_combined'].sum()),score_and_gain=int((sub['gate_score']&sub['gate_gain']).sum()),score_and_rr=int((sub['gate_score']&sub['gate_rr']).sum())))
    pd.concat(logs).to_csv(OUT/'combined_candidates.csv.gz',index=False,compression={'method':'gzip','mtime':0})
    pd.DataFrame(gate_counts).to_csv(OUT/'combined_gate_counts.csv',index=False)
    for label,start,end in periods:
        for mode,fee,spread,slip in modes:
            for strategy in STRATEGIES:
                metrics,trades,curve=simulate(frames,strategy,start,end,fee,spread,slip)
                rec=dict(period=label,mode=mode,strategy=strategy,scope='portfolio',**metrics)
                records.append(rec)
                print(label,mode,strategy,round(metrics['return_pct'],2),metrics['trades'],flush=True)
                all_trades.extend(dict(period=label,mode=mode,strategy=strategy,scope='portfolio',**t) for t in trades)
                if mode=='etoro':curve.rename('equity').to_csv(OUT/f'curve_{label}_{strategy}.csv.gz',compression={'method':'gzip','mtime':0})
                for symbol in frames:
                    m,ts,_=simulate({symbol:frames[symbol]},strategy,start,end,fee,spread,slip,initial=1000,stake=1000)
                    records.append(dict(period=label,mode=mode,strategy=strategy,scope=symbol,**m))
                    all_trades.extend(dict(period=label,mode=mode,strategy=strategy,scope=symbol,**t) for t in ts)
    (OUT/'comparisons.json').write_text(json.dumps(records,indent=2,allow_nan=False)+'\n')
    pd.DataFrame(records).to_csv(OUT/'comparisons.csv',index=False)
    pd.DataFrame(all_trades).to_csv(OUT/'research_trades.csv.gz',index=False,compression={'method':'gzip','mtime':0})
    manifest['status']='complete'
    manifest['artifacts_sha256']={name:hashlib.sha256((OUT/name).read_bytes()).hexdigest() for name in ('comparisons.json','research_trades.csv.gz','combined_candidates.csv.gz')}
    (OUT/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print('Research complete:',len(records),'metric rows',len(all_trades),'closed trades',flush=True)

if __name__=='__main__':main()
