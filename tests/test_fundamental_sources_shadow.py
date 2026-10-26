import json
from pathlib import Path
import unittest
from unittest.mock import patch
from datetime import datetime,timezone,timedelta
import urllib.error
from scripts.fundamental_sources_shadow import inspect,error_details,Probe,diagnostics
from v11.project_metrics import parse

NOW=datetime(2026,10,26,12,tzinfo=timezone.utc)
SOURCE=dict(id='fed',url='https://www.federalreserve.gov/feeds/press_all.xml',official=True,coverage=['Fed'])

def feed(day,title='Fed interest rate decision'):
    return f'<rss><channel><item><title>{title}</title><link>https://www.federalreserve.gov/a</link><pubDate>{day.isoformat()}</pubDate></item></channel></rss>'.encode()

class SourceDiagnosticsTests(unittest.TestCase):
    def test_current_parsed_feed(self):
        r=inspect(feed(NOW),SOURCE,NOW)
        self.assertEqual(r['status'],'OK_CURRENT');self.assertEqual(r['relevant_items'],1)
    def test_stale_feed_is_not_transport_failure(self):
        r=inspect(feed(NOW-timedelta(days=10)),SOURCE,NOW)
        self.assertEqual(r['status'],'STALE');self.assertTrue(r['schema_valid'])
    def test_empty_relevant_feed_is_not_successful_evidence(self):
        self.assertEqual(inspect(feed(NOW,title='Unrelated garden report'),SOURCE,NOW)['status'],'OK_NO_RECENT_RELEVANT_ITEMS')
    def test_html_challenge_not_feed(self):
        with self.assertRaises(ValueError):inspect(b'<html>challenge</html>',SOURCE,NOW)
    def test_network_tunnel_vs_http_origin(self):
        a=error_details(urllib.error.URLError('Tunnel connection failed: 403 Forbidden'))
        b=error_details(urllib.error.HTTPError(SOURCE['url'],403,'Forbidden',None,None))
        self.assertEqual(a['status'],'NETWORK_BLOCKED');self.assertEqual(b['status'],'HTTP_ERROR')
    def test_probe_records_failure_without_body_or_credential(self):
        p=Probe(NOW)
        with patch('scripts.fundamental_sources_shadow.fundamentals.fetch',side_effect=urllib.error.URLError('synthetic sensitive body')):
            with self.assertRaises(urllib.error.URLError):p.fetch(SOURCE)
        self.assertNotIn('sensitive',json.dumps(p.rows));self.assertFalse(p.rows[0]['schema_valid'])
    def test_probe_successful_http_invalid_schema(self):
        p=Probe(NOW)
        with patch('scripts.fundamental_sources_shadow.fundamentals.fetch',return_value=b'<html>challenge</html>'):p.fetch(SOURCE)
        self.assertEqual(p.rows[0]['retrieval'],'SUCCESS');self.assertEqual(p.rows[0]['status'],'INVALID_FORMAT')
    def test_fee_not_mislabeled_as_revenue(self):
        raw=json.dumps(dict(dataType='dailyFees',totalDataChart=[])).encode()
        with self.assertRaisesRegex(ValueError,'METRIC_TYPE_MISMATCH'):parse(raw,NOW,expected_type='dailyRevenue')
        with self.assertRaisesRegex(ValueError,'METRIC_TYPE_MISMATCH'):
            inspect(raw,dict(url='https://api.llama.fi/summary/fees/aave?dataType=dailyRevenue'),NOW)
    def test_missing_fee_schema(self):
        with self.assertRaisesRegex(ValueError,'FEES_CHART_SCHEMA_MISSING'):parse(b'{"error":"not found"}',NOW)
    def test_missing_macro_values_not_fabricated(self):
        r=inspect(b'observation_date,DGS2,DGS10\n2026-10-26,.,.\n',dict(url='https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS2,DGS10'),NOW)
        self.assertEqual(r['status'],'NO_RECENT_VALID_OBSERVATIONS');self.assertIsNone(r['latest_observation'])
    def test_calendar_without_time_preserved(self):
        source=dict(SOURCE,format='ics')
        raw=b'BEGIN:VCALENDAR\nBEGIN:VEVENT\nDTSTART;VALUE=DATE:20261028\nSUMMARY:FOMC meeting\nEND:VEVENT\nEND:VCALENDAR'
        r=inspect(raw,source,NOW);self.assertEqual(r['dates'],['2026-10-28'])
    def test_manual_workflow_no_delivery_or_private_secrets(self):
        root=Path(__file__).resolve().parents[1]
        w=(root/'.github/workflows/fundamental-sources-shadow.yml').read_text()
        for text in ('workflow_dispatch:', 'workflow_call:', 'contents: read', "BOT_DISABLE_TELEGRAM: '1'", 'actions/upload-artifact@v4','feature/v11-1-review'):
            self.assertIn(text,w)
        for text in ('schedule:', 'push:', 'contents: write', 'secrets.TELEGRAM', 'PROD_STATE_TOKEN', 'secrets: inherit'):
            self.assertNotIn(text,w)
        entry=(root/'.github/workflows/run.yml').read_text().split('  fundamental-sources:\n',1)[1].split('  private-state-authorization:',1)[0]
        self.assertIn('secrets.GROQ_API_KEY',entry);self.assertNotIn('secrets: inherit',entry)
    def test_report_separates_usage_proxy(self):
        report=diagnostics([],{},dict(requested=False),NOW)
        self.assertIn('nie počet používateľov',report);self.assertIn('Percento všetkých',report)

class SourceHarnessTests(unittest.TestCase):
    def test_full_harness_outputs_only_isolated_report(self):
        import tempfile
        from scripts import fundamental_sources_shadow as harness
        from test_briefing import snapshot
        root=Path(__file__).resolve().parents[1]
        fund=dict(events=[],sources=[],metrics={})
        api=type('API',(),dict(GROQ_API_KEY='',groq_attempts=0,requests=[]))()
        fake_ai=dict(available=False,fundamental_ranking=dict(available=False,ids=[]))
        snap=snapshot();snap['complete']=True
        with tempfile.TemporaryDirectory(dir=root/'shadow-output') as directory:
            with patch.object(harness,'ShadowAPI',return_value=api),patch.object(harness.data,'collect',return_value=snap),patch.object(harness.fundamentals,'collect',return_value=fund),patch.object(harness.macro_context,'collect',return_value={}),patch.object(harness.macro_context,'economic_observations',return_value={}),patch.object(harness,'render',return_value=({'evening':'SHADOW N/A'}, {}, fake_ai)),patch.object(harness,'outage_checks',return_value=({'passed':True},{})):
                self.assertEqual(harness.run(directory),0)
            p=Path(directory)
            self.assertTrue((p/'analysis_validation.json').exists())
            summary=json.loads((p/'summary.json').read_text())
            self.assertFalse(summary['telegram_enabled']);self.assertFalse(summary['orders_enabled'])
            self.assertFalse(summary['real_positions_loaded']);self.assertTrue(summary['protected_files_unchanged'])
            self.assertFalse((p/'morning.txt').exists())

class SchemaRegressionTests(unittest.TestCase):
    def test_treasury_html_not_reported_as_empty_valid_data(self):
        with self.assertRaisesRegex(ValueError,'TREASURY_XML_SCHEMA_MISSING'):
            inspect(b'<html>challenge</html>',dict(url='https://home.treasury.gov/resource.xml'),NOW)
    def test_truncated_calendar(self):
        with self.assertRaisesRegex(ValueError,'ICS_SCHEMA_MISSING'):
            inspect(b'BEGIN:VCALENDAR',dict(SOURCE,format='ics'),NOW)
    def test_wrong_csv_headers(self):
        with self.assertRaisesRegex(ValueError,'FRED_CSV_SCHEMA_MISSING'):
            inspect(b'observation_date,OTHER\n2026-10-26,4\n',dict(url='https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS2,DGS10'),NOW)

class LiveAIRequestTests(unittest.TestCase):
    def test_known_reasoning_model_gets_low_effort(self):
        from scripts.v111_shadow import ShadowAPI
        api=ShadowAPI();api.GROQ_API_KEY='synthetic';api.model='openai/gpt-oss-120b'
        with patch.object(api,'request',return_value={'choices':[{'message':{'content':'{"ids":["x"]}'}}]}) as request:
            self.assertEqual(api.groq_json('test'),{'ids':['x']})
        self.assertEqual(request.call_args.kwargs['payload']['reasoning_effort'],'low')
    def test_other_model_does_not_get_unsupported_parameter(self):
        from scripts.v111_shadow import ShadowAPI
        api=ShadowAPI();api.GROQ_API_KEY='synthetic';api.model='other-model'
        with patch.object(api,'request',return_value={'choices':[{'message':{'content':'{}'}}]}) as request:api.groq_json('test')
        self.assertNotIn('reasoning_effort',request.call_args.kwargs['payload'])

class AIRankingProtocolTests(unittest.TestCase):
    def test_json_mode_prompt_explicitly_mentions_json(self):
        from v11.ai import rank_evidence
        class API:
            GROQ_API_KEY='synthetic'
            def groq_json(self,prompt,**kwargs):
                if 'JSON' not in prompt:raise AssertionError('JSON mode requires explicit JSON instruction')
                return {'ids':['known']}
        result=rank_evidence(API(),{},[dict(id='known',title='Fed rate decision',categories=['Fed'],significance='rates',material=True)],NOW)
        self.assertTrue(result['available'])

class FeedFreshnessTests(unittest.TestCase):
    def test_new_channel_timestamp_does_not_freshen_old_news(self):
        old=NOW-timedelta(days=10)
        raw=feed(old).replace(b'<channel>',('<channel><pubDate>'+NOW.isoformat()+'</pubDate>').encode())
        self.assertEqual(inspect(raw,SOURCE,NOW)['status'],'STALE')
