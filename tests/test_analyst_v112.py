import copy,json,tempfile,unittest
from datetime import datetime,timezone,timedelta
from pathlib import Path
from unittest.mock import patch
from v11 import analyst,fundamentals
from scripts import v111_integrated_delivery as delivery
from tests import test_manual_v111 as manual

NOW=datetime(2026,10,27,11,tzinfo=timezone.utc)

def sample():
    prices={'SOL':100,'TAO':250,'FET':.2,'AAVE':130,'ONDO':.4,'RENDER':1.7,'BTC':80000,'ETH':2000}
    coins={}
    for s,p in prices.items():
        frames={}
        for tf in ('4h','1d'):
            frames[tf]=dict(ema20=p*1.01,ema50=p*1.03,ema100=p*1.05,ema200=p*1.08,rsi14=45,macd_hist=p*.001,support=p*.94,resistance=p*1.1,atr=p*.02,adx=22,relative_volume=1.,higher_structure=False,retest=False,support_broken=False,bullish_divergence=False,candles=300)
        raw=[dict(timestamp=int((NOW-timedelta(hours=4*(301-i))).timestamp()*1000),open=p*(1+(299-i)*.0008),close=p*(1+(299-i)*.0008),high=p*(1+(299-i)*.0008)+p*.001,low=p*(1+(299-i)*.0008)-p*.001,volume=1000+i) for i in range(300)]
        coins[s]=dict(price=p,change_24h=-1,market_cap=p*1e7,volume_24h=p*1e6,frames=frames,raw={'4h':raw},stale=False,metadata_at=NOW.isoformat(),relative_strength_btc_7d=-.01)
    return dict(coins=coins,global_data=dict(cap=2.7e12,volume=8e10,dominance=60,change=-3,at=NOW.timestamp()),at=NOW.timestamp(),complete=True)

def model(snap=None,fund=None,old=None):
    snap=snap or sample();quotes={s:dict(action='REDUCE',trend_score_10=2.5) for s in analyst.COINS};ev={s:dict(action='REDUCE',risk_pts=5) for s in analyst.COINS}
    return analyst.prepare(snap,fund or {},NOW,quotes,ev,old)

INVENTORY={'positions':[{'symbol':'AAVE','quantity':7,'average_cost':42,'currency':'USD'}],'cash':None} # SYNTHETIC, not user's investments

class AnalystTests(unittest.TestCase):
    def test_single_held_conclusion_not_legacy_reduce(self):
        snap=sample();m=model(snap);before=copy.deepcopy(m)
        text=analyst.final_text(m,snap,NOW,'manual',INVENTORY)
        self.assertIn('HOLD (držba)',text);self.assertNotIn('— REDUCE',text)
        self.assertIn('WAIT (nový nákup)',text);self.assertEqual(m,before)
        self.assertNotIn('eToro',text);self.assertNotIn('1 %',text)
    def test_existing_private_reduce_not_suppressed(self):
        snap=sample();snap['coins']['AAVE']['frames']['4h'].update(support_broken=True,relative_volume=2,macd_hist=-1)
        snap['coins']['AAVE']['frames']['1d']['ema50']=200
        text=analyst.final_text(model(snap),snap,NOW,'manual',INVENTORY)
        self.assertIn('REDUCE (držba)',text);self.assertIn('Zvýšené riziko držby',text)
    def test_unknown_holdings_not_assumed(self):
        text=analyst.final_text(model(),sample(),NOW,'morning')
        self.assertNotIn('HOLD (držba)',text);self.assertNotIn('SELL (držba)',text)
    def test_incomplete_held_frames_never_fabricate_hold(self):
        snap=sample();snap['coins']['AAVE']['frames'].pop('1d')
        text=analyst.final_text(model(snap),snap,NOW,'manual',INVENTORY)
        self.assertIn('WAIT (držba)',text);self.assertIn('nejde o potvrdené HOLD',text)
    def test_same_snapshot_future_and_bad_reference_refused(self):
        m=model();obs=m['observation']
        for old in (obs,dict(obs,at=(NOW+timedelta(hours=1)).isoformat()),dict(obs,global_data=[]),dict(obs,coins={'SOL':None})):
            self.assertEqual(analyst.comparison(old,obs)['status'],'N/A')
    def test_real_changes_not_24h_change_and_dominance_in_points(self):
        obs=model()['observation'];old=copy.deepcopy(obs);old.update(at=(NOW-timedelta(hours=1)).isoformat(),fingerprint='a'*64)
        old['global_data'].update(cap=obs['global_data']['cap']/1.02,dominance=59)
        for c in old['coins'].values():c['price']/=1.01
        c=analyst.comparison(old,obs)
        self.assertEqual(c['direction'],'zlepšuje sa');self.assertAlmostEqual(c['global_cap_pct'],2)
        self.assertAlmostEqual(c['dominance_pp'],1);self.assertAlmostEqual(c['coins']['SOL']['price_pct'],1)
    def test_distinct_source_values_can_compare_even_with_flat_coin_prices(self):
        snap=sample();old=model(snap)['observation'];snap['global_data']['cap']*=1.01
        now=NOW+timedelta(hours=1)
        quotes={s:dict(action='REDUCE',trend_score_10=2.5) for s in analyst.COINS}
        cur=analyst.observation(snap,{},now,quotes)
        self.assertEqual(analyst.comparison(old,cur)['status'],'COMPARED')
    def test_unknown_incident_and_routine_code_not_headline(self):
        events=[dict(id=str(i),title=title,url='https://example.org/'+str(i),source='synthetic',published_at=NOW.isoformat(),retrieved_at=NOW.isoformat(),categories=cats,kind=kind) for i,(title,cats,kind) in enumerate([('Unknown wallet hacked',['hack'],'news'),('Solana code release',['project'],'software_release_notice'),('RENDER marketing proposal',['project'],'news')])]
        self.assertEqual(analyst.relevant_events({'events':events},NOW),[])
    def test_duplicate_macro_topic_once_and_future_news_ignored(self):
        event=dict(id='a',title='Fed rate decision',url='https://example.org/a',source='synthetic',published_at=NOW.isoformat(),retrieved_at=NOW.isoformat(),categories=['Fed'])
        f={'events':[event,dict(event,id='b',title='Fed meeting update'),dict(event,id='future',published_at=(NOW+timedelta(days=1)).isoformat())]}
        self.assertEqual(len(analyst.relevant_events(f,NOW)),1)
    def test_horizons_individual_levels_no_probabilities_or_broken_support(self):
        m=model();self.assertNotEqual(m['forecasts']['AAVE']['24–72 h']['support'],m['forecasts']['FET']['24–72 h']['support'])
        for fs in m['forecasts'].values():
            for f in fs.values():self.assertIsNone(f['probability'])
        c=sample()['coins']['BTC'];c['frames']['4h']['support']=85000
        self.assertIsNone(analyst.outlook(c,'4h')['support'])
    def test_no_buy_is_activated_by_native_buy_or_headline(self):
        snap=sample();q={s:dict(action='BUY NOW') for s in analyst.COINS};ev={s:dict(action='BUY NOW') for s in analyst.COINS}
        m=analyst.prepare(snap,{},NOW,q,ev)
        self.assertTrue(any(c['candidate'] for c in m['coins'].values()))
        self.assertTrue(all(c['action']=='WAIT' for c in m['coins'].values()))
    def test_fees_can_disqualify_a_watch_candidate(self):
        snap=sample()
        for c in snap['coins'].values():c['frames']['4h'].update(support=c['price']*.999,resistance=c['price']*1.001,atr=c['price']*.0001)
        q={s:dict(action='BUY NOW') for s in analyst.COINS};ev={s:dict(action='BUY NOW') for s in analyst.COINS}
        m=analyst.prepare(snap,{},NOW,q,ev)
        self.assertFalse(any(c['candidate'] for c in m['coins'].values()))
    def test_aave_small_current_tvl_fallback_has_provenance(self):
        def fetch(source):
            url=source['url']
            if url.endswith('/protocol/aave'):raise fundamentals.SourcePolicyError('PAYLOAD_LIMIT_EXCEEDED')
            if url.endswith('/tvl/aave'):return b'123456'
            return b'{}'
        with patch.object(fundamentals,'SOURCES',[]):result=fundamentals.collect({},NOW,fetch)
        self.assertEqual(result['metrics']['AAVE']['value'],123456)
        self.assertIn('/tvl/aave',result['metrics']['AAVE']['url'])
        self.assertIsNone(result['metrics']['AAVE']['published_at'])
        self.assertIsNone(result['metrics']['AAVE']['at']);self.assertEqual(result['metrics']['AAVE']['freshness'],'ASOF_UNKNOWN')
    def test_failed_sources_remain_missing_not_zero(self):
        with patch.object(fundamentals,'SOURCES',[]):
            result=fundamentals.collect({},NOW,lambda s:(_ for _ in ()).throw(OSError('offline')))
        self.assertEqual(result['metrics'],{});self.assertTrue(all(s['status']=='N/A' for s in result['metric_sources']))

class AnalystDeliveryTests(unittest.TestCase):
    def test_manual_reference_saved_only_after_sent_and_private_not_exported(self):
        with tempfile.TemporaryDirectory() as directory,manual.ManualV111Tests().setup_run(private=True,directory=directory) as (j,collect,send):
            collect.side_effect=lambda *a,**k:sample()
            old=copy.deepcopy(j.value['slots'])
            with patch.dict('os.environ',{'V112_ANALYTICS_ENABLED':'true'}),patch('v11.advisory_portfolio.load',return_value=copy.deepcopy(INVENTORY)):
                delivery.run()
            self.assertIn('last_analysis_v112',j.value);self.assertEqual(j.value['slots'],old)
            self.assertNotIn('last_analysis_v112',j.writes[0])
            self.assertIn('HOLD (držba)',send.call_args.args[0])
            self.assertIn('V11.2 — RUČNÁ | github-run-1000',send.call_args.args[0])
            for value in [json.dumps(j.value),*(p.read_text() for p in Path(directory).iterdir())]:
                self.assertNotIn('average_cost',value);self.assertNotIn('quantity',value)
            self.assertEqual(json.loads((Path(directory)/'v112_analysis.json').read_text())['coins']['AAVE']['context'],'new_purchase')
    def test_failed_delivery_does_not_advance_last_reference(self):
        with manual.ManualV111Tests().setup_run() as (j,collect,send):
            collect.side_effect=lambda *a,**k:sample();send.side_effect=TimeoutError('synthetic')
            with patch.dict('os.environ',{'V112_ANALYTICS_ENABLED':'true'}),self.assertRaises(TimeoutError):delivery.run()
            self.assertNotIn('last_analysis_v112',j.value)
            self.assertEqual(j.value['manual_slots']['github-run-1000']['status'],'uncertain')
    def test_final_journal_failure_blocks_resend_without_advancing_reference(self):
        with manual.ManualV111Tests().setup_run() as (j,collect,send):
            collect.side_effect=lambda *a,**k:sample();save=j.save;calls=[]
            def fail_second(value):
                calls.append(1)
                if len(calls)==2:raise RuntimeError('synthetic final CAS failure')
                save(value)
            with patch.dict('os.environ',{'V112_ANALYTICS_ENABLED':'true'}),patch.object(j,'save',side_effect=fail_second):
                with self.assertRaises(RuntimeError):delivery.run()
                delivery.run()
            send.assert_called_once();self.assertNotIn('last_analysis_v112',j.value)
            self.assertEqual(j.value['manual_slots']['github-run-1000']['status'],'attempting')

class FinalReviewTests(unittest.TestCase):
    def test_missing_reference_hash_is_not_verified(self):
        obs=model()['observation'];old=copy.deepcopy(obs);old.pop('fingerprint');old['at']=(NOW-timedelta(hours=1)).isoformat()
        self.assertEqual(analyst.comparison(old,obs)['status'],'N/A')
    def test_stale_btc_is_not_printed_as_current(self):
        snap=sample();snap['coins']['BTC']['stale']=True
        text=analyst.final_text(model(snap),snap,NOW,'manual')
        self.assertIn('BTC N/A',text);self.assertNotIn('BTC $80,000',text)
    def test_invalid_price_or_levels_cannot_create_forecast_or_held_action(self):
        snap=sample();snap['coins']['BTC']['price']=0
        self.assertEqual(analyst.outlook(snap['coins']['BTC'],'4h')['status'],'N/A')
        snap['coins']['AAVE']['frames']['4h']['atr']=-1
        text=analyst.final_text(model(snap),snap,NOW,'manual',INVENTORY)
        self.assertIn('WAIT (držba)',text)
    def test_candidate_requires_an_available_target_above_current_price(self):
        snap=sample()
        for c in snap['coins'].values():c['frames']['4h'].update(support=c['price']*.9,resistance=c['price']*.99,atr=c['price']*.001)
        q={s:dict(action='BUY NOW') for s in analyst.COINS};ev={s:dict(action='BUY NOW') for s in analyst.COINS}
        self.assertFalse(any(c['candidate'] for c in analyst.prepare(snap,{},NOW,q,ev)['coins'].values()))
        self.assertIsNone(analyst.delta(1e308,1e-308))
