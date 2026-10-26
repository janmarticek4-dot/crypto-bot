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
        self.assertEqual(first,second);self.assertEqual(quotes,quotes2);self.assertEqual(snap,before)
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
            self.assertTrue(all(q['rule_engine']=='v10.6-original' for q in quotes.values()));return 0
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
