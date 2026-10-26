"""One-time confirmed encrypted inventory import. No stdout data or artifacts."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from v11.advisory_portfolio import initialize_from_secret

if __name__=='__main__':
    try:
        initialize_from_secret()
        print('Private advisory inventory initialized and verified. No orders executed.')
    except Exception:
        print('Private inventory import refused or failed; values suppressed.',file=sys.stderr)
        raise SystemExit(1)
