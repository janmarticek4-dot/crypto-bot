import unittest
from unittest.mock import patch
import numpy as np
import pandas as pd
import engine


class ResearchExecution(unittest.TestCase):
    def setUp(self):
        self.index=pd.date_range('2024-01-01',periods=8,freq='4h',tz='UTC')
        self.f=pd.DataFrame(index=self.index,data=dict(open=100.,high=110.,low=90.,close=100.,b_trend=False,c_pullback=False,d_breakout=False,f_combined=False,warm=True,retest=True,e_exit=False,daily_bear2=False))
        hours=pd.date_range(self.index[0],periods=32,freq='1h')
        engine.HOURLY['SOL']=pd.DataFrame(index=hours,data=dict(open=100.,low=90.))
    def simulate(self,strategy,fee=.01,spread=.001,slip=.001):
        with patch('engine.with_cost_signals',side_effect=lambda f,*a:f):
            return engine.simulate({'SOL':self.f},strategy,'2024-01-01','2024-01-02',fee,spread,slip,initial=1000)
    def test_hold_exact_roundtrip_costs(self):
        metrics,trades,_=self.simulate('A_hold')
        expected=1000*(1-.01)*(1-.002)/((1+.01)*(1+.002))
        self.assertAlmostEqual(metrics['final_equity'],expected)
        self.assertEqual(len(trades),1)
    def test_signal_executes_only_at_next_open(self):
        self.f.loc[self.index[1],'b_trend']=True
        self.f.loc[self.index[2],'open']=120
        engine.HOURLY['SOL'].loc[self.index[2]:,'open']=120
        engine.HOURLY['SOL'].loc[self.index[2]:,'low']=110
        _,trades,_=self.simulate('B_trend')
        self.assertEqual(trades[0]['entry_at'],str(self.index[2]))
        self.assertEqual(trades[0]['entry_mid'],120)
    def test_stop_respects_adverse_gap(self):
        self.f.loc[self.index[0],'b_trend']=True
        # Entry 100 at 04:00; later hourly gap to 70, below the 80 stop.
        engine.HOURLY['SOL'].loc[self.index[1]+pd.Timedelta('1h'),['open','low']]=[70,65]
        _,trades,_=self.simulate('B_trend')
        self.assertEqual(trades[0]['reason'],'hard_stop')
        self.assertEqual(trades[0]['exit_mid'],70)
    def test_missing_hourly_data_while_invested_fails(self):
        self.f.loc[self.index[0],'b_trend']=True
        engine.HOURLY['SOL'].iloc[5,0]=np.nan
        with self.assertRaises(ValueError):self.simulate('B_trend')


class Causality(unittest.TestCase):
    def test_future_changes_cannot_change_past_signals(self):
        def frame(dates):
            cs=100+np.arange(len(dates))*.02+np.sin(np.arange(len(dates)))*2
            return pd.DataFrame(dict(date=dates,open=cs,high=cs+3,low=cs-3,close=cs,volume=1000+np.arange(len(dates))))
        four=frame(pd.date_range('2023-01-01',periods=2400,freq='4h',tz='UTC'))
        daily=frame(pd.date_range('2023-01-01',periods=400,freq='1d',tz='UTC'))
        with patch('engine.load',side_effect=lambda s,tf:four.copy() if tf=='4h' else daily.copy()):before=engine.features('SOL')
        cutoff=pd.Timestamp('2023-11-01',tz='UTC')
        four.loc[four.date>=cutoff,['open','close','high','low']]*=10
        daily.loc[daily.date>=cutoff,['open','close','high','low']]*=10
        with patch('engine.load',side_effect=lambda s,tf:four.copy() if tf=='4h' else daily.copy()):after=engine.features('SOL')
        pd.testing.assert_frame_equal(before.loc[before.decision_at<cutoff],after.loc[after.decision_at<cutoff])
        known=before['available_at'].notna()
        self.assertTrue((before.loc[known,'available_at']<=before.loc[known,'decision_at']).all())
        self.assertFalse(before.loc[~known,'warm'].any())


class PortfolioAndReentry(unittest.TestCase):
    setUp=ResearchExecution.setUp
    simulate=ResearchExecution.simulate
    def test_small_correction_holds(self):
        self.f.loc[self.index[0],'b_trend']=True
        metrics,trades,_=self.simulate('E_protective')
        self.assertEqual(len(trades),1)
        self.assertEqual(trades[0]['reason'],'end_of_period')
    def test_reentry_requires_net_advantage_after_both_legs(self):
        self.f.loc[[self.index[0],self.index[3]],'f_combined']=True
        self.f.loc[self.index[2],'e_exit']=True
        self.f.loc[self.index[4],'open']=96
        _,trades,_=self.simulate('F_combined_reentry')
        self.assertEqual(len(trades),1)
        self.f.loc[self.index[4],'open']=90
        engine.HOURLY['SOL'].loc[self.index[4]:,'low']=85
        _,trades,_=self.simulate('F_combined_reentry')
        self.assertEqual(len(trades),2)
    def test_portfolio_cannot_spend_more_than_cash(self):
        engine.HOURLY['AAVE']=engine.HOURLY['SOL'].copy()
        with patch('engine.with_cost_signals',side_effect=lambda f,*a:f):
            m,trades,_=engine.simulate({'SOL':self.f,'AAVE':self.f},'A_hold','2024-01-01','2024-01-02',initial=1500)
        self.assertAlmostEqual(sum(t['cash_debit'] for t in trades),1500)
        self.assertLess(m['final_equity'],1500)


class ArchiveSelection(unittest.TestCase):
    def test_free_fee_and_other_strategies_cannot_replace_original_report(self):
        import contextlib,importlib.util,io,json,tempfile,zipfile
        from pathlib import Path
        spec=importlib.util.spec_from_file_location('original_report',engine.ROOT/'backtesting/report.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'docs').mkdir();archives=root/'archives';archives.mkdir()
            for period in ['20240101-20250101','20250101-20260101']:
                for strategy in ['TrendComponent','PullbackComponent','CombinedStrategy']:
                    r=dict(timerange=period,timeframe_detail='1h',profit_total=.1,max_drawdown_account=.2,total_trades=1,winrate=.5,profit_factor=1.2,sharpe=.3,sortino=.4,pairlist=['SOL/USDT'],backtest_start='2024-01-01',backtest_end='2025-01-01')
                    with zipfile.ZipFile(archives/f'{period}-{strategy}.zip','w') as z:
                        z.writestr('result.json',json.dumps({'strategy':{strategy:r}}));z.writestr('result_config.json',json.dumps({'fee':.012}))
            r['profit_total']=999
            for strategy,fee in [('TrendComponent',0),('LegacyNoProtectiveExit',.012)]:
                with zipfile.ZipFile(archives/f'zzz-{strategy}.zip','w') as z:
                    z.writestr('result.json',json.dumps({'strategy':{strategy:r}}));z.writestr('result_config.json',json.dumps({'fee':fee}))
            baseline={'profit_total':.05,'max_drawdown_account':.2}
            with patch.object(module,'RESULTS',archives),patch.object(module,'ROOT',root/'backtesting'),patch.object(module,'baseline',return_value=baseline),contextlib.redirect_stdout(io.StringIO()):module.build()
            result=json.loads((root/'docs/BACKTEST_RESULTS.json').read_text())
            self.assertEqual(len(result),6)
            self.assertTrue(all(row['profit_total']==.1 for row in result))


class ArtifactIntegrity(unittest.TestCase):
    def test_incomplete_run_is_not_reported_as_success(self):
        import json,tempfile
        from pathlib import Path
        import report
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'manifest.json').write_text(json.dumps({'status':'running'}))
            with self.assertRaises(RuntimeError):report.verify_run(root)
    def test_changed_completed_artifact_is_rejected(self):
        import json,hashlib,tempfile
        from pathlib import Path
        import report
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);artifact=root/'comparisons.json';artifact.write_text('[]')
            m={'status':'complete','code_sha256':hashlib.sha256(Path(engine.__file__).read_bytes()).hexdigest(),'artifacts_sha256':{'comparisons.json':hashlib.sha256(artifact.read_bytes()).hexdigest()}}
            (root/'manifest.json').write_text(json.dumps(m))
            report.verify_run(root)
            artifact.write_text('["changed"]')
            with self.assertRaises(RuntimeError):report.verify_run(root)

if __name__ == "__main__":
    unittest.main()
