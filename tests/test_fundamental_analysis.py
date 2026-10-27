import unittest
from datetime import datetime,timezone,timedelta
from copy import deepcopy
from v11.fundamental_analysis import analyze,overview,coin_lines,SYMBOLS
from v11.ai import rank_evidence
from v11.macro_context import parse_fred
from v11.fundamentals import parse_feed

NOW=datetime(2026,10,26,12,tzinfo=timezone.utc)
def item(**changes):
    e=dict(id='one',title='Aave governance proposal',source='aave',url='https://governance.aave.com/t/1',
           published_at=NOW.isoformat(),retrieved_at=NOW.isoformat(),categories=['project'],symbol='AAVE',kind='news')
    e.update(changes);return e
def result(*events):return dict(events=list(events),sources=[])
class FundamentalAnalysisTests(unittest.TestCase):
    def test_proposal_not_adoption(self):
        a=analyze(result(item()),NOW)['evidence'][0]
        self.assertFalse(a['material']);self.assertIn('neutrálny',a['impact'])
    def test_release_not_adoption(self):
        self.assertFalse(analyze(result(item(title='Release v2',kind='software_release_notice')),NOW)['evidence'][0]['material'])
    def test_partnership_not_revenue(self):
        self.assertFalse(analyze(result(item(title='Aave announces partnership')),NOW)['evidence'][0]['material'])
    def test_stale_and_future_rejected(self):
        for t in (NOW-timedelta(days=4),NOW+timedelta(minutes=1)):
            self.assertEqual(analyze(result(item(published_at=t.isoformat())),NOW)['evidence'],[])
    def test_stale_collection_rejected(self):
        self.assertEqual(analyze(result(item(retrieved_at=(NOW-timedelta(days=2)).isoformat())),NOW)['evidence'],[])
    def test_malformed_rejected(self):
        for e in (None,{},item(title=None),item(url='http://wrong'),item(published_at='yesterday')):
            self.assertEqual(analyze(result(e),NOW)['evidence'],[])
    def test_duplicates(self):
        self.assertEqual(len(analyze(result(item(),item()),NOW)['evidence']),1)
    def test_no_news_not_complete(self):
        text=' '.join(overview(result(),NOW)+coin_lines('SOL',result(),NOW))
        self.assertIn('neúplné',text);self.assertIn('neznámy',text);self.assertIn('neznamená to absenciu',text)
    def test_incident_conditional(self):
        a=analyze(result(item(title='Solana exploit reported',categories=['hack'],symbol=None)),NOW)['evidence'][0]
        self.assertEqual(a['symbols'],['SOL']);self.assertIn('ak sa potvrdí',a['impact'])
    def test_numeric_levels_not_generated(self):
        text=' '.join(overview(result(item()),NOW))
        self.assertNotIn('BUY',text);self.assertNotIn('pravdepodobnosť 80',text)
    def test_input_immutable(self):
        r=result(item());before=deepcopy(r);analyze(r,NOW);self.assertEqual(before,r)
    def test_yield_changes(self):
        raw=b'observation_date,DGS2,DGS10\n2026-10-23,3.5,4.0\n2026-10-26,3.6,3.9\n'
        y=parse_fred(raw,NOW);self.assertEqual(y['change_bp'],{'2y':10.0,'10y':-10.0})
    def test_secondary_attribution_six_symbols(self):
        source=dict(id='secondary',url='https://example.org/feed',official=False)
        raw=b'<rss><channel><item><title>Solana upgrade activated</title><link>https://example.org/a</link><pubDate>Mon, 26 Oct 2026 12:00:00 GMT</pubDate></item></channel></rss>'
        self.assertEqual(parse_feed(raw,source,NOW)[0]['symbol'],'SOL')
    def test_ai_429_cooldown(self):
        class API:
            GROQ_API_KEY='synthetic';calls=0
            def groq_json(self,*a,**kw):self.calls+=1;raise RuntimeError('HTTP 429')
        api=API();state={};e=analyze(result(item(title='Aave exploit',categories=['hack'])),NOW)['evidence']
        self.assertFalse(rank_evidence(api,state,e,NOW)['available'])
        rank_evidence(api,state,e,NOW+timedelta(minutes=5));self.assertEqual(api.calls,1)
    def test_ai_fabrication_rejected(self):
        class API:
            GROQ_API_KEY='synthetic'
            def groq_json(self,*a,**kw):return {'ids':['invented'],'explanation':'Buy now'}
        e=analyze(result(item(title='Aave exploit',categories=['hack'])),NOW)['evidence']
        self.assertEqual(rank_evidence(API(),{},e,NOW),dict(ids=['one'],available=False))
    def test_ai_cache(self):
        class API:
            GROQ_API_KEY='synthetic';calls=0
            def groq_json(self,*a,**kw):self.calls+=1;return {'ids':['one']}
        e=analyze(result(item(title='Aave exploit',categories=['hack'])),NOW)['evidence'];api=API();state={}
        rank_evidence(api,state,e,NOW);rank_evidence(api,state,e,NOW+timedelta(minutes=2));self.assertEqual(api.calls,1)

class ProjectMetricsTests(unittest.TestCase):
    def test_closed_daily_only(self):
        import json
        from v11.project_metrics import parse
        rows=[[(NOW-timedelta(days=1)).replace(hour=0).timestamp(),123],
              [NOW.replace(hour=0).timestamp(),999]]
        self.assertEqual(parse(json.dumps({'totalDataChart':rows}).encode(),NOW)['value'],123)
    def test_malformed_and_stale(self):
        from v11.project_metrics import parse
        self.assertIsNone(parse(b'{"totalDataChart":[[1,100],[true,3],[null,4]]}',NOW))
    def test_failure_no_synthetic_zero(self):
        from v11.project_metrics import collect
        def fail(_):raise RuntimeError('unavailable')
        r=collect(fail,NOW);self.assertEqual(r['observations'],{})
        self.assertTrue(all(s['status']=='N/A' for s in r['sources']))

class FundamentalRegressionTests(unittest.TestCase):
    def test_report_clock_after_collection_not_snapshot_start(self):
        from test_briefing import snapshot
        from v11.briefing import build
        snap=snapshot();snap['at']=NOW.timestamp()-30
        ev={s:dict(action='WAIT',held=False,reasons=[],data_complete=True,score=3) for s in SYMBOLS}
        e=item(title='CPI release published',categories=['CPI'],symbol=None)
        text='\n'.join(build(snap,ev,{},dict(state='NORMAL',reasons=[]),result(e),{},'SHADOW_07:00',NOW))
        self.assertIn('CPI release published',text)
        self.assertLess(text.index('FUNDAMENTÁLNY SÚHRN'),text.index('SOL: WAIT'))
    def test_same_headline_different_publishers_deduplicates(self):
        self.assertEqual(len(analyze(result(item(),item(url='https://other.example/news')),NOW)['evidence']),1)
    def test_warnings_not_wars(self):
        from v11.fundamentals import PATTERNS
        import re
        self.assertFalse(re.search(PATTERNS['geopolitics'],'Musk warns of software issues',re.I))
    def test_malformed_timestamp(self):
        from v11.fundamentals import timestamp
        self.assertIsNone(timestamp([1,2]));self.assertIsNone(timestamp(123))
