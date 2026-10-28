import copy,math,unittest
from v11 import prediction_shadow as m

def rows(n=400):
    return [dict(timestamp=i*m.STEP,open=100+i*.05,close=100+i*.05+math.sin(i/5),high=103+i*.05,low=97+i*.05,volume=1000+i%20) for i in range(n)]

class PredictionTests(unittest.TestCase):
    def test_causality(self):
        r=rows();a=m.forecast(r[:280],6);r[300]['close']=9999
        self.assertEqual(a,m.forecast(r[:280],6))
        self.assertIsNone(a['probabilities']);self.assertEqual(a['confidence'],'NÍZKA')
    def test_gaps_nan_and_invalid(self):
        for key,value in [('close',float('nan')),('volume',-1),('low',999),('timestamp',0)]:
            r=rows();r[100][key]=value;self.assertEqual(m.forecast(r,6)['status'],'NO_DATA')
    def test_closed_history_and_unique_levels(self):
        a=m.forecast(rows(),6);r=rows()
        for bar in r:
            for k in ('open','high','low','close'):bar[k]*=3
        b=m.forecast(r,6);self.assertAlmostEqual(b['low'],a['low']*3)
    def test_splits_and_baselines(self):
        result=m.evaluate(rows(330))
        self.assertFalse(result['independent_validation'])
        self.assertIn('flat',result['results']['24 h']['test']['models'])
    def test_journal_private_rejected(self):
        with self.assertRaises(ValueError):m.journal_update([], [{'symbol':'SOL','quantity':1}],{},0)
    def test_journal_dedup_exact_time_and_bound(self):
        r=dict(id='x',symbol='SOL',created=0,due=6,price=100,point=101,low=90,high=110,direction='RAST')
        j=m.journal_update([],[r,r],{('SOL',7):102},10);self.assertEqual(len(j),1);self.assertNotIn('result',j[0])
        j=m.journal_update(j,[],{('SOL',6):102},10);self.assertTrue(j[0]['result']['inside'])
    def test_stale_never_opportunity(self):
        self.assertEqual(m.coin_view({'raw':{'4h':rows()},'stale':True})['status'],'NO_DATA')
    def test_no_automatic_trade(self):
        v=m.coin_view(dict(raw={'4h':rows()},price=121,stale=False))
        self.assertEqual(v['action'],'WAIT');self.assertEqual(set(v['forecasts']),set(m.HORIZONS))
    def test_reject_bad_journal_bounds(self):
        r=dict(id='x',symbol='SOL',created=0,due=6,price=100,point=101,low=110,high=90,direction='RAST')
        with self.assertRaises(ValueError):m.journal_update([],[r],{},0)
    def test_matured_result_not_rewritten(self):
        r=dict(id='x',symbol='SOL',created=0,due=6,price=100,point=101,low=90,high=110,direction='RAST')
        j=m.journal_update([],[r],{('SOL',6):102},10)
        self.assertEqual(m.journal_update(j,[],{('SOL',6):105},20)[0]['result']['actual'],102)
    def test_journal_bounded(self):
        r=[dict(id=str(i),symbol='SOL',created=i,due=i+6,price=100,point=101,low=90,high=110,direction='RAST') for i in range(610)]
        self.assertEqual(len(m.journal_update([],r,{},0)),600)
    def test_fee_sensitivity_without_signal(self):
        v=m.coin_view(dict(raw={'4h':rows()},price=121,stale=False))
        self.assertEqual(v['action'],'WAIT')
        if v['economics']:
            self.assertLess(v['economics']['0.012']['net_target_pct'],v['economics']['0.01']['net_target_pct'])
    def test_invalid_current_price(self):
        for p in (None,float('nan'),-1):
            self.assertEqual(m.coin_view(dict(raw={'4h':rows()},price=p,stale=False))['status'],'NO_DATA')
