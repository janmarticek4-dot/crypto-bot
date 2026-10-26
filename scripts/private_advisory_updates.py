"""Record ONLY owner-declared inventory changes. Never execute a market order."""
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import sys
import urllib.request
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from v11.advisory_portfolio import connect,validate,ALLOWED
from v11.secure_state import StateError


def authorized(message,chat_id,user_id=None):
    chat=message.get('chat',{});sender=message.get('from',{})
    if str(chat.get('id'))!=str(chat_id) or sender.get('is_bot'):return False
    if user_id:return str(sender.get('id'))==str(user_id)
    return chat.get('type')=='private' and str(sender.get('id'))==str(chat_id)


def apply_inventory_command(state,text):
    words=text.strip().upper().split();book=validate(state['advisory_portfolio'])
    if words==['POZICIE']:
        return '\n'.join(f"{p['symbol']}: množstvo {p['quantity'] if p['quantity'] is not None else 'N/A'}, priemerný all-in náklad {p['average_cost'] if p['average_cost'] is not None else 'N/A'} {p['currency']}" for p in book['positions']) or 'Súkromná evidencia je prázdna.'
    old=json.loads(json.dumps(book))
    if len(words)==5 and words[0]=='POZICIA' and words[1] in ALLOWED:
        row={'symbol':words[1],'quantity':None if words[2]=='?' else float(words[2]),
             'average_cost':None if words[3]=='?' else float(words[3]),'currency':words[4]}
        candidate={'positions':[p for p in book['positions'] if p['symbol']!=row['symbol']]+[row],'cash':book['cash']}
        validate(candidate);state['advisory_portfolio']=candidate
    elif len(words)==2 and words[0]=='UZAVRETA' and words[1] in ALLOWED:
        state['advisory_portfolio']={'positions':[p for p in book['positions'] if p['symbol']!=words[1]],'cash':book['cash']}
    else:raise ValueError('Formát: POZICIA SYMBOL mnozstvo priemerny_all_in_naklad USD/EUR; ? = neznáme. UZAVRETA SYMBOL alebo POZICIE. Ide iba o evidenciu, nie objednávku.')
    state['as_of']=datetime.now(timezone.utc).isoformat()
    history=state.setdefault('inventory_change_history',[])
    history.append({'at':state['as_of'],'before':old,'after':state['advisory_portfolio'],'source':'user_declared_change_not_order'})
    state['inventory_change_history']=history[-100:]
    return 'Súkromná evidencia aktualizovaná. Žiadny obchod nebol vykonaný.'


def telegram(method,payload):
    if method not in ('getUpdates','sendMessage'):raise StateError('Telegram operation refused')
    req=urllib.request.Request('https://api.telegram.org/bot'+os.environ['TELEGRAM_TOKEN']+'/'+method,
        data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=20) as r:
        value=json.load(r)
    if not value.get('ok'):raise StateError('Telegram request failed')
    return value


def run():
    if not os.environ.get('PROD_STATE_TOKEN') or not os.environ.get('PROD_STATE_ENCRYPTION_KEY') or not os.environ.get('PROD_STATE_REPOSITORY'):return 0
    client=connect()
    try:state=client.read()
    except StateError as exc:
        if str(exc)=='Private state missing; explicit initialization/restore is required':
            print('Private advisory inventory awaits explicit initialization.')
            return 0
        raise
    validate(state.get('advisory_portfolio'))
    result=telegram('getUpdates',{'offset':state.get('telegram_update_offset',0),'timeout':0,'allowed_updates':['message']})
    for update in sorted(result.get('result',[]),key=lambda row:row['update_id']):
        identity=update['update_id']
        if identity<state.get('telegram_update_offset',0):continue
        message=update.get('message',{});text=message.get('text','').strip();reply=None
        boundary=datetime.fromisoformat(state.get('inventory_start_at') or state.get('as_of','1970-01-01T00:00:00+00:00')).timestamp()
        if message.get('date',0)>=boundary and authorized(message,os.environ['TELEGRAM_CHAT_ID'],os.getenv('ADVISORY_TELEGRAM_USER_ID')):
            if text.upper().split()[:1] in (['POZICIA'],['UZAVRETA'],['POZICIE']):
                try:reply=apply_inventory_command(state,text)
                except (ValueError,TypeError,StateError):reply='Záznam odmietnutý: skontroluj formát a konečné kladné čísla; žiadny obchod nebol vykonaný.'
        state['telegram_update_offset']=identity+1
        client.commit(state)  # Encrypted state and offset durable BEFORE acknowledgement.
        if reply:telegram('sendMessage',{'chat_id':os.environ['TELEGRAM_CHAT_ID'],'text':reply})
    return 0


if __name__=='__main__':
    try:raise SystemExit(run())
    except Exception:
        print('Private advisory update unavailable; details suppressed.',file=sys.stderr)
        raise SystemExit(1)
