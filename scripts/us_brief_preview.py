"""Read-only current US preview; no private storage, Telegram or state writes."""
import sys,json
from pathlib import Path
from datetime import datetime,timezone
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from us_context import report as us
from scripts.fundamental_sources_shadow import run as collect
from v11 import analyst,integration,event_lifecycle
from v11.us_brief import render
import main as legacy

def run():
    target=Path('shadow-output/us-brief');target.mkdir(parents=True,exist_ok=True)
    collect(target/'sources',False)
    snap=json.loads((target/'sources/market_snapshot.json').read_text())
    fund=json.loads((target/'sources/fundamentals.json').read_text())
    now=datetime.now(timezone.utc);context=us.collect(us.PublicUSAPI(),now)
    now=datetime.now(timezone.utc);us.refresh(context,now)
    fund=event_lifecycle.collect(fund,now,snap);now=datetime.now(timezone.utc)
    previous=json.loads(Path('trial-public/v111-delivery.json').read_text()).get('last_analysis_v112')
    _,quotes,ev=integration.render(legacy,snap,fund,now,'usa',integration.read_rule_state(Path('bot_state.json')),previous)
    model=analyst.prepare(snap,fund,now,quotes,ev,previous)
    from v11 import event_notices
    model['event_notices']=event_notices.plan(fund,json.loads(Path('trial-public/v111-delivery.json').read_text()),now,limit=1)
    text=render(context,model,snap,fund,now)
    (target/'USA.txt').write_text(text)
    (target/'model.json').write_text(json.dumps(model,ensure_ascii=False,allow_nan=False))
    from v11.state_policy import require_public_data
    diagnostics=dict(context=context,at=now.isoformat(),telegram_sent=False,private_loaded=False)
    require_public_data(diagnostics)
    (target/'source-diagnostics.json').write_text(json.dumps(diagnostics,ensure_ascii=False,default=lambda d:d.isoformat(),allow_nan=False))
    print(text)
    print("::notice title=USA public preview::"+json.dumps(dict(text=text),ensure_ascii=False))
    print('::notice title=US brief contract::'+json.dumps(dict(characters=len(text),urls_absent='http' not in text,telegram_sent=False,private_loaded=False,phase=context['market']['phase'])))

if __name__=='__main__':run()
