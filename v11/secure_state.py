"""Encrypted private GitHub state, optimistic CAS, write-through checkpoints.

No external repository is provisioned automatically. Trading permissions are
never needed. Tokens and plaintext are never written to logs or Git history.
"""
import argparse
import fcntl
from contextlib import contextmanager
import base64
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import urllib.request
import urllib.error
import zlib
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class StateError(RuntimeError):
    pass


def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()


def stable_state(state):
    out=copy.deepcopy(state)
    out.pop('last_run',None)
    for key,field in [('crash_monitor_v11','checked_at'),('crash_monitor','last_checked_at')]:
        if isinstance(out.get(key),dict):out[key].pop(field,None)
    return out


class GitHubState:
    def __init__(self,repo,token,key,environment='prod',transport=None):
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9][A-Za-z0-9_.-]*',repo):raise StateError('Invalid private repository name')
        if environment not in ('prod','test'):raise StateError('State environment must be prod or test')
        if len(key)!=32 or not token:raise StateError('Missing state token or 32-byte encryption key')
        self.repo=repo;self.token=token;self.key=key;self.environment=environment
        self.path=f'{environment}/state.enc';self.sha=None;self.previous=None;self.digest=None
        self.transport=transport or self.request
        self.aad=f'crypto-bot:v1:{repo}:{environment}'.encode()

    @classmethod
    def from_env(cls):
        try:key=base64.b64decode(os.environ['STATE_ENCRYPTION_KEY'],validate=True)
        except (KeyError,ValueError):raise StateError('Set STATE_ENCRYPTION_KEY securely; base64 of 32 random bytes') from None
        return cls(os.environ.get('PRIVATE_STATE_REPO',''),os.environ.get('STATE_REPO_TOKEN',''),key,os.environ.get('STATE_ENV','prod'))

    def request(self,method,path,body=None):
        req=urllib.request.Request('https://api.github.com/repos/'+self.repo+path,
            data=canonical(body) if body is not None else None,method=method,
            headers={'Authorization':'Bearer '+self.token,'Accept':'application/vnd.github+json','Content-Type':'application/json','X-GitHub-Api-Version':'2022-11-28','User-Agent':'crypto-bot-private-state'})
        try:
            with urllib.request.urlopen(req,timeout=20) as r:return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code==404:return {'_not_found':True}
            if e.code in (409,422):raise StateError('Private state conflict; refusing to overwrite concurrent changes') from None
            raise StateError('Private state API failed, HTTP '+str(e.code)) from None
        except (OSError,ValueError):raise StateError('Private state API unavailable; state was not acknowledged') from None

    def verify_private(self):
        meta=self.transport('GET','')
        if meta.get('private') is not True:raise StateError('State repository must exist and be PRIVATE')

    def encrypt(self,state):
        nonce=secrets.token_bytes(12)
        data=canonical(state)
        if len(data)>5_000_000:raise StateError('State too large; archive transaction history securely before continuing')
        cipher=AESGCM(self.key).encrypt(nonce,zlib.compress(data),self.aad)
        payload=canonical(dict(version=1,nonce=base64.b64encode(nonce).decode(),ciphertext=base64.b64encode(cipher).decode()))
        if len(payload)>900_000:raise StateError('Encrypted checkpoint exceeds safe GitHub Contents limit; secure archival is required')
        return payload

    def decrypt(self,payload):
        try:
            blob=json.loads(payload)
            if blob['version']!=1:raise ValueError()
            nonce=base64.b64decode(blob['nonce'],validate=True)
            cipher=base64.b64decode(blob['ciphertext'],validate=True)
            data=AESGCM(self.key).decrypt(nonce,cipher,self.aad)
            decompressor=zlib.decompressobj()
            raw=decompressor.decompress(data,5_000_001)
            if len(raw)>5_000_000 or not decompressor.eof:raise ValueError()
            out=json.loads(raw)
            if not isinstance(out,dict):raise ValueError()
            return out
        except Exception:raise StateError('Encrypted state failed authentication or decoding; refusing reset') from None

    def read(self,commit=None):
        self.verify_private()
        suffix=''
        if commit:
            if not re.fullmatch('[0-9a-f]{40}',commit):raise StateError('Restore requires an exact commit SHA')
            suffix='?ref='+commit
        response=self.transport('GET','/contents/'+self.path+suffix)
        if response.get('_not_found'):raise StateError('Private state missing; explicit initialization/restore is required')
        try:payload=base64.b64decode(response['content'])
        except Exception:raise StateError('Private state content invalid') from None
        state=self.decrypt(payload)
        if not commit:
            self.sha=response['sha'];self.previous=payload;self.digest=hashlib.sha256(canonical(stable_state(state))).hexdigest()
        return state

    def initialize(self,state):
        self.verify_private()
        response=self.transport('GET','/contents/'+self.path)
        if not response.get('_not_found'):raise StateError('Private state already exists; initialization refused')
        payload=self.encrypt(stable_state(state))
        reply=self.transport('PUT','/contents/'+self.path,dict(message='Initialize encrypted bot state',content=base64.b64encode(payload).decode()))
        self.sha=reply['content']['sha'];self.previous=payload;self.digest=hashlib.sha256(canonical(stable_state(state))).hexdigest()

    def commit(self,state):
        stable=stable_state(state);digest=hashlib.sha256(canonical(stable)).hexdigest()
        if self.digest==digest:return
        if self.sha is None:raise StateError('State must be loaded before writing')
        self.verify_private()
        payload=self.encrypt(stable)
        # Backups are immutable, encrypted, content-addressed. A racing writer
        # cannot overwrite another writer's backup or current ledger.
        backup=f'/contents/{self.environment}/backups/{self.sha}.enc'
        existing=self.transport('GET',backup)
        if existing.get('_not_found'):
            self.transport('PUT',backup,dict(message='Backup encrypted state',content=base64.b64encode(self.previous).decode()))
        try:
            reply=self.transport('PUT','/contents/'+self.path,dict(message='Checkpoint encrypted bot state',content=base64.b64encode(payload).decode(),sha=self.sha))
        except StateError:
            # A timeout after a successful PUT is ambiguous. Confirm exact state;
            # do not retry an update against a stale SHA or overwrite a competitor.
            current=self.transport('GET','/contents/'+self.path)
            if not current.get('content'):raise
            plain=self.decrypt(base64.b64decode(current['content']))
            if hashlib.sha256(canonical(stable_state(plain))).hexdigest()!=digest:raise
            reply={'content':{'sha':current['sha']}}
        self.sha=reply['content']['sha'];self.previous=payload;self.digest=digest


def atomic_local(path,state):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    temp=path.with_suffix('.tmp')
    fd=os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
    with os.fdopen(fd,'w') as f:
        json.dump(state,f,allow_nan=False);f.flush();os.fsync(f.fileno())
    os.replace(temp,path)


def state_path():
    environment=os.environ.get('STATE_ENV','prod')
    if environment not in ('test','prod'):raise StateError('Invalid state environment')
    base=Path.cwd()/'.private-state'
    base.mkdir(exist_ok=True,mode=0o700)
    parent=base/environment
    parent.mkdir(exist_ok=True,mode=0o700)
    return parent/'state.json'


@contextmanager
def session():
    # Lock BEFORE refreshing local plaintext; another process must never replace
    # a running writer's checkpoint with a stale remote download.
    path=state_path()
    with open(str(path)+'.lock','a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        store=GitHubState.from_env()
        atomic_local(path,store.read())
        yield store,str(path)


def cli():
    p=argparse.ArgumentParser()
    sub=p.add_subparsers(dest='command',required=True)
    init=sub.add_parser('initialize');init.add_argument('--confirm-empty-portfolio',action='store_true',required=True)
    restore=sub.add_parser('restore');restore.add_argument('--commit',required=True);restore.add_argument('--output',required=True)
    rollback=sub.add_parser('rollback');rollback.add_argument('--commit',required=True);rollback.add_argument('--confirm-state-rollback',action='store_true',required=True)
    args=p.parse_args();store=GitHubState.from_env()
    if args.command=='initialize':
        from .portfolio import initialize
        state={};initialize(state);store.initialize(state)
        print('Encrypted private state initialized.')
    elif args.command=='rollback':
        store.read()  # Current SHA protects against a concurrent writer.
        historical=store.read(args.commit)
        store.commit(historical)
        print('Historical encrypted state restored remotely. Reconcile transactions before restarting the scheduler.')
    else:
        target=Path(args.output).resolve()
        if '.private-state' not in target.parts:raise StateError('Restore output must be in an ignored .private-state directory')
        atomic_local(target,store.read(args.commit))
        print('Encrypted historical state restored to private local storage. Remote current state unchanged.')


if __name__=='__main__':
    try:cli()
    except StateError as e:raise SystemExit(str(e)) from None
