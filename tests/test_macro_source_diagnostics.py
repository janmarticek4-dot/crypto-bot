import copy
from datetime import datetime,timezone
from email.message import Message
import json
from pathlib import Path
import socket
import ssl
import unittest
from unittest.mock import patch
import urllib.error

from scripts import macro_source_diagnostics as m

RSS=b'<rss><channel><title>Official releases</title><item><title>Release</title><link>https://www.bls.gov/x</link><pubDate>Thu, 22 Oct 2026 10:00:00 GMT</pubDate></item></channel></rss>'
SOURCE=dict(provider='BLS',id='test',format='rss',url='https://www.bls.gov/x')


class MacroDiagnosticsTests(unittest.TestCase):
    def test_all_seven_providers_and_only_free_https_endpoints(self):
        self.assertEqual({s['provider'] for s in m.sources(2026)},{'Fed','BLS','BEA','ECB','SEC','CFTC','Treasury'})
        self.assertTrue(all(s['url'].startswith('https://') for s in m.sources(2026)))
        self.assertIn('2026',m.sources(2026)[-1]['url'])

    def test_success_and_empty_valid_feed_not_certified_as_coverage(self):
        result=m.probe(SOURCE,lambda s:(RSS,dict(http_status=200)))
        self.assertEqual(result['status'],'SUCCESS')
        self.assertEqual(result['validation']['records'],1)
        self.assertIn('not event time',result['validation']['note'])
        self.assertEqual(m.validate(b'<rss><channel><title>x</title></channel></rss>','rss')['records'],0)

    def test_tunnel403_is_not_origin403(self):
        def fail(s):raise urllib.error.URLError('Tunnel connection failed: 403 Forbidden')
        result=m.probe(SOURCE,fail)
        self.assertEqual(result['status'],'NETWORK_BLOCKED')
        self.assertEqual(result['proxy_status'],403)
        self.assertIsNone(result['origin_http_status'])
        self.assertEqual(result['layer'],'proxy_connect')

    def test_http403_and429_are_http_responses_not_tunnel_errors(self):
        for code in (403,404,429,503):
            def fail(s):raise urllib.error.HTTPError(s['url'],code,'not exported',{'Retry-After':'120'},None)
            result=m.probe(SOURCE,fail)
            self.assertEqual(result['status'],'HTTP_ERROR')
            self.assertEqual(result['http_status'],code)
            self.assertEqual(result['retry_after'],'120')
            self.assertIsNone(result['origin_http_status'])

    def test_explicit_http_proxy407_is_network_blocking(self):
        def fail(s):raise urllib.error.HTTPError(s['url'],407,'proxy auth',{},None)
        self.assertEqual(m.probe(SOURCE,fail)['status'],'NETWORK_BLOCKED')

    def test_network_dns_tls_and_timeouts_separate(self):
        for reason,layer,status in [(socket.gaierror('dns'),'dns','NETWORK_ERROR'),
                                    (ssl.SSLCertVerificationError('certificate'),'tls','TLS_ERROR'),
                                    (TimeoutError(),'timeout','NETWORK_ERROR')]:
            def fail(s):raise urllib.error.URLError(reason)
            result=m.probe(SOURCE,fail)
            self.assertEqual((result['layer'],result['status']),(layer,status))

    def test_direct_tls_error_is_not_reported_as_generic_transport(self):
        def fail(s):raise ssl.SSLCertVerificationError('private failure detail')
        result=m.probe(SOURCE,fail)
        self.assertEqual(result['status'],'TLS_ERROR')
        self.assertNotIn('private failure detail',json.dumps(result))

    def test_html_challenge_or_wrong_xml_at200_is_invalid_format(self):
        for raw in (b'<html><title>Access denied</title></html>',b'<error>denied</error>',b'<rss>broken',b''):
            result=m.probe(SOURCE,lambda s:(raw,dict(http_status=200)))
            self.assertEqual(result['status'],'INVALID_FORMAT')
            self.assertEqual(result['http_status'],200)

    def test_valid_ics_and_malformed_events(self):
        raw=b'BEGIN:VCALENDAR\nBEGIN:VEVENT\nDTSTART;TZID=America/New_York:20261023T083000\nSUMMARY:Release\nEND:VEVENT\nEND:VCALENDAR'
        self.assertEqual(m.validate(raw,'ics')['structurally_valid_records'],1)
        for bad in (b'<html>calendar blocked</html>',b'BEGIN:VCALENDAR\nBEGIN:VEVENT\nEND:VEVENT\nEND:VCALENDAR'):
            with self.assertRaises(m.InvalidFormat):m.validate(bad,'ics')

    def test_fomc_page_checks_schema_not_any_html200(self):
        raw=b'<h2>2026 FOMC Meetings</h2><div class="fomc-meeting__month">October</div><div class="fomc-meeting__date">27-28</div>'
        self.assertEqual(m.validate(raw,'fomc_html')['years'],['2026'])
        with self.assertRaises(m.InvalidFormat):m.validate(b'<html>FOMC access denied</html>','fomc_html')

    def test_treasury_requires_real_finite_observation_fields(self):
        raw=b'<feed><properties><NEW_DATE>2026-10-21T00:00:00</NEW_DATE><BC_2YEAR>4.1</BC_2YEAR><BC_10YEAR>4.2</BC_10YEAR></properties></feed>'
        self.assertEqual(m.validate(raw,'treasury_xml')['latest_observation_date'],'2026-10-21')
        with self.assertRaises(m.InvalidFormat):m.validate(raw.replace(b'4.1',b'NaN'),'treasury_xml')
        with self.assertRaises(m.InvalidFormat):m.validate(b'<feed><title>not yields</title></feed>','treasury_xml')

    def test_redirects_cannot_contact_telegram_http_or_other_publisher(self):
        for target in ('http://www.bls.gov/x','https://api.telegram.org/x','https://www.bls.gov.evil.invalid/x','https://user:secret@www.bls.gov/x','https://www.bls.gov:8443/x'):
            self.assertFalse(m.redirect_allowed(SOURCE,target))
        self.assertTrue(m.redirect_allowed(SOURCE,'https://www.bls.gov/new-feed'))
        bea=dict(SOURCE,url='https://apps.bea.gov/rss/rss.xml',publisher='bea.gov')
        self.assertTrue(m.redirect_allowed(bea,'https://www.bea.gov/feed'))

    def test_redirect_policy_exception_has_explicit_result(self):
        def fail(s):raise m.UnsafeRedirect('private details never exported')
        result=m.probe(SOURCE,fail)
        self.assertEqual(result['status'],'REDIRECT_BLOCKED')
        self.assertNotIn('private details',json.dumps(result))

    def test_unexpected_error_does_not_dump_sensitive_exception(self):
        def fail(s):raise RuntimeError('fake-secret-in-exception')
        result=m.probe(SOURCE,fail)
        self.assertEqual(result['status'],'DIAGNOSTIC_ERROR')
        self.assertNotIn('fake-secret',json.dumps(result))

    def test_output_restricted_and_no_production_imports_secrets_or_schedule(self):
        with self.assertRaises(ValueError):m.run(m.ROOT)
        script=(m.ROOT/'scripts/macro_source_diagnostics.py').read_text()
        self.assertNotIn('from v11',script)
        self.assertNotIn('import main',script)
        text=(m.ROOT/'.github/workflows/macro-sources-diagnostics.yml').read_text()
        for token in ('secrets.','  schedule:','pip install','main.py','bot_state.json'):
            self.assertNotIn(token,text)
        self.assertIn('runs-on: ubuntu-latest',text)
        self.assertIn('  workflow_dispatch:',text)
        self.assertIn('  contents: read',text)
        self.assertIn('if: always()',text)

    def test_complete_report_writes_results_without_source_success_requirement(self):
        out=m.ROOT/'macro-diagnostics-output'/'unit-test'
        def blocked(source):
            return dict(source,status='NETWORK_BLOCKED',layer='proxy_connect',proxy_status=403)
        try:
            with patch.object(m,'probe',side_effect=blocked):self.assertEqual(m.run(out),0)
            data=json.loads((out/'results.json').read_text())
            self.assertEqual(data['counts'],{'NETWORK_BLOCKED':9})
            self.assertTrue((out/'REPORT.md').exists())
            self.assertNotIn('HTTPS_PROXY',json.dumps(data))
        finally:
            import shutil
            if out.exists():shutil.rmtree(out)
