import unittest
from datetime import datetime,timezone
from v11 import fundamentals as f

NOW=datetime(2026,10,21,12,tzinfo=timezone.utc)
SOURCE=dict(id='test',url='https://www.bls.gov/feed/x',official=True,coverage=['CPI'])


class FundamentalTests(unittest.TestCase):
    def rss(self,date,title='Consumer Price Index release',url='https://www.bls.gov/news/cpi'):
        return f'<rss><channel><item><title>{title}</title><link>{url}</link><pubDate>{date}</pubDate></item></channel></rss>'.encode()
    def test_current_official_release_has_date_source_mechanism(self):
        items=f.parse_feed(self.rss('Wed, 21 Oct 2026 08:00:00 GMT'),SOURCE,NOW)
        self.assertEqual(len(items),1)
        self.assertIn('CPI',items[0]['categories'])
        self.assertIsNone(items[0]['event_at'])
        self.assertTrue(items[0]['mechanisms'])
    def test_old_future_and_undated_items_rejected(self):
        for date in ['Wed, 01 Oct 2026 08:00:00 GMT','Thu, 22 Oct 2026 08:00:00 GMT','']:
            self.assertEqual(f.parse_feed(self.rss(date),SOURCE,NOW),[])
    def test_official_label_cannot_be_spoofed_by_external_link(self):
        self.assertEqual(f.parse_feed(self.rss('Wed, 21 Oct 2026 08:00:00 GMT',url='https://unknown.invalid/x'),SOURCE,NOW),[])
    def test_ics_dst_event_time(self):
        raw=b'BEGIN:VCALENDAR\nBEGIN:VEVENT\nDTSTART;TZID=America/New_York:20261023T083000\nSUMMARY:Employment situation\nURL:https://www.bls.gov/schedule/x\nEND:VEVENT\nEND:VCALENDAR'
        events=f.parse_calendar(raw,SOURCE,NOW)
        self.assertEqual(events[0]['event_at'],'2026-10-23T12:30:00+00:00')
        self.assertIsNone(events[0]['published_at'])
    def test_unavailable_not_zero_or_invented(self):
        def missing(source):raise OSError('offline')
        result=f.collect({},NOW,missing)
        self.assertEqual(result['events'],[])
        self.assertTrue(all(s['status']=='N/A' for s in result['sources']))
    def test_dedup_and_cache(self):
        raw=self.rss('Wed, 21 Oct 2026 08:00:00 GMT')
        state={}
        result=f.collect(state,NOW,lambda source:raw)
        self.assertLessEqual(len(result['events']),1)
        def must_not_fetch(source):raise AssertionError('cache broken')
        self.assertEqual(f.collect(state,NOW,must_not_fetch),result)
    def test_canonical_utm_removal(self):
        self.assertEqual(f.canonical_url('https://a.com/x?utm_source=y#z'),'https://a.com/x')

class PublisherAliases(unittest.TestCase):
    def test_bea_official_publisher_can_differ_from_feed_subdomain(self):
        source=dict(id='bea',url='https://apps.bea.gov/rss/rss.xml',publisher_host='bea.gov',official=True)
        raw=b'<rss><channel><item><title>Personal income and outlays</title><link>https://www.bea.gov/news/2026/release</link><pubDate>Wed, 21 Oct 2026 08:00:00 GMT</pubDate></item></channel></rss>'
        self.assertEqual(len(f.parse_feed(raw,source,NOW)),1)
    def test_calendar_cannot_label_external_url_official(self):
        raw=b'BEGIN:VEVENT\nDTSTART:20261023T123000Z\nSUMMARY:Consumer Price Index\nURL:https://unknown.invalid/calendar\nEND:VEVENT'
        self.assertEqual(f.parse_calendar(raw,SOURCE,NOW),[])

class OfficialProjectFeeds(unittest.TestCase):
    def test_atom_updated_is_not_claimed_as_release_publication(self):
        source=next(x for x in f.SOURCES if x['id']=='sol_agave')
        raw=b'<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>v1.2 release notice</title><updated>2026-10-21T08:00:00Z</updated><link rel="alternate" href="https://github.com/anza-xyz/agave/releases/tag/v1.2"/></entry></feed>'
        item=f.parse_feed(raw,source,NOW)[0]
        self.assertEqual(item['symbol'],'SOL')
        self.assertEqual(item['timestamp_kind'],'updated')
        self.assertIsNone(item['event_at'])
    def test_other_repo_cannot_impersonate_official_release(self):
        source=next(x for x in f.SOURCES if x['id']=='sol_agave')
        raw=b'<feed><entry><title>v1.2</title><updated>2026-10-21T08:00:00Z</updated><link href="https://github.com/other/repo/releases/tag/v1.2"/></entry></feed>'
        self.assertEqual(f.parse_feed(raw,source,NOW),[])


class ReplacementSelectionTests(unittest.TestCase):
    def feed(self,source,date,title='Consumer Price Index release'):
        return ('<rss><channel><item><title>'+title+'</title><link>'+source['url']+'/release</link><pubDate>'+date+'</pubDate></item></channel></rss>').encode()
    def selection(self,primary_raw,backup_raw):
        from unittest.mock import patch
        primary=dict(id='primary',url='https://primary.example/feed',official=True,coverage=['CPI'])
        backup=dict(id='backup',url='https://backup.example/feed',official=False,coverage=['CPI'])
        def fetch(s):
            raw=primary_raw if s['url']==primary['url'] else backup_raw if s['url']==backup['url'] else OSError('not requested')
            if isinstance(raw,Exception):raise raw
            return raw
        with patch.object(f,'SOURCES',[primary]),patch.dict(f.FALLBACKS,{'primary':[backup]},clear=True):
            return f.collect({},NOW,fetch)
    def test_stale_primary_tries_current_backup_with_own_provenance(self):
        primary=dict(url='https://primary.example/feed');backup=dict(url='https://backup.example/feed')
        out=self.selection(self.feed(primary,'Thu, 01 Oct 2026 08:00:00 GMT'),self.feed(backup,'Wed, 21 Oct 2026 08:00:00 GMT'))
        row=out['sources'][0]
        self.assertEqual(row['selected_source'],'backup');self.assertFalse(row['official'])
        self.assertEqual(out['events'][0]['source'],'backup')
        self.assertEqual(row['attempts'][0]['freshness'],'STALE')
    def test_empty_primary_tries_backup(self):
        out=self.selection(b'<rss><channel/></rss>',self.feed(dict(url='https://backup.example/feed'),'Wed, 21 Oct 2026 08:00:00 GMT'))
        self.assertEqual(out['sources'][0]['selected_source'],'backup')
    def test_quiet_valid_primary_remains_available_when_backup_fails(self):
        out=self.selection(b'<rss><channel/></rss>',OSError('fixture'))
        self.assertEqual(out['sources'][0]['status'],'OK')
        self.assertEqual(out['sources'][0]['selected_source'],'primary')
        self.assertEqual(out['sources'][0]['attempts'][-1]['status'],'N/A')
        self.assertEqual(out['events'],[])

    def test_shared_secondary_downloaded_once_per_collection(self):
        from unittest.mock import patch
        from collections import Counter
        counts=Counter();url='https://primary.example/feed'
        sources=[dict(id=k,url=url,official=True,coverage=['CPI']) for k in ('a','b')]
        def fetch(source):
            counts[source['url']]+=1
            if source['url']!=url:raise OSError('fixture')
            return self.feed(dict(url=url),'Wed, 21 Oct 2026 08:00:00 GMT')
        with patch.object(f,'SOURCES',sources),patch.dict(f.FALLBACKS,{},clear=True):
            f.collect({},NOW,fetch)
        self.assertEqual(counts[url],1)
    def test_larger_aave_limit_is_bounded_and_endpoint_specific(self):
        from unittest.mock import patch,MagicMock
        for url,limit in [('https://api.llama.fi/protocol/aave',32000000),('https://api.llama.fi/protocol/other',8000000),('https://example.org/news',2000000)]:
            response=MagicMock();response.geturl.return_value=url;response.read.return_value=b'{}'
            with patch.object(f.urllib.request,'urlopen') as opening:
                opening.return_value.__enter__.return_value=response
                self.assertEqual(f.fetch(dict(url=url)),b'{}')
            response.read.assert_called_once_with(limit+1)
    def test_new_secondary_registry_never_claims_official_status(self):
        for name in ('decrypt','theblock'):
            self.assertFalse(next(x for x in f.SOURCES if x['id']==name)['official'])
        self.assertIn('bea_calendar',[x['id'] for x in f.SOURCES])

    def test_payload_over_new_cap_still_rejected_without_parsing(self):
        from unittest.mock import patch,MagicMock
        for url,limit in [('https://api.llama.fi/protocol/aave',32000000),('https://example.org/news',2000000)]:
            raw=MagicMock();raw.__len__.return_value=limit+1
            response=MagicMock();response.geturl.return_value=url;response.read.return_value=raw
            with patch.object(f.urllib.request,'urlopen') as opening:
                opening.return_value.__enter__.return_value=response
                with self.assertRaises(f.SourcePolicyError) as err:f.fetch(dict(url=url))
            self.assertEqual(err.exception.reason_code,'PAYLOAD_LIMIT_EXCEEDED')
