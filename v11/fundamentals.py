"""Dated, attributed public-source events. No AI-created news or probabilities."""
import concurrent.futures
import hashlib
import re
import urllib.request
import urllib.error
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo

SOURCES=[
    dict(id='fed',url='https://www.federalreserve.gov/feeds/press_all.xml',official=True,coverage=['Fed']),
    dict(id='bls',url='https://www.bls.gov/feed/bls_latest.rss',official=True,coverage=['CPI','employment']),
    dict(id='bls_calendar',url='https://www.bls.gov/schedule/news_release/bls.ics',official=True,coverage=['CPI','employment'],format='ics'),
    dict(id='bea',url='https://apps.bea.gov/rss/rss.xml',publisher_host='bea.gov',official=True,coverage=['PCE']),
    dict(id='sec',url='https://www.sec.gov/newsroom/press-releases/rss.xml',official=True,coverage=['regulation']),
    dict(id='aave',url='https://governance.aave.com/latest.rss',official=False,coverage=['project'],symbol='AAVE'),
    dict(id='ondo',url='https://blog.ondo.finance/rss/',official=True,coverage=['project'],symbol='ONDO'),
    dict(id='sol_agave',url='https://github.com/anza-xyz/agave/releases.atom',official=True,publisher_path='/anza-xyz/agave/',coverage=['project'],symbol='SOL',kind='software_release_notice'),
    dict(id='tao_subtensor',url='https://github.com/opentensor/subtensor/releases.atom',official=True,publisher_path='/opentensor/subtensor/',coverage=['project'],symbol='TAO',kind='software_release_notice'),
    dict(id='fet_fetchd',url='https://github.com/fetchai/fetchd/releases.atom',official=True,publisher_path='/fetchai/fetchd/',coverage=['project'],symbol='FET',kind='software_release_notice'),
    dict(id='render_rnp',url='https://github.com/rendernetwork/RNPs/commits/main.atom',official=False,coverage=['project'],symbol='RENDER',kind='governance_repository_change'),
    dict(id='coindesk',url='https://www.coindesk.com/arc/outboundfeeds/rss/',official=False,coverage=['regulation','hack','project']),
    dict(id='cointelegraph',url='https://cointelegraph.com/rss',official=False,coverage=['regulation','hack','project']),
]
PATTERNS={
 'Fed':r'\bfomc\b|federal reserve|monetary policy|interest rate',
 'CPI':r'consumer price|\bcpi\b',
 'PCE':r'personal consumption|personal income and outlays|\bpce\b',
 'employment':r'employment situation|nonfarm|unemployment|payroll',
 'regulation':r'\bsec\b|regulat|lawsuit|securities and exchange|enforcement',
 'unlock':r'token unlock|vesting|token release',
 'hack':r'hack|exploit|security breach|depeg|bankruptcy|insolven|withdrawals suspended',
}
MECHANISMS={
 'Fed':'Zmena sadzieb alebo likvidity môže ovplyvniť diskontovanie a ochotu podstupovať riziko; smer bez údajov nie je potvrdený.',
 'CPI':'Prekvapenie inflácie môže zmeniť očakávania sadzieb; samotný titulok nepotvrdzuje dopad.',
 'PCE':'Inflácia a spotreba môžu ovplyvniť očakávania Fedu; smer vyžaduje porovnanie s očakávaniami.',
 'employment':'Údaje trhu práce môžu ovplyvniť sadzby aj ochotu riskovať; bez konsenzu je dopad neistý.',
 'regulation':'Regulačná udalosť môže zmeniť prístup k obchodovaniu alebo prevádzkové riziko.',
 'unlock':'Uvoľnená ponuka môže zvýšiť predajný tlak, ale uvoľnenie neznamená automatický predaj.',
 'hack':'Incident môže spôsobiť stratu dôvery, likvidity alebo nákazu medzi subjektmi; rozsah vyžaduje preverenie.',
 'project':'Projektová udalosť môže zmeniť využitie alebo riziko tokenu; titulok nie je dôkaz rastu hodnoty.'}


def timestamp(raw):
    if not raw:return None
    try:out=datetime.fromisoformat(raw.replace('Z','+00:00'))
    except ValueError:
        try:out=parsedate_to_datetime(raw)
        except (TypeError,ValueError):return None
    if out.tzinfo is None:return None
    return out.astimezone(timezone.utc)


def canonical_url(url):
    p=urllib.parse.urlsplit(url)
    if p.scheme!='https' or not p.hostname or p.username or p.password:return None
    params=[(k,v) for k,v in urllib.parse.parse_qsl(p.query) if not k.lower().startswith('utm_')]
    return urllib.parse.urlunsplit((p.scheme,p.netloc,p.path,urllib.parse.urlencode(params),''))


def event(title,url,published,source,event_at=None,scheduled=False):
    categories=[k for k,v in PATTERNS.items() if re.search(v,title,re.I)]
    if not categories and source.get('symbol'):categories=['project']
    if not categories:return None
    return dict(id=hashlib.sha256((url+'|'+re.sub(r'\s+',' ',title.strip().lower())).encode()).hexdigest(),
        title=title[:500],url=url,source=source['id'],kind=source.get('kind','news'),published_at=published.isoformat() if published else None,
        event_at=event_at.isoformat() if event_at else None,scheduled=scheduled,categories=categories,symbol=source.get('symbol'),
        confidence='oficiálny zdroj, dopad neoverený' if source['official'] else 'správa/návrh; vyžaduje samostatné potvrdenie',
        mechanisms=[MECHANISMS[k] for k in categories])


def parse_feed(raw,source,now=None):
    now=now or datetime.now(timezone.utc)
    root=ET.fromstring(raw)
    out=[]
    for node in root.iter():
        if node.tag.rsplit('}',1)[-1] not in ('item','entry'):continue
        values={};url=None
        for child in node:
            tag=child.tag.rsplit('}',1)[-1]
            values[tag]=(child.text or '').strip()
            if tag=='link':
                if child.get('href') and child.get('rel','alternate')=='alternate':url=child.get('href')
                elif child.text:url=child.text.strip()
        url=canonical_url(url or '')
        published=timestamp(values.get('pubDate') or values.get('published') or values.get('updated'))
        title=values.get('title','')
        if not url or not title or published is None or not now-timedelta(hours=72)<=published<=now+timedelta(minutes=5):continue
        # Official trust is attached only to links hosted on that publisher's domain.
        if source['official']:
            host=source.get('publisher_host') or urllib.parse.urlsplit(source['url']).hostname.removeprefix('www.')
            target=urllib.parse.urlsplit(url).hostname.removeprefix('www.')
            if target!=host and not target.endswith('.'+host):continue
        if source.get('publisher_path') and not urllib.parse.urlsplit(url).path.startswith(source['publisher_path']):continue
        item=event(title,url,published,source)
        if item:
            item['timestamp_kind']='published' if values.get('pubDate') or values.get('published') else 'updated'
            out.append(item)
    return out


def parse_calendar(raw,source,now=None):
    now=now or datetime.now(timezone.utc)
    text=re.sub(r'\r?\n[ \t]','',raw.decode('utf-8'))
    out=[]
    for block in text.split('BEGIN:VEVENT')[1:]:
        values={}
        for line in block.split('END:VEVENT')[0].splitlines():
            if ':' in line:
                key,value=line.split(':',1);values[key]=value
        dt_key=next((k for k in values if k.startswith('DTSTART')),None)
        if not dt_key:continue
        date=values[dt_key]
        try:
            if date.endswith('Z'):dt=datetime.strptime(date,'%Y%m%dT%H%M%SZ').replace(tzinfo=timezone.utc)
            elif 'TZID=' in dt_key:
                tz=ZoneInfo(dt_key.split('TZID=',1)[1].split(';')[0])
                dt=datetime.strptime(date,'%Y%m%dT%H%M%S').replace(tzinfo=tz).astimezone(timezone.utc)
            else:continue  # Floating or date-only event has no proven precise time.
        except (ValueError,KeyError):continue
        if not now<=dt<=now+timedelta(days=30):continue
        url=canonical_url(values.get('URL',source['url']))
        if not url:continue
        host=source.get('publisher_host') or urllib.parse.urlsplit(source['url']).hostname.removeprefix('www.')
        target=urllib.parse.urlsplit(url).hostname.removeprefix('www.')
        if source['official'] and target!=host and not target.endswith('.'+host):continue
        item=event(values.get('SUMMARY',''),url,None,source,dt,True)
        if item:out.append(item)
    return out


def fetch(source):
    req=urllib.request.Request(source['url'],headers={'User-Agent':'CryptoBotResearch/11.0 (public-source calendar reader)'})
    with urllib.request.urlopen(req,timeout=8) as r:
        initial=urllib.parse.urlsplit(source['url']).hostname.removeprefix('www.')
        final=urllib.parse.urlsplit(r.geturl()).hostname.removeprefix('www.')
        publisher=source.get('publisher_host',initial)
        if urllib.parse.urlsplit(r.geturl()).scheme!='https' or (final!=initial and final!=publisher and not final.endswith('.'+publisher)):raise ValueError('Unexpected feed redirect')
        raw=r.read(2_000_001)
        if len(raw)>2_000_000:raise ValueError('Feed too large')
        return raw


def collect(state,now=None,fetcher=fetch):
    now=now or datetime.now(timezone.utc)
    old=state.get('fundamentals_v11',{})
    cached_at=timestamp(old.get('fetched_at'))
    if cached_at and 0<=(now-cached_at).total_seconds()<6*3600:return old
    events=[];statuses=[]
    def one(source):
        try:
            raw=fetcher(source)
            items=(parse_calendar if source.get('format')=='ics' else parse_feed)(raw,source,now)
            return items,dict(source=source['id'],url=source['url'],status='OK',events=len(items),checked_at=now.isoformat())
        except Exception as exc:
            # Exceptions can contain request data. Record only a type/code.
            code=getattr(exc,'code',None)
            if code is None and 'Tunnel connection failed: 403' in str(getattr(exc,'reason','')):code=403
            return [],dict(source=source['id'],url=source['url'],status='N/A',error_type=type(exc).__name__,http_status=code,checked_at=now.isoformat())
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
        for items,status in pool.map(one,SOURCES):events.extend(items);statuses.append(status)
    unique={}
    for item in events:
        # Scheduled monthly releases sharing a calendar URL remain distinct.
        key=item['id']+str(item['event_at'])
        unique[key]=item
    result=dict(fetched_at=now.isoformat(),events=sorted(unique.values(),key=lambda x:x['event_at'] or x['published_at'],reverse=True)[:200],sources=statuses,
                unavailable=['overený projektový token-unlock kalendár','priame potvrdenie incidentu z primárneho zdroja','potvrdenie skutočnej aktivácie upgrade na sieti'])
    state['fundamentals_v11']=result
    return result


def lines(result,limit=5):
    out=['FUNDAMENTÁLNE UDALOSTI (dátum vydania ≠ dátum udalosti):']
    for e in result['events'][:limit]:
        date=e['event_at'] if e['scheduled'] else e['published_at']
        stamp={'published':'vydané','updated':'aktualizované','scheduled':'plánované'}[e.get('timestamp_kind','scheduled')]
        out.append(f"{date} | {e['source']} ({stamp}) | {e['title']} — {e['url']} | {e['confidence']}")
        out.append('Možný mechanizmus: '+e['mechanisms'][0])
    if not result['events']:out.append('N/A — žiadne dostupné aktuálne overiteľné udalosti.')
    unavailable=[s['source'] for s in result['sources'] if s['status']!='OK']
    if unavailable:out.append('Zdroje N/A: '+', '.join(unavailable))
    out.append('N/A: '+', '.join(result['unavailable']))
    return out
