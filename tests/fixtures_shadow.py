import copy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import v111_shadow as shadow
from tests.test_briefing import snapshot


class ShadowTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 22, 10, tzinfo=timezone.utc)
        self.snap = snapshot()
        self.snap['complete'] = True
        self.snap['coins']['ETH'] = copy.deepcopy(self.snap['coins']['BTC'])
        for coin in self.snap['coins'].values():
            for frame in coin['frames'].values():
                frame.update(ema20=99., ema100=97., macd_hist=.1, relative_volume=1.2,
                             higher_structure=True, retest=False, support_broken=False, breakout=False)
        self.fund = dict(events=[], sources=[], metrics={}, macro_context={})

    def test_no_delivery_or_state_api_even_with_credentials_in_environment(self):
        with patch.dict(os.environ, {'TELEGRAM_TOKEN': 'never-use', 'TELEGRAM_CHAT_ID': 'never-use',
                                     'STATE_REPO_TOKEN': 'never-use', 'GROQ_API_KEY': 'never-use'}):
            api = shadow.ShadowAPI()
            self.assertFalse(api.TELEGRAM_TOKEN)
            self.assertFalse(api.TELEGRAM_CHAT_ID)
            self.assertFalse(api.GROQ_API_KEY)
            for method in ('load_state', 'save_state', 'telegram_send', 'telegram_send_long', 'create_order'):
                self.assertFalse(hasattr(api, method))

    def test_telegram_broker_and_redirect_destinations_refused_before_network(self):
        api = shadow.ShadowAPI()
        for url, method in [('https://api.telegram.org/botFAKE/sendMessage','POST'),
                            ('https://api.binance.com/api/v3/order','POST'),
                            ('https://api.groq.com/openai/v1/chat/completions','GET'),
                            ('http://api.coingecko.com/api/v3/global','GET')]:
            with patch('requests.request') as request:
                with self.assertRaises(ValueError): api.request(url, method)
                request.assert_not_called()

    def test_missing_groq_is_deterministic_and_not_a_fake_success(self):
        api = shadow.ShadowAPI()
        before = copy.deepcopy(self.snap)
        with patch.object(api, 'groq_json') as groq:
            reports, evals, ai = shadow.render(self.snap, self.fund, api, self.now)
            groq.assert_not_called()
        self.assertFalse(ai['available'])
        self.assertEqual(self.snap, before)
        self.assertEqual(set(evals), set(shadow.SYMBOLS))
        self.assertTrue(all(not e['held'] for e in evals.values()))
        for report in reports.values():
            self.assertIn('SHADOW TEST', report)
            self.assertIn('rovnaký aktuálny snapshot', report)
            self.assertNotIn('POROVNANIE S RÁNOM', report)
            for symbol in shadow.SYMBOLS:self.assertIn(symbol+':', report)

    def test_groq_and_all_fundamentals_outage_still_render_na(self):
        with patch('socket.socket.connect', side_effect=RuntimeError('No network')):
            results, reports = shadow.outage_checks(self.snap, self.now)
        self.assertTrue(results['passed'])
        self.assertTrue(results['deterministic_decisions_unchanged'])
        self.assertTrue(all('N/A' in r for r in reports.values()))

    def test_long_retry_after_never_retries_early(self):
        import requests
        response = requests.Response(); response.status_code = 429
        response.headers['Retry-After'] = '120'
        with patch('requests.request', return_value=response) as request, patch('time.sleep') as sleep:
            with self.assertRaises(requests.HTTPError):shadow.ShadowAPI().http_json('https://api.coingecko.com/api/v3/global')
            self.assertEqual(request.call_count,1)
            sleep.assert_not_called()

    def test_ai_cannot_change_actions_or_author_new_reasons(self):
        class AI(shadow.ShadowAPI):
            def __init__(self):self.GROQ_API_KEY='test-only'
            def groq_json(self,*a,**k):return {'selections':{'SOL':[999,0]},'action':'BUY NOW','news':'invented'}
        reports, original, _ = shadow.render(self.snap,self.fund,shadow.ShadowAPI(),self.now)
        texts, actual, _ = shadow.render(self.snap,self.fund,AI(),self.now)
        self.assertEqual({s:e['action'] for s,e in original.items()},{s:e['action'] for s,e in actual.items()})
        self.assertTrue(all('invented' not in text for text in texts.values()))

    def test_runner_writes_only_isolated_outputs_and_restores_watchlist_environment(self):
        original = shadow.data.COINS
        with tempfile.TemporaryDirectory(dir=shadow.ROOT) as tmp:
            # run requires the explicitly reserved artifact directory.
            out = shadow.ROOT/'shadow-output'/'unit-test'
            def collect(api, full=True):
                self.assertEqual(set(shadow.data.COINS),set(shadow.SYMBOLS))
                self.assertEqual(os.environ['BOT_DISABLE_TELEGRAM'],'1')
                return copy.deepcopy(self.snap)
            try:
                with patch.dict(os.environ,{'BOT_DATA_MODE':'test-original'}), \
                     patch.object(shadow.data,'collect',side_effect=collect), \
                     patch.object(shadow.fundamentals,'collect',return_value=copy.deepcopy(self.fund)), \
                     patch.object(shadow.macro_context,'collect',return_value={'treasury':None}):
                    code=shadow.run(out)
                    self.assertEqual(os.environ['BOT_DATA_MODE'],'test-original')
                self.assertEqual(code,0)
                self.assertIs(shadow.data.COINS,original)
                summary=json.loads((out/'summary.json').read_text())
                self.assertTrue(summary['protected_files_unchanged'])
                self.assertFalse(summary['state_written'])
                self.assertFalse(summary['telegram_enabled'])
                self.assertTrue((out/'morning.txt').exists())
                self.assertTrue((out/'evening.txt').exists())
            finally:
                import shutil
                if out.exists():shutil.rmtree(out)

    def test_output_cannot_overwrite_repository_state(self):
        with self.assertRaises(ValueError):shadow.run(shadow.ROOT)

    def test_live_workflow_has_no_schedule_or_production_secrets(self):
        text=(shadow.ROOT/'.github/workflows/v11-1-shadow-test.yml').read_text()
        self.assertNotIn('secrets.TELEGRAM',text)
        self.assertNotIn('STATE_REPO_TOKEN',text)
        self.assertIn('persist-credentials: false',text)
        self.assertIn("if: always()",text)
        self.assertIn('  contents: read',text)
        self.assertIn('  workflow_dispatch:',text)
        self.assertNotIn('  schedule:',text)
        self.assertNotIn('  push:',text)

    def test_market_api_outage_yields_wait_na_without_synthetic_prices(self):
        class DownPublic(shadow.ShadowAPI):
            def http_json(self,*a,**k):raise ConnectionError('test outage')
            def coingecko_markets(self,*a):raise ConnectionError('test outage')
        api=DownPublic()
        snap=shadow.data.collect(api,full=True)
        reports,evals,_=shadow.render(snap,self.fund,api,self.now)
        self.assertFalse(snap['complete'])
        self.assertTrue(all(e['action']=='WAIT' and not e['data_complete'] for e in evals.values()))
        self.assertTrue(all('Cena N/A' in r for r in reports.values()))

    def test_renderer_fails_closed_when_groq_returns_invalid_payload(self):
        class BadAI(shadow.ShadowAPI):
            def __init__(self):self.GROQ_API_KEY='unit-test-only'
            def groq_json(self,*a,**k):return {'selections':{'SOL':['BUY NOW',-1,10000]}}
        _,_,ai=shadow.render(self.snap,self.fund,BadAI(),self.now)
        self.assertFalse(ai['available'])
        self.assertFalse(any(ai.get('selections',{}).values()))
