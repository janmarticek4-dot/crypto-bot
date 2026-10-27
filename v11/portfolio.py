"""Manual fills only; amounts are total cash debits inclusive of buy fee."""
import copy
import os
import math
import uuid
from datetime import datetime, timezone

BUY_FEE = float(os.getenv('BUY_FEE','.01'))
SELL_FEE = float(os.getenv('SELL_FEE','.01'))
if not (0 <= BUY_FEE < 1 and 0 <= SELL_FEE < 1):
    raise ValueError('Poplatky musia byť v [0,1).')


def initialize(state):
    return state.setdefault('portfolio_v11', dict(initial_cash=8500., cash=8500.,
        additional_capital=10000., additional_active=False, transactions=[], positions={},
        realized=0., fees=0., high_water=8500., command_offset=0, pending_correction=None))


def finite_positive(s):
    x = float(s)
    if not math.isfinite(x) or x <= 0:
        raise ValueError('Hodnota musí byť kladné konečné číslo.')
    return x


def apply_fill(book, text, symbols, txid=None, timestamp=None, buy_rate=BUY_FEE, sell_rate=SELL_FEE):
    parts = text.upper().split()
    if len(parts) != 4 or parts[0] not in ('KUPIL','PREDAL'):
        raise ValueError('Formát: KUPIL SOL 105 1500 alebo PREDAL SOL 125 50% / VSETKO.')
    kind, sym, raw_price, raw_amount = parts
    if sym not in symbols:
        raise ValueError('Neznámy sledovaný symbol.')
    price = finite_positive(raw_price)
    pos = book['positions'].get(sym, dict(qty=0., cost=0.))
    if kind == 'KUPIL':
        debit = finite_positive(raw_amount)
        if debit > book['cash']+1e-8:
            raise ValueError('Nedostatok hotovosti; dodatočný kapitál nie je aktivovaný.')
        notional = debit/(1+buy_rate)
        qty, fee = notional/price, debit-notional
        new_pos = dict(qty=pos['qty']+qty, cost=pos['cost']+debit)
        cash_delta, realized = -debit, 0.
    else:
        fraction = 1. if raw_amount == 'VSETKO' else finite_positive(raw_amount[:-1])/100 if raw_amount.endswith('%') else None
        if fraction is None or fraction > 1 or pos['qty'] <= 0:
            raise ValueError('Predaj vyžaduje vlastnenú pozíciu a VSETKO alebo 0–100%.')
        qty, removed_cost = pos['qty']*fraction, pos['cost']*fraction
        gross = qty*price
        fee = gross*sell_rate
        cash_delta, realized = gross-fee, gross-fee-removed_cost
        new_pos = dict(qty=max(0.,pos['qty']-qty), cost=max(0.,pos['cost']-removed_cost))
    tx = dict(id=txid or uuid.uuid4().hex[:12], command=text, timestamp=timestamp or datetime.now(timezone.utc).isoformat(),
              kind=kind, symbol=sym, price=price, qty=qty, fee=fee, buy_rate=buy_rate, sell_rate=sell_rate, cash_delta=cash_delta, realized=realized)
    book['positions'][sym] = new_pos
    book['cash'] += cash_delta
    book['realized'] += realized
    book['fees'] += fee
    book['transactions'].append(tx)
    return tx


def corrected(book, txid, symbols):
    txs = book['transactions']
    if not any(t['id'] == txid for t in txs):
        raise ValueError('ID transakcie neexistuje.')
    fresh = initialize({})
    for t in txs:
        if t['id'] != txid:
            apply_fill(fresh, t['command'], symbols, t['id'], t['timestamp'], t.get('buy_rate',.01), t.get('sell_rate',.01))
    for key in ('command_offset','additional_capital','additional_active'):
        fresh[key] = book[key]
    fresh['corrections'] = copy.deepcopy(book.get('corrections',[]))+[dict(removed=txid, at=datetime.now(timezone.utc).isoformat())]
    return fresh


def valuation(book, prices):
    missing = [s for s,p in book['positions'].items() if p['qty'] > 0 and prices.get(s) is None]
    if missing:
        return dict(complete=False, missing=missing, equity=None, drawdown=None)
    value = sum(p['qty']*prices.get(s,0)*(1-SELL_FEE) for s,p in book['positions'].items() if p['qty'] > 0)
    equity = book['cash']+value
    book['high_water'] = max(book['high_water'],equity)
    dd = (1-equity/book['high_water'])*100
    level = 'kritická ochrana' if dd>=20 else 'výrazné preverenie redukcie' if dd>=15 else 'preverenie rizika' if dd>=10 else 'zvýšená pozornosť' if dd>=5 else 'bežný dohľad'
    return dict(complete=True,equity=equity,drawdown=dd,exposure=value/equity if equity else 0,
                unrealized=value-sum(p['cost'] for p in book['positions'].values()), risk=level,
                ai_concentration=sum(p['qty']*prices.get(s,0)*(1-SELL_FEE) for s,p in book['positions'].items() if p['qty'] and s in ('TAO','FET','RENDER'))/equity if equity else 0)


def command(state, text, symbols):
    book = initialize(state)
    text = text.strip().upper()
    if text.startswith(('KUPIL ', 'PREDAL ')):
        tx = apply_fill(book,text,symbols)
        return f"Záznam {tx['id']} uložený. Nevykonal sa žiadny obchod. Hotovosť ${book['cash']:.2f}."
    if text == 'HOTOVOST':
        return f"Hotovosť ${book['cash']:.2f}; dodatočných $10 000 neaktivovaných."
    if text == 'HISTORIA':
        return '\n'.join(f"{t['id']} | {t['command']} | poplatok ${t['fee']:.2f}" for t in book['transactions'][-20:]) or 'Bez transakcií.'
    if text == 'PORTFOLIO':
        lines = [f"Hotovosť ${book['cash']:.2f}; realizovaný výsledok ${book['realized']:.2f}; poplatky ${book['fees']:.2f}."]
        lines += [f"{s}: {p['qty']:.8f}, priemerný all-in náklad ${p['cost']/p['qty']:.4f}" for s,p in book['positions'].items() if p['qty']>0]
        return '\n'.join(lines)
    if text.startswith('OPRAV '):
        txid = text.split()[-1].lower()
        corrected(book,txid,symbols)  # Check replay is possible before asking confirmation.
        book['pending_correction'] = txid
        return f'Na zrušenie záznamu potvrď POTVRDIT {txid}. Potom môžeš vložiť správny obchod.'
    if text.startswith('POTVRDIT '):
        txid = text.split()[-1].lower()
        if book['pending_correction'] != txid:
            raise ValueError('Nie je pripravená táto oprava.')
        state['portfolio_v11'] = corrected(book,txid,symbols)
        return 'Záznam zrušený a celá účtovná kniha prepočítaná.'
    raise ValueError('Príkazy: KUPIL, PREDAL, PORTFOLIO, HOTOVOST, HISTORIA, OPRAV ID, POTVRDIT ID.')
