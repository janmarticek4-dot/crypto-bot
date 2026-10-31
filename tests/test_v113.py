import copy,unittest
from datetime import datetime,timezone
from v11.v113 import prediction_label,incident_fact,movement_review
from v11 import event_notices
from scripts.confirm_empty_inventory import correct

class V113Tests(unittest.TestCase):
    def test_flat_is_not_evidence_of_sideways_market(self):
        self.assertEqual(prediction_label({'model':'flat','direction':'DO STRANY'}),'REFERENCIA')
        self.assertEqual(prediction_label({'model':'ridge_technical','direction':'DO STRANY'}),'NEURČENÉ')
        for direction in ('RAST','POKLES'):self.assertEqual(prediction_label({'model':'regime_momentum','direction':direction}),direction)
    def test_explicit_empty_correction_preserves_cash_and_offsets_and_is_once_only(self):
        s=dict(advisory_portfolio=dict(positions=[dict(symbol='SOL',quantity=None,average_cost=98,currency='USD')],cash=None),telegram_update_offset=7,telegram_inventory={'offset':7,'pending':{'id':'synthetic'}})
        self.assertTrue(correct(s));self.assertEqual(s['advisory_portfolio'],{'positions':[],'cash':None});self.assertEqual(s['telegram_update_offset'],7)
        self.assertIsNone(s['telegram_inventory']['pending'])
        # A later real buy must NEVER be erased by rerunning this correction.
        s['advisory_portfolio']['positions']=[dict(symbol='SOL',quantity=1,average_cost=98,currency='USD')]
        self.assertFalse(correct(s));self.assertEqual(len(s['advisory_portfolio']['positions']),1)
    def test_incident_semantics_new_headline_not_new_fact(self):
        a=dict(title='Binance hackers raced to move billions',published_at='2026-10-31T01:00:00Z')
        b=dict(title='Recap how the Binance hack unfolded',published_at='2026-10-31T02:00:00Z')
        self.assertTrue(event_notices.same_notice(a,b))
        b['title']='Binance withdrawals resumed after hack';self.assertFalse(event_notices.same_notice(a,b))
        b['title']='Coinbase hack reported';self.assertFalse(event_notices.same_notice(a,b))
    def test_rapid_move_requires_causal_review_without_claiming_cause(self):
        r=movement_review({'global_data':{'change':-7.2},'coins':{'BTC':{}}},{})
        self.assertTrue(r['required']);self.assertEqual(r['causal_attribution'],'UNCONFIRMED');self.assertFalse(r['checks']['liquidations'])
    def test_empty_inventory_not_unknown_or_hold(self):
        from tests.test_smart_brief import CompactTests
        from v11 import compact_main
        # Reuse actual production fixture setup used by existing regressions.
        from tests.test_analyst_v112 import sample,model,NOW
        from v11 import trend_reversal
        snap=sample();m=model(snap);trend_reversal.attach(m,snap,{},NOW,{})
        text=compact_main.render(m,snap,NOW,'morning',{'positions':[],'cash':None})
        self.assertIn('Otvorené pozície: žiadne',text);self.assertNotIn('HOLD (držba)',text)
