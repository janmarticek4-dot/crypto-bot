import copy,unittest
from datetime import timedelta
from unittest.mock import patch
from tests.test_us_outlook import snapshot
from tests.test_analyst_v112 import sample,model,NOW
from v11.us_brief import render
from v11 import analyst
from us_context import report as us

class BriefTests(unittest.TestCase):
    def setUp(self):
        self.snap=sample();self.model=model(self.snap);self.context=snapshot(NOW)
        for s in analyst.COINS:self.context['crypto']['coins'][s]=dict(change=-1,price=100,at=NOW,source='test')
        self.context['crypto']['coins']['BTC']['change']=-2
        self.context['crypto']['cap_change']=-3
    def text(self,inventory=None):return render(self.context,self.model,self.snap,{},NOW,inventory)
    def test_coherent_correction_and_mixed_not_growth(self):
        self.assertIn('VERDIKT TRHU: Korekcia',self.text())
        self.context['crypto']['coins']['BTC']['change']=2
        self.assertIn('VERDIKT TRHU: Neistota',self.text())
        self.assertNotIn('VERDIKT TRHU: Rast',self.text())
    def test_growth_needs_broad_confirmation(self):
        self.context['crypto']['cap_change']=3
        for c in self.context['crypto']['coins'].values():c['change']=1
        self.assertIn('VERDIKT TRHU: Rast',self.text())
    def test_unknown_data_never_assumed_sell_or_hold(self):
        self.context['crypto']['cap_change']=None
        text=self.text();self.assertIn('Neistota',text);self.assertIn('držba bezpečne neoverená',text)
        self.assertNotIn('SOL: HOLD',text);self.assertNotIn('TAO: SELL',text)
    def test_short_no_urls_or_dump_and_correct_periods(self):
        text=self.text();self.assertLessEqual(len(text),2000)
        for bad in ('https://','EMA','RSI','MACD','ATR'):self.assertNotIn(bad,text)
        self.assertIn('Nie je to meranie reakcie po otvorení',text)
        self.assertEqual(text.count('• '),2)
    def test_personal_actions_exactly_same_and_no_inventory_leak(self):
        inv={'positions':[{'symbol':'SOL','quantity':7,'average_cost':42,'currency':'USD'},{'symbol':'TAO','quantity':3,'average_cost':99,'currency':'USD'}],'cash':None}
        before=copy.deepcopy((self.model,self.snap,inv))
        text=self.text(inv)
        baseline=analyst.final_text(self.model,self.snap,NOW,'usa',inv)
        for symbol in ('SOL','TAO'):
            from v11.report_verdict import actions
            action=next(a for s,a,c in actions(baseline) if s==symbol and c=='držba')
            self.assertIn(symbol+': '+action,text)
        self.assertNotIn('quantity',text);self.assertEqual((self.model,self.snap,inv),before)
    def test_current_cash_change_not_claimed_since_open(self):
        self.context['market']['phase']='AFTER OPEN'
        for s,q in self.context['quotes'].items():
            if q['kind']=='index':q.update(change=-1,price=100,at=NOW,status='oneskorený zdroj')
        text=self.text();self.assertIn('nie od dnešného otvorenia',text);self.assertIn('Akcie klesajú',text)
    def test_stale_quotes_not_interpreted(self):
        self.context['market']['phase']='AFTER OPEN'
        for q in self.context['quotes'].values():q.update(change=10,price=100,at=NOW-timedelta(hours=2))
        self.assertIn('spoľahlivé porovnateľné kotácie chýbajú',self.text())
    def test_native_rules_not_called_by_renderer(self):
        with patch('main.evaluate_coin',side_effect=AssertionError('new rules')) if hasattr(__import__('main'),'evaluate_coin') else patch('main.main',side_effect=AssertionError('side effect')):
            self.text()
    def test_scheduled_past_never_presented_as_future(self):
        event=dict(scheduled=True,event_at=(NOW-timedelta(hours=1)).isoformat(),categories=['CPI'],source='BLS',lifecycle='UPCOMING')
        text=render(self.context,self.model,self.snap,{'events':[event]},NOW)
        self.assertNotIn('CPI USA',text)
        event['event_at']=(NOW+timedelta(hours=2)).isoformat()
        text=render(self.context,self.model,self.snap,{'events':[event]},NOW)
        self.assertIn('CPI USA',text);self.assertIn('Bratislava (BLS)',text)
        self.assertLessEqual(len(text),2000)
    def test_macro_result_full_quotes_and_holdings_fit_budget(self):
        self.context['market']['phase']='AFTER OPEN'
        for q in self.context['quotes'].values():q.update(change=-1.23,price=100,at=NOW,status='oneskorený zdroj')
        release=dict(status='RELEASED',event_date='2026-10-27',published_at=NOW.isoformat(),decision='decided to maintain',rate_range=[4.25,4.5],reaction={},comments=[])
        text=render(self.context,self.model,self.snap,{'event_lifecycle':{'releases':[release]}},NOW)
        self.assertIn('Fed ',text);self.assertIn('ponechal',text);self.assertLessEqual(len(text),2000)
    def test_stale_snapshot_does_not_reuse_old_price_boundaries(self):
        self.snap['at']=(NOW-timedelta(hours=1)).timestamp()
        text=self.text();self.assertNotIn('BTC podpora $',text);self.assertIn('smer nemožno spoľahlivo určiť',text)
    def test_opposite_us_equities_and_crypto_not_one_sided_verdict(self):
        self.context['market']['phase']='AFTER OPEN'
        for q in self.context['quotes'].values():q.update(change=1,price=100,at=NOW,status='oneskorený zdroj')
        text=self.text();self.assertIn('VERDIKT TRHU: Neistota',text);self.assertIn('protichodný smer',text)
