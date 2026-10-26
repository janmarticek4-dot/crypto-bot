"""No private GitHub access. In-memory API, public deterministic test vectors only."""
import base64
import concurrent.futures
import contextlib
import copy
import io
import json
import os
from pathlib import Path
import shutil
import tempfile
import threading
import unittest
from unittest.mock import patch
from scripts import private_state_integration as p
from tests.test_state_hardening import MemoryGitHub
from v11.secure_state import GitHubState,StateError,decode_content

TEST_KEY=bytes([17])*32  # Deterministic PUBLIC test vector, not a deployable key.
TEST_TOKEN='synthetic-unit-test-access-token-only'
REPO='fixture/crypto-bot-state-integration-test'

class RemoteFixture(MemoryGitHub):
    def __init__(self):
        super().__init__();self.lock=threading.RLock();self.marker=copy.deepcopy(p.MARKER_DATA)
        self.root=[{'name':p.MARKER},{'name':'README.md'},{'name':'test'}]
        self.noisy=False;self.deny_real_access=False;self.attempts=[]
    def call(self,token,method,path,body=None):
        with self.lock:
            self.attempts.append((method,path))
            if token==p.DENIED_TOKEN or self.deny_real_access:raise StateError('Private state API failed, HTTP 401')
            if self.noisy:print('SYNTHETIC LEAK CANARY; MUST BE SUPPRESSED')
            if path=='':return dict(private=self.private,full_name=REPO,archived=False,disabled=False)
            if path=='/contents/'+p.MARKER:
                return dict(content=base64.b64encode(json.dumps(self.marker).encode()).decode(),sha='a'*40)
            if path=='/contents':return copy.deepcopy(self.root)
            return super().__call__(method,path,body)
    def factory(self,repo,token,key,environment,namespace=None):
        return GitHubState(repo,token,key,environment,
            transport=lambda method,path,body=None:self.call(token,method,path,body),namespace=namespace)


def environment(**updates):
    return dict(STATE_TEST_CONFIRMED='true',TEST_STATE_REPOSITORY=REPO,
                TEST_STATE_TOKEN=TEST_TOKEN,TEST_STATE_ENCRYPTION_KEY=base64.b64encode(TEST_KEY).decode(),
                GITHUB_REPOSITORY='fixture/crypto-bot',GITHUB_RUN_ID='123456',GITHUB_RUN_ATTEMPT='1',**updates)

class PrivateStateIntegration(unittest.TestCase):
    def setUp(self):self.remote=RemoteFixture()
    def run_harness(self,env=None):
        with tempfile.TemporaryDirectory() as directory,patch.object(p,'ROOT',Path(directory)):
            capture=io.StringIO()
            with contextlib.redirect_stdout(capture),contextlib.redirect_stderr(capture):
                result=p.run(Path(directory)/'state-integration-output',env or environment(),self.remote.factory,live_api=False)
            files=list(Path(directory).rglob('*'))
            self.assertEqual([f.name for f in files if f.is_file()],['report.json'])
            report=json.loads((Path(directory)/'state-integration-output/report.json').read_text())
            return result,report,capture.getvalue()

    def test_complete_integration_model_and_sanitized_report(self):
        result,report,output=self.run_harness()
        self.assertEqual(result,0);self.assertEqual(report['status'],'PASSED')
        self.assertEqual(set(report['checks']),set(p.CHECK_IDS))
        self.assertTrue(all(report['checks'].values()))
        self.assertFalse(report['api_requested'])
        serialized=json.dumps(report)+output
        for private in (TEST_TOKEN,base64.b64encode(TEST_KEY).decode(),TEST_KEY.hex(),'SYNTHETIC-NOT-AN-INVESTMENT-',REPO,'portfolio_v11'):
            self.assertNotIn(private,serialized)
        self.assertTrue(all('/test/integration/run-123456-1/' in path for path in self.remote.files))
        for stored in self.remote.files.values():
            self.assertNotIn(b'portfolio_v11',decode_content(stored))

    def test_public_repo_missing_marker_or_production_root_refused_before_write(self):
        for mode in ('public','marker','production_root'):
            self.remote=RemoteFixture()
            if mode=='public':self.remote.private=False
            elif mode=='marker':self.remote.marker={'synthetic_only':False}
            else:self.remote.root.append({'name':'prod'})
            result,report,_=self.run_harness()
            self.assertEqual(result,1);self.assertEqual(self.remote.writes,0)
            self.assertEqual(report['failure_stage'],'private_dedicated_repository')

    def test_no_confirmation_no_token_bad_key_or_wrong_repository_makes_no_request(self):
        for key,value in [('STATE_TEST_CONFIRMED','false'),('TEST_STATE_TOKEN',''),
                          ('TEST_STATE_ENCRYPTION_KEY','bad-base64'),('TEST_STATE_REPOSITORY','fixture/real-production-state'),
                          ('GITHUB_RUN_ID','../prod')]:
            env=environment();env[key]=value
            result,report,_=self.run_harness(env)
            self.assertEqual(result,1);self.assertEqual(self.remote.attempts,[])
            self.assertEqual(report['failure_stage'],'configuration')

    def test_unexpected_library_output_never_reaches_logs_or_artifact(self):
        self.remote.noisy=True
        result,report,output=self.run_harness()
        self.assertEqual(result,1)
        self.assertNotIn('SYNTHETIC LEAK CANARY',output+json.dumps(report))
        self.assertEqual(report['failure_stage'],'no_library_output_or_plaintext_files')

    def test_loss_of_all_remote_access_fails_without_writes_or_error_details(self):
        self.remote.deny_real_access=True
        result,report,output=self.run_harness()
        self.assertEqual(result,1);self.assertEqual(self.remote.writes,0)
        self.assertNotIn('HTTP 401',json.dumps(report)+output)

    def test_rerun_same_identity_refuses_reinitialization_without_overwrite(self):
        self.assertEqual(self.run_harness()[0],0)
        writes=self.remote.writes
        self.assertEqual(self.run_harness()[0],1)
        self.assertEqual(self.remote.writes,writes)

    def test_namespace_crypto_and_write_boundaries(self):
        first=GitHubState(REPO,TEST_TOKEN,TEST_KEY,'test',namespace='run-1-1')
        second=GitHubState(REPO,TEST_TOKEN,TEST_KEY,'test',namespace='run-1-2')
        with self.assertRaises(StateError):second.decrypt(first.encrypt({'fixture':True}))
        for env,namespace in [('prod','run-1-1'),('test','../prod'),('test','run-x-1')]:
            with self.assertRaises(StateError):GitHubState(REPO,TEST_TOKEN,TEST_KEY,env,namespace=namespace)
        calls=[]
        restricted=p.ScopedTransport(lambda *a:None,'test/integration/run-1-1','canary',calls)
        for path in ('/contents/prod/state.enc','/contents/test/state.enc','/contents/test/integration/run-2-1/state.enc','/contents/'+p.MARKER):
            with self.assertRaises(p.Refused):restricted('PUT',path,{})
        self.assertEqual(calls,[])

    def test_workflow_uses_only_test_environment_credentials_and_one_fixed_artifact(self):
        root=Path(__file__).resolve().parents[1]
        text=(root/'.github/workflows/private-state-integration.yml').read_text()
        self.assertIn('environment: state-storage-integration',text)
        self.assertIn('persist-credentials: false',text)
        self.assertIn('path: state-integration-output/report.json',text)
        for forbidden in ('secrets.STATE_REPO_TOKEN','secrets.STATE_ENCRYPTION_KEY','TELEGRAM_TOKEN','main.py','bot_state.json','git push','  schedule:','secrets: inherit'):
            self.assertNotIn(forbidden,text)
        self.assertLess(text.index('Offline integration harness'),text.index('TEST_STATE_TOKEN:'))
        self.assertIn('needs: authorize',text)
        entry=(root/'.github/workflows/run.yml').read_text()
        self.assertIn("inputs.task == 'private-state'",entry)
        job=entry.split('\n  private-state:\n',1)[1]
        self.assertIn('environment: state-storage-integration',job)
        self.assertIn('needs: private-state-authorization',job)
        self.assertIn('TEST_STATE_TOKEN: ${{ secrets.TEST_STATE_TOKEN }}',job)
        self.assertNotIn('uses: ./.github/workflows/private-state-integration.yml',entry)
        self.assertNotIn('secrets.STATE_REPO_TOKEN',entry)

    def test_unexpected_private_report_fields_are_refused_before_serialization(self):
        def poisoned(config,factory,checks):
            checks['accidental_ledger']={'cash':'SYNTHETIC-PRIVATE-CANARY'}
        with patch.object(p,'exercise',side_effect=poisoned):
            result,report,output=self.run_harness()
        self.assertEqual(result,1);self.assertEqual(report['status'],'REFUSED')
        self.assertNotIn('SYNTHETIC-PRIVATE-CANARY',json.dumps(report)+output)
        self.assertNotIn('accidental_ledger',json.dumps(report))

    def test_configuration_error_codes_do_not_reveal_values_or_make_requests(self):
        cases=[('TEST_STATE_REPOSITORY','','REPOSITORY_VARIABLE_MISSING'),
               ('TEST_STATE_REPOSITORY','https://example.invalid/private','REPOSITORY_VARIABLE_INVALID'),
               ('TEST_STATE_TOKEN','','TOKEN_SECRET_MISSING'),
               ('TEST_STATE_TOKEN','SHORT-TEST','TOKEN_SECRET_TOO_SHORT'),
               ('TEST_STATE_ENCRYPTION_KEY','','ENCRYPTION_SECRET_MISSING'),
               ('TEST_STATE_ENCRYPTION_KEY','NOT-BASE64-CANARY','ENCRYPTION_SECRET_INVALID_BASE64'),
               ('TEST_STATE_ENCRYPTION_KEY',base64.b64encode(b'fake').decode(),'ENCRYPTION_SECRET_NOT_32_BYTES')]
        for name,value,expected in cases:
            env=environment();env[name]=value
            result,report,output=self.run_harness(env)
            self.assertEqual(result,1);self.assertEqual(report['failure_code'],expected)
            if value:self.assertNotIn(value,json.dumps(report)+output)
            self.assertEqual(self.remote.attempts,[])

    def test_missing_token_reports_presence_only_and_never_secret_values(self):
        env=environment();env['TEST_STATE_TOKEN']=''
        result,report,output=self.run_harness(env)
        self.assertEqual(result,1)
        self.assertEqual(report['configuration_presence'],{
            'token_available':False,'encryption_key_available':True,'repository_variable_available':True})
        self.assertIn('token_available=missing',output)
        self.assertNotIn(env['TEST_STATE_ENCRYPTION_KEY'],output+json.dumps(report))
        self.assertEqual(self.remote.attempts,[])
