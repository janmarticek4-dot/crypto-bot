"""All portfolios, events and prices in this file are synthetic fixtures."""
import copy,json,re,tempfile,unittest
from datetime import timedelta
from unittest.mock import patch
from v11 import trend_reversal as tr,event_notices as en,integrated_report,analyst,report_verdict as rv,prediction_runtime as rt
from tests import test_trend_reversal as fixtures
from tests.test_analyst_v112 import NOW,INVENTORY

URL='https://www.federalreserve.gov/newsevents/pressreleases/monetary20261027a.htm'
def release():return dict(status='RELEASED',event_date='2026-10-27',published_at=(NOW-timedelta(hours=2)).isoformat(),url=URL,rate_range=[1,1.25],decision='The Committee decided to maintain the target range',voting='approved by 10-2 vote',comments=[],reaction={})
def fund():return {'event_lifecycle':{'releases':[release()]}}
def story(ident='one',title='SEC approves synthetic spot Bitcoin ETF',at=None,source='sec'):
    return dict(id=ident,title=title,source=source,url='https://www.sec.gov/synthetic/'+ident,published_at=(at or NOW-timedelta(hours=1)).isoformat(),retrieved_at=NOW.isoformat(),categories=['regulation'])

class FailedRecoveryTests(unittest.TestCase):
    def setup_failed(self,prior_state='RECOVERY_ATTEMPT'):
        snap=fixtures.snapshot('bounce','down',volume=False);old=fixtures.old(snap,cap=1200)
        old['reversal']['state']=prior_state
        for c in old['coins'].values():c['price']*=1.1
        m=fixtures.model(snap);tr.attach(m,snap,{},NOW,{'last_analysis_v112':old});return snap,m
    def test_old_positive_rebound_cannot_override_newer_broad_deterioration(self):
        snap,m=self.setup_failed();r=m['trend_reversal']
        self.assertTrue(r['coins']['BTC']['four']['rebound'])
        self.assertEqual(r['state'],'RECOVERY_FAILED');self.assertEqual(r['failure_evidence']['alts_lower_since_reference'],6)
        text=integrated_report.render(m,snap,NOW,'evening',INVENTORY)
        self.assertIn('🌐 TRH: ODRAZ ZLYHÁVA',text);self.assertNotIn('🌐 TRH: POKUS O OBRAT',text)
    def test_no_prior_recovery_means_correction_not_invented_failed_bounce(self):
        self.assertEqual(self.setup_failed('CORRECTION')[1]['trend_reversal']['state'],'CORRECTION')
    def test_short_pullback_in_bull_does_not_create_failed_bounce_or_sell(self):
        snap=fixtures.snapshot();old=fixtures.old(snap,cap=1200);old['reversal']['state']='UPTREND_CONFIRMED'
        for c in old['coins'].values():c['price']*=1.1
        m=fixtures.model(snap);tr.attach(m,snap,{},NOW,{'last_analysis_v112':old})
        self.assertNotEqual(m['trend_reversal']['state'],'RECOVERY_FAILED')
        text=integrated_report.render(m,snap,NOW,'evening',INVENTORY)
        self.assertIn('AAVE DRŽAŤ',text);self.assertNotIn('— SELL',text)
    def test_missing_cap_cannot_manufacture_failure_or_optimistic_confirmation(self):
        snap,m=self.setup_failed();snap['global_data']['cap']=None
        tr.attach(m,snap,{},NOW,{})
        self.assertNotIn(m['trend_reversal']['state'],('RECOVERY_FAILED','UPTREND_CONFIRMED','RECOVERY_ATTEMPT'))

class EventNoticeTests(unittest.TestCase):
    def test_first_result_then_no_repeat_after_new_process(self):
        j={};first=en.plan(fund(),j,NOW);self.assertEqual(len(first['selected']),1)
        self.assertEqual(j,{}) # Preview never consumes an event.
        en.commit(j,first,NOW)
        j=json.loads(json.dumps(j));self.assertEqual(en.plan(fund(),j,NOW+timedelta(hours=1))['selected'],[])
        stored=next(iter(j[en.KEY].values()));self.assertIn('last_announced_at',stored);self.assertIn('published_at',stored)
    def test_new_reaction_timestamp_is_not_a_new_fed_decision(self):
        j={};en.commit(j,en.plan(fund(),j,NOW),NOW)
        revised=fund();revised['event_lifecycle']['releases'][0]['reaction']={'BTC':{'after_at':999999,'change_pct':-3}}
        self.assertFalse(en.plan(revised,j,NOW+timedelta(hours=1))['selected'])
    def test_real_revision_is_reported_once(self):
        j={};en.commit(j,en.plan(fund(),j,NOW),NOW)
        revised=fund();revised['event_lifecycle']['releases'][0]['rate_range']=[2,2.25]
        planned=en.plan(revised,j,NOW+timedelta(hours=1));self.assertEqual(len(planned['selected']),1)
        self.assertIn('Nová aktualizácia',planned['selected'][0]['text'])
        en.commit(j,planned,NOW+timedelta(hours=1));self.assertFalse(en.plan(revised,j,NOW+timedelta(hours=2))['selected'])
    def test_copy_from_another_provider_is_not_new_event(self):
        j={};f={'events':[story()]};en.commit(j,en.plan(f,j,NOW),NOW)
        other={'events':[story('two',source='secondary')]}
        self.assertFalse(en.plan(other,j,NOW)['selected'])
    def test_new_fact_or_different_authority_is_not_suppressed(self):
        j={};en.commit(j,en.plan({'events':[story()]},j,NOW),NOW)
        for title in ('CFTC approves synthetic spot Bitcoin ETF','SEC denies synthetic spot Bitcoin ETF','SEC approves synthetic spot Ethereum ETF'):
            self.assertTrue(en.plan({'events':[story('two',title)]},j,NOW)['selected'],title)
    def test_future_past_calendar_and_unknown_expectation(self):
        e=dict(id='calendar',scheduled=True,lifecycle='UPCOMING',event_at=(NOW+timedelta(hours=2)).isoformat(),published_at=NOW.isoformat(),title='Consumer Price Index',categories=['CPI'],url='https://www.bls.gov/synthetic',expectation='invented')
        planned=en.plan({'events':[e]}, {}, NOW)
        self.assertEqual(len(planned['selected']),1);self.assertNotIn('invented',planned['selected'][0]['text'])
        self.assertIn('konsenzus neoverený',planned['selected'][0]['text'])
        e['event_at']=(NOW-timedelta(hours=1)).isoformat();self.assertFalse(en.plan({'events':[e]}, {},NOW)['selected'])
    def test_empty_sources_create_no_fundamental_comment(self):
        snap=fixtures.snapshot();m=fixtures.assess(snap);m['event_notices']=en.plan({}, {},NOW)
        text=integrated_report.render(m,snap,NOW,'morning');self.assertNotIn('DÔLEŽITÉ UDALOSTI',text)
    def test_uncertain_send_is_not_automatically_announced_in_next_slot(self):
        planned=en.plan(fund(),{},NOW)
        record={'status':'uncertain','event_notifications':[{k:v for k,v in planned['selected'][0].items() if k not in ('text','url')}]}
        j={'slots':{'synthetic':record}}
        self.assertFalse(en.plan(fund(),j,NOW+timedelta(hours=1))['selected'])
        self.assertNotIn(en.KEY,j)
    def test_ledger_bounded_no_secret_or_private_fields(self):
        j={}
        for i in range(300):
            row=dict(id=str(i),state='NEWS',semantic=str(i),published_at=NOW.isoformat(),title='synthetic',categories=[],symbols=[],kind='news',text='synthetic',url='https://example.invalid')
            en.commit(j,{'selected':[row]},NOW+timedelta(seconds=i))
        self.assertEqual(len(j[en.KEY]),256)
        self.assertNotIn('text',next(iter(j[en.KEY].values())))

class CompactTests(unittest.TestCase):
    def make(self):
        snap=fixtures.snapshot('bounce','down');m=fixtures.assess(snap);ms=int(NOW.timestamp()*1000)
        m['experimental_predictions']={s:{h:dict(generated_at=ms,valid_until=ms+900000,model='flat',price=c['price'],point=c['price'],low=c['price']*.95,high=c['price']*1.05,low_pct=-5,high_pct=5,direction='DO STRANY') for h in rt.HORIZONS} for s,c in snap['coins'].items() if s in tr.COINS}
        m['event_notices']={'selected':[]};return snap,m
    def test_full_eighteen_short_directions_actions_and_40_60_percent_reduction(self):
        snap,m=self.make();before=copy.deepcopy(m)
        text=integrated_report.render(m,snap,NOW,'morning',INVENTORY)
        old=integrated_report.render_detailed(m,snap,NOW,'morning',INVENTORY)
        baseline=analyst.final_text(m,snap,NOW,'morning',INVENTORY)
        self.assertEqual(rv.actions(text),rv.actions(baseline));self.assertEqual(text.count('DO STRANY'),18)
        self.assertTrue(text.startswith('📊 CRYPTO AI BOT — RANNÁ'))
        self.assertEqual(rv.contract(text,18)['format_version'],'brief-v2')
        self.assertNotIn('https://',text);self.assertNotIn('EMA',text);self.assertNotIn('$152',text)
        reduction=1-len(text)/len(old);self.assertTrue(.4<=reduction<=.6,(len(text),len(old),reduction))
        self.assertEqual(m,before)
    def test_stale_forecasts_are_not_represented_as_current(self):
        snap,m=self.make();text=integrated_report.render(m,snap,NOW+timedelta(minutes=16),'evening')
        self.assertNotIn('DO STRANY',text);self.assertIn('🌐 TRH: NEISTOTA',text)
    def test_compact_prediction_count_keeps_all_eighteen(self):
        snap,m=self.make();text=integrated_report.render(m,snap,NOW,'morning')
        self.assertEqual(len(re.findall(r'(?:24h|72h|14d) (?:RAST|POKLES|DO STRANY)(?=\s|[.;]|$)',text)),18)

class DeliveryEventTests(unittest.TestCase):
    def exercise(self,fail=False):
        from tests.test_manual_v111 import ManualV111Tests
        from scripts import v111_trial as pilot
        from v11.state_policy import require_public_data
        with ManualV111Tests().setup_run(now=NOW) as (journal,collect,send):
            planned=en.plan(fund(),{},NOW)
            observation=fixtures.old(fixtures.snapshot());observation['at']=NOW.isoformat();observation['event_notices_pending']=planned
            with patch.dict('os.environ',{'V112_ANALYTICS_ENABLED':'true'}),patch.object(pilot,'render',return_value=('synthetic no Telegram',{'_v112_observation':observation})):
                if fail:
                    send.side_effect=TimeoutError('synthetic')
                    with self.assertRaises(TimeoutError):pilot.run('github-run-1000')
                    self.assertNotIn(en.KEY,journal.value)
                    self.assertFalse(en.plan(fund(),journal.value,NOW+timedelta(hours=1))['selected'])
                else:
                    pilot.run('github-run-1000');self.assertTrue(journal.value[en.KEY])
                    self.assertFalse(en.plan(fund(),journal.value,NOW+timedelta(hours=1))['selected'])
                first=journal.writes[0]['manual_slots']['github-run-1000']
                self.assertEqual(first['status'],'attempting');self.assertTrue(first['event_notifications'])
                require_public_data(journal.value)
    def test_success_records_notification_only_after_send(self):self.exercise(False)
    def test_uncertain_keeps_duplicate_protection_without_false_confirmed_record(self):self.exercise(True)
    def test_bad_event_ledger_cannot_break_main_or_be_reset(self):
        j={en.KEY:[]};before=copy.deepcopy(j)
        planned=en.plan(fund(),j,NOW);self.assertIn('error',planned);self.assertFalse(planned['selected'])
        en.commit(j,planned,NOW);self.assertEqual(j,before)

class MechanismTests(unittest.TestCase):
    def test_flat_output_is_identical_to_no_change_baseline(self):
        from v11.prediction_review import review
        f={'SOL':{'24 h':{'model':'flat','price':100,'point':100,'low':95,'high':105}}}
        result=review({'predictions':[]},f,int(NOW.timestamp()*1000))
        self.assertEqual(result['mechanism']['flat_outputs'],1)
        self.assertEqual(result['matured'],0);self.assertFalse(result['independent_validation'])
    def test_same_features_and_changed_quote_rebase_intervals(self):
        from tests import test_report_quality as fixtures_clock
        fixtures_clock.ClockPrecisionTests.setUpClass();c=fixtures_clock.ClockPrecisionTests
        snap=copy.deepcopy(c.snapshot);a=rt.predict(snap,c.package,c.now)
        snap['coins']['SOL']['price']*=1.01;b=rt.predict(snap,c.package,c.now)
        for h in rt.HORIZONS:
            self.assertAlmostEqual(b['SOL'][h]['low']/a['SOL'][h]['low'],1.01)
            self.assertEqual(a['SOL'][h]['input_features'],b['SOL'][h]['input_features'])

class RelevanceTests(unittest.TestCase):
    def test_fec_hack_and_fridge_comment_are_not_market_events(self):
        for title,cats in [('Crypto PAC spending obscured after reported FEC hack',['hack']),('Your fridge could one day stake Ether: CFTC chair',['regulation']),('Fed hawkish rate hold keeps pressure on Bitcoin: Analysts',['Fed'])]:
            e=story('x',title);e['categories']=cats
            p=en.plan({'events':[e]}, {},NOW)
            self.assertFalse(p['selected'],title)
    def test_exchange_incident_is_not_filtered_as_political_hack(self):
        e=story('hack','Crypto exchange halts withdrawals after wallet hack');e['categories']=['hack']
        self.assertTrue(en.plan({'events':[e]}, {},NOW)['selected'])
    def test_lagging_volume_cannot_hide_broad_failure_below_closed_price_levels(self):
        snap=fixtures.snapshot('bounce','down',volume=True);old=fixtures.old(snap,cap=1200)
        old['reversal']['state']='RECOVERY_ATTEMPT'
        for c in old['coins'].values():c['price']*=1.2
        # Current public quotes have fallen below the last closed rebound bar;
        # all old candles remain unchanged, and their up-volume can still dominate.
        for c in snap['coins'].values():c['price']*=.95
        m=fixtures.model(snap);tr.attach(m,snap,{},NOW,{'last_analysis_v112':old})
        self.assertTrue(m['trend_reversal']['failure_evidence']['closed_level_lost'])
        self.assertEqual(m['trend_reversal']['state'],'RECOVERY_FAILED')

class MigrationTests(unittest.TestCase):
    def test_only_verified_sent_old_report_can_seed_announced_facts(self):
        import zipfile
        from pathlib import Path
        from scripts.event_notice_seed import build
        context=dict(status='sent',source='68805b3a5b6331251ad3deb6dd4eaebac6244df0',at=NOW.isoformat(),run_id=123)
        with tempfile.TemporaryDirectory() as d:
            archive=Path(d)/'public.zip'
            with zipfile.ZipFile(archive,'w') as z:z.writestr('v112_analysis.json',json.dumps({'observation':{'at':NOW.isoformat()},'_current_fundamentals':fund()}))
            seed=build(archive,context);self.assertEqual(len(seed['records']),1)
            with self.assertRaises(ValueError):build(archive,dict(context,status='uncertain'))
            with self.assertRaises(ValueError):build(archive,dict(context,at=(NOW+timedelta(seconds=1)).isoformat()))
    def test_fundamental_section_limit_three(self):
        events=[story(str(i),'SEC approves synthetic Bitcoin ETF product '+str(i)) for i in range(5)]
        self.assertLessEqual(len(en.plan({'events':events}, {},NOW)['selected']),3)

class SharedUSNoticeTests(unittest.TestCase):
    def test_us_keeps_layout_but_suppresses_old_fed_when_not_new(self):
        from tests.test_us_outlook import snapshot as us_snapshot
        from v11.us_brief import render
        snap=fixtures.snapshot();m=fixtures.assess(snap);context=us_snapshot(NOW)
        m['event_notices']={'selected':[]}
        text=render(context,m,snap,fund(),NOW)
        self.assertNotIn('cieľové sadzby',text)
        self.assertIn('ČO ROBIŤ:',text);self.assertIn('ČO SLEDOVAŤ:',text)
        self.assertLessEqual(len(text),2000)
        m['event_notices']=en.plan(fund(),{},NOW,limit=1)
        self.assertIn('cieľové sadzby',render(context,m,snap,fund(),NOW))
