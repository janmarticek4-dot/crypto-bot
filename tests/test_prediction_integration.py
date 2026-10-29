"""Synthetic integration fixtures; not model-accuracy or actual portfolio evidence."""
import copy,json,os,tempfile,unittest,urllib.error
from datetime import datetime,timezone,timedelta
from pathlib import Path
from unittest.mock import patch
from v11 import prediction_runtime as rt,integrated_report,report_verdict
from scripts import v2_context
from tests import test_report_quality as clockfixtures
from tests.test_analyst_v112 import sample,model

class ReadOnlyFixture:
    def __init__(self,package):self.package=package
    def read(self):return {'runtime_package':copy.deepcopy(self.package)}
    def append(self,*args):raise AssertionError('No writes from isolated preview')

class PredictionIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):clockfixtures.ClockPrecisionTests.setUpClass()
    def setUp(self):
        self.now=datetime.fromtimestamp(clockfixtures.ClockPrecisionTests.now/1000,timezone.utc)
        self.snap=sample();self.snap['at']=clockfixtures.ClockPrecisionTests.snapshot['at']
        base=clockfixtures.ClockPrecisionTests.snapshot['coins']['SOL']['raw']['4h']
        self.package=copy.deepcopy(clockfixtures.ClockPrecisionTests.package)
        item=self.package['coins']['SOL'];self.package['coins']={}
        for symbol in (*rt.COINS,'BTC'):
            price=self.snap['coins'][symbol]['price'];scale=price/base[-1]['close']
            rows=[dict(row,**{k:row[k]*scale for k in ('open','high','low','close')}) for row in base]
            self.snap['coins'][symbol]['raw']['4h']=rows
            if symbol in rt.COINS:
                self.package['coins'][symbol]=copy.deepcopy(item)
                self.package['coins'][symbol]['input_digest']=rt.r.digest(rows)
        self.inventory={'positions':[{'symbol':'SOL','quantity':1,'average_cost':42,'currency':'USD'},{'symbol':'TAO','quantity':1,'average_cost':99,'currency':'USD'}],'cash':None}
    def enrich(self,package=None,snapshot=None):
        snap=snapshot or self.snap;m=model(snap)
        v2_context.enrich(snap,{},self.now,m,persist=False,store=ReadOnlyFixture(package or self.package))
        return m
    def test_eighteen_in_both_main_reports_and_private_verdict(self):
        m=self.enrich();before=copy.deepcopy((m,self.snap,self.inventory))
        self.assertEqual(m['prediction_diagnostics']['available_predictions'],dict.fromkeys(rt.COINS,3))
        self.assertEqual(m['prediction_diagnostics']['missing_predictions'],{})
        for kind in ('morning','evening'):
            text=integrated_report.render(m,self.snap,self.now,kind,self.inventory)
            self.assertTrue(text.startswith('📌 INVESTIČNÝ VERDIKT:'))
            self.assertIn('SOL DRŽAŤ',text);self.assertIn('TAO DRŽAŤ',text)
            self.assertEqual(text.count('24h DO STRANY'),6)
            self.assertEqual(text.count('72h DO STRANY'),6)
            self.assertEqual(text.count('14d DO STRANY'),6)
            self.assertIn('PRESNOSŤ NEOVERENÁ',text);self.assertNotIn('Náhradný technický scenár',text)
        self.assertEqual((m,self.snap,self.inventory),before)
    def test_freshness_deadlines_not_extended_to_target_horizon(self):
        m=self.enrich();now=int(self.now.timestamp()*1000)
        for forecasts in m['experimental_predictions'].values():
            for forecast in forecasts.values():
                self.assertEqual(forecast['generated_at'],now)
                self.assertLessEqual(forecast['valid_until'],int(self.snap['at']*1000)+900000)
                self.assertIsNone(forecast['probabilities'])
        self.assertEqual(sum(map(len,rt.current_predictions(m,now).values())),18)
        self.assertEqual(sum(map(len,rt.current_predictions(m,now+900001).values())),0)
        text=integrated_report.render(m,self.snap,self.now+timedelta(minutes=16),'morning')
        self.assertNotIn('V2: 24h',text);self.assertIn('Náhradný technický scenár',text)
        self.assertIn('neaktuálny snapshot',text)
    def test_future_or_unclocked_cached_output_not_current(self):
        m=self.enrich();now=int(self.now.timestamp()*1000)
        self.assertEqual(sum(map(len,rt.current_predictions(m,now-1).values())),0)
        for forecasts in m['experimental_predictions'].values():
            for forecast in forecasts.values():forecast.pop('generated_at')
        self.assertEqual(sum(map(len,rt.current_predictions(m,now).values())),0)
    def test_expired_package_falls_back_with_precise_reason(self):
        package=copy.deepcopy(self.package);package['created']-=49*3600000
        for item in package['coins'].values():item['asof']=package['created']
        m=self.enrich(package)
        self.assertEqual(m['prediction_diagnostics']['prediction_reason'],'Runtime package stale/future')
        self.assertEqual(len(m['prediction_diagnostics']['missing_predictions']),6)
        self.assertEqual(sum(m['prediction_diagnostics']['available_predictions'].values()),0)
        text=integrated_report.render(m,self.snap,self.now,'morning',self.inventory)
        self.assertIn('SOL DRŽAŤ',text);self.assertIn('ZÁVER:',text)
        self.assertIn('Náhradný technický scenár',text)
    def test_missing_horizon_is_reported_without_discarding_other_seventeen(self):
        package=copy.deepcopy(self.package);package['coins']['SOL']['states'].pop('7–14 dní')
        m=self.enrich(package)
        self.assertEqual(sum(m['prediction_diagnostics']['available_predictions'].values()),17)
        self.assertEqual(m['prediction_diagnostics']['missing_predictions'],{'SOL':{'7–14 dní':'MODEL_HORIZON_MISSING'}})
    def test_one_coin_data_gap_does_not_remove_other_fifteen(self):
        self.snap['coins']['SOL']['raw']['4h'].pop(100)
        m=self.enrich();self.assertEqual(sum(m['prediction_diagnostics']['available_predictions'].values()),15)
        reason=m['prediction_diagnostics']['missing_predictions']['SOL']['24 h']
        self.assertIn('INVALID_OR_UNALIGNED_CLOSED_CANDLES',reason)
    def test_store_outage_uses_only_a_valid_dated_bundled_package(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'v11').mkdir()
            (root/'v11/prediction_runtime.py').write_text('# synthetic provenance')
            (root/'v11/frozen_prediction_package.json').write_text(json.dumps(self.package))
            store=ReadOnlyFixture(self.package)
            with patch.object(store,'read',side_effect=urllib.error.HTTPError('https://example.invalid',429,'synthetic',{},None)),patch.object(v2_context,'ROOT',root):
                m=model(self.snap);v2_context.enrich(self.snap,{},self.now,m,persist=False,store=store)
            self.assertEqual(m['prediction_diagnostics']['public_store_http_status'],429)
            self.assertEqual(m['prediction_diagnostics']['package_source'],'bundled-frozen')
            self.assertEqual(sum(m['prediction_diagnostics']['available_predictions'].values()),18)
    def test_inference_does_not_fit_new_model_or_call_ai(self):
        with patch.object(rt.r,'fit_state',side_effect=AssertionError('No training in delivery')),patch.object(rt.r,'fit_predict',side_effect=AssertionError('No fitting in delivery')):
            self.assertEqual(sum(self.enrich()['prediction_diagnostics']['available_predictions'].values()),18)
    def test_actual_scheduled_entrypoint_renders_eighteen_once_and_preserves_us_hook(self):
        from tests.test_manual_v111 import ManualV111Tests
        from scripts import v111_integrated_delivery as delivery,v111_trial as pilot
        from scripts.public_prediction_store import PublicPredictionStore
        from v11 import event_lifecycle
        from v11.reporting import chunks
        original_usa=pilot.usa_prepare
        with ManualV111Tests().setup_run(now=self.now,private=True) as (journal,collect,send):
            collect.side_effect=lambda *args,**kwargs:copy.deepcopy(self.snap)
            env={'V111_MANUAL_ANALYSIS':'false','GITHUB_EVENT_NAME':'schedule','V112_ANALYTICS_ENABLED':'true','V2_REPORT_ENABLED':'true'}
            with patch.dict(os.environ,env),patch.object(PublicPredictionStore,'read',return_value={'runtime_package':self.package}),patch.object(PublicPredictionStore,'append',return_value=None),patch.object(event_lifecycle,'collect',side_effect=lambda f,*args:f),patch('v11.advisory_portfolio.load',return_value=self.inventory):
                delivery.run()
                record=journal.value['slots']['2026-10-29-morning']
                self.assertEqual(record['status'],'sent')
                self.assertEqual(record['report_validation']['v2_count'],18)
                text=send.call_args.args[0]
                self.assertIn('SOL DRŽAŤ',text);self.assertIn('TAO DRŽAŤ',text)
                self.assertLessEqual(len(chunks(text)),2)
                self.assertNotIn('average_cost',json.dumps(journal.writes))
                self.assertNotIn('quantity',json.dumps(journal.writes))
                delivery.run();self.assertEqual(send.call_count,1)
        self.assertIs(pilot.usa_prepare,original_usa)
