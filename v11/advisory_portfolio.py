"""User-declared private inventory for advice, never orders or inferred fills."""
import base64
import json
import math
import os
import re
from datetime import datetime,timezone
from .secure_state import GitHubState,StateError,decode_content

MARKER='PRODUCTION_ADVISORY_ONLY.json'
MARKER_VALUE={'schema':1,'purpose':'crypto-bot-private-advisory','trading_enabled':False}
ALLOWED={'SOL','TAO','ONDO','RENDER','AAVE','FET','BTC','ETH'}


def valid_number(value):
    return type(value) in (int,float) and math.isfinite(value) and value>0


def validate(value):
    if not isinstance(value,dict) or set(value)!={'positions','cash'}:raise StateError('Invalid private advisory schema')
    if value['cash'] is not None and (type(value['cash']) not in (int,float) or not math.isfinite(value['cash']) or value['cash']<0):raise StateError('Invalid declared cash')
    if not isinstance(value['positions'],list):raise StateError('Invalid declared inventory')
    seen=set()
    for row in value['positions']:
        if not isinstance(row,dict) or set(row)!={'symbol','quantity','average_cost','currency'}:raise StateError('Invalid inventory row')
        symbol=row['symbol']
        if symbol not in ALLOWED or symbol in seen:raise StateError('Invalid or duplicate inventory symbol')
        seen.add(symbol)
        if row['currency'] not in ('USD','EUR'):raise StateError('Unsupported declared currency')
        for key in ('quantity','average_cost'):
            if row[key] is not None and not valid_number(row[key]):raise StateError('Invalid declared inventory value')
    return value


def connect(env=None,transport=None):
    env=env if env is not None else os.environ
    repo=env.get('PROD_STATE_REPOSITORY','')
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/crypto-bot-state-production',repo):raise StateError('Dedicated production repository required')
    try:key=base64.b64decode(env.get('PROD_STATE_ENCRYPTION_KEY',''),validate=True)
    except Exception:raise StateError('Invalid production encryption configuration') from None
    client=GitHubState(repo,env.get('PROD_STATE_TOKEN',''),key,'prod',transport)
    client.verify_private()
    marker=client.transport('GET','/contents/'+MARKER)
    parsed=json.loads(decode_content(marker))
    if parsed!=MARKER_VALUE or parsed.get('trading_enabled') is not False or type(parsed.get('schema')) is not int:raise StateError('Production advisory marker required')
    return client


def initialize_from_secret(env=None,transport=None):
    env=env if env is not None else os.environ
    if env.get('CONFIRM_PRIVATE_IMPORT')!='true':raise StateError('Private import not confirmed')
    try:inventory=validate(json.loads(env.get('INITIAL_ADVISORY_PORTFOLIO','')))
    except Exception:raise StateError('Private inventory input invalid; values suppressed') from None
    client=connect(env,transport)
    state={'advisory_portfolio':inventory,'as_of':datetime.now(timezone.utc).isoformat(),
           'source':'user_declared_inventory_not_trade_history','trading_enabled':False,'inventory_start_at':datetime.now(timezone.utc).isoformat()}
    client.initialize(state)  # Creation only; existing private state is never replaced.
    if client.read()!=state:raise StateError('Private import verification failed')
    return True


def load(env=None,transport=None):
    value=connect(env,transport).read()
    if value.get('trading_enabled') is not False or value.get('source')!='user_declared_inventory_not_trade_history':raise StateError('Unexpected private inventory state')
    return validate(value.get('advisory_portfolio'))


def advice(inventory,snapshot):
    """Private Telegram-only text. Caller must never store it in public outputs."""
    from .strategy import decide
    out=['','SÚKROMNÉ PORTFÓLIO — údaje používateľa, iba odporúčania:']
    for position in validate(inventory)['positions']:
        symbol=position['symbol'];coin=snapshot.get('coins',{}).get(symbol,{})
        evaluation=decide(coin,held=True,approved=False,market_complete=snapshot.get('complete',False))
        if not evaluation.get('data_complete'):
            out.append(symbol+': posúdenie N/A — údaje neúplné/zastarané; neznamená potvrdené HOLD.')
            continue
        action=evaluation['action']
        reason='; '.join(evaluation['reasons'][:2]) if action in ('REDUCE','SELL') else 'Bez úplnej kombinácie support breakdownu, predajného objemu a slabého denného trendu; samotná korekcia nestačí na predaj.'
        out.append(symbol+': '+action+' (predbežné analytické odporúčanie, vykonanie je na tebe). '+reason)
        if evaluation.get('stop'):
            out.append(f"Technická ochranná hranica {evaluation['stop']:.6g} USD; uzavretie pod ňou vyžaduje preverenie, nie automatický obchod.")
        if position['quantity'] is None or position['average_cost'] is None:
            out.append('Výsledok pozície N/A — množstvo alebo priemerný all-in náklad nezadaný.')
        elif position['currency']!='USD':
            out.append('Výsledok pozície N/A — chýba overený kurz meny nákupnej evidencie.')
        else:
            gross=(coin['price']/position['average_cost']-1)*100
            out.append(f"Cena vs zadaný all-in náklad {gross:+.2f}%; nie čistý výsledok predaja. Predaj približne1% + neoverený spread.")
    if not inventory['positions']:out.append('Používateľ uviedol prázdnu evidenciu pozícií.')
    out.append('Predaj a spätný nákup len pri jasnej výhode po poplatkoch a neistote; hotovosť sa nedopĺňa predvolenou sumou.')
    return '\n'.join(out)
