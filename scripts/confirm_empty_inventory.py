"""Explicit user correction, once only. No trading, cash assumption or Telegram."""
import os,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from v11.advisory_portfolio import connect,validate
ID='owner-declared-all-closed-v113-20261031'

def correct(state):
    validate(state['advisory_portfolio'])
    markers=state.setdefault('owner_corrections',{})
    if ID in markers:return False
    from datetime import datetime,timezone
    at=datetime.now(timezone.utc).isoformat()
    old=state['advisory_portfolio']
    state.setdefault('inventory_change_history',[]).append(dict(at=at,before=old,source=ID))
    state['advisory_portfolio']=dict(positions=[],cash=old['cash'])
    state['telegram_inventory']=dict(state.get('telegram_inventory',{}),pending=None)
    state['as_of']=at;markers[ID]=dict(at=at,source='explicit_owner_instruction_not_inferred_fill')
    return True

def run():
    if os.getenv('CONFIRM_OWNER_CLOSED_ALL')!='true':raise RuntimeError('Explicit approval missing')
    client=connect();state=client.read()
    if correct(state):client.commit(state)
    if validate(client.read()['advisory_portfolio'])['positions']:raise RuntimeError('Inventory not empty; review concurrent user changes')
    print('::notice title=Private correction::Explicit empty inventory verified; no orders, no Telegram, no cash assumption.')
if __name__=='__main__':
    try:run()
    except Exception:raise SystemExit('Private inventory correction unavailable; values suppressed.') from None
