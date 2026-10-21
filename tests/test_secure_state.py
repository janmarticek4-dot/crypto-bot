import base64
import copy
import json
import unittest
from unittest.mock import patch
from v11.secure_state import GitHubState, StateError, stable_state


class FakeGitHub:
    def __init__(self):self.files={};self.private=True;self.n=0;self.writes=0
    def __call__(self,method,path,body=None):
        if not path:return {'private':self.private}
        if method=='GET':return copy.deepcopy(self.files.get(path,{'_not_found':True}))
        current=self.files.get(path,{})
        if current.get('sha')!=body.get('sha'):raise StateError('conflict')
        self.n+=1;self.writes+=1
        value=dict(content=body['content'],sha=str(self.n));self.files[path]=value
        return {'content':{'sha':value['sha']}}


class PrivateStateTests(unittest.TestCase):
    def setUp(self):
        self.remote=FakeGitHub();self.key=bytes(range(32))
        self.client=GitHubState('owner/private','token',self.key,transport=self.remote)
    def test_encrypt_roundtrip_not_plaintext(self):
        plain={'portfolio_v11':{'cash':12345,'transactions':[{'symbol':'SOL'}]}}
        cipher=self.client.encrypt(plain)
        self.assertNotIn(b'SOL',cipher)
        self.assertNotIn(b'12345',cipher)
        self.assertEqual(self.client.decrypt(cipher),plain)
    def test_tamper_and_environment_binding(self):
        cipher=self.client.encrypt({'cash':50})
        other=GitHubState('owner/private','token',self.key,'test',transport=self.remote)
        with self.assertRaises(StateError):other.decrypt(cipher)
        altered=json.loads(cipher);altered['ciphertext']='AAAA'
        with self.assertRaises(StateError):self.client.decrypt(json.dumps(altered).encode())
    def test_public_repository_refused(self):
        self.remote.private=False
        with self.assertRaises(StateError):self.client.initialize({'cash':8500})
        self.assertEqual(self.remote.writes,0)
    def test_missing_state_never_resets(self):
        with self.assertRaises(StateError):self.client.read()
    def test_backup_and_recovery(self):
        self.client.initialize({'cash':8500})
        sha=self.client.sha
        self.client.commit({'cash':7000})
        backup=self.remote.files[f'/contents/prod/backups/{sha}.enc']
        self.assertEqual(self.client.decrypt(base64.b64decode(backup['content'])),{'cash':8500})
        self.assertEqual(self.client.read(),{'cash':7000})
    def test_optimistic_concurrent_write_refused(self):
        self.client.initialize({'cash':8500})
        second=GitHubState('owner/private','token',self.key,transport=self.remote)
        second.read();self.client.commit({'cash':8000})
        with self.assertRaises(StateError):second.commit({'cash':7000})
        self.assertEqual(self.client.read(),{'cash':8000})
    def test_quiet_monitor_does_not_expand_history(self):
        self.client.initialize({'last_run':'first','crash_monitor_v11':{'checked_at':1,'sent':{}},'cash':8500})
        writes=self.remote.writes
        self.client.commit({'last_run':'second','crash_monitor_v11':{'checked_at':2,'sent':{}},'cash':8500})
        self.assertEqual(self.remote.writes,writes)
    def test_main_refuses_public_ledger(self):
        import main
        with patch.object(main,'STATE_FILE',str(__import__('pathlib').Path(main.__file__).with_name('bot_state.json'))):
            with self.assertRaises(RuntimeError):main.save_state({'portfolio_v11':{'cash':8500}})
    def test_ambiguous_success_is_confirmed_not_duplicated(self):
        self.client.initialize({'cash':8500})
        original=self.client.transport
        def ambiguous(method,path,body=None):
            result=original(method,path,body)
            if method=='PUT' and path=='/contents/prod/state.enc':raise StateError('timeout after write')
            return result
        self.client.transport=ambiguous
        self.client.commit({'cash':8000})
        self.assertEqual(self.client.read(),{'cash':8000})

class LocalSessionConcurrency(unittest.TestCase):
    def test_second_reader_cannot_clobber_active_plaintext(self):
        import tempfile,threading
        from pathlib import Path
        from unittest.mock import MagicMock
        from v11.secure_state import session,atomic_local
        entered=threading.Event();started=threading.Event();failures=[]
        store=MagicMock();store.read.return_value={'cash':8500}
        with tempfile.TemporaryDirectory() as d:
            target=Path(d)/'state.json'
            def reader():
                try:
                    started.set()
                    with session():entered.set()
                except Exception as e:failures.append(type(e).__name__)
            with patch('v11.secure_state.state_path',return_value=target),patch.object(GitHubState,'from_env',return_value=store):
                with session():
                    atomic_local(target,{'marker':'active writer'})
                    thread=threading.Thread(target=reader);thread.start()
                    self.assertTrue(started.wait(1))
                    self.assertFalse(entered.wait(.05))
                    self.assertEqual(json.loads(target.read_text()),{'marker':'active writer'})
                thread.join(2)
                self.assertFalse(thread.is_alive())
                self.assertTrue(entered.is_set())
                self.assertEqual(failures,[])

class PublicCheckoutProtection(unittest.TestCase):
    def test_nondefault_public_filename_is_also_rejected(self):
        import main
        from pathlib import Path
        alternate=Path(main.__file__).with_name('accidental-portfolio.json')
        with patch.object(main,'STATE_FILE',str(alternate)):
            with self.assertRaises(RuntimeError):main.save_state({'portfolio_v11':{'cash':8500}})
        self.assertFalse(alternate.exists())

class CheckpointSize(unittest.TestCase):
    def test_large_ciphertext_cannot_create_unreadable_remote_file(self):
        import os
        client=GitHubState('owner/private','synthetic',bytes(range(32)))
        with self.assertRaises(StateError):client.encrypt({'data':base64.b64encode(os.urandom(800000)).decode()})
