import copy,json,os,unittest
from datetime import datetime,timezone,timedelta
from unittest.mock import patch
from v11 import prediction_research as r,prediction_runtime as rt,report_verdict as rv,integrated_report,event_lifecycle as ev
from tests.test_prediction_research import candles
from tests.test_analyst_v112 import sample,model,INVENTORY,NOW

class ClockPrecisionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        rows=candles(1200);shift=1793232000000-rows[-1]['timestamp']
        for row in rows:row['timestamp']+=shift
        # Fixed flat states isolate clock handling from data-dependent research
        # model selection / minimum-fold eligibility. No optimization in this test.
        close=rows[-1]['timestamp']+rt.STEP
        states={h:dict(model='flat',volatility_limit=.02,tolerance_factor=.2,offsets=[-1.,1.],ridge=None) for h in rt.HORIZONS}
        cls.package=dict(schema=rt.SCHEMA,version=r.VERSION,created=close,coins={'SOL':dict(asof=close,input_digest=r.digest(rows),btc_digest=r.digest(rows),states=states)})
        cls.snapshot=dict(at=1793254123.6515152,coins={s:dict(price=rows[-1]['close'],stale=False,raw={'4h':rows[-299:]}) for s in ('SOL','BTC')})
        cls.now=1793254123651
    def test_actual_morning_submillisecond_difference_not_future_data(self):
        self.assertLess(self.now-self.snapshot['at']*1000,0)
        diagnostics={};forecasts=rt.predict(self.snapshot,self.package,self.now,diagnostics)
        self.assertEqual(len(forecasts['SOL']),3);self.assertEqual(diagnostics['snapshot_age_ms'],0)
    def test_true_future_snapshot_remains_rejected(self):
        snapshot=copy.deepcopy(self.snapshot);snapshot['at']=(self.now+2)/1000
        with self.assertRaisesRegex(ValueError,'Snapshot stale/future'):rt.predict(snapshot,self.package,self.now)
    def test_stale_snapshot_remains_rejected(self):
        snapshot=copy.deepcopy(self.snapshot);snapshot['at']=(self.now-901000)/1000
        with self.assertRaisesRegex(ValueError,'Snapshot stale/future'):rt.predict(snapshot,self.package,self.now)
    def test_gapped_series_has_concrete_diagnostic(self):
        snapshot=copy.deepcopy(self.snapshot);snapshot['coins']['SOL']['raw']['4h'].pop(100)
        diagnostics={};result=rt.predict(snapshot,self.package,self.now,diagnostics)
        self.assertFalse(result['SOL']);self.assertIn('CLOSED_CANDLES',diagnostics['coin_errors']['SOL'])
    def test_missing_model_and_stale_btc_not_silently_omitted(self):
        snapshot=copy.deepcopy(self.snapshot);snapshot['coins']['BTC']['stale']=True
        diagnostics={};rt.predict(snapshot,self.package,self.now,diagnostics)
        self.assertEqual(diagnostics['coin_errors']['SOL'],'CURRENT_BTC_QUOTE_MISSING_OR_STALE')
        self.assertEqual(diagnostics['coin_errors']['TAO'],'MODEL_STATE_MISSING')

class VerdictTests(unittest.TestCase):
    def test_verdict_first_and_private_actions_preserved(self):
        snapshot=sample();m=model(snapshot);baseline=__import__('v11.analyst',fromlist=['final_text']).final_text(m,snapshot,NOW,'morning',INVENTORY)
        before=copy.deepcopy(m);text=integrated_report.render(m,snapshot,NOW,'morning',INVENTORY)
        self.assertTrue(text.startswith('📌 INVESTIČNÝ VERDIKT: KOREKCIA'))
        self.assertIn('POČKAŤ s novými nákupmi',text);self.assertIn('AAVE DRŽAŤ',text)
        for line in baseline.splitlines():
            if any(line.startswith(s+' ') for s in ('SOL','TAO','FET','AAVE','ONDO','RENDER')):self.assertIn(line,text)
        self.assertEqual(m,before)
    def test_no_positions_never_implies_hold_all(self):
        text=integrated_report.render(model(),sample(),NOW,'morning')
        self.assertIn('bez bezpečne načítaných pozícií neposúdená',text)
        self.assertNotIn('DRŽAŤ všetky',text)
    def test_interpretation_of_cap_volume_and_relative_weakness(self):
        snapshot=sample();m=model(snapshot);m['comparison']=dict(status='COMPARED',global_cap_pct=-2,global_volume_pct=20)
        self.assertIn('indície predajného tlaku',rv.interpretation(m,snapshot))
        m['comparison']['global_volume_pct']=None
        self.assertIn('Objemové potvrdenie',rv.interpretation(m,snapshot))
    def test_fallback_not_eighteen_na_or_invented_bands(self):
        text=integrated_report.render(model(),sample(),NOW,'morning')
        self.assertEqual(text.count('Náhradný technický scenár (nie V2)'),6)
        self.assertNotIn('Predikcia 24 h: N/A',text)
        self.assertTrue(rv.contract(text,0)['technical_fallback_labeled'])
    def test_stale_fallback_cannot_manufacture_scenario(self):
        snapshot=sample();snapshot['at']-=1000
        self.assertIn('neaktuálny snapshot',rv.fallback(model(),snapshot,'SOL','24 h',NOW))
    def test_missing_technical_data_not_invented(self):
        m=model();m['forecasts']['SOL']={}
        self.assertIn('neúplné údaje',rv.fallback(m,sample(),'SOL','24 h',NOW))
    def test_fed_is_slovak_not_raw_english(self):
        entry=dict(status='REACTION',event_date='2026-10-28',published_at='2026-10-28T18:00:00+00:00',rate_range=[3.75,4],decision='The Committee decided to maintain the target range',voting='approved by a 10 – 2 vote',comments=['Economic activity is expanding at a strong pace. Inflation remains elevated.'],reaction={})
        before=copy.deepcopy(entry);text=' '.join(ev.lines({'event_lifecycle':{'releases':[entry]}},datetime(2026,10,28,20,40,tzinfo=timezone.utc)))
        self.assertIn('ponechal',text);self.assertIn('3,75–4 %',text);self.assertIn('10:2',text)
        self.assertIn('inflácia podľa Fedu',text);self.assertNotIn('Economic activity',text);self.assertNotIn('The Committee',text)
        self.assertEqual(entry,before)
    def test_rate_cut_not_confused_with_maintaining_reserves(self):
        entry=dict(status='RELEASED',event_date='2026-10-28',published_at='2026-10-28T18:00:00+00:00',rate_range=[1,1.25],decision='The Committee decided to lower the target range. The Committee is maintaining ample reserves.',comments=[],reaction={})
        text=' '.join(ev.lines({'event_lifecycle':{'releases':[entry]}},datetime(2026,10,28,20,tzinfo=timezone.utc)))
        self.assertIn('znížil',text);self.assertNotIn('ponechal',text)
    def test_important_global_incident_not_lost_when_shortening(self):
        m=model();m['evidence']=[dict(title='Synthetic exchange withdrawals suspended after incident',published_at=NOW.isoformat(),source='synthetic',categories=['hack'],impact='riziko vyžaduje potvrdenie')]
        text=integrated_report.render(m,sample(),NOW,'morning')
        self.assertIn('withdrawals suspended',text);self.assertIn('riziko vyžaduje potvrdenie',text)
        self.assertNotIn('https://',text)
    def test_metadata_contains_no_position_data(self):
        text=integrated_report.render(model(),sample(),NOW,'morning',INVENTORY)
        metadata=rv.contract(text,0)
        self.assertNotIn('AAVE',json.dumps(metadata));self.assertNotIn('quantity',json.dumps(metadata))
        self.assertTrue(metadata['verdict_first']);self.assertTrue(metadata['urls_absent'])
    def test_receipt_is_after_attempting_and_keeps_uncertain_dedup(self):
        from tests.test_manual_v111 import ManualV111Tests
        from scripts import v111_trial as pilot
        with ManualV111Tests().setup_run() as (journal,collect,send):
            with patch.object(pilot,'delivery_metadata',return_value=dict(format_version=rv.FORMAT,verdict_first=True,urls_absent=True,v2_count=18)):
                send.side_effect=TimeoutError('synthetic')
                with self.assertRaises(TimeoutError):pilot.run('github-run-1000')
                record=journal.value['manual_slots']['github-run-1000'];self.assertEqual(record['status'],'uncertain')
                self.assertEqual(record['report_validation']['v2_count'],18)
                self.assertEqual(pilot.run('github-run-1000'),0);self.assertEqual(send.call_count,1)
