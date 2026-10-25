"""All remote state, keys, balances and fills below are synthetic fixtures only."""
import base64
import contextlib
import io
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch
from v11.secure_state import GitHubState, StateError, atomic_local, state_path
from tests.test_secure_state import FakeGitHub

TEST_KEY=bytes(range(32))  # Public deterministic test vector, NEVER a production key.

class MemoryGitHub(FakeGitHub):
    def __call__(self,method,path,body=None):
        result=super().__call__(method,path,body)
        if method=='PUT':
            sha=f'{self.n:040x}';self.files[path]['sha']=sha
            result['content']['sha']=sha
        return result

class StateHardening(unittest.TestCase):
    def setUp(self):
        self.remote=MemoryGitHub()
        self.client=GitHubState('fixture/private','fixture-token',TEST_KEY,'test',self.remote)
        self.initial={'portfolio_v11':{'cash':123.,'positions':{'SOL':{'qty':2.,'cost':50.}},'transactions':[]},'legacy':{'keep':True}}

    def initialized_backup(self):
        self.client.initialize(self.initial);sha=self.client.sha
        self.client.commit(dict(self.initial,revision=2))
        return sha

    def test_non_deterministic_nonce_and_wrong_key_repo_environment(self):
        first=self.client.encrypt(self.initial);second=self.client.encrypt(self.initial)
        self.assertNotEqual(json.loads(first)['nonce'],json.loads(second)['nonce'])
        for repo,key,env in [('other/private',TEST_KEY,'test'),('fixture/private',bytes(reversed(TEST_KEY)),'test'),('fixture/private',TEST_KEY,'prod')]:
            with self.assertRaises(StateError):GitHubState(repo,'fixture-token',key,env,self.remote).decrypt(first)
        for payload in (first,second):self.assertEqual(self.client.decrypt(payload),self.initial)

    def test_corruption_rejected_without_mutation_or_plaintext_logging(self):
        self.client.initialize(self.initial)
        self.remote.files['/contents/test/state.enc']['content']=base64.b64encode(b'{broken fixture}').decode()
        before=self.remote.writes
        capture=io.StringIO()
        with contextlib.redirect_stdout(capture),contextlib.redirect_stderr(capture):
            with self.assertRaisesRegex(StateError,'refusing reset'):self.client.read()
        self.assertEqual(self.remote.writes,before)
        self.assertEqual(capture.getvalue(),'')

    def test_recover_authenticated_backup_when_current_is_corrupt(self):
        backup_sha=self.initialized_backup()
        current=self.remote.files['/contents/test/state.enc'];expected=current['sha']
        current['content']=base64.b64encode(b'corrupt fixture ciphertext').decode()
        with self.assertRaises(StateError):self.client.read()
        self.assertEqual(self.client.restore_backup(backup_sha,expected),self.initial)
        self.assertEqual(self.client.read(),self.initial)
        self.assertIn(f'/contents/test/backups/{backup_sha}.enc',self.remote.files)

    def test_recovery_refuses_changed_current_or_corrupt_backup(self):
        sha=self.initialized_backup();writes=self.remote.writes
        with self.assertRaises(StateError):self.client.restore_backup(sha,'f'*40)
        self.assertEqual(self.remote.writes,writes)
        self.remote.files[f'/contents/test/backups/{sha}.enc']['content']='!!!!'
        with self.assertRaises(StateError):self.client.restore_backup(sha,self.client.sha)
        self.assertEqual(self.remote.writes,writes)

    def test_api_cas_wins_against_writer_between_recovery_get_and_put(self):
        sha=self.initialized_backup();expected=self.client.sha
        original=self.client.transport
        def race(method,path,body=None):
            if method=='PUT' and path=='/contents/test/state.enc':
                self.remote.files[path]['sha']='e'*40
            return original(method,path,body)
        self.client.transport=race
        with self.assertRaises(StateError):self.client.restore_backup(sha,expected)
        self.assertEqual(self.remote.files['/contents/test/state.enc']['sha'],'e'*40)

    def test_poisoned_existing_backup_stops_current_checkpoint(self):
        self.client.initialize(self.initial);sha=self.client.sha
        self.remote.files[f'/contents/test/backups/{sha}.enc']=dict(content=base64.b64encode(self.client.encrypt({'different':'fixture'})).decode(),sha='c'*40)
        writes=self.remote.writes
        with self.assertRaises(StateError):self.client.commit(dict(self.initial,revision=2))
        self.assertEqual(self.remote.writes,writes)
        self.assertEqual(self.client.read(),self.initial)

    def test_existing_state_never_reinitialized_and_public_repo_read_fails(self):
        self.client.initialize(self.initial);writes=self.remote.writes
        with self.assertRaises(StateError):self.client.initialize({})
        self.remote.private=False
        with self.assertRaises(StateError):self.client.read()
        with self.assertRaises(StateError):self.client.restore_backup('a'*40,self.client.sha)
        self.assertEqual(self.remote.writes,writes)

    def test_github_base64_line_wrap_is_supported_but_junk_refused(self):
        self.client.initialize(self.initial)
        row=self.remote.files['/contents/test/state.enc']
        text=row['content'];row['content']='\n'.join(text[i:i+60] for i in range(0,len(text),60))+'\n'
        self.assertEqual(self.client.read(),self.initial)
        row['content']+='!'
        with self.assertRaises(StateError):self.client.read()

    def test_bad_envelope_nonce_version_and_oversize_are_rejected(self):
        good=json.loads(self.client.encrypt(self.initial))
        for field,value in [('nonce',base64.b64encode(b'short').decode()),('version',True),('version',2)]:
            altered=dict(good,**{field:value})
            with self.assertRaises(StateError):self.client.decrypt(json.dumps(altered).encode())
        with self.assertRaises(StateError):self.client.decrypt(b'x'*900001)

    def test_atomic_write_private_mode_no_temp_symlink_follow_and_failure_keeps_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'state.json';victim=Path(tmp)/'untouched.json'
            victim.write_text('untouched');path.with_suffix('.tmp').symlink_to(victim)
            atomic_local(path,{'fixture':1})
            self.assertEqual(victim.read_text(),'untouched')
            self.assertEqual(stat.S_IMODE(path.stat().st_mode),0o600)
            with self.assertRaises(ValueError):atomic_local(path,{'bad':float('nan')})
            self.assertEqual(json.loads(path.read_text()),{'fixture':1})
            self.assertEqual(list(Path(tmp).glob('.state-*.tmp')),[])
            linked=Path(tmp)/'linked.json';linked.symlink_to(victim)
            with self.assertRaises(StateError):atomic_local(linked,{'fixture':2})
            directory=Path(tmp)/'alias';directory.symlink_to(tmp,target_is_directory=True)
            with self.assertRaises(StateError):atomic_local(directory/'other.json',{})

    def test_local_environment_split_and_permissions(self):
        with tempfile.TemporaryDirectory() as tmp,patch('pathlib.Path.cwd',return_value=Path(tmp)):
            paths=[]
            for env in ('prod','test'):
                with patch.dict(os.environ,{'STATE_ENV':env}):
                    path=state_path();paths.append(path)
                    self.assertEqual(stat.S_IMODE(path.parent.stat().st_mode),0o700)
            self.assertNotEqual(*paths)
            with patch.dict(os.environ,{'STATE_ENV':'../public'}):
                with self.assertRaises(StateError):state_path()

    def test_development_main_refuses_private_fields_outside_portfolio_key(self):
        import main
        target=Path(main.__file__).with_name('never-created-public-account.json')
        for value in ({'cash':123},{'nested':{'transactions':[]}},{'credentials':{'password':'fixture'}}):
            with patch.object(main,'STATE_FILE',str(target)),patch.object(main,'STATE_STORE',None):
                with self.assertRaises(RuntimeError):main.save_state(value)
        self.assertFalse(target.exists())

    def test_missing_private_plaintext_never_initializes_empty_ledger(self):
        import main
        with tempfile.TemporaryDirectory() as tmp,patch.object(main,'STATE_FILE',str(Path(tmp)/'missing.json')),patch.object(main,'STATE_STORE',object()):
            with self.assertRaisesRegex(RuntimeError,'refusing'):main.load_state()

    def test_missing_environment_cannot_silently_select_production(self):
        with patch.dict(os.environ,{'STATE_ENCRYPTION_KEY':base64.b64encode(TEST_KEY).decode(),
                                     'STATE_REPO_TOKEN':'fixture-token','PRIVATE_STATE_REPO':'fixture/private'},clear=True):
            with self.assertRaises(StateError):GitHubState.from_env()
            with self.assertRaises(StateError):state_path()

    def test_restore_does_not_delete_legacy_unknown_fields(self):
        sha=self.initialized_backup()
        recovered=self.client.read_backup(sha)
        self.assertEqual(recovered['legacy'],{'keep':True})
        self.assertEqual(recovered['portfolio_v11'],self.initial['portfolio_v11'])
