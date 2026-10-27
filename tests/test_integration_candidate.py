import copy
from datetime import datetime,timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import main as legacy
from v11 import integration
from scripts import v111_integrated_delivery as delivery
from scripts.state_public_guard import check
from tests.test_briefing import snapshot

class IntegrationTests(unittest.TestCase):
    def data(self):
        snap=snapshot()
        for coin in snap['coins'].values():
            coin['raw']={'4h':[dict(timestamp=i*14400000,open=100+i*.2,high=101+i*.2,low=99+i*.2,close=100+i*.2,volume=100+i) for i in range(300)]}
            coin['price']=160
        return snap
    def test_exact_legacy_decision_parity_and_immutable_inputs(self):
        snap=self.data();state={'safety':{'state':'NORMAL'},'last_actions':{'SOL':{'action':'WAIT'}}};before=copy.deepcopy(state)
        ctx=integration.context(legacy,snap,state)
        baseline=legacy.evaluate_all(ctx,copy.deepcopy(state),legacy.get_usable_fundamentals(state))[2]
        _,_,_,actual=integration.evaluate(legacy,snap,state)
        self.assertEqual(baseline,actual);self.assertEqual(state,before)
    def test_negative_new_news_cannot_change_rules(self):
        snap=self.data();state={};before=copy.deepcopy(snap)
        text,quotes,first=integration.render(legacy,snap,{},datetime.now(timezone.utc),'evening',state)
        text2,quotes2,second=integration.render(legacy,snap,{'events':[{'id':'synthetic','title':'Aave exploit confirmed','source':'synthetic','url':'https://example.org/a','published_at':datetime.now(timezone.utc).isoformat(),'retrieved_at':datetime.now(timezone.utc).isoformat(),'symbol':'AAVE','categories':['hack']}]},datetime.now(timezone.utc),'evening',state)
        self.assertEqual(first,second);self.assertEqual({s:quotes[s] for s in legacy.PORTFOLIO},{s:quotes2[s] for s in legacy.PORTFOLIO});self.assertEqual(snap,before)
    def test_private_canary_refused_not_redacted(self):
        with self.assertRaises(Exception):integration.rule_state({'portfolio':{'SOL':{'quantity':99}}})
    def test_corrupt_state_never_reset(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'state.json';p.write_text('{bad');before=p.read_bytes()
            with self.assertRaises(Exception):integration.read_rule_state(p)
            with self.assertRaises(Exception):check(p)
            self.assertEqual(p.read_bytes(),before)
    def test_guard_rejects_empty_or_secret(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'state.json'
            for data in ({},{'api_key':'synthetic'}):
                p.write_text(json.dumps(data))
                with self.assertRaises(Exception):check(p)
    def test_old_pilot_actions_not_claimed_as_v106_baseline(self):
        text,_,_=integration.render(legacy,self.data(),{},datetime.now(timezone.utc),'evening',{},previous={'SOL':{'action':'BUY NOW','price':150}})
        self.assertIn('iný/neoverený pôvod',text)
    def test_feature_off_preserves_existing_entrypoint(self):
        with patch.dict('os.environ',{'V111_INTEGRATION_ENABLED':'false'}),patch.object(delivery.pilot,'run',return_value=0) as run,patch.object(delivery,'latest_public_rule_state') as read:
            self.assertEqual(delivery.run(),0);run.assert_called_once();read.assert_not_called()
    def test_usa_delegate_preserved_when_enabled(self):
        with patch.dict('os.environ',{'V111_INTEGRATION_ENABLED':'true'}),patch.object(delivery.pilot,'phase',return_value='usa'),patch.object(delivery.pilot,'run',return_value=0) as run,patch.object(delivery,'latest_public_rule_state') as read:
            self.assertEqual(delivery.run(),0);run.assert_called_once();read.assert_not_called()
    def test_existing_dedup_owner_and_renderer_restored(self):
        snap=self.data();original=delivery.pilot.render
        def same_owner():
            text,quotes=delivery.pilot.render(snap,{},datetime.now(timezone.utc),'morning')
            self.assertTrue(all(q['rule_engine']=='v10.6-original' for s,q in quotes.items() if s in legacy.PORTFOLIO));return 0
        with patch.dict('os.environ',{'V111_INTEGRATION_ENABLED':'true'}),patch.object(delivery.pilot,'phase',return_value='morning'),patch.object(delivery,'latest_public_rule_state',return_value={}),patch.object(legacy,'get_fear_greed',return_value={}),patch.object(delivery.pilot,'run',side_effect=same_owner) as run:
            self.assertEqual(delivery.run(),0);run.assert_called_once()
        self.assertIs(delivery.pilot.render,original)

class BaselineIdentityTests(unittest.TestCase):
    def test_production_files_byte_identical(self):
        import hashlib
        root=Path(__file__).resolve().parents[1]
        manifest=json.loads((root/'docs/integration/BASELINE.json').read_text())
        for name,expected in manifest['protected_files'].items():
            self.assertEqual(hashlib.sha256((root/name).read_bytes()).hexdigest(),expected,name)
    def test_no_schedule_or_credentials_in_integration_workflow(self):
        root=Path(__file__).resolve().parents[1]
        text=(root/'.github/workflows/v111-integration-shadow.yml').read_text()
        for forbidden in ('  schedule:', 'secrets:', 'contents: write','secrets.TELEGRAM','secrets.PROD_STATE'):
            self.assertNotIn(forbidden,text)
        self.assertIn('persist-credentials: false',text)
        self.assertIn('run.conclusion',text)
        self.assertIn('run.event',text)

class JournalContinuityTests(unittest.TestCase):
    def test_missing_established_journal_cannot_reinitialize(self):
        original=delivery.pilot.PublicJournal.read
        def call_existing():
            return delivery.pilot.PublicJournal.read(object())
        with patch.dict('os.environ',{'V111_INTEGRATION_ENABLED':'true'}),patch.object(delivery.pilot,'phase',return_value='usa'),patch.object(delivery.pilot.PublicJournal,'read',return_value={'schema':1,'slots':{}}),patch.object(delivery.pilot,'run',side_effect=call_existing):
            with self.assertRaisesRegex(RuntimeError,'refusing a reset'):delivery.run()
        self.assertIs(delivery.pilot.PublicJournal.read,original)

class ReadOnlyContentsTests(unittest.TestCase):
    def test_api_state_missing_never_becomes_empty_ledger(self):
        import urllib.error
        with patch.dict('os.environ',{'GITHUB_REPOSITORY':'owner/repo','GH_TOKEN':'synthetic'}),patch.object(delivery.urllib.request,'urlopen',side_effect=urllib.error.HTTPError('https://example.org',404,'missing',None,None)):
            with self.assertRaises(urllib.error.HTTPError):delivery.latest_public_rule_state()
    def test_empty_remote_state_refused_without_write(self):
        import base64
        from unittest.mock import MagicMock
        response=MagicMock();response.__enter__.return_value.read.return_value=json.dumps({'content':base64.b64encode(b'{}').decode()}).encode()
        with patch.dict('os.environ',{'GITHUB_REPOSITORY':'owner/repo','GH_TOKEN':'synthetic'}),patch.object(delivery.urllib.request,'urlopen',return_value=response) as request:
            with self.assertRaisesRegex(ValueError,'empty'):delivery.latest_public_rule_state()
        self.assertEqual(request.call_args.args[0].get_method(),'GET')

class NoNewPredictionModelTests(unittest.TestCase):
    def test_enabled_adapter_only_audits_old_forecasts(self):
        snap=IntegrationTests().data();original=delivery.pilot.forecast_audit.remember
        def existing_job():
            state={}
            delivery.pilot.forecast_audit.update(state,snap,{'events':[]},'SYNTHETIC_07:00')
            self.assertEqual(state['analysis_forecasts_v11'],[])
            return 0
        with patch.dict('os.environ',{'V111_INTEGRATION_ENABLED':'true'}),patch.object(delivery.pilot,'phase',return_value='morning'),patch.object(delivery,'latest_public_rule_state',return_value={}),patch.object(legacy,'get_fear_greed',return_value={}),patch.object(delivery.pilot,'run',side_effect=existing_job):
            self.assertEqual(delivery.run(),0)
        self.assertIs(delivery.pilot.forecast_audit.remember,original)

class IntegratedPrivacyTests(unittest.TestCase):
    def test_private_canary_only_reaches_existing_sender_not_public_journal(self):
        import os
        from v11.state_policy import require_public_data
        pilot=delivery.pilot;now=datetime(2026,10,27,6,tzinfo=timezone.utc);writes=[]
        snapshot=IntegrationTests().data()
        with patch.dict(os.environ,{'V111_INTEGRATION_ENABLED':'true','PRIVATE_ADVISORY_ENABLED':'true'}),patch.object(pilot,'datetime') as clock,patch.object(pilot,'PublicJournal') as journal,patch.object(pilot.data,'collect',return_value=snapshot),patch.object(pilot.fundamentals,'collect',return_value={'events':[]}),patch.object(pilot.macro_context,'collect',return_value={}),patch.object(pilot.macro_context,'economic_observations',return_value={'url':'https://fred.stlouisfed.org','checked_at':now.isoformat(),'observations':{}}),patch.object(delivery,'latest_public_rule_state',return_value={}),patch.object(legacy,'get_fear_greed',return_value={}),patch('v11.advisory_portfolio.load',return_value={'synthetic':True}),patch('v11.advisory_portfolio.advice',return_value='PRIVATE-CANARY-NOT-A-REAL-POSITION'),patch.object(pilot,'send') as send:
            clock.now.return_value=now
            journal.return_value.read.return_value={'schema':1,'slots':{'2026-10-26-evening':{'status':'sent'}}}
            journal.return_value.save.side_effect=lambda state:writes.append(copy.deepcopy(state))
            delivery.run()
        self.assertIn('PRIVATE-CANARY-NOT-A-REAL-POSITION',send.call_args.args[0])
        self.assertNotIn('Držba N/A',send.call_args.args[0])
        self.assertTrue(writes)
        for state in writes:
            self.assertNotIn('PRIVATE-CANARY',json.dumps(state));require_public_data(state)

class StateContinuityTests(unittest.TestCase):
    def test_nonempty_reset_also_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            state=Path(directory)/'state.json';schema=Path(directory)/'schema.json'
            state.write_text(json.dumps({'peaks':{},'last_actions':{},'last_run':'synthetic'}))
            check(state,record_schema=schema)
            state.write_text(json.dumps({'last_run':'synthetic reset'}))
            with self.assertRaisesRegex(ValueError,'sections were lost'):check(state,require_schema=schema)
    def test_schema_has_no_state_values(self):
        with tempfile.TemporaryDirectory() as directory:
            state=Path(directory)/'state.json';schema=Path(directory)/'schema.json'
            state.write_text(json.dumps({'last_run':'PUBLIC-STATE-VALUE-CANARY'}))
            check(state,record_schema=schema)
            self.assertNotIn('CANARY',schema.read_text());self.assertEqual(json.loads(schema.read_text()),['last_run'])
            check(state,require_schema=schema)
    def test_schema_cannot_overwrite_state(self):
        with tempfile.TemporaryDirectory() as directory:
            state=Path(directory)/'state.json';state.write_text('{"last_run":"synthetic"}');before=state.read_bytes()
            with self.assertRaises(ValueError):check(state,record_schema=state)
            self.assertEqual(state.read_bytes(),before)

class NativePlanPreservationTests(unittest.TestCase):
    def test_original_gross_rr_and_invalidation_retained(self):
        snap=IntegrationTests().data();ctx,metrics,safety,ev=integration.evaluate(legacy,snap,{})
        for value in ev.values():value.update(entry=100,stop=90,tp1=110,tp2=120,flip='SYNTHETIC INVALIDATION')
        with patch.object(integration,'evaluate',return_value=(ctx,metrics,safety,ev)):
            text,_,_=integration.render_detailed(legacy,snap,{},datetime.now(timezone.utc),'evening',{})
        self.assertIn('hrubé R:R 1.0 / 2.0',text);self.assertIn('SYNTHETIC INVALIDATION',text)
        self.assertIn('čisté R:R N/A',text)

class DiagnosticRepairTests(unittest.TestCase):
    def test_policy_error_is_not_network_failure(self):
        from scripts.fundamental_sources_shadow import error_details
        from v11.fundamentals import SourcePolicyError
        for reason in ('PAYLOAD_LIMIT_EXCEEDED','UNEXPECTED_REDIRECT'):
            value=error_details(SourcePolicyError(reason));self.assertEqual(value['status'],'SOURCE_POLICY_ERROR');self.assertEqual(value['error_code'],reason)
    def test_detailed_tvl_has_larger_but_bounded_payload(self):
        from v11 import fundamentals
        from unittest.mock import MagicMock
        for url,expected in [('https://api.llama.fi/protocol/aave',8_000_001),('https://www.bls.gov/feed/bls_latest.rss',2_000_001)]:
            response=MagicMock();response.__enter__.return_value.geturl.return_value=url;response.__enter__.return_value.read.return_value=b'{}'
            with patch.object(fundamentals.urllib.request,'urlopen',return_value=response):fundamentals.fetch(dict(url=url))
            response.__enter__.return_value.read.assert_called_once_with(expected)
    def test_risk_reasons_exactly_account_for_native_scores(self):
        _,_,_,ev=integration.evaluate(legacy,IntegrationTests().data(),{})
        for e in ev.values():self.assertTrue(integration.risk_breakdown(legacy,e)['matched'])
    def test_reported_seven_and_five_point_reduce_explained(self):
        for dd,points in [('hlboký pokles 15.9% od lokálneho maxima',7),('pokles 8.1% od lokálneho maxima (prah 6.0%)',5)]:
            e=dict(action='REDUCE',risk_pts=points,risk_reasons=[dd,'cena pod EMA50','cena pod EMA200','slabý trend (skóre 2.1/10)','bezpečnostný stav trhu: WARNING'])
            result=integration.risk_breakdown(legacy,e);self.assertEqual(result['sum'],points);self.assertTrue(result['matched']);self.assertIn('nie overenú predikciu',result['trigger'])
    def test_unrecognized_risk_reason_not_silently_assigned(self):
        r=integration.risk_breakdown(legacy,dict(action='REDUCE',risk_pts=5,risk_reasons=['unknown']))
        self.assertFalse(r['matched']);self.assertIsNone(r['components'][0]['points'])
    def test_routine_governance_and_code_release_not_prominent(self):
        from v11.fundamental_analysis import analyze,coin_lines
        now=datetime.now(timezone.utc)
        e=dict(id='synthetic',title='Risk Stewards: Cap Increases on Aave',source='aave',url='https://governance.aave.com/synthetic',published_at=now.isoformat(),retrieved_at=now.isoformat(),categories=['project'],symbol='AAVE')
        self.assertFalse(analyze({'events':[e]},now)['evidence'][0]['material'])
        self.assertNotIn(e['title'],' '.join(coin_lines('AAVE',{'events':[e]},now)))
    def test_regional_employment_not_in_main_calendar(self):
        from v11.briefing import event_lines
        now=datetime(2026,10,26,tzinfo=timezone.utc)
        event=dict(scheduled=True,event_at='2026-10-28T14:00:00+00:00',title='Metropolitan Area Employment',url='https://www.bls.gov',categories=['employment'])
        self.assertNotIn('Metropolitan',' '.join(event_lines({'events':[event]},now.timestamp())))
