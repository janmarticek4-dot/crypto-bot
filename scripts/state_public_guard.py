"""Read-only fail-closed preflight. No reset, migration, printing or writes."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from v11.state_policy import require_public_data

def check(path):
    path=Path(path)
    if not path.is_file() or path.stat().st_size>4_000_000:raise ValueError('State missing or oversized')
    value=json.loads(path.read_text())
    if not isinstance(value,dict) or not value:raise ValueError('State malformed or unexpectedly empty')
    require_public_data(value)
    return True

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--path',default='bot_state.json');args=p.parse_args()
    try:check(args.path)
    except Exception:print('Public state guard: REFUSED (no data printed)');raise SystemExit(1)
    print('Public state guard: PASSED')
