import copy,json,os,tempfile,unittest
from datetime import datetime,timezone,timedelta
from unittest.mock import patch
from v11 import event_lifecycle as e,integrated_report,analyst,prediction_research as r,prediction_runtime as rt,prediction_journal as j
from v11.telegram_text import without_links
from tests.test_analyst_v112 import sample,model,INVENTORY,NOW
from tests.test_prediction_research import candles

# Entirely synthetic test fixture, NOT the actual Fed decision or voting.
HTML=b'''<p>October 28, 2026</p><p>For release at 2:00 p.m. EDT</p>
<p>Federal Open Market Committee: inflation remains elevated.</p>
<p>The Committee decided to maintain the target range for the federal funds rate at 1 to 1-1/4 percent.</p>
<p>Voting for the monetary policy action were Synthetic Member A; Synthetic Member B. Voting against this action was Synthetic Member C.</p>'''
URL='https://www.federalreserve.gov/newsevents/pressreleases/monetary20261028a.htm'
AFTER=datetime(2026,10,28,19,40,tzinfo=timezone.utc) # 20:40 Bratislava, actual test case clock

class ProductionV2Tests(unittest.TestCase):
    def test_fed_oct28_exact_clock_and_verified_fields(self):
        out=e.parse_statement(HTML,URL,AFTER)
        self.assertEqual(out['published_at'],'2026-10-28T18:00:00+00:00')
        self.assertEqual(datetime.fromisoformat(out['published_at']).astimezone(e.BL).hour,19)
        self.assertEqual(out['rate_range'],[1,1.25]);self.assertIn('Synthetic Member C',out['voting'])
        self.assertIsNone(out['expectation'])
    def test_before_publication_cannot_use_future_result(self):
        with self.assertRaises(ValueError):e.parse_statement(HTML,URL,datetime(2026,10,28,17,59,tzinfo=timezone.utc))
    def test_calendar_not_a_result_and_past_not_upcoming(self):
        fund={'events':[dict(id='x',scheduled=True,event_date='2026-10-28',title='FOMC',categories=['Fed'])]}
        with patch.object(e.fundamentals,'fetch',side_effect=TimeoutError):out=e.collect(fund,AFTER)
        self.assertEqual(out['event_lifecycle']['releases'],[])
        self.assertNotEqual(out['events'][0]['lifecycle'],'UPCOMING')
        self.assertIn('N/A',' '.join(e.lines(out,AFTER)))
    def test_calendar_superseded_by_actual_statement(self):
        fund={'events':[dict(id='x',scheduled=True,event_date='2026-10-28',title='FOMC',categories=['Fed'])]}
        def fetch(s):
            if s['url']==URL:return HTML
            raise FileNotFoundError()
        out=e.collect(fund,AFTER,fetcher=fetch)
        self.assertEqual(out['events'][0]['lifecycle'],'SUPERSEDED')
        self.assertEqual(out['event_lifecycle']['releases'][0]['status'],'RELEASED')
    def test_wrong_date_and_nonofficial_refused(self):
        with self.assertRaises(ValueError):e.parse_statement(HTML,URL.replace('20261028','20261027'),AFTER)
        with self.assertRaises(ValueError):e.parse_statement(HTML,URL.replace('federalreserve.gov','example.com'),AFTER)
    def test_rate_fraction_formats(self):
        self.assertEqual(e.rate_number('3-3/4'),3.75);self.assertEqual(e.rate_number('3.75'),3.75)
        self.assertIsNone(e.rate_number('unknown'))
    def test_remove_all_link_forms_preserve_evidence_input(self):
        text='Fed https://example.com/news [výsledok](https://x.co/a) <a href="https://t.co/x">údaj</a> www.example.org'
        clean=without_links(text)
        self.assertNotIn('http',clean);self.assertNotIn('www.',clean);self.assertIn('výsledok',clean);self.assertIn('údaj',clean)
    def test_render_does_not_change_actions_or_public_model(self):
        snap=sample();m=model(snap);m['_current_fundamentals']={};m['experimental_predictions']={}
        old=analyst.final_text(m,snap,NOW,'evening',INVENTORY);before=copy.deepcopy(m)
        new=integrated_report.render(m,snap,NOW,'evening',INVENTORY)
        for line in old.splitlines():
            if any(line.startswith(s+' ') for s in analyst.COINS):self.assertIn(line,new)
        self.assertEqual(m,before);self.assertNotIn('https://',new);self.assertIn('PRESNOSŤ NEOVERENÁ',new)
        self.assertIn('N/A',new)
    def test_ridge_state_reproduces_prediction(self):
        import numpy as np
        x=np.arange(1000,dtype=float).reshape(100,10);y=np.sin(np.arange(100))
        state=r.fit_state(x,y)
        self.assertAlmostEqual(r.fit_predict(x,y,x[-1]),r.predict_state(state,x[-1]))
    def test_runtime_does_no_fitting(self):
        rows=candles(1200);result=r.experiment(rows,rows,'SOL');package=rt.package({'SOL':result},rows[-1]['timestamp']+rt.STEP)
        snap={'at':package['created']/1000,'coins':{s:dict(price=rows[-1]['close'],stale=False,raw={'4h':rows[-300:]}) for s in ('SOL','BTC')}}
        with patch.object(r,'fit_predict',side_effect=AssertionError('No fitting in delivery')):out=rt.predict(snap,package,package['created'])
        self.assertTrue(out['SOL'])
        with self.assertRaises(ValueError):rt.predict(snap,package,package['created']+49*3600000)
    def test_package_optional_backward_compatible_public_journal(self):
        old=j.load([]);old.pop('runtime_package')
        self.assertIsNone(j.load(old)['runtime_package'])
    def test_v2_failure_keeps_base_analysis_available(self):
        from scripts.v2_context import enrich
        snap=sample();m=model(snap)
        with patch('scripts.v2_context.PublicPredictionStore',side_effect=KeyError('missing public token')):
            enrich(snap,{},NOW,m,persist=False)
        text=integrated_report.render(m,snap,NOW,'evening')
        self.assertIn('SOL',text);self.assertIn('ZÁVER:',text)
    def test_economic_release_requires_official_body_not_calendar(self):
        fund={'events':[dict(id='cpi',scheduled=False,title='Consumer Price Index',source='bls',categories=['CPI'],published_at=AFTER.isoformat(),url='https://www.bls.gov/news.release/cpi.htm')]}
        raw=b'<p>Consumer prices increased in this synthetic fixture by an unspecified percent; this is test content, not a real CPI value.</p>'
        releases,_=e.economic_releases(fund,AFTER,lambda s:raw)
        self.assertEqual(releases[0]['status'],'RELEASED');self.assertIsNone(releases[0]['surprise'])
        fund['events'][0]['url']='https://unverified.example/cpi'
        self.assertEqual(e.economic_releases(fund,AFTER,lambda s:raw)[0],[])
    def test_comments_after_decision_and_other_voting_format(self):
        raw=HTML.replace(b'Voting for the monetary policy action were Synthetic Member A; Synthetic Member B. Voting against this action was Synthetic Member C.',b'The decision was unanimous.').replace(b'</p>\n<p>The decision',b'</p><p>Economic activity continued at a moderate pace in this synthetic fixture.</p>\n<p>The decision')
        result=e.parse_statement(raw,URL,AFTER)
        self.assertIn('unanimous',result['voting']);self.assertTrue(result['comments'])
    def test_missing_public_prediction_journal_never_resets(self):
        import urllib.error
        from scripts.public_prediction_store import PublicPredictionStore
        with patch.dict(os.environ,{'GITHUB_REPOSITORY':'example/public','GH_TOKEN':'synthetic'}):store=PublicPredictionStore()
        with patch.object(store,'request',side_effect=urllib.error.HTTPError('https://api.github.com',404,'missing',{},None)):
            with self.assertRaisesRegex(RuntimeError,'refusing reset'):store.read()

    def test_native_presentation_only_changes_outgoing_text(self):
        from scripts import native_presentation as native
        with patch.object(native.legacy, 'telegram_send') as sender:
            original = native.legacy.telegram_send
            def action():
                native.legacy.telegram_send('Risk: verified https://example.org/evidence')
                return 'unchanged native result'
            with patch.object(native.legacy, 'main', side_effect=action):
                self.assertEqual(native.run(), 'unchanged native result')
            self.assertIs(native.legacy.telegram_send, original)
            sender.assert_called_once_with('Risk: verified')
    def test_native_presentation_restores_sender_after_failure(self):
        from scripts import native_presentation as native
        with patch.object(native.legacy, 'telegram_send') as original:
            with patch.object(native.legacy, 'main', side_effect=RuntimeError('fixture')):
                with self.assertRaises(RuntimeError):native.run()
            self.assertIs(native.legacy.telegram_send, original)

    def test_missing_global_volume_not_reported_as_total_collapse(self):
        snap=sample();current=model(snap)['observation'];previous=copy.deepcopy(current)
        previous['at']=(NOW-timedelta(hours=1)).isoformat()
        previous['fingerprint']='a'*64
        previous['global_data']['volume']=1000000
        current['global_data']['volume']=0
        self.assertIsNone(analyst.comparison(previous,current)['global_volume_pct'])
        current['global_data']['volume']=800000
        self.assertAlmostEqual(analyst.comparison(previous,current)['global_volume_pct'],-20)
