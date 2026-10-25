"""Opt-in integration test in a dedicated PRIVATE, synthetic-only repository.

No main/state/portfolio imports, plaintext files, subprocesses, Telegram or key
creation. Only a fixed-schema aggregate report can leave this process.
"""
import base64
import concurrent.futures
import contextlib
import copy
import io
import json
import os
from pathlib import Path
import re
import sys
import threading
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from v11.secure_state import GitHubState, StateError, canonical, decode_content

ROOT=Path(__file__).resolve().parents[1]
MARKER='STATE_INTEGRATION_ONLY.json'
MARKER_DATA={'schema':1,'purpose':'crypto-bot-state-integration-only','synthetic_only':True,'allow_destructive_tests':True}
DENIED_TOKEN='invalid-synthetic-token-for-negative-access-test'
CHECK_IDS=(
 'private_dedicated_repository','encrypted_initialize_and_independent_read',
 'existing_state_not_reinitialized','encrypted_checkpoint_and_backup',
 'concurrent_writers_one_winner_one_conflict','negative_token_get_denied_live_api',
 'write_access_loss_injected_fail_closed','wrong_key_refused',
 'corruption_authentication_failure_no_reset','authenticated_backup_recovery_after_corruption',
 'recovery_stale_sha_refused','only_run_scoped_ciphertext_writes',
 'no_library_output_or_plaintext_files',
)

class Refused(RuntimeError):
    pass


def require(condition):
    if not condition:raise Refused('Integration check refused')


def configuration(env):
    require(env.get('STATE_TEST_CONFIRMED')=='true')
    repo=env.get('TEST_STATE_REPOSITORY','')
    require(bool(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*/crypto-bot-state-integration-test',repo)))
    require(repo.lower()!=env.get('GITHUB_REPOSITORY','').lower())
    token=env.get('TEST_STATE_TOKEN','')
    require(len(token)>=20)
    key=base64.b64decode(env.get('TEST_STATE_ENCRYPTION_KEY',''),validate=True)
    require(len(key)==32 and key not in (bytes(range(32)),bytes(32)))
    run_id=env.get('GITHUB_RUN_ID','');attempt=env.get('GITHUB_RUN_ATTEMPT','')
    require(bool(re.fullmatch('[0-9]+',run_id)) and bool(re.fullmatch('[0-9]+',attempt)))
    return dict(repo=repo,token=token,key=key,namespace=f'run-{run_id}-{attempt}')


class ScopedTransport:
    """A second write barrier: cannot write another run, prod, marker or repo."""
    def __init__(self,transport,prefix,marker,calls):
        self.original=transport;self.prefix='/contents/'+prefix+'/';self.marker=marker;self.calls=calls
    def __call__(self,method,path,body=None):
        require(method in ('GET','PUT'))
        require((method=='GET' and path in ('','/contents','/contents/'+MARKER)) or
                (path.startswith(self.prefix) and '..' not in path and '?' not in path))
        if method=='PUT':
            require(path.startswith(self.prefix))
            raw=decode_content(body)
            # Includes the deliberately damaged ciphertext, but never plaintext.
            envelope=json.loads(raw)
            require(set(envelope)=={'version','nonce','ciphertext'})
            require(self.marker.encode() not in raw and b'portfolio_v11' not in raw)
        self.calls.append((method,path))
        return self.original(method,path,body)


def exercise(config, client_factory=GitHubState, checks=None):
    """Return only fixed check IDs/booleans. Callers must suppress library output."""
    checks=checks if checks is not None else {};calls=[]
    canary='SYNTHETIC-NOT-AN-INVESTMENT-'+config['namespace']
    def make(token=None,key=None):
        client=client_factory(config['repo'],token or config['token'],key or config['key'],
                              'test',namespace=config['namespace'])
        client.transport=ScopedTransport(client.transport,client.prefix,canary,calls)
        return client
    client=make()
    meta=client.transport('GET','')
    require(meta.get('private') is True and not meta.get('archived') and not meta.get('disabled'))
    require(meta.get('full_name','').lower()==config['repo'].lower())
    marker=client.transport('GET','/contents/'+MARKER)
    marker_data=json.loads(decode_content(marker))
    require(marker_data==MARKER_DATA and type(marker_data.get('schema')) is int
            and marker_data.get('synthetic_only') is True and marker_data.get('allow_destructive_tests') is True)
    root=client.transport('GET','/contents')
    require(isinstance(root,list) and all(x.get('name') in (MARKER,'README.md','LICENSE','.gitignore','test') for x in root))
    checks['private_dedicated_repository']=True

    fixture={'synthetic_only':True,'privacy_canary':canary,'revision':1,
             'portfolio_v11':{'cash':123.45,'positions':{'SOL':{'qty':2.,'cost':20.}},
                             'transactions':[{'kind':'SYNTHETIC_FIXTURE','price':10.,'qty':2.}]}}
    client.initialize(fixture)
    backup_sha=client.sha
    raw=decode_content(client.transport('GET','/contents/'+client.path))
    require(canary.encode() not in raw and b'portfolio_v11' not in raw)
    require(make().read()==fixture)
    checks['encrypted_initialize_and_independent_read']=True
    writes=sum(m=='PUT' for m,p in calls)
    try:client.initialize(fixture)
    except StateError as exc:require(str(exc)=='Private state already exists; initialization refused')
    else:raise Refused()
    require(writes==sum(m=='PUT' for m,p in calls))
    checks['existing_state_not_reinitialized']=True

    second=copy.deepcopy(fixture);second['revision']=2
    client.commit(second)
    require(make().read()==second and client.read_backup(backup_sha)==fixture)
    checks['encrypted_checkpoint_and_backup']=True

    # Pre-create the common immutable backup so the race targets state CAS,
    # rather than two contenders trying to create the backup at once.
    backup_path=f'/contents/{client.prefix}/backups/{client.sha}.enc'
    client.transport('PUT',backup_path,dict(message='Synthetic integration race backup',
        content=base64.b64encode(client.previous).decode()))
    writers=[make(),make()]
    for writer in writers:require(writer.read()==second)
    barrier=threading.Barrier(2)
    def race(pair):
        i,writer=pair;value=copy.deepcopy(second);value['revision']=3+i
        barrier.wait(timeout=10)
        try:writer.commit(value);return ('written',value)
        except StateError as exc:
            require('conflict' in str(exc).lower())
            return ('conflict',None)
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        outcomes=list(pool.map(race,enumerate(writers)))
    winners=[value for status,value in outcomes if status=='written']
    require(len(winners)==1 and sum(status=='conflict' for status,_ in outcomes)==1)
    require(make().read()==winners[0])
    checks['concurrent_writers_one_winner_one_conflict']=True

    # Actual HTTPS negative-auth GET, never revocation of the real test token.
    denied=make(token=DENIED_TOKEN)
    before=len(calls);denied_ok=False
    try:response=denied.transport('GET','');denied_ok=response.get('_not_found') is True
    except StateError as exc:denied_ok=bool(re.search(r'HTTP (401|403)\b',str(exc)))
    require(denied_ok and all(m=='GET' for m,p in calls[before:]))
    require(make().read()==winners[0])
    checks['negative_token_get_denied_live_api']=True

    # Access loss during write is deliberately injected; no token privileges
    # need changing and no admin permission is requested.
    no_write=make();no_write.read();original=no_write.transport
    def deny_write(method,path,body=None):
        if method=='PUT':raise StateError('Injected access denied')
        return original(method,path,body)
    no_write.transport=deny_write
    changed=copy.deepcopy(second);changed['revision']=99
    try:no_write.commit(changed)
    except StateError as exc:require(str(exc)=='Injected access denied')
    else:raise Refused()
    require(make().read()==winners[0])
    checks['write_access_loss_injected_fail_closed']=True

    # Wrong key is a transient negative fixture, never stored or displayed.
    wrong=bytes([config['key'][0]^1])+config['key'][1:]
    try:make(key=wrong).read()
    except StateError as exc:require(str(exc)=='Encrypted state failed authentication or decoding; refusing reset')
    else:raise Refused()
    checks['wrong_key_refused']=True

    # Damage only this fresh run's synthetic ciphertext, with exact current SHA.
    current=client.transport('GET','/contents/'+client.path)
    blob=json.loads(decode_content(current));cipher=bytearray(base64.b64decode(blob['ciphertext']))
    cipher[0]^=1;blob['ciphertext']=base64.b64encode(cipher).decode()
    damaged=client.transport('PUT','/contents/'+client.path,dict(message='Synthetic integration corruption fixture',
        sha=current['sha'],content=base64.b64encode(canonical(blob)).decode()))
    expected_sha=damaged['content']['sha'];writes=sum(m=='PUT' for m,p in calls)
    try:make().read()
    except StateError as exc:require(str(exc)=='Encrypted state failed authentication or decoding; refusing reset')
    else:raise Refused()
    require(writes==sum(m=='PUT' for m,p in calls))
    checks['corruption_authentication_failure_no_reset']=True
    # A stale recovery expectation must not repair/overwrite any current state.
    stale='0'*40 if expected_sha!='0'*40 else 'f'*40
    try:client.restore_backup(backup_sha,stale)
    except StateError as exc:require(str(exc)=='Recovery conflict; refusing to overwrite current state')
    else:raise Refused()
    require(writes==sum(m=='PUT' for m,p in calls))
    require(client.restore_backup(backup_sha,expected_sha)==fixture)
    require(make().read()==fixture and client.read_backup(backup_sha)==fixture)
    checks['authenticated_backup_recovery_after_corruption']=True
    checks['recovery_stale_sha_refused']=True
    checks['only_run_scoped_ciphertext_writes']=True
    return checks


def safe_report(report):
    allowed={'schema','status','synthetic_only','api_requested','checks','production_migration','failure','failure_stage'}
    if set(report)-allowed:return False
    if report.get('schema')!='state-integration-v1' or report.get('synthetic_only') is not True:return False
    if report.get('production_migration') is not False or type(report.get('api_requested')) is not bool:return False
    checks=report.get('checks')
    if not isinstance(checks,dict) or set(checks)-set(CHECK_IDS) or any(v is not True for v in checks.values()):return False
    if report.get('status')=='PASSED':return set(checks)==set(CHECK_IDS) and 'failure' not in report
    return (report.get('status')=='FAILED' and
            report.get('failure')=='Configuration or integration check failed; private details suppressed' and
            report.get('failure_stage') in (*CHECK_IDS,'configuration','output_validation'))


def run(output, env=None, client_factory=GitHubState, live_api=True):
    output=Path(output).absolute()
    if output!=ROOT/'state-integration-output' or output.is_symlink():raise Refused('Unsafe output directory')
    output.mkdir(exist_ok=True)
    # Never print errors, tracebacks, API responses, ciphertext or captured output.
    captured=io.StringIO();report={'schema':'state-integration-v1','status':'FAILED',
        'synthetic_only':True,'api_requested':live_api,'checks':{},'production_migration':False}
    config=None
    try:
        with contextlib.redirect_stdout(captured),contextlib.redirect_stderr(captured):
            config=configuration(env if env is not None else os.environ)
            exercise(config,client_factory,report['checks'])
        require(not captured.getvalue())
        report['status']='PASSED'
        report['checks']['no_library_output_or_plaintext_files']=True
    except Exception:
        report['status']='FAILED'
        report['failure']='Configuration or integration check failed; private details suppressed'
        report['failure_stage']='configuration' if config is None else next((name for name in CHECK_IDS if name not in report['checks']),'output_validation')
    if not safe_report(report):
        report={'schema':'state-integration-v1','status':'REFUSED','synthetic_only':True}
    raw=json.dumps(report,sort_keys=True,indent=2)+'\n'
    if config:
        forbidden=[config['token'],base64.b64encode(config['key']).decode(),config['key'].hex(),
                   'SYNTHETIC-NOT-AN-INVESTMENT-'+config['namespace']]
        if any(value in raw for value in forbidden):
            raw='{"schema":"state-integration-v1","status":"REFUSED","synthetic_only":true}\n'
            report['status']='REFUSED'
    path=output/'report.json'
    require(not path.is_symlink())
    path.write_text(raw)
    print('Private state integration: '+report['status'])
    return 0 if report['status']=='PASSED' else 1


if __name__=='__main__':
    try:raise SystemExit(run(ROOT/'state-integration-output'))
    except Exception:
        print('Private state integration refused; no private details logged',file=sys.stderr)
        raise SystemExit(1)
