import copy,unittest
from research.exit_experiment import experiment as e

class ExperimentTests(unittest.TestCase):
    def coin(self,price=90):
        return dict(valid=True,price=price,technical={'ema20':100,'ema50':110,'ema200':120,'macd':{'histogram':-1}},score={'score':2},structure={'support_prev':100,'support_broken':True,'sell_pressure':False})
    def test_correlated_weakness_alone_is_hold(self):
        self.assertEqual(e.alternative(self.coin(),self.coin(),None,0)[0],'HOLD')
    def test_two_families_reduce_three_sell(self):
        c=self.coin();c['structure']['sell_pressure']=True
        self.assertEqual(e.alternative(c,self.coin(),None,0)[0],'REDUCE')
        self.assertEqual(e.alternative(c,self.coin(),self.coin(),0)[0],'SELL')
    def test_emergency_before_support_but_only_verified_current(self):
        c=self.coin(150);event=dict(known_at=100,verified=True,severity='severe',direct_exposure=True,primary_url='https://example.org/primary')
        self.assertEqual(e.alternative(c,None,None,100,event)[0],'SELL')
        for event in (dict(event,known_at=101),dict(event,known_at=-4000),dict(event,verified=False),dict(event,direct_exposure=False)):
            self.assertEqual(e.alternative(c,None,None,100,event)[0],'HOLD')
    def test_stale_critical_is_not_an_input(self):
        c=self.coin();c['safety']={'state':'CRITICAL','as_of':0}
        self.assertEqual(e.alternative(c,c,None,99999)[0],'HOLD')
    def test_prefix_invariance_of_features(self):
        rows=[dict(timestamp=i*14400000,open=100+i*.1,close=100+i*.1,high=101+i*.1,low=99+i*.1,volume=100+i) for i in range(301)]
        a=e.feature(rows[:300]);rows[-1]['close']=1e9
        self.assertEqual(a,e.feature(rows[:300]))
    def test_sale_never_executes_before_signal_available_and_costs_apply(self):
        times=[0,14400,28800];c=self.coin();features={t:{s:copy.deepcopy(c) for s in ('BTC',*e.SYMBOLS)} for t in times}
        frames={s:{t:dict(open=100,close=100,high=100,low=100) for t in times} for s in e.SYMBOLS}
        signals={t:{s:'SELL' for s in e.SYMBOLS} for t in times}
        rows,orders=e.simulate(frames,features,times,signals,'V10.6_technical',.01,.0025)
        self.assertTrue(all(o['time']>=o['signal_time'] for o in orders))
        self.assertLess(rows[-1]['net_return_pct'],0)
        self.assertEqual(rows[-1]['full_sells'],6)
        hold,_=e.simulate(frames,features,times,signals,'HOLD',.01,.0025)
        self.assertAlmostEqual(rows[-1]['net_return_pct'],hold[-1]['net_return_pct'])
    def test_reduce_is_once_per_exposure_episode_not_continuous_rebalance(self):
        times=[0,14400,28800,43200];c=self.coin();features={t:{s:copy.deepcopy(c) for s in ('BTC',*e.SYMBOLS)} for t in times}
        frames={s:{t:dict(open=100+i*10,close=100+i*10,high=100+i*10,low=100+i*10) for i,t in enumerate(times)} for s in e.SYMBOLS}
        signals={t:{s:'REDUCE' for s in e.SYMBOLS} for t in times}
        _,orders=e.simulate(frames,features,times,signals,'V10.6_technical',.01,.0025)
        self.assertEqual(len(orders),6)
    def test_future_price_cannot_change_earlier_orders(self):
        times=[i*14400 for i in range(5)];c=self.coin();features={t:{s:copy.deepcopy(c) for s in ('BTC',*e.SYMBOLS)} for t in times}
        frames={s:{t:dict(open=100,close=100,high=101,low=99) for t in times} for s in e.SYMBOLS}
        signals={t:{s:'SELL' for s in e.SYMBOLS} for t in times}
        _,before=e.simulate(frames,features,times,signals,'V10.6_technical',.01,.0025)
        for s in e.SYMBOLS:frames[s][times[-1]]['open']=1000000;features[times[-1]][s]['price']=1000000
        _,after=e.simulate(frames,features,times,signals,'V10.6_technical',.01,.0025)
        self.assertEqual([o for o in before if o['time']<times[-1]],[o for o in after if o['time']<times[-1]])
    def test_flat_hold_exact_roundtrip_cost(self):
        times=[0,14400];frames={s:{t:dict(open=100,close=100) for t in times} for s in e.SYMBOLS}
        rows,_=e.simulate(frames,{},times,{},'HOLD',.01,.0025)
        expected=((1-.0025)*(1-.01)/((1+.0025)*(1+.01))-1)*100
        self.assertAlmostEqual(rows[-1]['net_return_pct'],expected)
    def test_portfolio_drawdown_is_not_average_coin_drawdown(self):
        times=[0,14400];frames={s:{0:dict(open=100,close=100),14400:dict(open=100,close=50 if i<3 else 150)} for i,s in enumerate(e.SYMBOLS)}
        rows,_=e.simulate(frames,{},times,{},'HOLD',.01,.0025)
        self.assertLess(rows[-1]['max_drawdown_pct'],sum(r['max_drawdown_pct'] for r in rows[:-1])/6)
