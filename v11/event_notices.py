"""Persistent, delivery-confirmed public event announcements; no network or AI.
No announcement is consumed by a preview, attempt or uncertain Telegram send.
"""
import copy,hashlib,json,re
from datetime import timedelta
from urllib.parse import urlsplit,urlunsplit
from .fundamentals import timestamp
from .fundamental_analysis import analyze
from .event_groups import same_event,tokens
from .state_policy import require_public_data
from .shadow_pair import BL

KEY='event_notifications_v1'
SEED=__import__('pathlib').Path(__file__).with_name('event_notice_seed.json')

def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
def url_key(url):
    p=urlsplit(url);return urlunsplit((p.scheme,p.netloc.lower(),p.path.rstrip('/'),'',''))
def same_notice(a,b):
    for actor in ('SEC','CFTC','Binance','Coinbase','Bybit','Kraken','OKX','Tether','Circle'):
        pattern=r'\b'+actor+r'\b'
        if bool(re.search(pattern,a.get('title',''),re.I))!=bool(re.search(pattern,b.get('title',''),re.I)):return False
    for pattern in (r'\bbitcoin\b|\bBTC\b',r'\bethereum\b|\bether\b|\bETH\b'):
        if bool(re.search(pattern,a.get('title',''),re.I))!=bool(re.search(pattern,b.get('title',''),re.I)):return False
    aa=timestamp(a.get('published_at'));bb=timestamp(b.get('published_at'))
    if not aa or not bb or abs((aa-bb).total_seconds())>72*3600:return False
    # Reuse semantic/process checks without mistaking a delayed copy for a new event.
    return same_event(a,dict(b,published_at=a['published_at']))

def macro_type(item):
    if item.get('kind')!='economic_release':return 'Fed'
    return next((x for x in ('GDP','CPI','PCE','employment') if x in item.get('categories',[])),'economic')
def release_notice(item,now):
    at=timestamp(item.get('published_at'))
    if item.get('status') not in ('RELEASED','REACTION') or not at or not timedelta(0)<=now-at<=timedelta(hours=72):return None
    url=item.get('url','')
    if not url.startswith('https://'):return None
    kind=macro_type(item);identity='macro:'+kind+':'+url_key(url)
    # Reaction timestamps/prices and reworded copies are not a new result.
    fact={'rate_range':item.get('rate_range'),'decision':re.findall(r'(?:decided|voted) to (maintain|keep|leave|lower|reduce|cut|raise|increase)',item.get('decision',''),re.I),
        'voting':re.findall(r'\d+\s*[–-]\s*\d+\s+vote',item.get('voting') or '',re.I),
        'economic_values':re.findall(r'[-+]?\d+(?:[.,]\d+)?',item.get('result_excerpt') or '')}
    from .event_lifecycle import lines
    text=lines({'event_lifecycle':{'releases':[item]}},now)
    first=text[0] if text else kind+': výsledok bezpečne neštruktúrovaný.'
    impact='Odchýlka voči vopred overenému konsenzu nepotvrdená; miernejší/prísnejší výsledok môže podporiť/brzdiť rizikové aktíva.'
    reaction=item.get('reaction',{}).get('BTC',{})
    observed=''
    if all(type(reaction.get(k)) in (int,float) and __import__('math').isfinite(reaction[k]) for k in ('before_at','after_at','change_pct')) and reaction['before_at']<=at.timestamp()*1000<reaction['after_at']<=now.timestamp()*1000:
        end=__import__('datetime').datetime.fromtimestamp(reaction['after_at']/1000,BL).strftime('%d.%m. %H:%M')
        observed=f" BTC {reaction['change_pct']:+.1f}% od hodinového uzavretia okolo výsledku do {end}; časový súbeh nie je dôkaz príčiny."
    return dict(id=identity,state='RESULT',published_at=at.isoformat(),event_at=None,semantic=digest(fact),title=first,
        categories=[kind],symbols=[],url=url,text=first+' '+impact+observed,kind='official_release',fact_parts={k:digest(v) for k,v in fact.items()})

def news_relevance(e,now):
    title=e['title'];cats=set(e['categories']);at=timestamp(e.get('published_at'))
    if not e.get('material'):return False,'LOW_MATERIALITY'
    if at and now-at>timedelta(hours=24):return False,'OLD_NEWS_WITHOUT_NEW_FACT'
    if 'hack' in cats:
        exposed=re.search(r'exchange|protocol|bridge|wallet|DeFi|withdrawal|smart contract|private key|stolen crypto|crypto funds|solana|aave|bittensor|render network|fetch.ai|coinbase|binance|bybit|kraken|OKX',title,re.I)
        if not exposed:return False,'NO_CONFIRMED_CRYPTO_EXPOSURE'
    if 'regulation' in cats and not re.search(r'approv|deni|reject|lawsuit|enforce|settlement|\bban\b|\border\b|ruling|charges|licen[cs]|legislation|sanction|new rules|court',title,re.I):return False,'COMMENTARY_NOT_REGULATORY_ACTION'
    if 'Fed' in cats and not re.search(r'speech|remarks|testimony|(?:Powell|governor|chair).*(?:says|said|warns|signals)',title,re.I):return False,'NO_NEW_PRIMARY_POLICY_FACT'
    if cats&{'CPI','PCE','GDP','employment'} and not re.search(r'\b(released|release|revised|revision|report)\b',title,re.I):return False,'ECONOMIC_COMMENTARY_NOT_NEW_RESULT'
    if 'geopolitics' in cats and (not re.search(r'attack|strike|announc|impose|escalat|sanction|tariff|conflict|war',title,re.I) or re.search(r'could|might|what if|may affect',title,re.I)):return False,'SPECULATIVE_GEOPOLITICAL_COMMENTARY'
    if cats&{'Fed','geopolitics'} and at and now-at>timedelta(hours=24):return False,'OLD_CONTEXT_WITHOUT_NEW_FACT'
    return True,None

def candidates(fund,now):
    out=[]
    for item in fund.get('event_lifecycle',{}).get('releases',[]):
        row=release_notice(item,now)
        if row:out.append(row)
    official_kinds={r['categories'][0] for r in out}
    for event in fund.get('events',[]):
        if not event.get('scheduled') or event.get('lifecycle') not in (None,'UPCOMING'):continue
        at=timestamp(event.get('event_at'));cats=set(event.get('categories',[]))&{'Fed','CPI','PCE','GDP','employment'}
        if not at or not cats or not timedelta(0)<at-now<=timedelta(hours=24):continue
        if re.search(r'metropolitan|regional|county|state employment',event.get('title',''),re.I):continue
        category=sorted(cats)[0];label={'Fed':'Fed/FOMC','CPI':'CPI USA','PCE':'PCE USA','GDP':'HDP USA','employment':'Trh práce USA'}[category]
        forecast=None
        for consensus in fund.get('extensions',{}).get('consensus',[]):
            captured=timestamp(consensus.get('forecast_captured_at'))
            if consensus.get('official_schedule')=='MATCHED' and timestamp(consensus.get('event_at'))==at and captured and captured<=now<at and re.fullmatch(r'-?\d+(?:\.\d+)?(?:%|K|M|B)?',str(consensus.get('forecast',''))):
                forecast=consensus['forecast'];break
        out.append(dict(id='scheduled:'+category+':'+at.isoformat(),state='UPCOMING',published_at=event.get('published_at'),observed_at=now.isoformat(),event_at=at.isoformat(),semantic=digest([at.isoformat(),forecast]),title=event['title'],categories=[category],symbols=[],url=event.get('url',''),kind='calendar',
            text=label+' '+at.astimezone(BL).strftime('%d.%m. %H:%M')+' Bratislava; '+('prognóza kalendára '+str(forecast)+' (Forex Factory; metodika prieskumu neoverená)' if forecast is not None else 'konsenzus neoverený')+'. Prekvapenie môže zvýšiť volatilitu BTC a altcoinov.'))
    for e in analyze(fund,now)['evidence']:
        if not news_relevance(e,now)[0]:continue
        cats=set(e['categories'])
        # Generic Fed-result copies do not re-announce an official statement.
        if 'Fed' in cats and re.search(r'leaves.*rates?|holds.*rates?|keeps.*rates?|rates?.*unchanged|fomc.*statement',e['title'],re.I):continue
        if cats&official_kinds and re.search(r'unchanged|leaves|holds|keeps|rate decision|consumer price index|gross domestic product|personal consumption expenditure',e['title'],re.I):continue
        if not cats&{'hack','regulation','geopolitics','unlock','project','CPI','PCE','GDP','employment','Fed'}:continue
        title=e['title'];symbols=e.get('symbols',[]);name='/'.join(symbols) if len(symbols)<4 else 'Kryptotrh'
        actor=next((x for x in ('SEC','CFTC','Binance','Coinbase','Bybit','Kraken','OKX') if re.search(r'\b'+x+r'\b',title,re.I)),None)
        if actor:name=actor
        summary=('Hlásený bezpečnostný incident; negatívny dopad iba po potvrdení rozsahu a expozície.' if 'hack' in cats else
            'Regulačná udalosť; účinnosť rozhodnutia a dopad treba potvrdiť.' if 'regulation' in cats else
            'Geopolitická udalosť môže zvýšiť rizikovú averziu; vplyv na krypto nie je preukázanou príčinou pohybu.' if 'geopolitics' in cats else
            'Hlásená zmena tokenovej ponuky; odomknutie nie je automatický predaj.' if 'unlock' in cats else
            'Projektová alebo ekonomická správa; ekonomický dopad zatiaľ nepotvrdený.')
        if re.search(r'ETF',title,re.I):
            asset='BTC' if re.search(r'bitcoin|\bBTC\b',title,re.I) else 'ETH' if re.search(r'ethereum|ether|\bETH\b',title,re.I) else 'krypto'
            stage='hlásené schválenie' if re.search(r'approv|passes',title,re.I) else 'hlásené zamietnutie' if re.search(r'denies|denied|reject',title,re.I) else 'nová správa'
            summary=stage+' '+asset+' ETF; primárne rozhodnutie a následné toky treba overiť.'
        elif re.search(r'tokeniz',title,re.I):summary='Správa o tokenizovaných aktívach; realizovaný objem a dopyt po tokene neoverené.'
        elif 'Fed' in cats:summary='Nové vyjadrenie Fedu; význam pre očakávania sadzieb a rizikové aktíva treba potvrdiť.'
        out.append(dict(id='news:'+e['id'],state='NEWS',published_at=e['published_at'],event_at=None,semantic=digest(sorted(tokens(title))),title=title,categories=sorted(cats),symbols=symbols,url=e['url'],kind='news',
            text=name+': '+summary+' ('+e['published_at'][:10]+', '+e['source']+').'))
    for symbol,item in fund.get('extensions',{}).get('etf_flows',{}).items():
        value=item.get('net_flow_usd');day=item.get('date');observed=timestamp(item.get('retrieved_at'))
        if symbol not in ('BTC','ETH') or type(value) not in (int,float) or not __import__('math').isfinite(value) or abs(value)<100000000 or not item.get('complete') or not item.get('reconciled') or not observed:continue
        try:age=(now.date()-__import__('datetime').date.fromisoformat(day)).days
        except (TypeError,ValueError):continue
        if not 0<=age<=5:continue
        out.append(dict(id='etf:'+symbol+':'+day,state='FLOW',published_at=None,observed_at=observed.isoformat(),event_at=None,
            semantic=digest(value),title=symbol+' spot ETF '+day,categories=['ETF'],symbols=[symbol],url=item.get('url',''),kind='flow',
            text=f'{symbol} spot ETF USA, {day}: {value/1e6:+.0f} mil. USD čistý tok podľa Farside; '+('podpora' if value>0 else 'brzda')+' rizikového apetítu, nie záruka pohybu ceny. Čas publikácie neoverený.'))
    return out

def prior_records(journal,now):
    rows=copy.deepcopy(journal.get(KEY,{}))
    try:
        seed=json.loads(SEED.read_text())
        for k,v in seed.get('records',{}).items():
            announced=timestamp(v.get('last_announced_at'))
            if announced and announced<=now:rows.setdefault(k,v)
    except (OSError,ValueError,TypeError):pass
    for bucket in ('slots','manual_slots'):
        for record in journal.get(bucket,{}).values():
            if record.get('status') not in ('attempting','uncertain'):continue
            for event in record.get('event_notifications',[]):
                if event.get('id') not in rows:rows[event['id']]=dict(event,delivery_status=record['status'])
    require_public_data(rows);return rows

def _plan(fund,journal,now,limit=3):
    previous=prior_records(journal,now);selected=[];suppressed=[dict(id=e['id'],reason=news_relevance(e,now)[1]) for e in analyze(fund,now)['evidence'] if not news_relevance(e,now)[0]]
    for row in candidates(fund,now):
        old=previous.get(row['id']);matched_copy=False
        if old is None and row['kind']=='news':
            for item in previous.values():
                if item.get('state')!='NEWS':continue
                try:
                    a=dict(row);b=dict(item)
                    # Cross-provider copies within the existing semantic grouping.
                    if same_notice(a,b):old=item;matched_copy=True;break
                except (KeyError,TypeError,ValueError):continue
        repeated=old and (old.get('semantic')==row['semantic'] or matched_copy)
        if repeated:suppressed.append(dict(id=row['id'],reason='DELIVERY_UNCERTAIN' if old.get('delivery_status') else 'ALREADY_ANNOUNCED_SAME_FACT'));continue
        at=timestamp(row['published_at'])
        if row['state']=='RESULT' and now-at>timedelta(hours=24) and old is None:
            suppressed.append(dict(id=row['id'],reason='OLD_RESULT_WITHOUT_NEW_FACT'));continue
        if old:
            changed=[k for k,v in row.get('fact_parts',{}).items() if old.get('fact_parts',{}).get(k)!=v]
            row['text']='Nová aktualizácia'+(' ('+', '.join({'rate_range':'sadzby','decision':'rozhodnutie','voting':'hlasovanie','economic_values':'ekonomický výsledok'}[k] for k in changed)+')' if changed else '')+': '+row['text']
        # Same-run provider copies are deduplicated too.
        if row['kind']=='news' and any(x['kind']=='news' and same_notice(row,x) for x in selected):continue
        selected.append(row)
    selected.sort(key=lambda r:({'RESULT':0,'NEWS':1,'FLOW':1,'UPCOMING':2}[r['state']],-(timestamp(r.get('published_at') or r.get('observed_at')).timestamp() if timestamp(r.get('published_at') or r.get('observed_at')) else 0)))
    return dict(selected=selected[:limit],suppressed=suppressed,seeded_records=len(previous),version='event-notices-v1')

def plan(fund,journal,now,limit=3):
    try:return _plan(fund,journal,now,limit)
    except (KeyError,TypeError,ValueError,AttributeError) as exc:
        return dict(selected=[],suppressed=[],error=type(exc).__name__,scope='event section suppressed; existing ledger not reset')

def commit(journal,planned,now):
    if planned.get('error'):return
    rows=prior_records(journal,now)
    for row in planned.get('selected',[]):
        stored={k:copy.deepcopy(v) for k,v in row.items() if k not in ('text','url')}
        stored['last_announced_at']=now.isoformat();rows[row['id']]=stored
    rows={k:v for k,v in rows.items() if (at:=timestamp(v.get('last_announced_at'))) and timedelta(0)<=now-at<=timedelta(days=90)}
    journal[KEY]=dict(sorted(rows.items(),key=lambda kv:kv[1]['last_announced_at'])[-256:])
    require_public_data(journal[KEY])
