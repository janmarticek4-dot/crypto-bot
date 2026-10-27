"""Characterization, not approval of the legacy rules or parameter optimization."""
import copy,unittest
from datetime import datetime,timezone,timedelta
from unittest.mock import patch
import main as legacy
from scripts.audit_exit_signals import audit
from tests import test_integration_candidate as fixtures

class ExitAuditTests(unittest.TestCase):
    def case(self):
        snap=fixtures.IntegrationTests().data()
        from v11 import integration
        ctx,mm,safety,ev=integration.evaluate(legacy,snap,{})
        data=ctx['portfolio_data']['SOL'];data['technical_4h'].update(ema50=170,ema200=180,rsi14=45,macd={'histogram':1})
        data['technical_score_calc']['score']=2.5
        m=mm['SOL'];m.update(drawdown_pct=12,deep_thr=10,support_broken=False,sell_pressure=False,support=150,price=160)
        return ctx,data,m
    def test_sell_does_not_require_broken_support_or_negative_momentum(self):
        ctx,d,m=self.case()
        e=legacy.decide_coin('SOL',d,m,{'state':'CRITICAL'},ctx,{},None)
        self.assertEqual(e['action'],'SELL');self.assertEqual(e['risk_pts'],8)
        self.assertFalse(e['support_broken']);self.assertGreater(e['macd_hist'],0)
    def test_critical_memory_changes_reduce_to_sell(self):
        ctx,d,m=self.case()
        self.assertEqual(legacy.decide_coin('SOL',d,m,{'state':'WARNING'},ctx,{},None)['action'],'REDUCE')
        self.assertEqual(legacy.decide_coin('SOL',d,m,{'state':'CRITICAL'},ctx,{},None)['action'],'SELL')
    def test_smoothing_can_preserve_sell_below_sell_threshold(self):
        self.assertEqual(legacy.smooth_action('SELL','WAIT',4,4)[0],'SELL')
    def test_future_peak_is_accepted_by_existing_rule(self):
        now=datetime.now(timezone.utc);state={'peaks':{'SOL':dict(price=200,ts=(now+timedelta(days=30)).isoformat())}}
        value=legacy.update_peak(state,'SOL',{},100)
        self.assertEqual(value,200) # known defect; no fix in this audit
    def test_technical_cap_can_overshoot_documented_three(self):
        ctx=dict(global_change=None,btc_change_24h=None,btc_data={'technical_4h':dict(price=100,ema50=110,ema200=120,macd={'histogram':1})})
        result=legacy.market_safety_v2(ctx,{'BTC':dict(drawdown_pct=0,review_thr=6,support_broken=True)},{})
        self.assertEqual(result['score'],4) # 1+1+2 despite comment saying max 3
    def test_audit_is_deterministic_and_never_mutates_inputs(self):
        snap=fixtures.IntegrationTests().data();state={'safety':{'state':'CRITICAL'}};before=copy.deepcopy((snap,state));at=datetime(2026,10,27,12,tzinfo=timezone.utc)
        self.assertEqual(audit(snap,state,at),audit(snap,state,at));self.assertEqual((snap,state),before)
