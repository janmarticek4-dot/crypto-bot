"""Causality, actual execution, missing data and train-only selection invariants."""
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import pandas as pd
sys.path.insert(0,str(Path(__file__).parent))
from data import daily_features,alt_features,retests,global_history
from regime import classify
from sim import Dataset,simulate
from run import select_model


def candles(n=500,freq='1D'):
    i=np.arange(n);close=100+i*.1+np.sin(i/7)*3
    return pd.DataFrame(dict(date=pd.date_range('2020-01-01',periods=n,freq=freq,tz='UTC'),open=close-.1,high=close+1,low=close-1,close=close,volume=100+i%30))


def toy(prices=None,regimes=None,signals=(0,),low=None,high=None,missing=()):
    prices=np.array(prices if prices is not None else [100.]*24,dtype=float);n=len(prices)
    c={k:prices.copy() for k in ('open','close','high','low')}
    if low is not None:c['low']=np.array(low,dtype=float)
    if high is not None:c['high']=np.array(high,dtype=float)
    for k in ('pullback','breakout','retest','momentum','strong_neutral'):
        c[k]=np.isin(np.arange(n),signals)
    c['atr']=np.full(n,5.)
    for k in ('open','high','low','close'):c[k][list(missing)]=np.nan
    return SimpleNamespace(index=pd.date_range('2020-01-01',periods=n,freq='1h',tz='UTC'),symbols=['SOL'],coins={'SOL':c},regimes={'full':np.array(regimes if regimes is not None else [1]*n,dtype=np.int8)},any_signal={k:c[k] for k in ('pullback','breakout','retest','momentum')})


def runtoy(ds,entry='pullback',exit='fixed',**kw):
    return simulate(ds,entry,exit,'2020-01-01',(ds.index[-1]+pd.Timedelta('1h')).strftime('%Y-%m-%d %H:%M'),**kw)


class CausalityTests(unittest.TestCase):
    def test_daily_prefix_unchanged_by_future_prices(self):
        f=candles();a=daily_features(f.iloc[:400]);f.loc[400:,'close']*=4
        b=daily_features(f).iloc[:400]
        pd.testing.assert_frame_equal(a,b)
        self.assertTrue(a.available_at.eq(a.date+pd.Timedelta('1D')).all())

    def test_alt_features_prefix_unchanged(self):
        d=candles(500);h=candles(2400,'4h')
        a=alt_features(h.iloc[:1800],d.iloc[:300])
        h.loc[1800:,'close']*=4;d.loc[300:,'close']*=4
        b=alt_features(h,d).iloc[:1800]
        pd.testing.assert_frame_equal(a,b)

    def test_regime_is_prefix_causal_and_missing_global_excluded(self):
        f=daily_features(candles())
        f['alt_breadth']=.8;f['cap_momentum30']=np.nan;f['dominance_change30']=np.nan
        a=classify(f.iloc[:400]);f.loc[400:,'close']=1
        b=classify(f).iloc[:400]
        pd.testing.assert_frame_equal(a,b)
        self.assertTrue(a.cap_momentum30.isna().all())

    def test_confirmation_and_dwell(self):
        f=daily_features(candles(30))
        f['ema200']=100.;f['ema50']=110.;f['ema50_slope']=.1
        f['close']=[110.]*4+[100.]+[110.]*25
        f['alt_breadth']=np.nan;f['cap_momentum30']=np.nan;f['dominance_change30']=np.nan
        r=classify(f,groups=(),confirmation=3,dwell=5)
        self.assertEqual(r.regime.iloc[:3].tolist(),[0,0,1])
        self.assertEqual(r.regime.iloc[4],1)  # isolated neutral day cannot flip regime
        r=classify(f,groups=(),confirmation=1,dwell=5)
        changes=np.flatnonzero(r.regime.diff().fillna(0).ne(0))
        self.assertTrue(np.all(np.diff(changes)>=5))

    def test_retest_requires_a_prior_breakout(self):
        f=pd.DataFrame(dict(open=[99,100,102],close=[100,103,104],low=[98,99,101],resistance=[102,102,103],atr=[2]*3,hist=[1]*3,rvol=[2]*3))
        self.assertEqual(retests(f).tolist(),[False,False,True])

    def test_dataset_closed_signal_pulse_and_daily_availability(self):
        h=candles(24,'1h');feat=pd.DataFrame({'available_at':[h.date.iloc[4]],'atr':[5.],**{k:[True] for k in ['pullback','breakout','retest','momentum','strong_neutral']}})
        reg=pd.DataFrame({'available_at':[h.date.iloc[8]],'regime':[1]})
        ds=Dataset({'SOL':h},{'SOL':feat},{'full':reg},'2020-01-01','2020-01-02')
        self.assertEqual(np.flatnonzero(ds.coins['SOL']['pullback']).tolist(),[4])
        self.assertEqual(ds.regimes['full'][:9].tolist(),[0]*8+[1])

    def test_global_optional_and_revisions_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'g.csv';self.assertIsNone(global_history(p))
            f=pd.DataFrame(dict(date=['2020-01-01T00:00:00Z'],available_at=['2020-01-02T00:00:00Z'],total_cap_usd=[100],btc_dominance_pct=[60],source_url=['https://example.org'],vintage_type=['revised']))
            f.to_csv(p,index=False)
            with self.assertRaisesRegex(ValueError,'first-vintage'):global_history(p)
            f['vintage_type']='first_release';f['available_at']='2020-01-01T12:00:00Z';f.to_csv(p,index=False)
            with self.assertRaisesRegex(ValueError,'before day'):global_history(p)


class ExecutionTests(unittest.TestCase):
    def test_delayed_entry_uses_actual_open_and_costs(self):
        ds=toy(prices=[100,110]+[110]*22)
        m,t,_=runtoy(ds)
        self.assertEqual(t[0]['entry_mid'],110)
        self.assertEqual(t[0]['entry_at'],str(ds.index[1]))
        self.assertLess(t[0]['pnl'],0)
        self.assertAlmostEqual(t[0]['debit']-t[0]['credit'],t[0]['fees']+t[0]['friction'],places=8)
        self.assertLessEqual(t[0]['debit'],1000)

    def test_stop_low_observed_at_close_then_delay_not_low_fill(self):
        low=[100.]*24;low[2]=70
        ds=toy(low=low)
        m,t,_=runtoy(ds)
        self.assertEqual(t[0]['exit_at'],str(ds.index[4]))
        self.assertEqual(t[0]['trigger_at'],str(ds.index[3]))
        self.assertEqual(t[0]['exit_mid'],100)
        self.assertEqual(t[0]['reason'],'stop_observed')

    def test_gap_stop_fills_actual_later_open(self):
        ds=toy(prices=[100,100,70,60]+[60]*20)
        _,t,_=runtoy(ds)
        self.assertEqual(t[0]['exit_mid'],60)
        self.assertEqual(t[0]['reason'],'stop_gap')

    def test_trailing_never_assumes_high_before_low(self):
        high=[100.]*24;low=[100.]*24;high[2]=150;low[2]=90
        ds=toy(high=high,low=low)
        _,t,_=runtoy(ds,exit='trailing')
        self.assertEqual(t[0]['reason'],'stop_gap')
        self.assertEqual(t[0]['exit_at'],str(ds.index[4]))
        self.assertGreater(t[0]['exit_at'],str(ds.index[3]))

    def test_trailing_parameter_applies_from_entry(self):
        ds=toy(prices=[100,100]+[82]*22)
        _,tight,_=runtoy(ds,exit='trailing',trailing=.15)
        _,wide,_=runtoy(ds,exit='trailing',trailing=.25)
        self.assertEqual(tight[0]['reason'],'stop_gap')
        self.assertEqual(wide[0]['reason'],'scheduled_end')

    def test_hold_ignores_bear_and_normal_correction_hybrid_holds(self):
        ds=toy(prices=[100,100]+[90]*22,regimes=[1,1]+[-1]*22)
        _,t,_=runtoy(ds,entry='hold',exit='hybrid')
        self.assertEqual(t[0]['reason'],'scheduled_end')
        ds.regimes['full'][:]=1
        _,t,_=runtoy(ds,exit='hybrid')
        self.assertEqual(t[0]['reason'],'scheduled_end')

    def test_bear_exit_and_reentry_cooldown(self):
        ds=toy(regimes=[1,1]+[-1]*2+[1]*20,signals=(0,4,8))
        _,t,_=runtoy(ds,exit='hybrid')
        self.assertEqual(len(t),1)
        self.assertEqual(t[0]['reason'],'bear_regime')
        self.assertEqual(t[0]['exit_at'],str(ds.index[3]))

    def test_pending_entry_rechecks_regime(self):
        _,t,_=runtoy(toy(regimes=[1]+[-1]*23))
        self.assertEqual(t,[])

    def test_neutral_blocks_pullback(self):
        _,t,_=runtoy(toy(regimes=[0]*24))
        self.assertEqual(t,[])

    def test_missing_quote_waits_without_fake_fill(self):
        ds=toy(prices=[100,100,70,60,50]+[50]*19,missing=(3,))
        m,t,_=runtoy(ds)
        self.assertEqual(t[0]['exit_mid'],50)
        self.assertEqual(t[0]['exit_at'],str(ds.index[4]))
        self.assertEqual(m['stale_position_hours'],1)

    def test_boundary_cannot_liquidate_at_stale_quote(self):
        with self.assertRaisesRegex(ValueError,'stale boundary'):runtoy(toy(missing=(23,)))

    def test_selection_uses_training_gate_and_cash_fallback(self):
        good=dict(entry='pullback',exit='hybrid',trades=5,return_pct=8.,max_drawdown_pct=10.,profit_factor=1.2)
        bad=dict(good,entry='momentum',return_pct=100.,trades=2)
        self.assertEqual(select_model([good,bad]),good)
        self.assertIsNone(select_model([bad]))

    def test_future_quotes_and_regimes_cannot_change_completed_window(self):
        ds=toy()
        a=simulate(ds,'pullback','hybrid','2020-01-01','2020-01-01 12:00',keep_curve=True)
        for k in ('open','close','high','low'):ds.coins['SOL'][k][12:]*=10
        ds.regimes['full'][12:]=-1
        b=simulate(ds,'pullback','hybrid','2020-01-01','2020-01-01 12:00',keep_curve=True)
        self.assertEqual(a[0],b[0]);self.assertEqual(a[1],b[1]);np.testing.assert_array_equal(a[2],b[2])

    def test_fully_allocated_hold_reserves_no_future_listing(self):
        ds=toy()
        ds.coins['AAVE']={k:v.copy() for k,v in ds.coins['SOL'].items()}
        ds.coins['TAO']={k:v.copy() for k,v in ds.coins['SOL'].items()}
        for k in ('open','close','high','low'):ds.coins['TAO'][k][0]=np.nan
        _,t,_=runtoy(ds,entry='hold',hold_at_start=True)
        self.assertEqual({x['symbol'] for x in t},{'SOL','AAVE'})
        self.assertAlmostEqual(sum(x['debit'] for x in t),8500.)

    def test_cash_constraints_across_simultaneous_coins(self):
        ds=toy()
        for s in range(12):ds.coins[str(s)]={k:v.copy() for k,v in ds.coins['SOL'].items()}
        m,t,_=runtoy(ds)
        invested=sum(x['credit'] for x in t)
        cash=8500.-sum(x['debit'] for x in t)
        self.assertGreaterEqual(cash,0)
        self.assertLessEqual(invested/(cash+invested),.70)
        self.assertGreater(m['final_equity'],0)

if __name__=='__main__':unittest.main()
