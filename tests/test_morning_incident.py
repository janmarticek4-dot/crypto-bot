import copy
from datetime import datetime,timezone
import unittest
from unittest.mock import patch,MagicMock
from v11.production_schedule import phase,target
from v11 import verified_monitor as m
from scripts import v111_trial as p

NOW=datetime(2026,10,31,8,8,tzinfo=timezone.utc)
CTX=dict(btc_change_24h=-6.,global_change=-5.,market_global={'data':{'updated_at':NOW.timestamp()}},btc_data={'last_updated':NOW.timestamp()})
def news(extra=''):
    return [dict(title='Binance exchange hacked; withdrawals suspended '+extra,link='https://coindesk.com/a',pub_date=NOW.isoformat()),
            dict(title='Binance confirms security breach and pauses withdrawals '+extra,link='https://cointelegraph.com/b',pub_date=NOW.isoformat())]

class IncidentTests(unittest.TestCase):
    def test_delayed_morning_and_winter_transition(self):
        self.assertEqual(phase(NOW),'morning');self.assertEqual(target(NOW,'morning').utcoffset().total_seconds(),3600)
        self.assertEqual(phase(datetime(2026,10,24,5,tzinfo=timezone.utc)),'morning')
        self.assertEqual(phase(datetime(2026,10,25,6,tzinfo=timezone.utc)),'morning')
        self.assertIsNone(phase(datetime(2026,10,31,11,tzinfo=timezone.utc)))
        self.assertEqual(phase(datetime(2026,10,31,14,tzinfo=timezone.utc)),'usa')
        self.assertEqual(phase(datetime(2026,10,31,19,tzinfo=timezone.utc)),'evening')
    def test_alert_no_probabilities_no_free_ai(self):
        ev,why=m.assess(news(),CTX,NOW);self.assertIsNotNone(ev)
        text=m.render(ev);self.assertIn('V11.2',text);self.assertNotIn('88',text);self.assertNotIn('13 %',text)
        self.assertIn('už uskutočnený',text);self.assertNotIn('https://',text)
    def test_old_rumor_price_only_missing_data_quiet(self):
        self.assertIsNone(m.assess(news('rumor'),CTX,NOW)[0])
        self.assertIsNone(m.assess(news(),{},NOW)[0]);self.assertIsNone(m.assess([],CTX,NOW)[0])
        self.assertIsNone(m.assess(news(),dict(btc_change_24h=1,global_change=2),NOW)[0])
        items=news()
        for row in items:row['pub_date']='2026-10-28T00:00:00Z'
        self.assertIsNone(m.assess(items,CTX,NOW)[0])
    def test_frozen_assets_not_additional_loss_and_mitigation(self):
        ev,_=m.assess(news('frozen assets'),CTX,NOW);self.assertIn('nie ďalšiu stratu',m.render(ev))
        self.assertIsNone(m.assess(news('losses covered; withdrawals resumed'),CTX,NOW)[0])
    def test_identical_republication_not_two_independent_sources(self):
        items=news();items[1]['title']=items[0]['title'];self.assertIsNone(m.assess(items,CTX,NOW)[0])
    def setup_monitor(self,state):
        journal=MagicMock();journal.read.return_value=copy.deepcopy(state)
        api=MagicMock();api.get_rss_news.return_value=news();api.gather_market_data.return_value=CTX;api.load_state.return_value={}
        return journal,api
    def test_no_repeat_and_uncertain_send(self):
        ev,_=m.assess(news(),CTX,NOW)
        for status in ('sent','uncertain','attempting','legacy_notified'):
            journal,api=self.setup_monitor({'schema':1,'slots':{},'risk_alerts_v112':{ev['id']:dict(status=status,stage=ev['stage'])}})
            with patch.object(m,'datetime',wraps=datetime) as clock,patch.object(p,'PublicJournal',return_value=journal),patch.object(p,'send') as send:
                clock.now.return_value=NOW;m.run(api);send.assert_not_called();api.groq_call.assert_not_called()
    def test_send_failure_journal_uncertain_and_no_native_http_retries(self):
        journal,api=self.setup_monitor({'schema':1,'slots':{}})
        with patch.object(m,'datetime',wraps=datetime) as clock,patch.object(p,'PublicJournal',return_value=journal),patch.object(p,'send',side_effect=TimeoutError()) as send:
            clock.now.return_value=NOW
            with self.assertRaises(TimeoutError):m.run(api)
            send.assert_called_once();self.assertEqual(list(journal.save.call_args.args[0]['risk_alerts_v112'].values())[0]['status'],'uncertain')
    def test_market_api_failure_quiet(self):
        journal,api=self.setup_monitor({'schema':1,'slots':{}});api.gather_market_data.side_effect=TimeoutError()
        with patch.object(p,'PublicJournal',return_value=journal),patch.object(p,'send') as send:m.run(api);send.assert_not_called()
    def test_pre_attempt_api_retry_only(self):
        journal=MagicMock();journal.read.return_value={'slots':{}}
        with patch.object(p,'_run',side_effect=[TimeoutError(),0]) as run,patch.object(p,'PublicJournal',return_value=journal),patch.object(p,'datetime') as clock,patch.object(p.time,'sleep'):
            clock.now.return_value=NOW;self.assertEqual(p.run(),0);self.assertEqual(run.call_count,2)
    def test_existing_uncertain_blocks_retry(self):
        journal=MagicMock();journal.read.return_value={'slots':{'2026-10-31-morning':{'status':'uncertain'}}}
        with patch.object(p,'_run',side_effect=TimeoutError()) as run,patch.object(p,'PublicJournal',return_value=journal),patch.object(p,'datetime') as clock:
            clock.now.return_value=NOW
            with self.assertRaises(TimeoutError):p.run()
            run.assert_called_once()
    def test_missing_telegram_ack_not_success(self):
        response=MagicMock();response.__enter__.return_value.read.return_value=b'{"ok":true}'
        with patch.dict(p.os.environ,{'TELEGRAM_TOKEN':'synthetic','TELEGRAM_CHAT_ID':'synthetic'}),patch.object(p.urllib.request,'urlopen',return_value=response):
            with self.assertRaisesRegex(RuntimeError,'message ID'):p.send('synthetic')
