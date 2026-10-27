from datetime import datetime,timezone
import unittest
from unittest.mock import patch
from us_context import report as us,macro
from v11 import macro_context as m
from scripts import v111_trial as pilot

NOW=datetime(2026,10,26,14,tzinfo=timezone.utc)
class LiveUSIntegration(unittest.TestCase):
    def test_us_bls_alias_during_dst_mismatch(self):
        source=next(s for s in macro.SOURCES if s['id']=='bls_calendar')
        raw=b'BEGIN:VCALENDAR\nBEGIN:VEVENT\nDTSTART;TZID=US-Eastern:20261028T100000\nSUMMARY:Employment Situation\nEND:VEVENT\nEND:VCALENDAR'
        row=macro.parse_calendar(raw,source,NOW)[0]
        self.assertEqual(row['event_at'],'2026-10-28T14:00:00+00:00')
        with self.assertRaises(ValueError):macro.parse_feed(b'<html>denied</html>',source,NOW)
    def test_public_api_cannot_access_broker_or_telegram(self):
        api=us.PublicUSAPI()
        with patch('requests.get') as request:
            for url in ('https://api.telegram.org/sendMessage','https://api.binance.com/api/v3/order','http://query1.finance.yahoo.com/v8/finance/chart/%5EGSPC'):
                with self.assertRaises(ValueError):api.http_json(url)
            request.assert_not_called()
    def test_yahoo_secondary_endpoint_is_tried_without_loosening_quote_validation(self):
        class API(us.PublicUSAPI):
            def __init__(self):self.calls=[]
            def http_json(self,url,**kwargs):
                self.calls.append(url)
                if 'query1.finance' in url:raise OSError('primary unavailable')
                if 'query2.finance' in url:return {'chart':{'result':[{'meta':{}}],'error':None}}
                return {}
        api=API()
        with patch.object(us.fundamentals,'fetch',side_effect=OSError('offline')):
            result=us.collect(api,NOW)
        self.assertTrue(any('query2.finance' in u for u in api.calls))
        self.assertTrue(all(q['price'] is None for q in result['quotes'].values()))
    def test_fred_same_day_finite_fresh_values_only(self):
        raw=b'observation_date,DGS2,DGS10\n2026-10-23,3.5,4.2\n2026-10-26,.,4.3\n'
        self.assertEqual(m.parse_fred(raw,NOW),{'date':'2026-10-23','2y':3.5,'10y':4.2})
        for invalid in (raw.replace(b'2026-10-23',b'2026-09-01'),raw.replace(b'3.5',b'NaN'),b'<html>blocked</html>'):
            self.assertIsNone(m.parse_fred(invalid,NOW))
    def test_monthly_treasury_failure_uses_attributed_fred_fallback(self):
        calls=[]
        def fetch(source):
            calls.append(source['url'])
            if 'treasury.gov' in source['url']:raise TimeoutError()
            return b'observation_date,DGS2,DGS10\n2026-10-23,3.5,4.2\n'
        result=m.collect({},NOW,fetch)
        self.assertIn('field_tdr_date_value_month=202610',calls[0])
        self.assertIn('fredgraph.csv',result['url'])
        self.assertEqual(result['treasury']['2y'],3.5)
        self.assertIn('nie živá kotácia',m.lines(result)[0])
        self.assertEqual(result['attempts'][0]['status'],'N/A')
    def test_all_yield_sources_missing_stay_na(self):
        result=m.collect({},NOW,lambda source:b'<html>blocked</html>')
        self.assertIsNone(result['treasury']);self.assertIn('N/A',m.lines(result)[0])
    def test_usa_pilot_slot(self):
        self.assertEqual(pilot.phase(NOW),'usa')
        self.assertEqual(pilot.phase(datetime(2026,7,26,13,tzinfo=timezone.utc)),'usa')
