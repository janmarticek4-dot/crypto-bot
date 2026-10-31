"""Deterministic event + observed market stress. No AI percentages or orders.

Two editorial sources are corroboration, not proven original-source independence.
Missing source freshness, unsupported entities or market data => quiet.
"""
import hashlib
import json
import re
from datetime import datetime,timezone
from urllib.parse import urlparse

TRUSTED={'coindesk.com','cointelegraph.com','reuters.com','apnews.com','theblock.co','decrypt.co'}
ENTITIES=('binance','coinbase','tether','usdt','usdc','aave','solana','bittensor','ondo','render','fetch.ai')
EVENTS={'hack':r'\b(hack(?:ed)?|exploit|security breach)\b','withdrawals':r'withdrawals? (?:suspended|halted|paused|frozen)|halts? withdrawals',
        'insolvency':r'\b(bankruptcy|insolven\w*)\b','depeg':r'\b(depeg\w*|loses? (?:its )?peg)\b'}
NEGATION=r'\b(rumou?r|unconfirmed|denies?|denied|not hacked|false report|could|might|may have|simulation|drill)\b'
MITIGATIONS={'frozen':r'freez\w*|froze\w*|frozen assets|assets frozen','covered':r'losses (?:are |were |have been )?fully covered|all losses (?:are |were )?covered|fully reimbursed|no (?:user )?losses',
             'coverage_pledged':r'to cover|will cover|plans? to cover|matching tokens|reimburse|insurance fund|safu',
             'restart_planned':r'targets?.{0,45}withdrawal restart|plans?.{0,45}resume withdrawals',
             'resumed':r'withdrawals? (?:resumed|restored|reopened)|resumes? withdrawals|all services restored'}


def evidence(news,now):
    rows=[]
    for item in news or []:
        title=str(item.get('title',''))[:500];text=title.lower();url=item.get('link','')
        try:
            host=(urlparse(url).hostname or '').removeprefix('www.')
            stamp=datetime.fromisoformat(str(item.get('pub_date','')).replace('Z','+00:00'))
            if host not in TRUSTED or not url.startswith('https://') or not 0<=(now-stamp).total_seconds()<=24*3600:continue
        except (ValueError,TypeError):continue
        if re.search(NEGATION,text):continue
        entity=next((e for e in ENTITIES if re.search(r'(?<!\w)'+re.escape(e)+r'(?!\w)',text)),None)
        if not entity:continue
        flags={k:bool(re.search(pattern,text)) for k,pattern in MITIGATIONS.items()}
        kinds=[k for k,p in EVENTS.items() if re.search(p,text)]
        rows.append(dict(entity=entity,kinds=kinds,flags=flags,domain=host,title=title,url=url,at=stamp.isoformat()))
    return rows


def assess(news,ctx,now):
    rows=evidence(news,now)
    def number(v):return type(v) in (int,float) and __import__('math').isfinite(v)
    btc=ctx.get('btc_change_24h');cap=ctx.get('global_change')
    if not number(btc) or not number(cap):return None,'market_data_missing'
    if btc>-5 or cap>-4:return None,'no_combined_market_stress'
    for entity in ENTITIES:
        group=[r for r in rows if r['entity']==entity]
        for kind in EVENTS:
            reports=[r for r in group if kind in r['kinds']]
            # Syndicated/identical headline is one item, not independent corroboration.
            if len({r['domain'] for r in reports})<2 or len({re.sub(r'\W+',' ',r['title'].lower()).strip() for r in reports})<2:continue
            flags={k:any(r['flags'][k] for r in group) for k in MITIGATIONS}
            if flags['covered'] and flags['resumed']:return None,'mitigated_losses_covered_and_withdrawals_resumed'
            # Frozen assets are a mitigation, never treated as additional losses.
            stage='insolvency' if any('insolvency' in r['kinds'] for r in group) else 'withdrawals' if any('withdrawals' in r['kinds'] for r in group) else kind
            identity=entity+':systemic-incident'
            return dict(id=hashlib.sha256(identity.encode()).hexdigest(),entity=entity,kind=kind,stage=stage,flags=flags,
                        reports=reports,new_episode=all(re.search(r'\b(another|second|new) (?:hack|breach|exploit)\b',r['title'].lower()) for r in reports),btc_change_24h=btc,cap_change_24h=cap,at=now.isoformat()),'corroborated_event_and_market_stress'
    return None,'event_not_corroborated'


def render(event):
    flags=event['flags'];notes=[]
    if flags['frozen']:notes.append('Správy uvádzajú zmrazenie aktív; ide o možnú obnovu prostriedkov, nie ďalšiu stratu.')
    if flags['covered']:notes.append('Správy uvádzajú krytie/náhradu strát; rozsah a skutočné plnenie treba potvrdiť.')
    if flags.get('coverage_pledged') and not flags['covered']:notes.append('Oznámené rezervy/plán krytia nie sú dôkaz úplnej náhrady strát; chýba overené vyčíslenie skutočne nahradených prostriedkov.')
    if flags.get('restart_planned') and not flags['resumed']:notes.append('Obnovenie výberov je zatiaľ plán, nie potvrdený výsledok.')
    if flags['resumed']:notes.append('Správy uvádzajú obnovenie výberov; pretrvávanie obmedzení treba preveriť.')
    if not notes:notes.append('Krytie strát, zmrazené aktíva a obnovenie výberov nie sú v dostupných aktuálnych podkladoch potvrdené.')
    return '\n'.join(['🚨 CRYPTO AI BOT V11.2 — MIMORIADNE RIZIKO',
        event['entity'].upper()+': viaceré redakcie hlásia '+{'hack':'bezpečnostný incident','withdrawals':'obmedzenie výberov','insolvency':'platobné problémy','depeg':'stratu naviazania'}[event['kind']]+'.',
        f"BTC {event['btc_change_24h']:+.1f}% a kapitalizácia {event['cap_change_24h']:+.1f}% za24h: už uskutočnený pohyb, nie odhad ďalšieho poklesu.",
        *notes,'Možný ďalší dopad je neistý. Vážnosť incidentu neurčuje pravdepodobnosť ďalšieho výpredaja.',
        'Prever existujúce pozície a nové riziká; nejde o automatický SELL. Bot nevykonáva obchody.'])


def run(api):
    from scripts.v111_trial import PublicJournal,send
    now=datetime.now(timezone.utc)
    journal=PublicJournal();state=journal.read()
    book=state.setdefault('risk_alerts_v112',{})
    try:news=api.get_rss_news();ctx=api.gather_market_data(api.load_state())
    except Exception:
        print('MONITOR_DIAGNOSTIC input_unavailable; no Telegram, no AI');return
    try:
        stamps=[ctx['market_global']['data']['updated_at'],ctx['btc_data']['last_updated']]
        fresh=all(type(t) in (int,float) and 0<=now.timestamp()-t<=900 for t in stamps)
    except (KeyError,TypeError):fresh=False
    if not fresh:print('MONITOR_DIAGNOSTIC stale_or_unknown_quote_time; quiet');return
    event,reason=assess(news,ctx,now)
    if not event:print('MONITOR_DIAGNOSTIC '+reason+'; quiet');return
    # Preserve old native alert continuity without treating old AI prose as evidence.
    native=api.load_state().get('crash_monitor',{})
    if native.get('last_alert_event') and event['entity'] in native['last_alert_event'].lower():
        try:recent=0<=(now-datetime.fromisoformat(native['last_alert_ts'])).total_seconds()<72*3600
        except (KeyError,ValueError,TypeError):recent=False
        if recent and event['id'] not in book:
            book[event['id']]=dict(status='legacy_notified',at=native['last_alert_ts'],stage=event['stage'])
            journal.save(state)
    old=book.get(event['id'])
    if old and old.get('status') in ('sent','legacy_notified') and event.get('new_episode'):
        try:
            boundary=datetime.fromisoformat(old['at'])
            explicit_new=(now-boundary).total_seconds()>72*3600 and all(datetime.fromisoformat(r['at'])>boundary for r in event['reports'])
            old_urls={r.get('url') for r in old.get('evidence',[])}
            if explicit_new and not old_urls.intersection(r['url'] for r in event['reports']):old=None
        except (KeyError,ValueError,TypeError):pass
    if old:
        # Ambiguous/attempting deliveries are never retried automatically.
        # Same incident stays deduplicated; a new confirmed escalation may be announced once.
        if old.get('status') in ('attempting','uncertain') or old.get('stage')==event['stage']:
            print('MONITOR_DIAGNOSTIC known_incident; quiet');return
        if {'hack':1,'depeg':1,'withdrawals':2,'insolvency':3}.get(event['stage'],0)<={'hack':1,'depeg':1,'withdrawals':2,'insolvency':3}.get(old.get('stage'),0):print('MONITOR_DIAGNOSTIC no_new_escalation; quiet');return
    if len(book)>=64:
        print('MONITOR_DIAGNOSTIC incident_ledger_capacity; review required; quiet');return
    key=event['id'];book[key]=dict(status='attempting',at=now.isoformat(),stage=event['stage'],evidence=[{k:r[k] for k in ('url','at','domain')} for r in event['reports']])
    journal.save(state)
    try:send(render(event))
    except Exception:
        book[key]['status']='uncertain';journal.save(state);raise
    book[key]['status']='sent';journal.save(state)
    print('MONITOR_DIAGNOSTIC Telegram API acknowledged alert; no orders')
