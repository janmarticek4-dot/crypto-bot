from datetime import datetime, timezone
import unittest
import urllib.error
from scripts import macro_source_diagnostics as m
from scripts.macro_calendar_diagnostics import windows
from v11 import fundamentals as f

class RecoveryTests(unittest.TestCase):
    def test_retry_timeout_preserves_first_failure(self):
        calls=[]
        def fetch(source):
            calls.append(source)
            if len(calls)==1:raise TimeoutError()
            return b'<rss><channel/></rss>',dict(http_status=200)
        result=m.probe_with_retry(m.sources(2026)[0],fetch)
        self.assertEqual(result['status'],'SUCCESS')
        self.assertEqual(result['attempts'][0]['layer'],'timeout')
        self.assertEqual(calls[1]['timeout'],25)

    def test_no_retry_404_406_429_or_proxy_block(self):
        for code in (404,406,429,407):
            calls=[]
            def fetch(source):
                calls.append(source)
                raise urllib.error.HTTPError(source['url'],code,'error',{},None)
            m.probe_with_retry(m.sources(2026)[0],fetch)
            self.assertEqual(len(calls),1)

    def test_retry_stops_after_two_attempts(self):
        calls=[]
        def fetch(source):
            calls.append(source)
            raise TimeoutError()
        result=m.probe_with_retry(m.sources(2026)[0],fetch)
        self.assertEqual(len(calls),2)
        self.assertEqual(result['status'],'NETWORK_ERROR')

    def test_html_is_not_empty_successful_fundamental_feed(self):
        with self.assertRaises(ValueError):
            f.parse_feed(b'<html><title>Access denied</title></html>',f.SOURCES[1])

    def test_calendar_windows_and_dst_mismatch_week(self):
        now=datetime(2026,10,26,0,tzinfo=timezone.utc)
        raw=b'BEGIN:VCALENDAR\nBEGIN:VEVENT\nDTSTART;TZID=America/New_York:20261026T083000\nSUMMARY:Consumer Price Index\nEND:VEVENT\nEND:VCALENDAR'
        source=dict(id='bls',url='https://www.bls.gov/calendar',official=True)
        events=f.parse_calendar(raw,source,now)
        result=windows(events,now)
        self.assertEqual(result['24h'][0]['bratislava_at'],'2026-10-26T13:30:00+01:00')
        self.assertIsNone(result['24h'][0]['consensus'])
        self.assertEqual(windows(events,datetime(2026,10,27,tzinfo=timezone.utc))['14d'],[])

    def test_unknown_time_is_candidate_not_exact_event(self):
        events=[dict(event_at=None,event_date='2026-10-22')]
        row=windows(events,datetime(2026,10,22,12,tzinfo=timezone.utc))['24h'][0]
        self.assertIsNone(row['bratislava_at'])
        self.assertEqual(row['window_precision'],'date_only_candidate')
