"""Fail closed on changed inputs, inconsistent accounting or test selection."""
import hashlib
import json
from pathlib import Path
import subprocess
import numpy as np
import pandas as pd
from data import ROOT,DATA,load
from run import select_model

OUT=ROOT/'docs/phase3'

def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def verify():
    m=json.loads((OUT/'manifest.json').read_text());a=json.loads((OUT/'analysis_manifest.json').read_text())
    assert m['status']=='complete'
    assert digest(OUT/'manifest.json')==a['source_manifest_sha256']
    assert digest(ROOT/'research/phase3/design.json')==m['design_sha256']
    for name,info in m['source_files'].items():assert digest(DATA/name)==info['sha256'],name
    for manifest in (m,a):
        for name,sha in manifest['code_sha256'].items():assert digest(ROOT/'research/phase3'/name)==sha,name
        for name,sha in manifest['artifacts_sha256'].items():assert digest(OUT/name)==sha,name
    assert set(a['code_sha256'])=={p.name for p in (ROOT/'research/phase3').glob('*.py')}
    results=pd.read_csv(OUT/'results.csv');trades=pd.read_csv(OUT/'trades.csv.gz')
    assert len(results)==508
    main=results[results.category=='main'];assert len(main)==140
    assert main.groupby('period').size().eq(20).all()
    assert results.return_pct.ge(-100).all() and results.max_drawdown_pct.between(0,100).all()
    assert results.mean_exposure_pct.between(0,100).all()
    for _,row in main.iterrows():
        t=trades[trades.run.eq(row.id)]
        assert len(t)==row.trades
        np.testing.assert_allclose(t.pnl.sum(),8500*row.return_pct/100,rtol=1e-9,atol=1e-8)
        np.testing.assert_allclose(t.fees.sum(),row.fees,rtol=1e-9,atol=1e-8)
        np.testing.assert_allclose(t.friction.sum(),row.spread_slippage,rtol=1e-9,atol=1e-8)
        np.testing.assert_allclose(row.final_equity,8500+t.pnl.sum(),rtol=1e-9,atol=1e-8)
    prices={s:load(s,'1h').set_index('date') for s in trades.symbol.unique()}
    for _,t in trades.iterrows():
        entry=pd.Timestamp(t.entry_at);signal=pd.Timestamp(t.signal_at);exit_at=pd.Timestamp(t.exit_at)
        assert entry>=signal+pd.Timedelta('1h') and exit_at>=entry
        np.testing.assert_allclose(t.entry_mid,prices[t.symbol].loc[entry,'open'])
        if t.reason=='scheduled_end':expected=prices[t.symbol].loc[exit_at-pd.Timedelta('1h'),'close']
        else:
            expected=prices[t.symbol].loc[exit_at,'open']
            assert exit_at>=pd.Timestamp(t.trigger_at)+pd.Timedelta('1h')
        np.testing.assert_allclose(t.exit_mid,expected)
    wf=pd.read_csv(OUT/'walk_forward.csv');training=pd.read_csv(OUT/'walk_forward_training.csv')
    assert len(wf)==10 and len(training)==200
    wealth=8500.
    for _,fold in wf.iterrows():
        assert fold.train_end==fold.test_start
        assert pd.Timestamp(fold.train_start)<pd.Timestamp(fold.train_end)<pd.Timestamp(fold.test_end)
        candidates=training[training.fold.eq(fold.test_start)].replace({np.nan:None}).to_dict('records')
        chosen=select_model(candidates)
        assert fold.chosen==('CASH' if chosen is None else chosen['entry']+'/'+chosen['exit'])
        np.testing.assert_allclose(fold.starting_equity,wealth)
        wealth*=1+fold.return_pct/100
        np.testing.assert_allclose(fold.final_equity,wealth)
    wt=pd.read_csv(OUT/'walk_forward_trades.csv')
    ws=json.loads((OUT/'walk_forward_summary.json').read_text())
    assert len(wt)==ws['trades']
    np.testing.assert_allclose(wt.pnl.sum(),wealth-8500)
    np.testing.assert_allclose(wt.fees.sum(),ws['fees'])
    np.testing.assert_allclose(wt.friction.sum(),ws['spread_slippage'])
    np.testing.assert_allclose(wt[wt.pnl>0].pnl.sum()/-wt[wt.pnl<0].pnl.sum(),ws['profit_factor'])
    final=json.loads((OUT/'final_policy.json').read_text())
    ft=pd.read_csv(OUT/'final_holdout_training.csv').replace({np.nan:None}).to_dict('records')
    chosen=select_model(ft)
    assert final['chosen']==('CASH' if chosen is None else chosen['entry']+'/'+chosen['exit'])
    assert final['train_end']==final['test_start']
    changed=subprocess.check_output(['git','diff','--name-only','e4c610d'],cwd=ROOT,text=True).splitlines()
    assert all(p.startswith(('research/phase3/','docs/phase3/')) for p in changed),changed
    print(f'VERIFIED: hashes, 508 matrix rows, {len(trades)} alternative trades, costs, actual prices, causal execution, train-only selections; production diff empty.')

if __name__=='__main__':verify()
