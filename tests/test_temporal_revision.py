import copy
from datetime import datetime,timedelta,timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfo
from v11.macro_context import yield_comparison
from v11.fundamental_analysis import analyze,overview,coin_lines
from v11.project_metrics import parse
from v11 import shadow_pair as pair
from scripts.temporal_shadow import scheduled_phase,run
from tests.test_shadow_pair import sample
from tests.test_fundamental_analysis import item,result,NOW

BL=ZoneInfo('Europe/Bratislava')
class RevisionTests(unittest.TestCase):
    def test_four_basis_points_not_four_percentage_points(self):
        y=yield_comparison([dict(date='2026-10-23',**{'2y':4.65,'10y':4.65}),dict(date='2026-10-26',**{'2y':4.69,'10y':4.69})])
        self.assertEqual(y['change_bp']['2y'],4)
        text=' '.join(overview(dict(macro_context=dict(treasury=y,url='https://example.org')),NOW))
        self.assertIn('+4 bp',text);self.assertNotIn('+4 percentuálne',text)
    def test_daily_previous_not_discarded_by_freshness(self):
        now=datetime(2026,10,26,7,tzinfo=timezone.utc)
        rows=[[(now-timedelta(days=n)).replace(hour=0).timestamp(),100/n] for n in (1,2,3)]
        parsed=parse(json.dumps(dict(totalDataChart=rows)).encode(),now)
        self.assertEqual(parsed['value'],100);self.assertEqual(parsed['previous_value'],50)
        self.assertIn('24',parsed['previous_period'])
    def test_stale_latest_still_refused(self):
        rows=[[(NOW-timedelta(days=3)).replace(hour=0).timestamp(),100]]
        self.assertIsNone(parse(json.dumps(dict(totalDataChart=rows)).encode(),NOW))
    def test_semantic_duplicate_merges_with_both_citations(self):
        events=result(item(id='a',title='Fed holds rates unchanged after October meeting',categories=['Fed'],symbol=None),item(id='b',title='Federal Reserve leaves interest rates unchanged at October meeting',categories=['Fed'],symbol=None,url='https://other.example/article'))
        e=analyze(events,NOW)['evidence'];self.assertEqual(len(e),1);self.assertEqual(len(e[0]['citations']),2)
    def test_different_values_or_stages_do_not_merge(self):
        for titles in [('CPI inflation rises to 3.1 percent','CPI inflation rises to 3.2 percent'),('Aave governance proposal approved','Aave governance proposal denied')]:
            r=result(item(id='a',title=titles[0],categories=['CPI','project']),item(id='b',title=titles[1],categories=['CPI','project'],url='https://other.example/a'))
            self.assertEqual(len(analyze(r,NOW)['evidence']),2)
    def test_tvl_previous_period_rendered(self):
        f=dict(metrics={'SOL':dict(value=120,at='2026-10-26',previous_at='2026-10-25',previous_value=100,url='https://example.org',observed_at=NOW.isoformat())})
        text=' '.join(coin_lines('SOL',f,NOW));self.assertIn('+20.0',text);self.assertIn('2026-10-25',text)
    def test_sources_access_not_coverage_or_freshness(self):
        r=analyze(dict(sources=[dict(status='OK',freshness='STALE')]),NOW)
        self.assertEqual(r['source_ok'],1);self.assertEqual(r['current_relevant_sources'],0);self.assertFalse(any(r['coverage'].values()))
    def test_dst_and_boundary_slots(self):
        for day,offset in [('2026-03-28',1),('2026-03-29',2),('2026-10-24',2),('2026-10-25',1)]:
            am=datetime.fromisoformat(day+'T07:00:00').replace(tzinfo=BL);pm=am.replace(hour=20)
            self.assertEqual(scheduled_phase(am.astimezone(timezone.utc)),'morning')
            self.assertEqual(scheduled_phase(pm.astimezone(timezone.utc)),'evening')
            self.assertEqual(am.utcoffset().total_seconds()/3600,offset)
            self.assertEqual(scheduled_phase(am.replace(hour=6,minute=59)),'')
            self.assertEqual(scheduled_phase(pm.replace(hour=21,minute=31)),'')
    def test_pair_includes_changed_fundamentals(self):
        am=datetime(2026,10,26,7,tzinfo=BL);pm=am.replace(hour=20)
        old=dict(sources=[dict(status='OK')],events=[])
        new=dict(sources=[dict(status='OK')],events=[item(published_at=pm.astimezone(timezone.utc).isoformat(),retrieved_at=pm.astimezone(timezone.utc).isoformat())])
        ev={s:dict(action='WAIT') for s in pair.SYMBOLS}
        saved=pair.checkpoint(sample(am),ev,am,old)
        compared=pair.compare(saved,sample(pm),ev,pm,new)
        self.assertTrue(compared['verified_temporal_pair']);self.assertEqual(len(compared['fundamentals']['new']),1)
    def test_same_metric_period_is_revision_not_new_day(self):
        old=dict(metrics={'SOL':dict(value=100,at='2026-10-25')})
        new=dict(metrics={'SOL':dict(value=120,at='2026-10-25')})
        r=pair.metric_changes(old,new)[0];self.assertEqual(r['period_status'],'SAME_PERIOD_REVISION');self.assertAlmostEqual(r['change_pct'],20)
    def test_missing_fundamentals_na(self):
        self.assertEqual(pair.compare_fundamentals(None,{},NOW,NOW)['status'],'N/A')
    def test_schedule_is_only_in_mirror_template(self):
        root=Path(__file__).resolve().parents[1]
        workflow=(root/'.github/workflows/v11-temporal-shadow.yml').read_text()
        self.assertNotIn('  schedule:',workflow);self.assertNotIn('secrets:',workflow)
        self.assertIn('SHADOW_SOURCE_SHA',workflow);self.assertIn('status: \'success\'',workflow)
        self.assertIn('steps.reference.outputs.skip',workflow)
        template=(root/'docs/v11.1/temporal-shadow/shadow-temporal.yml.example').read_text()
        self.assertIn('  schedule:',template);self.assertIn('5-7,18-20',template)

class TemporalDriverTests(unittest.TestCase):
    def invoke(self,phase,at,directory,reference=None,snap=None):
        from scripts import temporal_shadow as driver
        class Clock:
            @staticmethod
            def now(zone):return at.astimezone(zone)
        def collect(out,use_ai,report_phase):
            self.assertFalse(use_ai)
            out=Path(out);out.mkdir(parents=True,exist_ok=True)
            data=snap or sample(at);data['complete']=True
            for name,value in [('market_snapshot.json',data),('fundamentals.json',dict(sources=[dict(status='OK')],events=[])),('summary.json',{})]:
                (out/name).write_text(json.dumps(value))
            (out/(report_phase+'.txt')).write_text('SYNTHETIC TEST ONLY\n')
            return 0
        with patch.object(driver,'datetime',Clock),patch.object(driver,'collect',side_effect=collect):
            return driver.run(phase,directory,reference)
    def test_missing_morning_retains_evening_and_na(self):
        root=Path(__file__).resolve().parents[1]
        at=datetime(2026,10,26,20,tzinfo=BL)
        with tempfile.TemporaryDirectory(dir=root/'shadow-output') as directory:
            self.assertEqual(self.invoke('evening',at,directory),0)
            compared=json.loads((Path(directory)/'comparison.json').read_text())
            self.assertEqual(compared['status'],'N/A');self.assertFalse(compared['verified_temporal_pair'])
            self.assertIn('N/A',(Path(directory)/'evening.txt').read_text())
    def test_two_separate_synthetic_observations_driver(self):
        root=Path(__file__).resolve().parents[1]
        am=datetime(2026,10,26,7,tzinfo=BL);pm=am.replace(hour=20)
        with tempfile.TemporaryDirectory(dir=root/'shadow-output') as directory:
            first=Path(directory)/'am';second=Path(directory)/'pm'
            self.assertEqual(self.invoke('morning',am,first),0)
            self.assertEqual(self.invoke('evening',pm,second,first/'checkpoints/morning.json'),0)
            compared=json.loads((second/'comparison.json').read_text())
            self.assertTrue(compared['verified_temporal_pair']);self.assertEqual(compared['hours'],13)
    def test_reused_source_snapshot_rejected_in_driver(self):
        root=Path(__file__).resolve().parents[1]
        am=datetime(2026,10,26,7,tzinfo=BL);pm=am.replace(hour=20)
        with tempfile.TemporaryDirectory(dir=root/'shadow-output') as directory:
            first=Path(directory)/'am';second=Path(directory)/'pm'
            self.invoke('morning',am,first)
            reused=sample(am);reused['at']=pm.timestamp()
            self.assertEqual(self.invoke('evening',pm,second,first/'checkpoints/morning.json',reused),2)
            self.assertFalse(json.loads((second/'comparison.json').read_text())['verified_temporal_pair'])

class TVLHistoryTests(unittest.TestCase):
    def test_collector_keeps_previous_available_tvl_and_ignores_future(self):
        from v11 import fundamentals
        now=datetime(2026,10,26,7,tzinfo=timezone.utc)
        values=[dict(date=(now-timedelta(days=1)).timestamp(),totalLiquidityUSD=120),
                dict(date=(now-timedelta(days=3)).timestamp(),totalLiquidityUSD=100),
                dict(date=(now+timedelta(days=1)).timestamp(),totalLiquidityUSD=999)]
        def fetch(source):
            if source['url']=='https://api.llama.fi/protocol/aave':return json.dumps(dict(tvl=values)).encode()
            raise RuntimeError('synthetic unavailable')
        f=fundamentals.collect({},now,fetcher=fetch)
        self.assertEqual(f['metrics']['AAVE']['value'],120)
        self.assertEqual(f['metrics']['AAVE']['previous_value'],100)
    def test_fundamental_provenance_cannot_be_changed_without_checksum(self):
        am=datetime(2026,10,26,7,tzinfo=BL);pm=am.replace(hour=20)
        ev={s:dict(action='WAIT') for s in pair.SYMBOLS}
        saved=pair.checkpoint(sample(am),ev,am,dict(events=[]))
        saved['fundamentals']['events'].append({'invented':True})
        with self.assertRaisesRegex(ValueError,'checksum'):pair.compare(saved,sample(pm),ev,pm,{})

class PublicationCoverageTests(unittest.TestCase):
    def test_lost_secondary_source_is_not_new_fundamental_update(self):
        am=datetime(2026,10,26,7,tzinfo=BL);pm=am.replace(hour=20)
        a=item(id='a',title='Aave governance proposal',published_at=am.isoformat(),retrieved_at=am.isoformat())
        b=item(id='b',title='Aave governance proposal',url='https://other.example/a',published_at=am.isoformat(),retrieved_at=am.isoformat())
        old=dict(events=[a,b],sources=[dict(status='OK')]);new=dict(events=[dict(a,retrieved_at=pm.isoformat())],sources=[dict(status='OK')])
        compared=pair.compare_fundamentals(old,new,am,pm)
        self.assertEqual(compared['updated'],[]);self.assertEqual(compared['unchanged'],1)
