"""At-most-once attempt journal. Telegram has no idempotency key.

An uncertain delivery is held for review rather than automatically replayed.
This trades availability for avoiding duplicate multi-part reports.
"""
import hashlib
import time


def already_attempted(state,key):
    return key in state.get('delivery_v111',{})


def send_once(api,state,message,key):
    journal=state.setdefault('delivery_v111',{})
    if key in journal:return False
    journal[key]=dict(status='sending',at=time.time(),sha256=hashlib.sha256(message.encode()).hexdigest())
    api.save_state(state)  # Durable BEFORE the non-idempotent external side effect.
    try:
        api.telegram_send_long(message)
    except Exception:
        journal[key]['status']='uncertain'
        api.save_state(state)
        raise
    journal[key]['status']='sent'
    api.save_state(state)
    return True
