"""Public GET diagnostics, no state/delivery/credentials and no bot import."""
from datetime import datetime,timezone
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from us_context import report as us
from v11 import fundamentals,macro_context
from v11.state_policy import require_public_data


def run():
    now=datetime.now(timezone.utc)
    context=us.collect(us.PublicUSAPI(),now)
    ready=datetime.now(timezone.utc);us.refresh(context,ready)
    fund=fundamentals.collect({},ready);yields=macro_context.collect({},ready)
    economic=macro_context.economic_observations(ready)
    quotes={symbol:dict(kind=q['kind'],status=q['status'],price=q['price'],at=q['at'].isoformat() if q['at'] else None,source=q['source']) for symbol,q in context['quotes'].items()}
    count=sum(q['price'] is not None for q in quotes.values())
    result=dict(checked_at=ready.isoformat(),status='AVAILABLE' if count==4 else 'DEGRADED',phase=context['market']['phase'],
        quotes=quotes,sources=context['sources'],yield_context=yields,economic_observations=economic,
        fundamentals=[{key:s.get(key) for key in ('source','status','selected_source','fallback','events')} for s in fund['sources']],
        coverage_complete=False,telegram_sent=False,production_state_read=False,
        note='Reachability/format is not complete fundamentals or forecast validation. Dates alone do not establish an event hour.')
    require_public_data(result)
    output=Path('us-source-diagnostics');output.mkdir(exist_ok=True)
    (output/'report.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    status='notice' if count==4 else 'warning'
    print(f"::{status}::US_QUOTES_AVAILABLE={count}/4; YIELDS_AVAILABLE={bool(yields.get('treasury'))}; FUND_FEEDS_AVAILABLE={sum(s['status']=='OK' for s in fund['sources'])}/{len(fund['sources'])}; MACRO_OBSERVATIONS={len(economic['observations'])}/4; PHASE={context['market']['phase']}")
    return 0

if __name__=='__main__':
    try:raise SystemExit(run())
    except Exception as exc:
        print('Public source check failed: '+type(exc).__name__)
        raise SystemExit(1)
