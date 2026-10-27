import copy
from datetime import datetime,timedelta,timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfo
from v11 import shadow_pair as pair, fundamentals as f
from v11.diagnostics import technical,entry_diagnostic,risk_evidence
from v11.runtime import market_status
from v11.briefing import event_lines
from scripts import v111_shadow
from tests import fixtures_shadow as shadow_fixtures

BL=ZoneInfo('Europe/Bratislava')


def sample(at):
    base=shadow_fixtures.ShadowTests();base.setUp();snap=base.snap;snap['at']=at.timestamp()
    for c in snap['coins'].values():
        c['raw']={'4h':[dict(timestamp=int((at-timedelta(hours=4)).timestamp()*1000),close=c['price'])]}
        c['change_24h']=-2.
    return snap


class PairTests(unittest.TestCase):
    def setUp(self):
        self.am=datetime(2026,10,23,7,tzinfo=BL);self.pm=self.am.replace(hour=20)
        self.first=sample(self.am);self.second=sample(self.pm)
        self.e={s:dict(action='WAIT') for s in pair.SYMBOLS}
        self.saved=pair.checkpoint(self.first,self.e,self.am)

    def test_real_time_pair_changes_all_requested_fields(self):
        self.second['coins']['SOL'].update(price=110.,market_cap=1200.,volume_24h=150.)
        self.second['coins']['SOL']['frames']['4h'].update(higher_structure=False,adx=30.)
        new=copy.deepcopy(self.e);new['SOL']['action']='HOLD'
        result=pair.compare(self.saved,self.second,new,self.pm)
        sol=next(r for r in result['rows'] if r['symbol']=='SOL')
        self.assertAlmostEqual(sol['price_pct'],10.)
        self.assertAlmostEqual(sol['market_cap_pct'],20.)
        self.assertAlmostEqual(sol['volume24h_pct'],50.)
        self.assertEqual((sol['morning_action'],sol['evening_action']),('WAIT','HOLD'))
        self.assertNotEqual(sol['morning_trend'],sol['evening_trend'])
        self.assertEqual(result['hours'],13.)

    def test_same_source_snapshot_with_only_new_timestamp_is_rejected(self):
        duplicate=copy.deepcopy(self.first);duplicate['at']=self.pm.timestamp()
        with self.assertRaisesRegex(ValueError,'Reused'):pair.compare(self.saved,duplicate,self.e,self.pm)

    def test_stale_future_too_close_and_wrong_day_rejected(self):
        cases=[(self.second,self.pm+timedelta(days=1)),(self.first,self.pm),
               (self.second,self.am+timedelta(hours=1))]
        for snap,now in cases:
            with self.assertRaises(ValueError):pair.compare(self.saved,snap,self.e,now)
        bad=copy.deepcopy(self.second);bad['at']=self.pm.timestamp()+10
        with self.assertRaises(ValueError):pair.compare(self.saved,bad,self.e,self.pm)

    def test_checksum_and_morning_window_cannot_be_bypassed(self):
        changed=copy.deepcopy(self.saved);changed['evaluations']['SOL']['action']='BUY NOW'
        with self.assertRaises(ValueError):pair.compare(changed,self.second,self.e,self.pm)
        noon=self.am.replace(hour=12)
        with self.assertRaises(ValueError):pair.checkpoint(sample(noon),self.e,noon)

    def test_checkpoint_never_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'morning.json';pair.save_once(path,self.saved)
            old=path.read_bytes()
            with self.assertRaises(ValueError):pair.save_once(path,{'bad':'overwrite'})
            self.assertEqual(old,path.read_bytes())

    def test_missing_values_not_zero_and_missing_current_data_refused(self):
        self.second['coins']['SOL']['market_cap']=None
        result=pair.compare(self.saved,self.second,self.e,self.pm)
        self.assertIsNone(next(r for r in result['rows'] if r['symbol']=='SOL')['market_cap_pct'])
        self.second['coins']['SOL']['stale']=True
        with self.assertRaises(ValueError):pair.compare(self.saved,self.second,self.e,self.pm)

    def test_dst_dates_keep_correct_windows(self):
        for day in (23,25,26):
            morning=datetime(2026,10,day,7,tzinfo=BL);evening=morning.replace(hour=20)
            result=pair.compare(pair.checkpoint(sample(morning),self.e,morning),sample(evening),self.e,evening)
            self.assertEqual(result['hours'],13.)
            self.assertEqual(pair.slot(morning.astimezone(timezone.utc),'morning'),morning.date().isoformat())


class ExplanationTests(unittest.TestCase):
    def test_normal_is_not_a_low_risk_claim_at_minus5_cap(self):
        snap=sample(datetime(2026,10,23,7,tzinfo=BL));snap['global_data']['change']=-5.12
        safety=market_status(snap,{})
        self.assertEqual(safety['state'],'NORMAL')
        diagnostic=risk_evidence(snap,safety)
        self.assertEqual(diagnostic['price_context'],'výrazné cenové oslabenie')
        self.assertFalse(diagnostic['alerts_generated'])
        self.assertIsNone(diagnostic['crash_probability'])
        self.assertIn('nie nízke',diagnostic['interpretation'])
        snap['complete']=False
        self.assertEqual(market_status(snap,{})['state'],'UNKNOWN')

    def test_strong_technical_setup_does_not_clear_real_entry_blocks(self):
        d=sample(datetime(2026,10,23,7,tzinfo=BL))['coins']['SOL']
        from v11.strategy import decide
        with patch.dict('os.environ',{'V11_RULES_VALIDATED':'false','SPREAD_ESTIMATE':''}):
            e=decide(d,approved=False)
            result=entry_diagnostic(d,e,approved=False)
        self.assertEqual(result['technical']['score'],6)
        self.assertEqual(result['actual_action'],'WAIT')
        self.assertIn('spread neznámy',result['entry_blockers'])
        self.assertIn('dostupnosť na eToro neoverená',result['entry_blockers'])

    def test_report_starts_with_action_summary_without_causal_invention(self):
        snap=sample(datetime(2026,10,23,7,tzinfo=BL))
        reports,_,_=v111_shadow.render(snap,{'events':[],'sources':[]},v111_shadow.ShadowAPI(),datetime(2026,10,23,7,tzinfo=BL))
        self.assertLess(reports['morning'].index('AKČNÝ SÚHRN'),reports['morning'].index('TRH:'))
        self.assertIn('Overená príčina pohybu: N/A',reports['morning'])
        self.assertIn('Samostatné blokovania',reports['morning'])


class SourceRepairTests(unittest.TestCase):
    def test_tunnel_failure_distinct_from_publisher_http_failure(self):
        import urllib.error
        result=f.collect({},datetime(2026,10,23,tzinfo=timezone.utc),
            lambda source:(_ for _ in ()).throw(urllib.error.URLError('Tunnel connection failed: 403 Forbidden')))
        self.assertTrue(all(a['error_layer']=='network_tunnel' for s in result['sources'] for a in s['attempts']))

    def test_aave_fallback_keeps_secondary_trust_and_repository_kind(self):
        now=datetime(2026,10,23,12,tzinfo=timezone.utc)
        raw=b'<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Governance proposal update</title><updated>2026-10-23T08:00:00Z</updated><link href="https://github.com/aave/aip/commit/123"/></entry></feed>'
        def fetch(source):
            if source.get('id')=='aave_aip':return raw
            raise ConnectionError('offline')
        result=f.collect({},now,fetch)
        status=next(s for s in result['sources'] if s['source']=='aave')
        self.assertTrue(status['fallback']);self.assertFalse(status['official'])
        item=result['events'][0]
        self.assertEqual(item['kind'],'governance_repository_change')
        self.assertNotIn('oficiálny zdroj',item['confidence'])
        self.assertEqual(item['symbol'],'AAVE')

    def test_ondo_secondary_feed_does_not_tag_unrelated_news_or_price_prediction(self):
        source=f.FALLBACKS['ondo'][0];now=datetime(2026,10,23,12,tzinfo=timezone.utc)
        def raw(title):return f'<rss><channel><item><title>{title}</title><pubDate>Fri, 23 Oct 2026 08:00:00 GMT</pubDate><link>https://www.coindesk.com/2026/news</link></item></channel></rss>'.encode()
        self.assertFalse(f.parse_feed(raw('Bitcoin upgrade announced'),source,now))
        self.assertFalse(f.parse_feed(raw('Ondo price prediction'),source,now))
        item=f.parse_feed(raw('Ondo launches tokenized fund'),source,now)[0]
        self.assertEqual(item['symbol'],'ONDO');self.assertIn('vyžaduje',item['confidence'])

    def test_calendar_buckets_boundary_and_dst_and_date_only(self):
        now=datetime(2026,10,22,12,tzinfo=timezone.utc);source=dict(id='fixture',url='https://www.bls.gov/x',official=True)
        events=[]
        for hours,title in ((23,'Consumer Price Index in24h'),(24,'Employment situation in7d'),(7*24,'CPI in14d'),(14*24,'CPI at14d'),(14*24+1,'CPI outside')):
            at=now+timedelta(hours=hours)
            raw=f'BEGIN:VCALENDAR\nBEGIN:VEVENT\nDTSTART:{at:%Y%m%dT%H%M%SZ}\nSUMMARY:{title}\nEND:VEVENT\nEND:VCALENDAR'.encode()
            events+=f.parse_calendar(raw,source,now)
        text='\n'.join(event_lines({'events':events},now.timestamp()))
        for title in ('in24h','in7d','in14d','at14d'):self.assertIn(title,text)
        self.assertNotIn('outside',text)
        raw=b'BEGIN:VCALENDAR\nBEGIN:VEVENT\nDTSTART;VALUE=DATE:20261026\nSUMMARY:Consumer Price Index fixture\nEND:VEVENT\nEND:VCALENDAR'
        e=f.parse_calendar(raw,source,now)[0]
        self.assertIsNone(e['event_at']);self.assertEqual(e['event_date'],'2026-10-26')
        self.assertIn('presný čas Bratislava N/A','\n'.join(event_lines({'events':[e]},now.timestamp())))
        raw=b'BEGIN:VEVENT\nDTSTART;TZID=America/New_York:20261026T083000\nSUMMARY:Employment situation fixture\nEND:VEVENT'
        e=f.parse_calendar(raw,source,now)[0]
        self.assertIn('26.10.2026 13:30','\n'.join(event_lines({'events':[e]},now.timestamp())))

class PairIntegrationTests(unittest.TestCase):
    def test_evening_renderer_uses_immutable_morning_not_current_as_reference(self):
        am=datetime(2026,10,23,7,tzinfo=BL);pm=am.replace(hour=20)
        first=sample(am);second=sample(pm);second['coins']['SOL']['price']=110.
        api=v111_shadow.ShadowAPI()
        fund=dict(events=[],sources=[])
        morning_reports,ev,_=v111_shadow.render(first,fund,api,am,phase='morning')
        saved=pair.checkpoint(first,ev,am)
        old=copy.deepcopy(saved)
        evening,new,_=v111_shadow.render(second,fund,api,pm,phase='evening',morning=saved)
        verified=pair.compare(saved,second,new,pm)
        self.assertEqual(saved,old)
        self.assertEqual(set(morning_reports),{'morning'})
        self.assertEqual(set(evening),{'evening'})
        self.assertIn('POROVNANIE S RÁNOM',evening['evening'])
        self.assertIn('Od rána: cena +10.00%',evening['evening'])
        self.assertTrue(verified['verified_temporal_pair'])

    def test_wrong_commit_cannot_use_old_checkpoint(self):
        am=datetime(2026,10,23,7,tzinfo=BL);pm=am.replace(hour=20)
        with patch.dict('os.environ',{'GITHUB_SHA':'first','GITHUB_REF_NAME':'feature/v11-1-review'}):
            saved=pair.checkpoint(sample(am),{s:dict(action='WAIT') for s in pair.SYMBOLS},am)
        with patch.dict('os.environ',{'GITHUB_SHA':'second','GITHUB_REF_NAME':'feature/v11-1-review'}):
            with self.assertRaisesRegex(ValueError,'another commit'):
                pair.compare(saved,sample(pm),saved['evaluations'],pm)

    def test_workflow_checks_reference_provenance_without_state_secrets(self):
        text=(v111_shadow.ROOT/'.github/workflows/v11-1-shadow-test.yml').read_text()
        for token in ('actions: read','run.head_sha !== context.sha','run.conclusion','actions/download-artifact@v4','--checkpoint'):
            self.assertIn(token,text)
        self.assertNotIn('secrets.STATE_',text)
        self.assertNotIn('secrets.TELEGRAM',text)

class AttributionTests(unittest.TestCase):
    def test_repository_path_alone_cannot_impersonate_publisher(self):
        source=f.FALLBACKS['aave'][0]
        raw=b'<feed><entry><title>Governance proposal update</title><updated>2026-10-23T08:00:00Z</updated><link href="https://evil.invalid/aave/aip/commit/123"/></entry></feed>'
        self.assertEqual(f.parse_feed(raw,source,datetime(2026,10,23,12,tzinfo=timezone.utc)),[])
