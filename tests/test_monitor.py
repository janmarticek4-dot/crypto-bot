import copy
import unittest
from unittest.mock import MagicMock, patch
from datetime import datetime
import main
from v11.runtime import run_monitor


class MonitorTests(unittest.TestCase):
    def setUp(self):
        self.state={}
        self.api=MagicMock()
        self.api.load_state.side_effect=lambda:self.state
        self.api.now_local.return_value=datetime.now(main.TZ)
        self.api.iso_now.return_value='2026-10-21T12:00:00+00:00'
        self.api._crisis_news_candidates.side_effect=main._crisis_news_candidates
        self.api.get_rss_news.return_value=[
            dict(title='Binance withdrawals suspended after incident',link='https://cointelegraph.com/1',pub_date='2026-10-21',source='A'),
            dict(title='Binance withdrawals suspended during investigation',link='https://www.coindesk.com/2',pub_date='2026-10-21',source='B')]
        self.snap={'at':2000000,'complete':True,'coins':{'BTC':{'change_24h':-6},'ETH':{'change_24h':-7}}}
    def run_monitor(self):
        with patch('v11.runtime.collect',return_value=self.snap):run_monitor(self.api)
    def test_no_ordinary_volatility_alert(self):
        self.snap['coins']['BTC']['change_24h']=-2
        self.run_monitor()
        self.api.telegram_send_long.assert_not_called()
    def test_no_incomplete_data_alert(self):
        self.snap['complete']=False
        self.run_monitor()
        self.api.telegram_send_long.assert_not_called()
    def test_single_source_not_enough(self):
        self.api.get_rss_news.return_value=self.api.get_rss_news.return_value[:1]
        self.run_monitor()
        self.api.telegram_send_long.assert_not_called()
    def test_cooldown_dedup(self):
        self.run_monitor()
        self.run_monitor()
        self.assertEqual(self.api.telegram_send_long.call_count,1)
        message=self.api.telegram_send_long.call_args.args[0]
        self.assertIn('nie sú kalibrované',message)
        self.assertEqual(self.state['crash_monitor_v11']['result'],'quiet')
