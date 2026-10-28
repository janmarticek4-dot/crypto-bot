import copy,math,unittest
import numpy as np
from v11 import prediction_research as r,prediction_journal as j
from v11.prediction_shadow import forecast,STEP
from v11.indicators import summary


def candles(n=1200):
    result=[]
    p=100.
    for i in range(n):
        close=p*math.exp(.0002+.007*math.sin(i*.71)+.002*math.sin(i*.13))
        result.append(dict(timestamp=i*STEP,open=p,close=close,high=max(p,close)*1.003,low=min(p,close)*.997,volume=1000+100*math.sin(i)))
        p=close
    return result


def paper():
    return dict(id='v2:x:SOL:24',symbol='SOL',created=601000,due=87060000,price=100.,point=101.,low=90.,high=110.,direction='DO STRANY',continuation=102.,
        model_version=r.VERSION,model='flat',source_digest='a'*64,btc_digest='b'*64,requested_hours=24,tolerance_log=.02,source_cutoff=600000,source_close=0,source_mode='FORWARD_PAPER',inputs=dict(features=[0.]*10,volatility_4h=.01,regime='SIDEWAYS',model_code_digest='c'*64,vintage_digest='d'*64))

class ResearchTests(unittest.TestCase):
    def test_sideways_tolerance(self):
        self.assertEqual(r.direction(.005,.01),'DO STRANY')
        self.assertEqual(r.direction(-.02,.01),'POKLES')
        self.assertEqual(r.direction(.02,.01),'RAST')
    def test_indicator_consistency(self):
        rows=candles(300);d=r.prepare(rows,rows);s=summary(rows)
        self.assertAlmostEqual(d['ema'][50][-1],s['ema50'])
        self.assertAlmostEqual(d['macd_hist'][-1],s['macd_hist'])
        self.assertAlmostEqual(d['rsi'][-1],s['rsi14'])
        self.assertAlmostEqual(d['atr'][-1],s['atr'])
    def test_legacy_point_reproduced(self):
        rows=candles(300);d=r.prepare(rows,rows)
        for h in (6,18,84):
            q=r.point_models(d,299,h,.1)['legacy_v1']
            self.assertAlmostEqual(rows[-1]['close']*math.exp(q),forecast(rows,h)['point'],places=10)
    def test_features_have_no_future(self):
        rows=candles(350);first=r.prepare(rows[:300],rows[:300]);full=r.prepare(rows,rows)
        np.testing.assert_allclose(first['features'][250:300],full['features'][250:300],equal_nan=True)
    def test_training_labels_are_matured(self):
        d=r.prepare(candles(500),candles(500));idx,_=r.label_data(d,84,400)
        self.assertLess(max(idx)+84,400)
    def test_btc_alignment_and_missing_fail_closed(self):
        a=candles(300);b=copy.deepcopy(a);b[40]['timestamp']+=1
        with self.assertRaises(ValueError):r.prepare(a,b)
        a[20]['volume']=float('nan')
        with self.assertRaises(ValueError):r.prepare(a,candles(300))
    def test_zero_volatility_no_ridge(self):
        x=np.ones((100,2));y=np.zeros(100)
        self.assertAlmostEqual(r.fit_predict(x,y,np.ones(2)),0.)
    def test_fit_not_enough_evidence(self):
        self.assertIsNone(r.fit_predict(np.ones((2,2)),np.ones(2),np.ones(2)))
    def test_direction_intervals_and_no_probabilities(self):
        m=r.metrics([dict(abs_error_pct=1.,direction_correct=True,inside=True,width_pct=10.,actual_direction='RAST',predicted_direction='RAST')]*6)
        self.assertLess(m['direction_ci95'][0],1);self.assertIsNotNone(m['mae_ci95'])
        self.assertIn('N/A',m['probability_calibration'])
    def test_sparse_metrics(self):
        self.assertEqual(r.metrics([])['status'],'NO_DATA')
        self.assertIsNone(r.uncertainty([1,2]))
    def test_vintage_cannot_backdate_revisions(self):
        v=dict(symbol='*',feature='yield_2y',value=4.,available_at=1000,published_at=1000,retrieved_at=1100,source_url='https://fred.stlouisfed.org/',vintage_id='first-seen:1')
        with self.assertRaises(ValueError):r.validate_vintage(v)
        v['available_at']=1100;r.validate_vintage(v)
        self.assertIsNone(r.pit_features([v],'SOL',1099))
        self.assertIsNotNone(r.pit_features([v],'SOL',1100))
        self.assertIsNone(r.pit_features([v],'SOL',1100,True))
    def test_expired_vintage_not_forward_filled(self):
        v=dict(symbol='*',feature='yield_2y',value=4.,available_at=0,published_at=0,retrieved_at=0,source_url='https://fred.stlouisfed.org/',vintage_id='x')
        self.assertIsNone(r.pit_features([v],'SOL',8*86400000))
    def test_regime_determined_at_origin(self):
        rows=candles(400);a=r.prepare(rows[:300],rows[:300]);b=r.prepare(rows,rows)
        self.assertEqual(r.regime(a,299,.1),r.regime(b,299,.1))
    def test_split_selection_and_future_mutation(self):
        rows=candles();first=r.experiment(rows,rows,'SOL')
        future=copy.deepcopy(rows)
        for x in future[1100:]:
            for key in ('open','high','low','close'):x[key]*=1.1
        second=r.experiment(future,future,'SOL')
        for h in first['results']:
            self.assertEqual(first['results'][h]['selected_on_validation'],second['results'][h]['selected_on_validation'])
            self.assertEqual(first['results'][h]['tolerance_factor'],second['results'][h]['tolerance_factor'])
        early=[x for x in first['records'] if x['origin']<=1000*STEP]
        other={(x['origin'],x['horizon'],x['model']):x for x in second['records']}
        for x in early:self.assertEqual(x['point'],other[x['origin'],x['horizon'],x['model']]['point'])
        __import__('json').dumps(first,allow_nan=False)
        self.assertFalse(first['independent_validation'])
        self.assertEqual(first['results']['24 h']['ablation']['status'],'NO_POINT_IN_TIME_HISTORY')
    def test_no_overlap_within_test_model(self):
        res=r.experiment(candles(),candles(),'SOL')
        for h in r.HORIZONS:
            a=[x for x in res['records'] if x['horizon']==h and x['model']=='flat' and x['part']=='test']
            self.assertTrue(all(b['origin']>=x['due'] for x,b in zip(a,a[1:])))
    def test_migrate_old_journal_not_paper(self):
        p=paper();old={k:v for k,v in p.items() if k in j.OLD}
        migrated=j.update([old],[],[],{('SOL',old['due']):103},old['due']+1000)
        self.assertNotIn('result',migrated['predictions'][0])
    def test_paper_origin_not_backdated(self):
        p=paper();p['created']=0
        with self.assertRaises(ValueError):j.validate_record(p)
    def test_paper_endpoint_and_immutability(self):
        p=paper();value=j.update([], [p],[],{('SOL',p['due']+1):103},p['due']+1000)
        self.assertNotIn('result',value['predictions'][0])
        value=j.update(value,[],[],{('SOL',p['due']):103},p['due']+1000)
        self.assertEqual(value['predictions'][0]['result']['actual'],103)
        p2=copy.deepcopy(p);p2['point']=200
        again=j.update(value,[p2],[],{('SOL',p['due']):120},p['due']+2000)
        self.assertEqual(again['predictions'][0]['point'],101)
        self.assertEqual(again['predictions'][0]['result']['actual'],103)
    def test_private_journal_and_corruption_refused(self):
        p=paper();p['quantity']=10
        with self.assertRaises(ValueError):j.load([p])
        with self.assertRaises(ValueError):j.load({'schema':'oops'})
    def test_vintages_do_not_mutate(self):
        old=j.load([]);p=paper();j.update(old,[p],[],{},p['created'])
        self.assertEqual(old['predictions'],[])
    def test_current_collection_is_not_backdated_history(self):
        from scripts.prediction_research import current_vintages
        values=current_vintages({'macro_context':{'treasury':{'2y':4.},'url':'https://fred.stlouisfed.org/graph/fredgraph.csv'}},10000)
        self.assertEqual(values[0]['available_at'],10000)
        self.assertIsNone(values[0]['published_at'])
        self.assertIsNone(r.pit_features(values,'SOL',9999))
    def test_macro_series_can_be_archived_with_shared_url(self):
        from scripts.prediction_research import current_vintages
        v=current_vintages({'economic_observations':{'url':'https://fred.stlouisfed.org/graph/fredgraph.csv','observations':{'CPIAUCSL':{'value':300}}}},10000)
        self.assertEqual(v[0]['feature'],'cpi')
    def test_both_macro_and_project_required_for_full_ablation(self):
        a=dict(symbol='*',feature='yield_2y',value=4.,available_at=10,published_at=None,retrieved_at=10,source_url='https://fred.stlouisfed.org/',vintage_id='a')
        b=dict(a,symbol='SOL',feature='fees',value=10.,vintage_id='b')
        self.assertIsNone(r.pit_features([a],'SOL',10,True))
        self.assertIsNotNone(r.pit_features([a,b],'SOL',10,True))
        self.assertIsNone(r.pit_features([a,b],'TAO',10,True))
    def test_future_paper_records_refused(self):
        with self.assertRaises(ValueError):j.update([], [paper()],[],{},0)
    def test_fake_result_refused(self):
        p=paper();p['result']='success'
        with self.assertRaises(ValueError):j.load([p])
    def test_legacy_clipping_includes_latest_shock(self):
        rows=candles(300);rows[-1]['close']*=1.3;rows[-1]['high']=rows[-1]['close']*1.01
        d=r.prepare(rows,rows)
        for h in (6,18,84):
            old=forecast(rows,h)
            point=rows[-1]['close']*math.exp(r.point_models(d,299,h,.1)['legacy_v1'])
            self.assertAlmostEqual(point,old['point'],places=10)
    def test_ablation_uses_same_training_rows(self):
        from unittest.mock import patch
        rows=candles(500);d=r.prepare(rows,rows);v=[]
        for i in range(200,500):
            for symbol,feature in [('*','yield_2y'),('SOL','fees')]:
                at=rows[i]['timestamp']+STEP
                v.append(dict(symbol=symbol,feature=feature,value=float(i%7),available_at=at,published_at=None,retrieved_at=at,source_url='https://example.org/public',vintage_id=f'{symbol}:{i}'))
        with patch.object(r,'fit_predict',wraps=r.fit_predict) as spy:
            out=r.point_models(d,499,6,.1,v,'SOL')
        self.assertTrue({'ridge_technical_matched','ridge_macro','ridge_macro_project'}<=set(out))
        a,b,c=spy.call_args_list[-3:]
        np.testing.assert_allclose(a.args[1],b.args[1]);np.testing.assert_allclose(a.args[1],c.args[1])
        self.assertEqual(len(a.args[0]),len(c.args[0]))
    def test_no_forward_prediction_without_fresh_quote(self):
        from scripts.prediction_research import forward_records
        self.assertEqual(forward_records({'SOL':dict(status='RESEARCH_ONLY',live={},source_end=0)},dict(coins={'SOL':dict(stale=False,price=100)}),STEP,'run'),[])
    def test_paper_metrics_pending_not_historical_success(self):
        from scripts.prediction_research import paper_summary
        result=paper_summary(j.load([]))
        self.assertEqual(result['SOL']['24']['status'],'PENDING')
        self.assertEqual(result['SOL']['24']['model']['n'],0)
    def test_constant_price_history_has_no_spurious_forecast(self):
        rows=[dict(timestamp=i*STEP,open=100.,high=101.,low=99.,close=100.,volume=1000.) for i in range(1200)]
        with self.assertRaisesRegex(ValueError,'NO_DATA'):r.experiment(rows,rows,'SOL')
    def test_lifetime_totals_not_double_counted(self):
        p=paper();v=j.update([], [p],[],{('SOL',p['due']):103},p['due']+1000)
        self.assertEqual(v['totals']['SOL:24']['n'],1)
        again=j.update(v,[],[],{('SOL',p['due']):105},p['due']+2000)
        self.assertEqual(again['totals'],v['totals'])
        self.assertEqual(again['predictions'][0]['result']['actual'],103)
    def test_forward_metrics_remove_overlapping_horizons(self):
        from scripts.prediction_research import paper_summary
        a=paper();b=copy.deepcopy(a);b['id']='v2:y:SOL:24';b['created']+=12*3600000;b['due']+=12*3600000
        value=j.update([], [a,b],[],{('SOL',a['due']):103.,('SOL',b['due']):99.},b['due']+1000)
        stats=paper_summary(value)['SOL']['24']
        self.assertEqual(stats['retained_matured'],2);self.assertEqual(stats['nonoverlapping_scored'],1)
        self.assertEqual(stats['lifetime']['n'],2)
