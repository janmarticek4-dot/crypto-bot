import copy
from datetime import datetime,timezone
import unittest
from unittest.mock import patch
from scripts import v111_trial as p
from tests import test_shadow as fixtures

class PilotTests(unittest.TestCase):
    def test_slots_follow_bratislava_dst(self):
        for month,hour in [(7,5),(10,6)]:
            self.assertEqual(p.phase(datetime(2026,month,27,hour,tzinfo=timezone.utc)),'morning')
            self.assertEqual(p.phase(datetime(2026,month,27,hour+13,tzinfo=timezone.utc)),'evening')
        self.assertIsNone(p.phase(datetime(2026,10,27,13,tzinfo=timezone.utc)))
    def test_report_has_unknown_holdings_and_precise_small_prices(self):
        f=fixtures.ShadowTests();f.setUp();snap=f.snap
        text,quotes=p.render(snap,{'events':[]},f.now,'evening')
        self.assertIn('Držba N/A',text);self.assertNotIn('HOLD: žiadne',text)
        self.assertIn('Porovnanie rána N/A',text)
        self.assertEqual(p.price(.1755),'$0.1755')
        self.assertTrue(all(q['action']=='WAIT' for q in quotes.values()))
    def test_existing_attempt_is_not_sent_again(self):
        now=datetime(2026,10,27,6,tzinfo=timezone.utc)
        with patch.object(p,'datetime') as clock,patch.object(p,'PublicJournal') as j,patch.object(p,'send') as send:
            clock.now.return_value=now
            j.return_value.read.return_value={'schema':1,'slots':{'2026-10-27-morning':{'status':'uncertain'}}}
            self.assertEqual(p.run(),0);send.assert_not_called()
    def test_cas_failure_before_telegram_prevents_delivery(self):
        f=fixtures.ShadowTests();f.setUp();now=datetime(2026,10,27,6,tzinfo=timezone.utc)
        with patch.object(p,'datetime') as clock,patch.object(p,'PublicJournal') as j,patch.object(p.data,'collect',return_value=f.snap),patch.object(p.fundamentals,'collect',return_value={'events':[]}),patch.object(p,'send') as send:
            clock.now.return_value=now;j.return_value.read.return_value={'schema':1,'slots':{}}
            j.return_value.save.side_effect=RuntimeError('conflict')
            with self.assertRaises(RuntimeError):p.run()
            send.assert_not_called()
    def test_evening_uses_separate_morning_prices(self):
        f=fixtures.ShadowTests();f.setUp();first=p.observation(f.snap);second=copy.deepcopy(f.snap)
        second['coins']['SOL']['price']*=1.1
        text,_=p.render(second,{'events':[]},f.now,'evening',first)
        self.assertIn('Od rána: cena +10.00%',text)
