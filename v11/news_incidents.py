"""Bounded incident entities, source facts and persistent delivery history.
No inference that all exchange incidents or same-day stories describe one event.
"""
import copy,hashlib,json,re
from datetime import timedelta
from decimal import Decimal
from .fundamentals import timestamp

ENTITIES={'mercado-bitcoin':r'\bmercado bitcoin\b','binance':r'\bbinance\b','coinbase':r'\bcoinbase\b','bybit':r'\bbybit\b','kraken':r'\bkraken\b','okx':r'\bokx\b'}
NAMES={'mercado-bitcoin':'Mercado Bitcoin','binance':'Binance','coinbase':'Coinbase','bybit':'Bybit','kraken':'Kraken','okx':'OKX'}
KEY='incident_announcements_v114'
def digest(x):return hashlib.sha256(json.dumps(x,sort_keys=True).encode()).hexdigest()
def extract(row):
    title=row.get('title','');body=row.get('excerpt','');text=(title+' '+body).lower()
    if not re.search(r'\bhack\w*|\bexploit\w*|\bbreach\b|withdrawals? (?:halted|suspended|resumed)',text):return None
    entities=[e for e,p in ENTITIES.items() if re.search(p,text)]
    if not entities and row.get('incident_entity') in ENTITIES:entities=[row['incident_entity']]
    if len(entities)>1:
        primary=[e for e in entities if re.search(ENTITIES[e]+r' (?:exchange )?(?:hack|exploit|breach)',text)]
        if len(primary)==1:entities=primary
        else:return None # Cross-exchange comparisons are not a unique incident.
    amounts=sorted({format((Decimal(n)*scale).normalize(),'f') for n,u in re.findall(r'\$?\s*(\d+(?:\.\d+)?)\s*(billion|million|bn\b|[bm]\b)',text) for scale in [1000000000 if u.startswith('b') else 1000000]})
    facts={'breach'}
    for fact,pattern in {'withdrawals_paused':r'halts? withdrawals|withdrawals? (?:halted|paused|suspended)',
                         'withdrawals_resumed':r'resumes? withdrawals|withdrawals? (?:resumed|restored)',
                         'funds_moving':r'launder\w*|moving funds|move funds|hack loot',
                         'asset_freeze':r'freez\w*|frozen assets',
                         'coverage_plan':r'to cover|will cover|matching tokens|safu',
                         'repaid':r'fully reimbursed|losses fully covered'}.items():
        if re.search(pattern,text):facts.add(fact)
    # Only explicit occurrence dates; publication date is not the incident date.
    date=row.get('incident_date') or next(iter(re.findall(r'(?:hack|breach|exploit) (?:on|dated) (20\d\d-\d\d-\d\d)',text)),None)
    return dict(entity=entities[0] if entities else None,amounts=amounts,facts=sorted(facts),incident_date=date,
                distinct=bool(re.search(r'\b(?:another|second|separate|new) (?:hack|breach|exploit)\b',text)),
                content_scope='RSS_EXCERPT' if body else 'HEADLINE_ONLY')

def group_news(rows,previous,now):
    """Groups known incidents, retains material facts, suppresses unidentifiable hype."""
    groups=[];diagnostics=[]
    known=[]
    for old in previous:
        f=extract(old)
        if f and f['entity']:known.append((old,f))
    parsed=[(r,extract(r)) for r in rows]
    for row,f in parsed:
        if f and f['entity']:known.append((row,f))
    for row,f in parsed:
        if not f:
            if 'hack' in row.get('categories',[]):diagnostics.append(dict(id=row['id'],reason='AMBIGUOUS_OR_UNVERIFIED_SECURITY_EVENT'))
            else:groups.append(row)
            continue
        at=timestamp(row.get('published_at'))
        if not at:continue
        if not f['entity']:
            matches={g['entity'] for old,g in known if f['amounts'] and set(f['amounts'])&set(g['amounts']) and timestamp(old.get('published_at')) and abs((at-timestamp(old['published_at'])).total_seconds())<=72*3600}
            if len(matches)==1:f['entity']=matches.pop()
            else:diagnostics.append(dict(id=row['id'],reason='UNVERIFIED_INCIDENT_IDENTITY'));continue
        match=None;legacy=None
        for old,g in known:
            t=timestamp(old.get('published_at'))
            if not t or g['entity']!=f['entity'] or abs((at-t).total_seconds())>7*86400:continue
            if f['incident_date'] and g['incident_date'] and f['incident_date']!=g['incident_date']:continue
            if (f['distinct'] or g['distinct']) and row['id']!=old['id'] and not (f['incident_date'] and f['incident_date']==g['incident_date']):continue
            old_id=old.get('incident_id') or 'incident:'+digest([f['entity'],g['incident_date'] or old['id']])
            match=old_id
            if any(old is prior for prior in previous):legacy=old['id']
            break
        identity=match or 'incident:'+digest([f['entity'],f['incident_date'] or row['id']])
        # The same entity can have separate explicitly dated/new incidents.
        existing=next((x for x in groups if x.get('incident_id')==identity),None)
        citation=dict(id=row['id'],url=row.get('url'),source=row.get('source'),published_at=row['published_at'],content_scope=f['content_scope'])
        if existing:
            existing['incident_facts']=sorted(set(existing['incident_facts'])|set(f['facts']))
            existing['reported_amounts']=sorted(set(existing['reported_amounts'])|set(f['amounts']))
            existing['citations'].append(citation)
            continue
        value=copy.deepcopy(row);value.update(id=identity,incident_id=identity,incident_entity=f['entity'],incident_date=f['incident_date'],
            legacy_record_id=legacy,incident_facts=f['facts'],reported_amounts=f['amounts'],citations=[citation],content_scope=f['content_scope'])
        groups.append(value)
    for value in groups:
        if not value.get('incident_id'):continue
        value['citations_truncated']=len(value['citations'])>6
        value['citations']=value['citations'][-6:]
        legacy=[]
        for old in previous:
            f=extract(old);at=timestamp(old.get('published_at'));current=timestamp(value['published_at'])
            if not f or f['entity']!=value['incident_entity'] or not at or abs((current-at).total_seconds())>7*86400:continue
            if f['incident_date'] and value.get('incident_date') and f['incident_date']!=value['incident_date']:continue
            if f['distinct'] and old['id']!=value.get('legacy_record_id'):continue
            legacy.append(old['id'])
        value['legacy_ids']=legacy
        facts=set(value['incident_facts']);parts=[]
        if value['reported_amounts'] and not facts&{'asset_freeze','coverage_plan','repaid'}:
            amounts=[f'{Decimal(v)/1000000:g}' for v in value['reported_amounts']]
            parts.append('zdroje uvádzajú '+('/'.join(amounts))+' mil. USD; '+('odhady sa líšia' if len(amounts)>1 else 'nezávislé vyčíslenie nepotvrdené'))
        if 'withdrawals_resumed' in facts:parts.append('hlásené obnovenie výberov zmierňuje prevádzkové riziko')
        elif 'withdrawals_paused' in facts:parts.append('hlásené zastavenie výberov zvyšuje likviditné riziko')
        if 'funds_moving' in facts:parts.append('hlásené presuny ukradnutých aktív; nejde o nový hack')
        if 'asset_freeze' in facts:parts.append('hlásené zmrazenie aktív nie je dokončená náhrada')
        if 'coverage_plan' in facts:parts.append('plán krytia strát ešte nie je náhradou')
        if 'repaid' in facts:parts.append('hlásená náhrada strát zmierňuje riziko')
        if not parts:
            value['suppress_uninformative']=True;continue
        value['text']=NAMES[value['incident_entity']]+': '+ '; '.join(parts)+'. Samotná správa nemení BUY/SELL.'
        value['semantic']=digest([value['incident_facts'],value['reported_amounts']])
    return groups,diagnostics
