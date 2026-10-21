import json
import os
import urllib.request
from datetime import datetime
from .data import COINS, PRIMARY, collect
from .portfolio import initialize, command, valuation
from .strategy import decide


def telegram_updates(api,state):
    book=initialize(state)
    if not api.TELEGRAM_TOKEN or not api.TELEGRAM_CHAT_ID:
        return
    url=f'https://api.telegram.org/bot{api.TELEGRAM_TOKEN}/getUpdates'
    req=urllib.request.Request(url,data=json.dumps(dict(offset=book['command_offset'],timeout=0,allowed_updates=['message'])).encode(),headers={'Content-Type':'application/json'})
    data=json.loads(api.http_request(req,timeout=15,retries=1))
    if not data.get('ok'):
        raise RuntimeError('Telegram getUpdates failed')
    for update in sorted(data['result'],key=lambda u:u['update_id']):
        if update['update_id'] < initialize(state)['command_offset']:
            continue
        msg=update.get('message',{})
        reply=None
        if str(msg.get('chat',{}).get('id')) == str(api.TELEGRAM_CHAT_ID):
            text=msg.get('text','').strip()
            if text:
                try:
                    reply=command(state,text,COINS)
                except (ValueError,TypeError,OverflowError) as exc:
                    reply=str(exc)
        initialize(state)['command_offset']=update['update_id']+1
        # Trade ledger and offset commit together before acknowledging a fill.
        api.save_state(state)
        if reply:
            api.telegram_send_long(reply)


def market_status(snapshot, state):
    if not snapshot['complete']:
        return dict(state='UNKNOWN',reasons=['Neúplné pokrytie; riziko nemožno znížiť.'])
    btc=snapshot['coins']['BTC']; eth=snapshot['coins']['ETH']
    bt=btc['frames']['4h']; et=eth['frames']['4h']
    weak=sum(d['frames'].get('4h',{}).get('support_broken',False) for s,d in snapshot['coins'].items() if s in PRIMARY)
    if bt['support_broken'] and et['support_broken'] and weak>=4:
        return dict(state='WARNING',reasons=['BTC/ETH a väčšina altcoinov prelomili support; nejde o predikciu percenta pádu.'])
    return dict(state='NORMAL',reasons=['V dostupných cenových dátach nie je kombinované potvrdenie krízy; udalosti nemusia byť pokryté.'])


def money(x):
    return 'N/A' if x is None else f'${x:,.2f}'


def pct(x):
    return 'N/A' if x is None else f'{x:+.1f}%'


def history(state,snapshot,evals):
    now=snapshot['at']
    items=state.setdefault('predictions_v11',[])
    for item in items:
        if item.get('outcome') is not None or now<item['due']:
            continue
        # Only closed 1H bars at the specified due time: do not substitute a
        # later quote when an Actions run is delayed.
        rows=snapshot['coins'].get(item['symbol'],{}).get('raw',{}).get('1h',[])
        candidates=[r for r in rows if item['due']*1000 <= r['timestamp']+3600000 < (item['due']+3600)*1000]
        if candidates:
            p=candidates[0]['close']
            item['outcome']=dict(price=p,return_pct=(p/item['price']-1)*100,inside=item['low']<=p<=item['high'],evaluated_at=now)
    horizons={'24h':24,'48–72h':72,'7–14 dní':336,'30 dní':720}
    for s,e in evals.items():
        for f in e['forecasts']:
            items.append(dict(symbol=s,at=now,due=now+horizons[f['horizon']]*3600,horizon=f['horizon'],price=snapshot['coins'][s]['price'],low=f['low'],high=f['high'],action=e['action'],outcome=None))
    state['predictions_v11']=items[-3000:]


def run_analysis(api, reason, slot=None):
    from .reporting import require_live_snapshot
    require_live_snapshot({})
    state=api.load_state();book=initialize(state)
    from .delivery import already_attempted, send_once
    if slot and (state.get('last_main_slot')==slot or already_attempted(state,slot)):
        return
    snap=collect(api,full=True)
    from .reporting import require_live_snapshot
    require_live_snapshot(snap)
    safety=market_status(snap,state)
    approved=set(x.strip().upper() for x in os.getenv('ETORO_VERIFIED_SYMBOLS','').split(',') if x.strip())
    evals={}
    for s in COINS:
        sales=[t for t in book['transactions'] if t['symbol']==s and t['kind']=='PREDAL']
        evals[s]=decide(snap['coins'][s],held=book['positions'].get(s,{}).get('qty',0)>0,sold=sales[-1]['price'] if sales else None,market_complete=snap['complete'],risk_normal=safety['state']=='NORMAL',approved=s in approved)
    from .fundamentals import collect as collect_fundamentals
    fundamentals=collect_fundamentals(state)
    from .macro_context import collect as collect_macro
    macro_context=collect_macro(state)
    fundamentals=dict(fundamentals,macro_context=macro_context)
    from .briefing import build, evaluate, remember
    evaluate(state,snap)
    from .event_ledger import update as update_events
    update_events(state,fundamentals.get('events',[]),snap)
    from .ai import explain
    val=valuation(book,{s:d['price'] if not d['stale'] else None for s,d in snap['coins'].items()})
    if val['complete'] and (val['drawdown']>=20 or (val['drawdown']>=15 and safety['state']=='WARNING')):
        for s,e in evals.items():
            if e['held'] and e['data_complete']:
                e.update(action='REDUCE',sale_kind='ochranný')
                e['reasons'].append('Portfólio prekročilo ochranný prah drawdownu; ochranné opatrenie, nie garancia limitu straty.')
    incident=state.get('crash_monitor_v11',{})
    recent_incident=any(snap['at']-at<=8*3600 for at in incident.get('sent',{}).values())
    if val['complete'] and val['drawdown']>=20 and safety['state']=='WARNING' and recent_incident and len(incident.get('sources',[]))>=2:
        for e in evals.values():
            if e['held'] and e['data_complete']:
                e.update(action='SELL',sale_kind='ochranný')
                e['reasons'].append('Kritický drawdown, široké cenové oslabenie a nedávny incident z dvoch zdrojov: posúď úplné ochranné uzavretie ručne.')
    previous=state.get('recommendations_v11',{})
    ai=explain(api,state,evals)
    for symbol,reasons in ai.get('selections',{}).items():
        if symbol in evals:evals[symbol]['display_reasons']=reasons
    lines=build(snap,evals,book,safety,fundamentals,state,slot,api.now_local())
    message='\n'.join(lines)
    if not send_once(api,state,message,slot or 'manual:'+api.iso_now()):
        return
    remember(state,snap,evals,slot)
    state['recommendations_v11']={s:dict(action=e['action'],price=snap['coins'][s]['price'],at=snap['at']) if e['data_complete'] else previous.get(s,dict(action='WAIT',price=None,at=snap['at'])) for s,e in evals.items()}
    state['snapshots_v11']={s:{k:d.get(k) for k in ('market_cap','volume_24h','circulating_supply')} for s,d in snap['coins'].items()}
    rec_history=state.setdefault('recommendation_history_v11',[])
    for s,e in evals.items():
        rec_history.append(dict(symbol=s,at=snap['at'],price=snap['coins'][s]['price'],action=e['action'],reasons=e['reasons']))
        if e['action'] in ('SELL','REDUCE') and e['data_complete']:
            state.setdefault('sale_recommendations_v11',{})[s]=dict(price=snap['coins'][s]['price'],at=snap['at'],action=e['action'])
    state['recommendation_history_v11']=rec_history[-2000:]
    state['fundamental_seen_v11']={s:[e['id'] for e in fundamentals.get('events',[]) if e.get('symbol')==s] for s in PRIMARY}
    state['fundamental_metrics_v11']=fundamentals.get('metrics',{})
    state['global_previous_v11']=snap.get('global_data',{})
    state['market_v11']=safety
    state['last_run']=api.iso_now();state['bot_version']='11.1'
    if slot and reason!='MANUAL':state['last_main_slot']=slot
    api.save_state(state)
    print('V11 analysis delivered and state saved.')


def run_outlook(api,slot):
    from us_context.report import run
    return run(api,slot)


def run_monitor(api):
    """No routine AI calls. Two real independent headlines + market stress.

    This is a conservative risk scenario, never a calibrated crash probability.
    Unknown data and isolated technical weakness cannot generate an alert.
    """
    import hashlib
    import re
    from urllib.parse import urlparse
    state=api.load_state()
    monitor=state.setdefault('crash_monitor_v11',{})
    snap=collect(api,full=False)
    news=api._crisis_news_candidates(api.get_rss_news())
    btc=snap['coins']['BTC']['change_24h'];eth=snap['coins']['ETH']['change_24h']
    stress=snap['complete'] and btc is not None and eth is not None and btc<=-5 and eth<=-5
    matched=[]
    major=('binance','coinbase','tether','usdt','usdc')
    categories=(('hack','hacked','security breach'),('depeg','loses its peg'),('bankruptcy','insolvent','insolvency'),('withdrawals suspended','withdrawals halted','frozen withdrawals'))
    for entity in major:
        for terms in categories:
            candidates=[n for n in news if entity in n['title'].lower() and any(t in n['title'].lower() for t in terms) and not any(x in n['title'].lower() for x in ('denies','denied','rumor','rumour','not hacked','not suspended','no hack','false report'))]
            domains={urlparse(n['link']).hostname.removeprefix('www.') for n in candidates if n['link'].startswith('https://') and urlparse(n['link']).hostname}
            if len(domains)>=2:
                matched=candidates;break
        if matched:break
    now=snap['at']
    fingerprint=hashlib.sha256((entity+terms[0]).encode()).hexdigest() if matched else None
    sent=monitor.setdefault('sent',{})
    monitor['checked_at']=now;monitor['result']='quiet'
    if stress and matched and now-sent.get(fingerprint,0)>=8*3600:
        lines=['🚨 CRYPTO BOT V11.0 — systémové riziko',api.now_local().strftime('%d.%m.%Y %H:%M Bratislava'),
               'Dva nezávislé RSS zdroje uvádzajú rovnaký typ incidentu pri významnom subjekte a BTC aj ETH klesajú najmenej o 5 % za 24h.',
               'Scenár: možný ďalší pokles trhu nad 10 %. Rozsah ani pravdepodobnosť nie sú kalibrované; nejde o pokyn na automatický predaj.',
               f'BTC {pct(btc)}; ETH {pct(eth)}.']
        lines += [f"{n['pub_date']} | {n['source']}: {n['title']} — {n['link']}" for n in matched[:4]]
        api.telegram_send_long('\n'.join(lines))
        sent[fingerprint]=now;monitor['result']='alert_sent'
        monitor['sources']=[n['link'] for n in matched]
        monitor['reason']='independent_matching_incident_and_btc_eth_stress'
    monitor['sent']={k:v for k,v in sent.items() if now-v<30*86400}
    state['last_run']=api.iso_now()
    api.save_state(state)
    print('V11 monitor:',monitor['result'])
