import copy
import io
import json
import math
import os
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch
import main
from v11 import indicators, portfolio, strategy, runtime, data


def bars(n=300):
    return [dict(timestamp=i*14400000,open=100+i,high=102+i,low=99+i,close=101+i,volume=100+i) for i in range(n)]


class Indicators(unittest.TestCase):
    def test_warmup(self):
        self.assertIsNone(indicators.ema([1]*199,200))
        self.assertEqual(indicators.ema([1]*200,200),1)
    def test_known_trend(self):
        t=indicators.summary(bars())
        self.assertEqual(t['rsi14'],100)
        self.assertAlmostEqual(t['adx'],100)
        self.assertGreater(t['bb_upper'],t['bb_lower'])
        self.assertGreater(t['vwap20'],0)
    def test_flat(self):
        t=indicators.summary([dict(timestamp=i,open=1,high=1,low=1,close=1,volume=0) for i in range(300)])
        self.assertEqual(t['rsi14'],50)
        self.assertEqual(t['adx'],0)
        self.assertIsNone(t['relative_volume'])
        self.assertIsNone(t['vwap20'])
    def test_no_forward_dependency(self):
        original=bars()
        prefix=copy.deepcopy(original[:250])
        original[250]['close']=100000
        self.assertEqual(indicators.summary(prefix),indicators.summary(original[:250]))
    def test_scenarios_not_probabilities(self):
        fs=indicators.scenarios(100,5,90)
        self.assertEqual(len(fs),4)
        self.assertTrue(all(f['probability_up'] is None for f in fs))


class Ledger(unittest.TestCase):
    def setUp(self):
        self.state={}; self.book=portfolio.initialize(self.state)
    def test_empty(self):
        self.assertEqual(self.book['positions'],{})
        self.assertEqual(self.book['cash'],8500)
    def test_buy_and_sell(self):
        portfolio.command(self.state,'KUPIL SOL 100 1010',data.COINS)
        self.assertEqual(self.book['positions']['SOL']['qty'],10)
        self.assertEqual(self.book['fees'],10)
        portfolio.command(self.state,'PREDAL SOL 110 50%',data.COINS)
        self.assertEqual(self.book['positions']['SOL']['qty'],5)
        self.assertAlmostEqual(self.book['realized'],39.5)
        self.assertAlmostEqual(self.book['cash'],8034.5)
    def test_overspend_atomic(self):
        before=copy.deepcopy(self.book)
        with self.assertRaises(ValueError):portfolio.command(self.state,'KUPIL SOL 100 10000',data.COINS)
        self.assertEqual(self.book,before)
    def test_no_unowned_sale(self):
        with self.assertRaises(ValueError):portfolio.command(self.state,'PREDAL SOL 100 VSETKO',data.COINS)
    def test_nonfinite(self):
        for val in ('nan','inf','-1','0'):
            with self.assertRaises(ValueError):portfolio.command(self.state,f'KUPIL SOL {val} 10',data.COINS)
    def test_correction_confirmation(self):
        portfolio.command(self.state,'KUPIL SOL 100 1010',data.COINS)
        tx=self.book['transactions'][0]['id']
        with self.assertRaises(ValueError):portfolio.command(self.state,'POTVRDIT '+tx,data.COINS)
        portfolio.command(self.state,'OPRAV '+tx,data.COINS)
        self.assertEqual(self.book['cash'],7490)
        portfolio.command(self.state,'POTVRDIT '+tx,data.COINS)
        self.assertEqual(self.state['portfolio_v11']['cash'],8500)
    def test_missing_price_no_valuation(self):
        portfolio.command(self.state,'KUPIL SOL 100 1010',data.COINS)
        self.assertFalse(portfolio.valuation(self.book,{})['complete'])
    def test_drawdown(self):
        portfolio.command(self.state,'KUPIL SOL 100 8080',data.COINS)
        v=portfolio.valuation(self.book,{'SOL':50})
        self.assertGreater(v['drawdown'],20)


class Strategy(unittest.TestCase):
    def test_no_data_is_not_sell(self):
        self.assertEqual(strategy.decide({},held=True)['action'],'HOLD')
        self.assertEqual(strategy.decide({})['action'],'WAIT')
    def test_fee_math(self):
        c=strategy.costs(100,110,90,spread=0)
        self.assertAlmostEqual(c['net'],110*.99/101-1)
        self.assertAlmostEqual(c['break_even'],101/.99)
        self.assertLess(strategy.reentry_edge(100,99),0)
    def test_no_buy_without_spread(self):
        with patch.dict(os.environ,{},clear=True):
            d={'price':400,'frames':{'4h':indicators.summary(bars())}}
            self.assertEqual(strategy.decide(d,approved=True)['action'],'WAIT')
    def test_incomplete_risk_unknown(self):
        self.assertEqual(runtime.market_status({'complete':False},{})['state'],'UNKNOWN')


class Integration(unittest.TestCase):
    def test_dst_slots(self):
        from datetime import datetime
        for day,offset in [('2026-01-10',1),('2026-07-10',2)]:
            dt=datetime.fromisoformat(day+'T07:10:00').replace(tzinfo=main.TZ)
            self.assertTrue(main.get_main_analysis_slot(dt).endswith('07:00'))
            self.assertEqual(dt.utcoffset().total_seconds()/3600,offset)
    def test_rate_limit_retry(self):
        error=urllib.error.HTTPError('https://api.groq.com',429,'limited',{'Retry-After':'2'},io.BytesIO())
        response=unittest.mock.MagicMock()
        response.__enter__.return_value.read.return_value=b'OK'
        with patch('urllib.request.urlopen',side_effect=[error,response]),patch('time.sleep') as sleep:
            self.assertEqual(main.http_request('url',retries=2),b'OK')
            sleep.assert_called_once_with(2)
    def test_long_retry_not_shortened(self):
        error=urllib.error.HTTPError('url',429,'limited',{'Retry-After':'100'},io.BytesIO())
        with patch('urllib.request.urlopen',side_effect=error),patch('time.sleep') as sleep:
            with self.assertRaises(urllib.error.HTTPError):main.http_request('url',retries=2)
            sleep.assert_not_called()
    def test_telegram_authorization_and_dedup(self):
        s={}
        msgs=[dict(update_id=5,message={'chat':{'id':999},'text':'KUPIL SOL 100 1010'}),dict(update_id=6,message={'chat':{'id':123},'text':'KUPIL SOL 100 1010'})]
        api=unittest.mock.MagicMock(TELEGRAM_TOKEN='test',TELEGRAM_CHAT_ID='123')
        api.http_request.return_value=json.dumps({'ok':True,'result':msgs}).encode()
        runtime.telegram_updates(api,s)
        runtime.telegram_updates(api,s)
        self.assertEqual(len(s['portfolio_v11']['transactions']),1)
        self.assertEqual(s['portfolio_v11']['command_offset'],7)
    def test_state_compatibility(self):
        with tempfile.TemporaryDirectory() as d,patch.object(main,'STATE_FILE',str(Path(d)/'state.json')):
            s={'legacy':{'nested':123}}
            portfolio.initialize(s);main.save_state(s)
            self.assertEqual(main.load_state()['legacy'],{'nested':123})



class MoreRegressions(unittest.TestCase):
    def test_ai_cannot_add_news(self):
        from v11.ai import explain
        api=unittest.mock.MagicMock()
        api.groq_json.return_value={'selections':{'SOL':[0,99,'fake'],'FAKE':[0]},'news':'invented'}
        facts={'SOL':{'action':'WAIT','reasons':['Known reason'],'confidence':'nízka'}}
        state={};result=explain(api,state,facts)
        self.assertEqual(result['selections'],{'SOL':['Known reason']})
        explain(api,state,facts)
        self.assertEqual(api.groq_json.call_count,1)
    def test_corrupt_state_refuses_reset(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'state.json';path.write_text('{')
            with patch.object(main,'STATE_FILE',str(path)):
                with self.assertRaises(RuntimeError):main.load_state()
    def test_coin_metadata_failure_does_not_block_candles(self):
        api=unittest.mock.MagicMock()
        api.coingecko_markets.side_effect=RuntimeError('CG offline')
        api.safe_float=main.safe_float
        now=__import__('time').time()
        api.http_json.return_value=[dict(symbol=s+'USDT',lastPrice='100',closeTime=now*1000,priceChangePercent='1') for s in {**data.COINS,**data.MARKET}]
        with patch('v11.data.candles',return_value=bars()):
            snap=data.collect(api,full=False)
        self.assertTrue(snap['complete'])
        self.assertEqual(snap['coins']['FET']['price'],100)
        self.assertIsNone(snap['coins']['FET']['market_cap'])

class DecisionGuards(unittest.TestCase):
    def setUp(self):
        self.d={'price':100,'frames':{'4h':dict(ema200=90,ema50=95,ema20=97,macd_hist=1,rsi14=55,relative_volume=1.5,higher_structure=True,retest=True,adx=25,support=95,resistance=130,atr=2,support_broken=False,bullish_divergence=False),'1d':dict(ema200=80,ema50=85,candles=250)}}
    def test_candidate_requires_validation(self):
        with patch.dict(os.environ,{'SPREAD_ESTIMATE':'.002','V11_RULES_VALIDATED':'false'}):
            self.assertEqual(strategy.decide(self.d,approved=True)['action'],'WAIT')
    def test_new_buy_requires_all_guards(self):
        with patch.dict(os.environ,{'SPREAD_ESTIMATE':'.002','V11_RULES_VALIDATED':'true'}):
            self.assertEqual(strategy.decide(self.d,approved=True)['action'],'BUY NOW')
            self.assertEqual(strategy.decide(self.d,approved=False)['action'],'WAIT')
            self.assertEqual(strategy.decide(self.d,approved=True,market_complete=False)['action'],'WAIT')
            self.assertEqual(strategy.decide(self.d,approved=True,risk_normal=False)['action'],'WAIT')
    def test_healthy_owned_is_hold(self):
        self.assertEqual(strategy.decide(self.d,held=True)['action'],'HOLD')
    def test_warning_does_not_block_protection(self):
        self.d['frames']['4h'].update(support_broken=True,macd_hist=-1,relative_volume=2)
        self.d['frames']['1d']['ema50']=110
        self.assertEqual(strategy.decide(self.d,held=True,risk_normal=False)['action'],'REDUCE')
    def test_no_daily_data_no_buy(self):
        self.d['frames']['1d']={}
        with patch.dict(os.environ,{'SPREAD_ESTIMATE':'.002','V11_RULES_VALIDATED':'true'}):
            self.assertEqual(strategy.decide(self.d,approved=True)['action'],'WAIT')
    def test_old_ai_sales_not_positions(self):
        state={'last_actions':{'SOL':{'action':'BUY NOW'}},'last_analysis':{'coins':[{'symbol':'SOL'}]}}
        self.assertEqual(portfolio.initialize(state)['positions'],{})

class ReportIntegration(unittest.TestCase):
    def test_full_report_does_not_create_positions(self):
        from datetime import datetime
        with tempfile.TemporaryDirectory() as d:
            path=str(Path(d)/'state.json')
            t=indicators.summary(bars())
            coin=dict(price=400,frames={'4h':t,'1d':t},raw={'1h':[]},market_cap=None,volume_24h=None,market_cap_change_24h=None,circulating_supply=None,volume_to_cap=None,stale=False,price_source='fixture',age_seconds=1,change_24h=1,relative_strength_btc_7d=None)
            snap=dict(at=1000000,complete=True,coins={s:copy.deepcopy(coin) for s in {**data.COINS,**data.MARKET}})
            with patch.object(main,'STATE_FILE',path),patch('v11.runtime.collect',return_value=snap),patch('v11.ai.explain',return_value={'available':False,'selections':{}}),patch.object(main,'telegram_send_long') as send,patch.object(main,'get_rss_news',return_value=[]),patch('v11.macro_context.collect',return_value={}),patch('v11.fundamentals.collect',return_value={'events':[],'sources':[],'unavailable':[]}):
                runtime.run_analysis(main,'scheduled','2026-10-21_07:00')
                report=send.call_args.args[0]
                self.assertIn('kapitalizácia N/A',report)
                self.assertNotIn('kapitalizácia $0',report)
                state=main.load_state()
                self.assertEqual(state['portfolio_v11']['positions'],{})
                self.assertEqual(state['last_main_slot'],'2026-10-21_07:00')
                self.assertEqual(len(state['recommendations_v11']),10)
    def test_send_failure_does_not_mark_delivered(self):
        with tempfile.TemporaryDirectory() as d:
            path=str(Path(d)/'state.json')
            t=indicators.summary(bars())
            coin=dict(price=400,frames={'4h':t,'1d':t},raw={'1h':[]},market_cap=None,volume_24h=None,market_cap_change_24h=None,circulating_supply=None,volume_to_cap=None,stale=False,price_source='fixture',age_seconds=1,change_24h=1,relative_strength_btc_7d=None)
            snap=dict(at=1000000,complete=True,coins={s:copy.deepcopy(coin) for s in {**data.COINS,**data.MARKET}})
            with patch.object(main,'STATE_FILE',path),patch('v11.runtime.collect',return_value=snap),patch('v11.ai.explain',return_value={'available':False,'selections':{}}),patch.object(main,'telegram_send_long',side_effect=RuntimeError('failed')),patch.object(main,'get_rss_news',return_value=[]),patch('v11.macro_context.collect',return_value={}),patch('v11.fundamentals.collect',return_value={'events':[],'sources':[],'unavailable':[]}):
                with self.assertRaises(RuntimeError):runtime.run_analysis(main,'scheduled','test-slot')
                self.assertNotIn('last_main_slot',main.load_state())



if __name__ == "__main__":
    unittest.main()
