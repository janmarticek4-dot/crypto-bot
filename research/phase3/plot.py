"""Standalone scientific figure; simulated equity, no private account data."""
from pathlib import Path
import os
os.environ.setdefault('MPLCONFIGDIR',str(Path('/tmp')/'crypto-bot-phase3-mpl'))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np
import pandas as pd
from data import ROOT

OUT=ROOT/'docs/phase3'
matplotlib.rcParams['svg.hashsalt']='crypto-bot-phase3'

def draw():
    fig,(ax,dd)=plt.subplots(2,1,figsize=(11,7),sharex=True,gridspec_kw={'height_ratios':[2,1]},layout='constrained')
    for filename,label,color in [('walk_forward_curve.csv.gz','Walk-forward (including CASH folds)','#1773b0'),('walk_forward_hold_curve.csv.gz','Continuous HOLD, same initial slots','#d87819')]:
        f=pd.read_csv(OUT/filename,parse_dates=['time']);equity=f.equity.to_numpy();time=f.time
        ax.plot(time,equity/8500*100,label=label,color=color,lw=1)
        peak=np.maximum.accumulate(np.r_[8500,equity])[1:]
        dd.plot(time,(equity/peak-1)*100,color=color,lw=1)
    ax.axhline(100,color='gray',lw=.8,ls='--');ax.set_ylabel('Net equity (initial = 100)')
    ax.legend(loc='upper left',fontsize=9);ax.set_title('Phase 3: historical portfolio validation, 2022–September 2026')
    dd.set_ylabel('Drawdown (%)');dd.xaxis.set_major_locator(mdates.YearLocator());dd.xaxis.set_major_formatter(mdates.DateFormatter('%Y'))
    for axis in (ax,dd):axis.grid(alpha=.2)
    fig.suptitle('1% buy + 1% sell fees; spread + slippage; 1-hour manual delay',fontsize=10)
    fig.savefig(OUT/'walk_forward.png',dpi=160)
    fig.savefig(OUT/'walk_forward.svg',metadata={'Date':None})
    svg=OUT/'walk_forward.svg'
    svg.write_text('\n'.join(line.rstrip() for line in svg.read_text().splitlines())+'\n')
    plt.close(fig)
    print('Saved walk_forward.png and .svg')

if __name__=='__main__':draw()
