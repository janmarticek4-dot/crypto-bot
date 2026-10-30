"""Single owner-only poller; no exchange API, public output or artifacts."""
import json
import os
from pathlib import Path
import sys
import time
import urllib.parse
import urllib.request
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from v11.advisory_portfolio import connect,validate
from v11.secure_state import StateError
from v11.telegram_inventory import process,IDS


def telegram(method,payload):
    if method not in ('getUpdates','sendMessage','answerCallbackQuery','getWebhookInfo'):raise StateError('Operation refused')
    if method in ('sendMessage','answerCallbackQuery') and os.getenv('BOT_DISABLE_TELEGRAM')=='1':raise StateError('Telegram sends disabled')
    req=urllib.request.Request('https://api.telegram.org/bot'+os.environ['TELEGRAM_TOKEN']+'/'+method,
        data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'})
    try:
        with urllib.request.urlopen(req,timeout=20) as r:value=json.load(r)
        if not value.get('ok'):raise ValueError()
        return value
    except Exception:raise StateError('Telegram operation unavailable; details suppressed') from None


def public_json(path):
    try:
        req=urllib.request.Request('https://api.coingecko.com/api/v3/'+path,headers={'User-Agent':'crypto-bot-inventory/1.0'})
        with urllib.request.urlopen(req,timeout=15) as r:
            raw=r.read(2_000_001)
        if len(raw)>2_000_000:raise ValueError()
        return json.loads(raw)
    except Exception:raise StateError('Public asset lookup unavailable') from None


def resolve(symbol):
    result=public_json('search?query='+urllib.parse.quote(symbol))
    matches=[c for c in result.get('coins',[]) if c.get('symbol','').upper()==symbol and isinstance(c.get('id'),str) and __import__('re').fullmatch('[a-z0-9-]{1,100}',c['id'])]
    if len(matches)>50:raise StateError('Asset identity too ambiguous')
    rows=[]
    for c in matches:
        # One batched price lookup, never N HTTP calls for ambiguous tickers.
        rows.append(dict(id=c['id'],symbol=symbol,price_available=False))
    if rows:
        try:
            prices=public_json('simple/price?'+urllib.parse.urlencode({'ids':','.join(r['id'] for r in rows),'vs_currencies':'usd','include_last_updated_at':'true'}))
            for row in rows:
                q=prices.get(row['id'],{});row['price_available']=valid_quote(q)
        except StateError:pass  # verified identity, clearly labelled no current price
    return rows


def valid_quote(q):
    from v11.telegram_inventory import dec
    try:return dec(q['usd'])>0 and 0<=time.time()-q['last_updated_at']<=900
    except (ValueError,KeyError,TypeError):return False


def quotes(state):
    assets=state.get('telegram_inventory',{}).get('assets',{})
    mapping={p['symbol']:assets.get(p['symbol'],{}).get('id',IDS.get(p['symbol'])) for p in state['advisory_portfolio']['positions']}
    mapping={s:i for s,i in mapping.items() if i}
    if not mapping:return {}
    try:
        prices=public_json('simple/price?'+urllib.parse.urlencode({'ids':','.join(mapping.values()),'vs_currencies':'usd','include_last_updated_at':'true'}))
        return {s:str(prices[i]['usd']) for s,i in mapping.items() if valid_quote(prices.get(i,{}))}
    except StateError:return {}


def run():
    # Fail closed before consuming Telegram updates. Explicit owner ID required.
    for key in ('TELEGRAM_TOKEN','TELEGRAM_CHAT_ID','ADVISORY_TELEGRAM_USER_ID'):
        if not os.environ.get(key):raise StateError('Owner Telegram configuration missing')
    client=connect();state=client.read();validate(state.get('advisory_portfolio'))
    if telegram('getWebhookInfo',{}).get('result',{}).get('url'):raise StateError('Existing webhook; polling refused, webhook unchanged')
    offset=state.get('telegram_inventory',{}).get('offset',state.get('telegram_update_offset',0))
    result=telegram('getUpdates',dict(offset=offset,timeout=0,limit=100,allowed_updates=['message','callback_query']))
    for update in sorted(result.get('result',[]),key=lambda u:u['update_id']):
        # No unauthorized quote/resolver calls; all authorization in pure processor.
        reply=process(state,update,os.environ['TELEGRAM_CHAT_ID'],os.environ['ADVISORY_TELEGRAM_USER_ID'],int(time.time()),resolve)
        client.commit(state)  # CAS + encrypted backup BEFORE confirmation/ack.
        if update.get('callback_query') and reply:
            telegram('answerCallbackQuery',{'callback_query_id':update['callback_query']['id']})
        if reply:
            if update.get('message',{}).get('text','').strip()=='/portfolio':
                from v11.telegram_inventory import portfolio_text
                reply={'text':portfolio_text(state,quotes(state))}
            # Atomic portfolio writes are NOT repeated if Telegram acknowledgement fails.
            text=reply.pop('text')
            if len(text)>3900:text=text[:3800]+'\nVýpis skrátený; ďalšie údaje v súkromnej evidencii.'
            telegram('sendMessage',dict(chat_id=os.environ['TELEGRAM_CHAT_ID'],text=text,**reply))
    print('Private inventory polling completed; values suppressed.')


if __name__=='__main__':
    try:run()
    except Exception:
        print('Private inventory processing unavailable; details suppressed.',file=sys.stderr)
        raise SystemExit(1)
