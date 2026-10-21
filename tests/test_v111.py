import copy
import os
import unittest
from unittest.mock import MagicMock,patch
from v11 import reporting,delivery,briefing,runtime
from tests.test_briefing import snapshot,NOW,coin
from v11.data import PRIMARY

class TransportTests(unittest.TestCase):
    def test_unicode_logical_chunks(self):
        message=('😀'*2200+'\n\nSOL – plán\n')*3
        chunks=reporting.chunks(message)
        self.assertGreater(len(chunks),1)
        self.assertTrue(all(reporting.units(c)<=3800 for c in chunks))
        self.assertTrue(all(c.startswith('[') for c in chunks))
    def test_preview_never_sends(self):
        import main
        with patch.dict(os.environ,{'BOT_DATA_MODE':'synthetic'}),patch.object(main,'http_request') as http:
            with self.assertRaises(RuntimeError):main.telegram_send('test')
            http.assert_not_called()
    def test_synthetic_live_rejected(self):
        with self.assertRaises(RuntimeError):reporting.require_live_snapshot({'synthetic':True})
    def test_delivery_uncertainty_does_not_replay(self):
        api=MagicMock();state={};api.telegram_send_long.side_effect=TimeoutError()
        with self.assertRaises(TimeoutError):delivery.send_once(api,state,'x','slot')
        self.assertEqual(state['delivery_v111']['slot']['status'],'uncertain')
        self.assertFalse(delivery.send_once(api,state,'changed message','slot'))
        self.assertEqual(api.telegram_send_long.call_count,1)
    def test_checkpoint_precedes_send(self):
        api=MagicMock();state={};checkpoints=[]
        api.save_state.side_effect=lambda s:checkpoints.append(copy.deepcopy(s))
        api.telegram_send_long.side_effect=lambda m:self.assertEqual(checkpoints[0]['delivery_v111']['slot']['status'],'sending')
        self.assertTrue(delivery.send_once(api,state,'x','slot'))
        self.assertFalse(delivery.send_once(api,state,'x','slot'))
    def test_checkpoint_failure_never_sends(self):
        api=MagicMock();api.save_state.side_effect=RuntimeError('offline')
        with self.assertRaises(RuntimeError):delivery.send_once(api,{},'x','slot')
        api.telegram_send_long.assert_not_called()
    def test_duplicate_slot_no_collection(self):
        api=MagicMock();api.load_state.return_value={'last_main_slot':'slot'}
        with patch('v11.runtime.collect') as collect:
            runtime.run_analysis(api,'scheduled','slot')
            collect.assert_not_called()

class ForecastTests(unittest.TestCase):
    def test_independent_price_boundaries(self):
        levels=[]
        for multiplier in (1,2,7):
            d=coin();d['price']*=multiplier
            for t in d['frames'].values():
                for k in ('support','resistance','atr','ema200'):t[k]*=multiplier
            levels.append(briefing.scenarios(d)[0]['high'])
        self.assertEqual(len(set(levels)),3)
    def test_forecasts_retain_method_and_sources(self):
        state={};briefing.remember(state,snapshot(),{},'slot')
        item=state['analysis_forecasts_v11'][0]
        self.assertEqual(item['sources']['price'],'fixture')
        self.assertEqual(item['method'],'closed-structure-v1')
        self.assertIn('text',item)
    def test_incomplete_analysis_preserves_previous_recommendation(self):
        from v11.data import COINS
        api=MagicMock();api.iso_now.return_value='2026-10-21T20:00:00+00:00'
        state={'recommendations_v11':{'SOL':dict(action='HOLD',price=100,at=NOW)}}
        api.load_state.return_value=state
        snap=snapshot();snap.update(complete=False)
        for s in COINS:snap['coins'].setdefault(s,coin())
        ev=dict(action='WAIT',held=False,reasons=['missing'],confidence='low',data_complete=False)
        with patch('v11.runtime.collect',return_value=snap),patch('v11.runtime.decide',return_value=ev),patch('v11.macro_context.collect',return_value={}),patch('v11.fundamentals.collect',return_value={'events':[]}),patch('v11.ai.explain',return_value={}),patch('v11.briefing.build',return_value=['test']):
            runtime.run_analysis(api,'scheduled','slot')
        self.assertEqual(state['recommendations_v11']['SOL']['action'],'HOLD')
        self.assertEqual(state['portfolio_v11']['positions'],{})

class MacroTests(unittest.TestCase):
    def test_treasury_not_live_and_not_dxy(self):
        from v11.macro_context import parse_treasury,lines
        from datetime import datetime,timezone
        raw=b'<feed xmlns:m="urn:m" xmlns:d="urn:d"><m:properties><d:NEW_DATE>2026-10-20T00:00:00</d:NEW_DATE><d:BC_2YEAR>4.1</d:BC_2YEAR><d:BC_10YEAR>4.3</d:BC_10YEAR></m:properties></feed>'
        result=parse_treasury(raw,datetime(2026,10,21,tzinfo=timezone.utc))
        self.assertEqual(result['10y'],4.3)
        self.assertIn('nie živá kotácia',' '.join(lines({'treasury':result,'url':'https://home.treasury.gov/'})))
    def test_bad_or_future_yields_na(self):
        from v11.macro_context import parse_treasury
        from datetime import datetime,timezone
        for value in ('NaN','Infinity','99'):
            raw=f'<x><properties><NEW_DATE>2026-10-20</NEW_DATE><BC_2YEAR>{value}</BC_2YEAR><BC_10YEAR>4</BC_10YEAR></properties></x>'.encode()
            self.assertIsNone(parse_treasury(raw,datetime(2026,10,21,tzinfo=timezone.utc)))
    def test_legacy_forecast_copy_keeps_original(self):
        original=dict(symbol='BTC',at=NOW-100,due=NOW+100,price=100,low=90,high=110,horizon='24h',outcome=None)
        state={'predictions_v11':[copy.deepcopy(original)]}
        briefing.evaluate(state,snapshot());briefing.evaluate(state,snapshot())
        self.assertEqual(state['predictions_v11'],[original])
        self.assertEqual(len(state['analysis_forecasts_v11']),1)
        self.assertEqual(state['analysis_forecasts_v11'][0]['method'],'legacy-volatility-envelope')

class DataProvenanceTests(unittest.TestCase):
    def test_invalid_ticker_cannot_refresh_stale_fallback(self):
        import main,time
        from datetime import datetime,timezone
        from v11 import data
        from tests.test_v11 import bars
        api=MagicMock();api.safe_float=main.safe_float;api.parse_timestamp=main.parse_timestamp
        old=datetime.fromtimestamp(time.time()-3600,timezone.utc).isoformat()
        api.coingecko_markets.return_value=[dict(id=cid,current_price=100,last_updated=old) for cid in {**data.MARKET,**data.COINS}.values()]
        api.http_json.return_value=[dict(symbol=s+'USDT',lastPrice='0',closeTime=time.time()*1000,priceChangePercent='2') for s in {**data.MARKET,**data.COINS}]
        with patch('v11.data.candles',return_value=bars()):snap=data.collect(api,full=False)
        self.assertTrue(snap['coins']['SOL']['stale'])
        self.assertEqual(snap['coins']['SOL']['price_source'],'CoinGecko')
        self.assertFalse(snap['complete'])

class ResearchMetricsTests(unittest.TestCase):
    def test_empty_trades_not_a_measured_win_rate(self):
        from backtesting.single_coin import metrics
        self.assertIsNone(metrics([])['win_rate'])
        self.assertIsNone(metrics([])['profit_factor'])
    def test_average_wins_losses_and_pf(self):
        from backtesting.single_coin import metrics
        result=metrics([{'profit_abs':20},{'profit_abs':10},{'profit_abs':-5}])
        self.assertEqual(result['profit_factor'],6)
        self.assertEqual(result['mean_profit_abs'],15)
        self.assertEqual(result['mean_loss_abs'],-5)

class ProductionIsolationTests(unittest.TestCase):
    def test_preview_main_cannot_load_real_state(self):
        import main
        with patch.dict(os.environ,{'BOT_DATA_MODE':'synthetic'}),patch.object(main,'load_state') as load:
            with self.assertRaises(RuntimeError):main.main()
            load.assert_not_called()
    def test_preview_analysis_cannot_load_real_state(self):
        api=MagicMock()
        with patch.dict(os.environ,{'BOT_DATA_MODE':'synthetic'}):
            with self.assertRaises(RuntimeError):runtime.run_analysis(api,'manual')
        api.load_state.assert_not_called()
