import copy,math,unittest
from datetime import timedelta
from unittest.mock import patch
from v11 import trend_reversal as tr,reversal_report as rr,analyst,integrated_report,prediction_review
from tests.test_analyst_v112 import sample,model,NOW,INVENTORY

def candles(tf,kind='up',volume=True):
    step=tr.STEPS[tf];end=int(NOW.timestamp()*1000)//step*step
    rows=[]
    for i in range(300):
        p=100+i*.2 if kind=='up' else 220-i*.2
        if kind=='bounce' and i>=297:p=160.8+(i-296)*.1
        up=kind=='up' or kind=='bounce' and i>=297
        rows.append(dict(timestamp=end-(300-i)*step,open=p-.05 if up else p+.05,close=p,high=p+.08,low=p-.08,volume=140 if i>=297 and volume else 100))
    return rows

def snapshot(kind='up',daily_kind=None,volume=True):
    snap=sample();snap['at']=NOW.timestamp();snap['global_data'].update(at=NOW.timestamp(),cap=1000,volume=200,change=-2)
    for s,c in snap['coins'].items():
        c['raw']={'4h':candles('4h',kind,volume),'1d':candles('1d',daily_kind or kind,volume)}
        c.update(price=c['raw']['4h'][-1]['close'],stale=False,change_24h=2,relative_strength_btc_7d=.01)
    return snap

def old(snap,cap=900,kind='morning'):
    return dict(schema='public-analysis-v112',at=(NOW-timedelta(hours=4)).isoformat(),fingerprint='a'*64,kind=kind,
        global_data={'cap':cap,'volume':150},coins={s:{'price':c['price']*.99} for s,c in snap['coins'].items()},metrics={},economics={},
        reversal=dict(state='REVERSAL_CONFIRMING',source_close=int(NOW.timestamp()*1000)//tr.STEPS['4h']*tr.STEPS['4h']-tr.STEPS['4h'],groups=dict(btc_structure=True,capitalization=True,directional_volume=True,breadth=True),coins=dict.fromkeys(tr.COINS,'RECOVERY_ATTEMPT')))

def assess(snap,prior=True):
    m=model(snap);j={'last_analysis_v112':old(snap)} if prior else {}
    tr.attach(m,snap,{},NOW,j);return m

class DetectorTests(unittest.TestCase):
    def test_real_confirmation_requires_independent_groups_and_stability(self):
        r=assess(snapshot())['trend_reversal']
        self.assertEqual(r['state'],'UPTREND_CONFIRMED');self.assertTrue(all(r['groups'].values()));self.assertTrue(r['stable'])
    def test_six_rising_alts_and_price_bounce_are_not_buy_or_confirmed_trend(self):
        m=assess(snapshot('bounce','down'));r=m['trend_reversal']
        self.assertEqual(r['breadth']['rising_24h'],6);self.assertEqual(r['state'],'RECOVERY_ATTEMPT')
        self.assertTrue(all(c['action']=='WAIT' for c in m['coins'].values()))
    def test_daily_not_confirmed_can_be_reversal_confirming_not_full_bull(self):
        self.assertEqual(assess(snapshot('up','down'))['trend_reversal']['state'],'REVERSAL_CONFIRMING')
    def test_continuing_decline_remains_correction(self):
        snap=snapshot('down');prior=old(snap,cap=1200);m=model(snap)
        tr.attach(m,snap,{},NOW,{'last_analysis_v112':prior});self.assertEqual(m['trend_reversal']['state'],'CORRECTION')
    def test_rising_rolling_volume_is_not_buying_pressure(self):
        snap=snapshot(volume=False);snap['global_data']['volume']=100000
        r=assess(snap)['trend_reversal'];self.assertFalse(r['groups']['directional_volume']);self.assertNotEqual(r['state'],'UPTREND_CONFIRMED')
    def test_ema_and_structure_are_one_price_group_not_separate_votes(self):
        groups=assess(snapshot())['trend_reversal']['groups']
        self.assertEqual(set(groups),{'btc_structure','capitalization','directional_volume','breadth'})
    def test_same_closed_candle_across_reports_not_temporal_confirmation(self):
        snap=snapshot();prior=old(snap);prior['reversal']['source_close']+=tr.STEPS['4h'];m=model(snap)
        tr.attach(m,snap,{},NOW,{'last_analysis_v112':prior});self.assertFalse(m['trend_reversal']['stable'])
        self.assertEqual(m['trend_reversal']['state'],'REVERSAL_CONFIRMING')
    def test_cap_missing_or_stale_prevents_full_confirmation(self):
        snap=snapshot();snap['global_data']['at']-=1000;r=assess(snap)['trend_reversal']
        self.assertFalse(r['groups']['capitalization']);self.assertNotEqual(r['state'],'UPTREND_CONFIRMED')
        self.assertNotEqual(assess(snapshot(),False)['trend_reversal']['state'],'UPTREND_CONFIRMED')
    def test_gaps_nan_stale_quotes_and_short_history_fail_closed(self):
        for kind in ('gap','nan','stale','short'):
            snap=snapshot()
            if kind=='gap':snap['coins']['BTC']['raw']['4h'].pop(200)
            elif kind=='nan':snap['coins']['BTC']['raw']['4h'][-1]['close']=math.nan
            elif kind=='stale':snap['coins']['BTC']['stale']=True
            else:snap['coins']['BTC']['raw']['1d']=[]
            m=model(snapshot())
            tr.attach(m,snap,{},NOW,{'last_analysis_v112':old(snap)})
            r=m['trend_reversal'];self.assertIsNone(r['state']);self.assertEqual(r['quality'],'INSUFFICIENT')
    def test_future_candles_do_not_change_origin_evidence(self):
        snap=snapshot();before=tr.profile(snap['coins']['SOL'],int(NOW.timestamp()*1000))
        row=copy.deepcopy(snap['coins']['SOL']['raw']['4h'][-1]);row['timestamp']+=2*tr.STEPS['4h'];row['close']=row['high']=100000
        snap['coins']['SOL']['raw']['4h'].append(row)
        self.assertEqual(before,tr.profile(snap['coins']['SOL'],int(NOW.timestamp()*1000)))
    def test_macro_title_alone_cannot_confirm_or_cause_a_buy(self):
        snap=snapshot('bounce');m=assess(snap);r=copy.deepcopy(m['trend_reversal'])
        tr.attach(m,snap,{'events':[{'title':'Fed causes massive bull run'}]},NOW,{'last_analysis_v112':old(snap)})
        self.assertEqual(m['trend_reversal']['state'],r['state']);self.assertEqual(m['trend_reversal']['macro']['verified_releases'],[])
    def test_symbol_levels_computed_independently(self):
        snap=snapshot()
        for row in snap['coins']['TAO']['raw']['4h']:
            for k in ('open','high','low','close'):row[k]*=3
        snap['coins']['TAO']['price']*=3
        r=assess(snap)['trend_reversal']['coins'];self.assertAlmostEqual(r['TAO']['entry_level'],r['SOL']['entry_level']*3)

class ReferenceTests(unittest.TestCase):
    def test_named_refs_last_and_partial_legacy_do_not_invent_cap(self):
        snap=snapshot();prior=old(snap);legacy={'status':'sent','quotes':{'SOL':{'price':140},'_context':{'at':prior['at'],'fingerprint':'b'*64}}}
        j={'last_analysis_v112':prior,'slots':{'2026-10-27-morning':legacy}}
        refs=tr.references(j,NOW);self.assertEqual(refs['latest']['global_data']['cap'],900)
        j.pop('last_analysis_v112');refs=tr.references(j,NOW);self.assertEqual(refs['morning']['global_data'],{})
    def test_future_identical_and_unsent_references_not_used(self):
        prior=old(snapshot());prior['at']=(NOW+timedelta(hours=1)).isoformat()
        self.assertIsNone(tr.references({'last_analysis_v112':prior},NOW)['latest'])
        prior['at']=(NOW-timedelta(days=8)).isoformat()
        self.assertIsNone(tr.references({'last_analysis_v112':prior},NOW)['latest'])
        self.assertIsNone(tr.legacy_reference({'status':'uncertain','quotes':{}},'morning'))
    def test_history_bounded_and_no_mutation_of_observation(self):
        j={};value=old(snapshot());before=copy.deepcopy(value)
        for i in range(70):
            value['at']=(NOW-timedelta(hours=70-i)).isoformat();tr.remember(j,value,'manual' if i%3 else 'morning')
        self.assertLessEqual(len(j['analysis_history_v112']),30)
        before['at']=value['at'];self.assertEqual(value,before)

class ReportTests(unittest.TestCase):
    def test_intro_recovery_and_actions_preserved(self):
        snap=snapshot('bounce','down');m=assess(snap);base=analyst.final_text(m,snap,NOW,'morning',INVENTORY)
        text=integrated_report.render(m,snap,NOW,'morning',INVENTORY)
        self.assertIn('INVESTIČNÝ VERDIKT: POKUS O OBRAT',text);self.assertIn('rastie 6/6',text)
        self.assertEqual(rr.actions(text),rr.actions(base));self.assertNotIn('https://',text)
    def test_guard_repairs_breadth_and_unverified_cause_without_action_changes(self):
        snap=snapshot();m=assess(snap);base=analyst.final_text(m,snap,NOW,'morning')
        text='📌 INVESTIČNÝ VERDIKT: KOREKCIA\nvšetky altcoiny klesajú\nFed spôsobil rast\n'+base
        fixed,checks=rr.guard(text,base,m,snap)
        self.assertNotIn('všetky altcoiny klesajú',fixed);self.assertNotIn('Fed spôsobil',fixed)
        self.assertEqual(len(checks['corrected_comments']),3);self.assertEqual(rr.actions(fixed),rr.actions(base))
    def test_guard_refuses_new_trade_instructions(self):
        snap=snapshot();m=assess(snap);base=analyst.final_text(m,snap,NOW,'morning')
        with self.assertRaises(ValueError):rr.guard(base.replace('WAIT (nový nákup)','BUY NOW (nový nákup)',1),base,m,snap)
    def test_false_full_confirmation_is_downgraded(self):
        snap=snapshot();m=assess(snap);m['trend_reversal']['groups']['capitalization']=False
        base=analyst.final_text(m,snap,NOW,'morning');fixed,checks=rr.guard('📌 INVESTIČNÝ VERDIKT: RASTOVÝ TREND POTVRDENÝ\n'+base,base,m,snap)
        self.assertIn('VERDIKT: NEISTOTA',fixed)
    def test_no_sizing_or_new_buy_activation(self):
        snap=snapshot();m=assess(snap);text=integrated_report.render(m,snap,NOW,'morning')
        self.assertTrue(all(c['action']=='WAIT' for c in m['coins'].values()));self.assertIn('technický',text.lower())
        self.assertNotIn('nakúp 10',text.lower())

class PaperReviewTests(unittest.TestCase):
    def test_no_immature_results_or_invented_success(self):
        out=prediction_review.review({'predictions':[]},{},int(NOW.timestamp()*1000))
        self.assertEqual(out['matured'],0);self.assertIsNone(out['coins']['SOL']['24 h']['mean_absolute_error_pct'])
    def test_direction_vs_flat_and_continuation_are_counted_not_probabilities(self):
        now=int(NOW.timestamp()*1000)
        row=dict(model_version=prediction_review.VERSION,source_mode='FORWARD_PAPER',symbol='SOL',requested_hours=24,created=now-90000000,due=now-3600000,
            price=100,point=105,low=95,high=110,direction='RAST',continuation=105,tolerance_log=.01,
            result=dict(evaluated_at=now-1,actual_direction='RAST',direction_correct=True,abs_error_pct=1))
        out=prediction_review.review({'predictions':[row]},{},now)['coins']['SOL']['24 h']
        self.assertEqual((out['direction_hits'],out['flat_direction_hits'],out['trend_direction_hits']),(1,0,1));self.assertIsNone(out['calibrated_probability'])
        row['result']['evaluated_at']=now+1
        self.assertEqual(prediction_review.review({'predictions':[row]},{},now)['matured'],0)

class ResolutionTests(unittest.TestCase):
    def test_rounding_noise_in_market_cap_is_not_independent_confirmation(self):
        snap=snapshot();prior=old(snap,cap=999.99);m=model(snap)
        tr.attach(m,snap,{},NOW,{'last_analysis_v112':prior})
        self.assertFalse(m['trend_reversal']['groups']['capitalization'])
    def test_v2_estimates_cannot_change_reversal_or_actions(self):
        snap=snapshot();m=assess(snap);before=copy.deepcopy(m['trend_reversal'])
        m['experimental_predictions']={'SOL':{'24 h':{'direction':'RAST','point':999999}}}
        tr.attach(m,snap,{},NOW,{'last_analysis_v112':old(snap)})
        self.assertEqual(m['trend_reversal'],before)
        self.assertTrue(all(c['action']=='WAIT' for c in m['coins'].values()))

class TimeBasisTests(unittest.TestCase):
    def test_ambiguous_since_analysis_24h_comment_is_not_allowed(self):
        snap=snapshot();m=assess(snap);base=analyst.final_text(m,snap,NOW,'morning')
        text=integrated_report.render(m,snap,NOW,'morning')+'\nOd rána rast o 5% za 24h'
        fixed,checks=rr.guard(text,base,m,snap)
        self.assertNotIn('Od rána rast o 5%',fixed)
        self.assertIn('AMBIGUOUS_TIME_BASIS',checks['corrected_comments'])
