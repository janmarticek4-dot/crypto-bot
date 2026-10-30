"""Owner-declared inventory, no orders. Pure transitions; caller persists by AES-GCM CAS.

Decimal strings preserve quantities; one inventory remains advisory_portfolio.
Pending confirmations and Telegram offsets live in the SAME encrypted checkpoint.
"""
import copy
import hashlib
import re
import secrets
from decimal import Decimal, InvalidOperation, localcontext
from .advisory_portfolio import validate
from .secure_state import StateError

IDS = {'SOL':'solana','TAO':'bittensor','FET':'fetch-ai',
       'AAVE':'aave','ONDO':'ondo-finance','RENDER':'render-token','BTC':'bitcoin','ETH':'ethereum'}
HELP = ('Evidencia ručných obchodov — žiadne objednávky.\n/portfolio\n'
        '/kupil SOL 500 USD cena 100 [poplatok 5]\n'
        '/kupil FET 1000 cena 0.18 [poplatok 1]\n'
        '/kupil SOL 505 USD celkom cena 100 poplatok 5\n'
        '/predal TAO | /predal SOL TAO\n/predal TAO 0.5 [cena 250] [poplatok 1]\n'
        '/predal TAO 300 USD cena 250 [poplatok 3]\n/hotovost 8500 USD\n/token SUI sui (výber identity)\n'
        'Zmenu vykoná až POTVRDIŤ (platnosť 30 min). Neznámy poplatok sa neodhaduje.\n'
        'Hotovosť je samostatná deklarácia; po obchode ju potvrď znova. '
        'Odpoveď pri plánovanom pollingu zvyčajne až pri ďalšom behu; čas nie je garantovaný.')


def dec(value, zero=False):
    try:
        if isinstance(value,bool):raise ValueError()
        d=Decimal(str(value).replace(',','.'))
        if not d.is_finite() or d<0 or (d==0 and not zero) or d.adjusted()>18 or d.as_tuple().exponent < -80:raise ValueError()
        return d
    except (InvalidOperation,ValueError,TypeError):raise ValueError('Neplatné číslo (najviac 80 desatinných miest).') from None


def fmt(d):
    return format(d,'f')


def book_hash(book):
    import json
    return hashlib.sha256(json.dumps(book,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def parse(text):
    words=text.strip().split()
    if not words or len(text)>1000:raise ValueError('Použi /pomoc.')
    op=words.pop(0).lower()
    if '@' in op:raise ValueError('Použi príkaz v súkromnom chate bez @mena.')
    if op in ('/pomoc','/portfolio') and not words:return {'op':op[1:]}
    if op=='/hotovost' and len(words)==2 and words[1].upper()=='USD':return {'op':'cash','cash':fmt(dec(words[0],True))}
    if op not in ('/kupil','/predal') or not words:raise ValueError('Použi /pomoc.')
    # Multiple tickers only means full close, never a quantity guess.
    if op=='/predal' and all(re.fullmatch('[A-Za-z][A-Za-z0-9.-]{0,19}',w) and w.lower() not in ('usd','cena','poplatok') for w in words):
        symbols=[w.upper() for w in words]
        if len(set(symbols))!=len(symbols) or len(symbols)>20:raise ValueError('Neplatný zoznam mincí.')
        return {'op':'sell_all','symbols':symbols}
    symbol=words.pop(0).upper()
    if not re.fullmatch('[A-Z][A-Z0-9.-]{0,19}',symbol) or not words:raise ValueError('Neplatný ticker alebo množstvo.')
    amount=fmt(dec(words.pop(0)));usd=False;total=False;price=None;fee=None
    if words and words[0].upper()=='USD':usd=True;words.pop(0)
    if words and words[0].lower()=='celkom':total=True;words.pop(0)
    while words:
        key=words.pop(0).lower()
        if not words or key not in ('cena','poplatok'):raise ValueError('Použi cena a voliteľne poplatok v USD.')
        val=fmt(dec(words.pop(0),key=='poplatok'))
        if key=='cena':
            if price is not None:raise ValueError('Duplicitná cena.')
            price=val
        else:
            if fee is not None:raise ValueError('Duplicitný poplatok.')
            fee=val
    if (usd or op=='/kupil') and price is None:raise ValueError('Doplň realizačnú cenu: cena 100. Trhovú cenu nedosadzujem.')
    if total and (not usd or op!='/kupil' or fee is None):raise ValueError('Celkový výdavok vyžaduje nákup v USD a skutočný poplatok.')
    return dict(op='buy' if op=='/kupil' else 'sell',symbol=symbol,amount=amount,usd=usd,total=total,price=price,fee=fee)


def transition(state,order,now):
    """Return proposed inventory + transaction; NEVER change supplied state."""
    with localcontext() as ctx:
        ctx.prec=60
        book=copy.deepcopy(validate(state['advisory_portfolio']))
        rows={p['symbol']:p for p in book['positions']};op=order['op'];tx=dict(order,at=now)
        if op=='cash':book['cash']=order['cash'];return book,tx
        symbols=order['symbols'] if op=='sell_all' else [order['symbol']]
        details=[]
        for symbol in symbols:
            old=rows.get(symbol)
            if old and old['currency']!='USD':raise ValueError('EUR pozíciu nemožno meniť USD obchodom bez potvrdenej konverzie.')
            if op!='buy' and old is None:raise ValueError('Predaj vyžaduje evidovanú pozíciu.')
            if old and old['quantity'] is None:raise ValueError('Najprv doplň skutočné množstvo pozície; nevypočítavam ho z odhadu.')
            oldqty=dec(old['quantity']) if old else Decimal(0)
            price=dec(order['price']) if order.get('price') else None
            fee=dec(order['fee'],True) if order.get('fee') is not None else None
            if op=='sell_all':qty=oldqty;gross=None;net=None
            else:
                amount=dec(order['amount'])
                if order['usd']:
                    gross=amount-fee if order['total'] else amount
                    if gross<=0:raise ValueError('Poplatok musí byť menší než celkový výdavok.')
                    qty=gross/price
                else:qty=amount;gross=qty*price if price is not None else None
                net=(gross+fee if op=='buy' else gross-fee) if gross is not None and fee is not None else None
                if net is not None and net<0:raise ValueError('Poplatok prevyšuje hrubú hodnotu.')
            remaining=oldqty+qty if op=='buy' else oldqty-qty
            if remaining<0:raise ValueError('Nemožno predať viac, než je evidované.')
            if op=='buy':
                # Unknown paid fees => unknown all-in basis, never fabricate 1%.
                cost=(dec(old['average_cost'])*oldqty if old and old['average_cost'] is not None else Decimal(0) if not old else None)
                average=fmt((cost+net)/remaining) if cost is not None and net is not None else None
                rows[symbol]=dict(symbol=symbol,quantity=fmt(remaining),average_cost=average,currency='USD')
            elif remaining==0:rows.pop(symbol)
            else:rows[symbol]=dict(old,quantity=fmt(remaining))
            details.append(dict(symbol=symbol,quantity=fmt(qty),price=fmt(price) if price else None,
                                gross=fmt(gross) if gross is not None else None,fee=fmt(fee) if fee is not None else None,
                                net=fmt(net) if net is not None else None,remaining=fmt(remaining)))
        book['positions']=list(rows.values());validate(book);tx['details']=details
        return book,tx


def proposal_text(book,tx):
    if tx['op']=='cash':return 'Nastaviť deklarovanú hotovosť '+book['cash']+' USD?'
    lines=['Potvrď iba evidenciu už vykonaného obchodu (žiadna objednávka):']
    for d in tx['details']:
        lines.append(f"{d['symbol']}: {'nákup' if tx['op']=='buy' else 'predaj'} {d['quantity']}; cena {d['price'] or 'nezadaná'} USD; hrubá hodnota {d['gross'] or 'neznáma'} USD; poplatok {d['fee'] if d['fee'] is not None else 'nezadaný'}; čistý {'výdavok' if tx['op']=='buy' else 'príjem'} {d['net'] or 'neúplný'} USD; zostane {d['remaining']}.")
    lines.append('Hotovosť sa nemení automaticky. Neznámy poplatok znamená neúplný čistý výsledok/náklad.')
    return '\n'.join(lines)


def portfolio_text(state,quotes=None):
    book=validate(state['advisory_portfolio']);quotes=quotes or {};lines=['SÚKROMNÉ PORTFÓLIO — evidencia, nie účet eToro'];total=Decimal(0);complete=True
    with localcontext() as ctx:
        ctx.prec=60
        for p in book['positions']:
            q=p['quantity'];avg=p['average_cost'];value=None;gain=None
            if q is not None and quotes.get(p['symbol']) is not None:
                value=dec(q)*dec(quotes[p['symbol']]);total+=value
                if avg is not None and p['currency']=='USD':gain=value-dec(q)*dec(avg)
            else:complete=False
            lines.append(f"{p['symbol']}: {q or 'neznáme'} ks; priemer {avg or 'neúplný'} {p['currency']}; hodnota {format(value,'.2f') if value is not None else 'nedostupná'} USD; P/L {format(gain,'+.2f') if gain is not None else 'neúplné'} USD.")
    if not book['positions']:lines.append('Žiadne aktívne pozície.')
    lines.append('Trhová hodnota '+(format(total,'.2f')+' USD' if complete else 'neúplná; známa časť '+format(total,'.2f')+' USD')+'.')
    lines.append('Deklarovaná hotovosť: '+(str(book['cash'])+' USD' if book['cash'] is not None else 'nezadaná')+(' (po obchode aktualizuj)' if state.get('telegram_inventory',{}).get('cash_needs_review') else ''))
    lines.append('P/L pred budúcimi predajnými nákladmi; priemer je all-in iba pri potvrdených nákladoch.')
    return '\n'.join(lines)


def authorized(message,chat_id,user_id):
    chat=message.get('chat',{});sender=message.get('from',{})
    return bool(user_id and chat_id and chat.get('type')=='private' and not sender.get('is_bot') and
                str(chat.get('id'))==str(chat_id) and str(sender.get('id'))==str(user_id))


def process(state,update,chat_id,user_id,now,resolver=None,quotes=None):
    """Returns reply with optional buttons. Caller commits BEFORE any reply.

    A crash after commit can lose an acknowledgement, but cannot repeat a fill.
    Confirmation binds inventory digest; external/concurrent change cancels it.
    """
    validate(state['advisory_portfolio'])
    identity=update.get('update_id')
    if type(identity) is not int or identity<0:raise ValueError('Invalid Telegram update identity')
    book=state.setdefault('telegram_inventory',dict(offset=state.get('telegram_update_offset',0),pending=None,assets={}))
    if identity<book['offset']:return None
    book['offset']=identity+1;state['telegram_update_offset']=identity+1
    cb=update.get('callback_query');msg=cb.get('message',{}) if cb else update.get('message',{})
    auth=dict(msg,**{'from':cb.get('from',{})}) if cb else msg
    if not authorized(auth,chat_id,user_id):return None
    if now-msg.get('date',0)>86400 or msg.get('date',0)>now+60:return {'text':'Správa je neaktuálna; pošli príkaz znova.'}
    # Initialization boundary also protects historical unread owner commands.
    from datetime import datetime
    boundary=state.get('inventory_start_at')
    if boundary and msg.get('date',0)<datetime.fromisoformat(boundary).timestamp():return None
    pending=book.get('pending')
    if cb:
        data=cb.get('data','')
        if not pending or now>pending['expires'] or data not in ('ok:'+pending['id'],'cancel:'+pending['id']):return {'text':'Potvrdenie neplatné alebo už použité.'}
        book['pending']=None
        if data.startswith('cancel:'):return {'text':'Zrušené. Evidencia sa nezmenila.'}
        if pending['base']!=book_hash(state['advisory_portfolio']):return {'text':'Evidencia sa medzičasom zmenila; pošli príkaz znova.'}
        order=pending['order']
        # Identity is pinned when proposed, never re-resolve ticker at confirmation.
        proposed,tx=transition(state,order,now)
        state['advisory_portfolio']=proposed;state['as_of']=__import__('datetime').datetime.fromtimestamp(now,__import__('datetime').timezone.utc).isoformat()
        history=book.setdefault('transactions',[]);history.append(dict(tx,id=pending['id']));book['transactions']=history[-1000:]
        if pending.get('asset'):book['assets'][order['symbol']]=pending['asset']
        book['cash_needs_review']=order['op']!='cash'
        return {'text':'Evidencia aktualizovaná. Žiadny obchod nebol vykonaný.\n'+portfolio_text(state,quotes)}
    try:
        text=msg.get('text','')
        selection=text.split()
        if selection and selection[0]=='/token':
            if len(selection)!=3 or not re.fullmatch('[A-Za-z][A-Za-z0-9.-]{0,19}',selection[1]) or resolver is None:raise ValueError('Použi /token SYMBOL CoinGecko-ID.')
            symbol=selection[1].upper();matches=resolver(symbol)
            chosen=[m for m in matches if m['id']==selection[2]]
            if len(chosen)!=1:raise ValueError('CoinGecko ID nezodpovedá overenému tickeru.')
            book.setdefault('selected_assets',{})[symbol]=chosen[0]
            return {'text':'Overená identita '+symbol+': '+chosen[0]['id']+'. Zopakuj /kupil; portfólio sa zatiaľ nemení.'}
        order=parse(text)
        if order['op']=='pomoc':return {'text':HELP}
        if order['op']=='portfolio':return {'text':portfolio_text(state,quotes)}
        asset=None
        if order['op']=='buy':
            symbol=order['symbol'];asset=book['assets'].get(symbol) or book.get('selected_assets',{}).get(symbol)
            if asset is None and symbol in IDS:asset=dict(id=IDS[symbol],symbol=symbol,price_available=None)
            elif asset is None:
                if resolver is None:raise ValueError('Identitu nového tokenu nemožno overiť; nákup sa nezapísal.')
                matches=resolver(symbol)
                if len(matches)!=1:
                    choices='; '.join('/token '+symbol+' '+m['id'] for m in matches[:8])
                    return {'text':('Nejednoznačný ticker; vyber overenú identitu: '+choices if matches else 'Token sa nepodarilo overiť; evidencia sa nezmenila.')}
                asset=matches[0]
        proposed,tx=transition(state,order,now)
        pid=secrets.token_hex(12)
        book['pending']=dict(id=pid,expires=now+1800,base=book_hash(state['advisory_portfolio']),order=order,asset=asset)
        text=proposal_text(proposed,tx)
        if asset:text+='\nToken: '+asset['id']+'. Cena '+('overená' if asset.get('price_available') else 'nedostupná/neoverená; automatická analytika nie je zaručená')+'.'
        return {'text':text,'reply_markup':{'inline_keyboard':[[{'text':'POTVRDIŤ','callback_data':'ok:'+pid},{'text':'ZRUŠIŤ','callback_data':'cancel:'+pid}]]}}
    except (ValueError,TypeError,KeyError,StateError):
        # Controlled validation errors contain no keys/transport payloads.
        return {'text':'Záznam odmietnutý. '+_safe_error(order if 'order' in locals() else None,msg.get('text',''),state,resolver)}


def _safe_error(order,text,state,resolver):
    try:
        order=parse(text)
        transition(state,order,0)
    except ValueError as exc:return str(exc)
    return 'Identitu tokenu nemožno jednoznačne overiť. Použi /token SYMBOL CoinGecko-ID a zopakuj nákup; /pomoc.'
