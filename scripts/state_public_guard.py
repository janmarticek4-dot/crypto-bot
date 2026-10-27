"""Fail-closed state-read-only preflight. Optional schema file contains keys, no values."""
import argparse
import json
import os
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from v11.state_policy import require_public_data

def validated(path):
    path=Path(path)
    if not path.is_file() or path.stat().st_size>4_000_000:raise ValueError('State missing or oversized')
    value=json.loads(path.read_text())
    if not isinstance(value,dict) or not value:raise ValueError('State malformed or unexpectedly empty')
    require_public_data(value)
    return value

def check(path,require_schema=None,record_schema=None):
    value=validated(path)
    if require_schema:
        expected=json.loads(Path(require_schema).read_text())
        if not isinstance(expected,list) or not all(isinstance(k,str) for k in expected) or not set(expected)<=set(value):raise ValueError('Existing state sections were lost')
    if record_schema:
        target=Path(record_schema)
        if target.resolve()==Path(path).resolve():raise ValueError('Cannot write metadata over state')
        fd=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,'w') as f:json.dump(sorted(value),f)
    return True

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--path',default='bot_state.json');p.add_argument('--require-schema');p.add_argument('--record-schema');args=p.parse_args()
    try:check(args.path,args.require_schema,args.record_schema)
    except Exception:print('Public state guard: REFUSED (no data printed)');raise SystemExit(1)
    print('Public state guard: PASSED')
