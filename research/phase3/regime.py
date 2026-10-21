"""Daily BULL/NEUTRAL/BEAR classifier with causal confirmation and dwell."""
import math
import numpy as np
import pandas as pd

NEUTRAL=0;BULL=1;BEAR=-1
GROUPS=('momentum','adx','volume','relative','volatility')
EXTRA=('global_cap','dominance')
SPECS={'full':GROUPS+EXTRA,'trend_only':()}
for group in GROUPS:SPECS['no_'+group]=tuple(g for g in GROUPS+EXTRA if g!=group)


def classify(f,groups=GROUPS+EXTRA,confirmation=3,dwell=5,band=.02,atr_guard=.06):
    f=f.copy()
    bull=(f.close>f.ema200*(1+band))&(f.ema50>f.ema200)&(f.ema50_slope>0)
    bear=(f.close<f.ema200*(1-band))&((f.ema50<f.ema200)|((f.momentum30<-.10)&(f.close<f.ema50)))
    bv=np.zeros(len(f));sv=np.zeros(len(f));valid=np.zeros(len(f))
    votes={
        'momentum':(f.momentum30>0,f.momentum30<0,f.momentum30.notna()),
        'adx':((f.adx>=20)&bull,(f.adx>=20)&bear,f.adx.notna()),
        'volume':((f.relative_volume>=1.1)&(f.return1>0),(f.relative_volume>=1.1)&(f.return1<0),f.relative_volume.notna()),
        'relative':(f.alt_breadth>=.6,f.alt_breadth<=.4,f.alt_breadth.notna()),
        'global_cap':(f.cap_momentum30>0,f.cap_momentum30<0,f.cap_momentum30.notna()),
        'dominance':(f.dominance_change30<=-.5,f.dominance_change30>=.5,f.dominance_change30.notna()),
    }
    for g in groups:
        if g=='volatility':continue
        b,s,v=votes[g];bv+=b.to_numpy();sv+=s.to_numpy();valid+=v.to_numpy()
    required=np.ceil(valid*.5)
    raw=np.where(bull&(bv>=required),BULL,np.where(bear&(sv>=required),BEAR,NEUTRAL))
    if 'volatility' in groups:raw=np.where((raw==BULL)&(f.atr_pct>atr_guard),NEUTRAL,raw)
    warm=f.ema200.notna()&f.ema50_slope.notna()
    raw=np.where(warm,raw,NEUTRAL)
    current=NEUTRAL;candidate=NEUTRAL;run=0;last_change=-dwell;out=[];lags=[]
    for i,target in enumerate(raw):
        if target==candidate:run+=1
        else:candidate=int(target);run=1
        if candidate!=current and run>=confirmation and i-last_change>=dwell:
            current=candidate;last_change=i;lags.append(run-1)
        out.append(current)
    f['raw_regime']=raw;f['regime']=out
    f['regime_age_days']=pd.Series(out).ne(pd.Series(out).shift()).cumsum().groupby(pd.Series(out).ne(pd.Series(out).shift()).cumsum()).cumcount().to_numpy()
    return f
