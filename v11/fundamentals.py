"""Dated, attributed public-source events. No AI-created news or probabilities."""
import concurrent.futures
import hashlib
import json
from html import unescape
import re
import urllib.request
import urllib.error
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo

SOURCES=[
    dict(id='fomc_calendar',url='https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm',official=True,coverage=['Fed'],format='fomc_html'),
    dict(id='fed',url='https://www.federalreserve.gov/feeds/press_all.xml',official=True,coverage=['Fed']),
    dict(id='bls',url='https://www.bls.gov/feed/bls_latest.rss',official=True,coverage=['CPI','employment']),
    dict(id='bls_calendar',url='https://www.bls.gov/schedule/news_release/bls.ics',official=True,coverage=['CPI','employment'],format='ics'),
    dict(id='bea',url='https://apps.bea.gov/rss/rss.xml',publisher_host='bea.gov',official=True,coverage=['PCE']),
    dict(id='ecb',url='https://www.ecb.europa.eu/rss/press.html',official=True,coverage=['Fed','regulation']),
    dict(id='cftc',url='https://www.cftc.gov/RSS/RSSGP/rssgp.xml',official=True,coverage=['regulation']),
    dict(id='sec',url='https://www.sec.gov/news/pressreleases.rss',official=True,coverage=['regulation']),
    dict(id='aave',url='https://governance.aave.com/latest.rss',official=False,coverage=['project'],symbol='AAVE'),
    dict(id='ondo',url='https://blog.ondo.finance/rss/',official=True,coverage=['project'],symbol='ONDO'),
    dict(id='sol_agave',url='https://github.com/anza-xyz/agave/releases.atom',official=True,publisher_path='/anza-xyz/agave/',coverage=['project'],symbol='SOL',kind='software_release_notice'),
    dict(id='tao_subtensor',url='https://github.com/opentensor/subtensor/releases.atom',official=True,publisher_path='/opentensor/subtensor/',coverage=['project'],symbol='TAO',kind='software_release_notice'),
    dict(id='fet_fetchd',url='https://github.com/fetchai/fetchd/releases.atom',official=True,publisher_path='/fetchai/fetchd/',coverage=['project'],symbol='FET',kind='software_release_notice'),
    dict(id='render_rnp',url='https://github.com/rendernetwork/RNPs/commits/main.atom',official=False,coverage=['project'],symbol='RENDER',kind='governance_repository_change'),
    dict(id='coindesk',url='https://www.coindesk.com/arc/outboundfeeds/rss/',official=False,coverage=['regulation','hack','project']),
    dict(id='cointelegraph',url='https://cointelegraph.com/rss',official=False,coverage=['regulation','hack','project']),
]
# Optional endpoint/feed alternatives. Fallback provenance never inherits a primary's trust.
FALLBACKS={
 'bea':[dict(id='bea_www',url='https://www.bea.gov/rss/rss.xml',official=True,publisher_host='bea.gov',coverage=['PCE'])],
 'fed':[dict(id='fed_monetary',url='https://www.federalreserve.gov/feeds/press_monetary.xml',official=True,coverage=['Fed'])],
 'bls_calendar':[dict(id='bls_year_calendar',url='https://www.bls.gov/schedule/news_release/current_year.ics',official=True,coverage=['CPI','employment'],format='ics')],
 'ecb':[dict(id='ecb_blog',url='https://www.ecb.europa.eu/rss/blog.html',official=True,coverage=['Fed'],kind='central_bank_blog_not_decision')],
 'sec':[dict(id='sec_new_path',url='https://www.sec.gov/newsroom/press-releases/rss.xml',official=True,coverage=['regulation'])],
 'aave':[dict(id='aave_aip',url='https://github.com/aave/aip/commits/main.atom',official=False,publisher_path='/aave/aip/',coverage=['project'],symbol='AAVE',kind='governance_repository_change')],
 'ondo':[dict(id='ondo_secondary',url='https://www.coindesk.com/arc/outboundfeeds/rss/',official=False,coverage=['project','regulation'],symbol='ONDO',title_filter=r'\bondo\b',kind='secondary_project_report')],
}
FUNDAMENTAL_TITLE=r'govern|proposal|tokeniz|unlock|emission|upgrade|launch|partner|regulat|enforcement|lawsuit|hack|exploit|treasury|treasuries|adoption'

PATTERNS={
 'Fed':r'monetary policy decisions|\bfomc\b|federal reserve|monetary policy|\bfed\b|interest[- ]rates?',
 'CPI':r'consumer price|producer price|\bppi\b|\bcpi\b',
 'PCE':r'personal consumption|personal income and outlays|\bpce\b',
 'GDP':r'gross domestic product|\bgdp\b',
 'employment':r'employment situation|nonfarm|unemployment|payroll',
 'regulation':r'\bsec\b|regulat|lawsuit|securities and exchange|enforcement|digital euro',
 'unlock':r'token unlock|vesting|token release',
 'geopolitics':r'\bwar\b|military conflict|\bsanctions\b|\btariffs\b|energy shock',
 'hack':r'hack|exploit|security breach|depeg|bankruptcy|insolven|withdrawals suspended',
}
MECHANISMS={
 'Fed':'Zmena sadzieb alebo likvidity môže ovplyvniť diskontovanie a ochotu podstupovať riziko; smer bez údajov nie je potvrdený.',
 'CPI':'Prekvapenie inflácie môže zmeniť očakávania sadzieb; samotný titulok nepotvrdzuje dopad.',
 'PCE':'Inflácia a spotreba môžu ovplyvniť očakávania Fedu; smer vyžaduje porovnanie s očakávaniami.',
 'GDP':'Rast ekonomiky môže ovplyvniť očakávania sadzieb; smer vyžaduje výsledok voči overenému konsenzu.',
 'employment':'Údaje trhu práce môžu ovplyvniť sadzby aj ochotu riskovať; bez konsenzu je dopad neistý.',
 'regulation':'Regulačná udalosť môže zmeniť prístup k obchodovaniu alebo prevádzkové riziko.',
 'unlock':'Uvoľnená ponuka môže zvýšiť predajný tlak, ale uvoľnenie neznamená automatický predaj.',
 'hack':'Incident môže spôsobiť stratu dôvery, likvidity alebo nákazu medzi subjektmi; rozsah vyžaduje preverenie.',
 'geopolitics':'Konflikt, sankcie alebo clá môžu meniť podmienky likvidity a rizikovú averziu; expozícia a smer vyžadujú potvrdenie.',
 'project':'Projektová udalosť môže zmeniť využitie alebo riziko tokenu; titulok nie je dôkaz rastu hodnoty.'}


def timestamp(raw):
    if not isinstance(raw,str) or not raw:return None
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
    if root.tag.rsplit('}',1)[-1] not in ('rss','feed'):
        raise ValueError('Expected RSS/Atom, not an HTML challenge or error document')
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
        if source.get('title_filter') and (not re.search(source['title_filter'],title,re.I) or not re.search(FUNDAMENTAL_TITLE,title,re.I)):continue
        if not url or not title or published is None or not now-timedelta(hours=72)<=published<=now+timedelta(minutes=5):continue
        # Official trust is attached only to links hosted on that publisher's domain.
        if source['official']:
            host=source.get('publisher_host') or urllib.parse.urlsplit(source['url']).hostname.removeprefix('www.')
            target=urllib.parse.urlsplit(url).hostname.removeprefix('www.')
            if target!=host and not target.endswith('.'+host):continue
        if source.get('publisher_path') and (urllib.parse.urlsplit(url).hostname!=urllib.parse.urlsplit(source['url']).hostname or not urllib.parse.urlsplit(url).path.startswith(source['publisher_path'])):continue
        attributed=dict(source)
        if not source.get('symbol') and re.search(FUNDAMENTAL_TITLE,title,re.I):
            from .fundamental_analysis import ALIASES
            symbols=[symbol for symbol,pattern in ALIASES.items() if re.search(pattern,title,re.I)]
            if len(symbols)==1:attributed['symbol']=symbols[0]
        item=event(title,url,published,attributed)
        if item:
            item['timestamp_kind']='published' if values.get('pubDate') or values.get('published') else 'updated'
            out.append(item)
    return out


def parse_calendar(raw,source,now=None,audit=None):
    now=now or datetime.now(timezone.utc)
    text=re.sub(r'\r?\n[ \t]','',raw.decode('utf-8'))
    out=[]
    audit = audit if audit is not None else {}
    audit.update(total=0, accepted=0, rejected={}, earliest_date=None, latest_date=None, timezone_identifiers={})
    def reject(reason):
        audit['rejected'][reason]=audit['rejected'].get(reason,0)+1
    for block in text.split('BEGIN:VEVENT')[1:]:
        audit['total']+=1
        values={}
        for line in block.split('END:VEVENT')[0].splitlines():
            if ':' in line:
                key,value=line.split(':',1);values[key]=value
        dt_key=next((k for k in values if k.startswith('DTSTART')),None)
        if not dt_key:
            reject('missing_dtstart');continue
        date=values[dt_key].strip()
        if re.match(r'^\d{8}',date):
            day=date[:8]
            audit['earliest_date']=min(audit['earliest_date'] or day,day)
            audit['latest_date']=max(audit['latest_date'] or day,day)
        date_only=None
        try:
            if 'VALUE=DATE' in dt_key or re.fullmatch(r'\d{8}',date):
                date_only=datetime.strptime(date,'%Y%m%d').date()
                dt=None
            elif date.endswith('Z'):dt=datetime.strptime(date,'%Y%m%dT%H%M%SZ').replace(tzinfo=timezone.utc)
            elif 'TZID=' in dt_key:
                name=dt_key.split('TZID=',1)[1].split(';')[0].strip(chr(34))
                audit['timezone_identifiers'][name]=audit['timezone_identifiers'].get(name,0)+1
                # Explicit Windows calendar identifier; observes US daylight saving.
                if name=='Eastern Standard Time':name='America/New_York'
                # BLS uses a non-IANA US-Eastern identifier in its official ICS.
                # Restrict this publisher-specific alias; unknown zones still fail closed.
                publisher=urllib.parse.urlsplit(source['url']).hostname
                if name=='US-Eastern' and publisher in ('www.bls.gov','bls.gov'):
                    name='America/New_York'
                tz=ZoneInfo(name)
                dt=datetime.strptime(date,'%Y%m%dT%H%M%S').replace(tzinfo=tz).astimezone(timezone.utc)
            else:
                # Preserve a source date but do not assume a timezone for floating times.
                date_only=datetime.strptime(date[:8],'%Y%m%d').date();dt=None
        except (ValueError,KeyError):
            reject('invalid_datetime_or_unknown_timezone');continue
        if dt is not None and not now<=dt<=now+timedelta(days=30):
            reject('past' if dt<now else 'beyond_30_days');continue
        if date_only is not None and not now.date()<=date_only<=(now+timedelta(days=30)).date():
            reject('past' if date_only<now.date() else 'beyond_30_days');continue
        url=canonical_url(values.get('URL',source['url']))
        if not url:
            reject('invalid_url');continue
        host=source.get('publisher_host') or urllib.parse.urlsplit(source['url']).hostname.removeprefix('www.')
        target=urllib.parse.urlsplit(url).hostname.removeprefix('www.')
        if source['official'] and target!=host and not target.endswith('.'+host):
            reject('untrusted_publisher');continue
        item=event(values.get('SUMMARY',''),url,None,source,dt,True)
        if item:
            if date_only is not None:item.update(event_date=date_only.isoformat(),date_precision='date_only',time_status='N/A – časové pásmo alebo presný čas neoverený')
            out.append(item)
            audit['accepted']+=1
        else:reject('irrelevant_title')
    return out


def parse_fomc(raw,source,now=None):
    """Official meeting dates; NEVER assume a decision time from convention."""
    now=now or datetime.now(timezone.utc)
    text=raw.decode('utf-8')
    headings=list(re.finditer(r'(20\d{2})\s+FOMC Meetings',text))
    months={name:i for i,name in enumerate(('January','February','March','April','May','June','July','August','September','October','November','December'),1)}
    out=[]
    for index,heading in enumerate(headings):
        year=int(heading.group(1));section=text[heading.end():headings[index+1].start() if index+1<len(headings) else len(text)]
        pairs=re.findall(r'class=["\'][^"\']*fomc-meeting__month[^"\']*["\'][^>]*>(.*?)</div>.*?class=["\'][^"\']*fomc-meeting__date[^"\']*["\'][^>]*>(.*?)</div>',section,re.S)
        for month_html,date_html in pairs:
            month=unescape(re.sub('<[^>]+>','',month_html)).strip()
            days=unescape(re.sub('<[^>]+>','',date_html)).strip()
            if month not in months or not re.fullmatch(r'\d{1,2}(?:[-–]\d{1,2})?\*?',days):continue
            end_day=int(re.findall(r'\d+',days)[-1])
            try:date=datetime(year,months[month],end_day,tzinfo=timezone.utc).date()
            except ValueError:continue
            if not now.date()<=date<=(now+timedelta(days=30)).date():continue
            item=event('FOMC zasadnutie – '+month+' '+days,source['url'],None,source,None,True)
            item.update(event_date=date.isoformat(),date_precision='date_only',time_status='N/A – presný čas rozhodnutia neoverený')
            out.append(item)
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
    if cached_at and 0<=(now-cached_at).total_seconds()<15*60:return old
    events=[];statuses=[]
    def one(source):
        attempts=[]
        for candidate in [source,*FALLBACKS.get(source['id'],[])]:
            try:
                raw=fetcher(candidate)
                fmt=candidate.get('format')
                if fmt=='ics' and b'BEGIN:VCALENDAR' not in raw and b'BEGIN:VEVENT' not in raw:raise ValueError('Unrecognized calendar schema')
                if fmt=='fomc_html' and not re.search(rb'20\d{2}\s+FOMC Meetings',raw):raise ValueError('Unrecognized FOMC calendar schema')
                parser={'ics':parse_calendar,'fomc_html':parse_fomc}.get(fmt,parse_feed)
                items=parser(raw,candidate,now)
                attempts.append(dict(source=candidate['id'],url=candidate['url'],status='OK',events=len(items)))
                for item in items:item['retrieved_at']=now.isoformat()
                return items,dict(source=source['id'],url=candidate['url'],selected_source=candidate['id'],
                    official=candidate['official'],symbol=source.get('symbol'),coverage=candidate.get('coverage',[]),kind=candidate.get('kind','news'),fallback=candidate is not source,
                    status='OK',events=len(items),checked_at=now.isoformat(),attempts=attempts)
            except Exception as exc:
                code=getattr(exc,'code',None)
                tunnel='Tunnel connection failed: 403' in str(getattr(exc,'reason',''))
                attempts.append(dict(source=candidate['id'],url=candidate['url'],status='N/A',error_type=type(exc).__name__,
                    http_status=403 if tunnel else code,error_layer='network_tunnel' if tunnel else 'http_origin_or_gateway' if code else 'transport_or_parse'))
        last=attempts[-1]
        return [],dict(source=source['id'],symbol=source.get('symbol'),coverage=source.get('coverage',[]),url=source['url'],status='N/A',error_type=last['error_type'],
            http_status=last['http_status'],error_layer=last['error_layer'],attempts=attempts,checked_at=now.isoformat())
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
        for items,status in pool.map(one,SOURCES):events.extend(items);statuses.append(status)
    unique={}
    for item in events:
        # Scheduled monthly releases sharing a calendar URL remain distinct.
        key=item['id']+str(item['event_at'])+str(item.get('event_date'))
        unique[key]=item
    metrics={}
    metric_sources=[('AAVE','https://api.llama.fi/protocol/aave'),('SOL','https://api.llama.fi/v2/historicalChainTvl/Solana'),('ONDO','https://api.llama.fi/protocol/ondo-finance')]
    for symbol,url in metric_sources:
        try:
            data=json.loads(fetcher(dict(url=url)))
            rows=data.get('tvl',[]) if isinstance(data,dict) else data
            latest=max(rows,key=lambda x:x['date'])
            value=latest.get('totalLiquidityUSD',latest.get('tvl'))
            at=datetime.fromtimestamp(latest['date'],timezone.utc)
            if isinstance(value,(int,float)) and 0<=value<float('inf') and timedelta(minutes=-5)<=now-at<=timedelta(hours=48):
                metrics[symbol]=dict(value=value,at=at.isoformat(),observed_at=now.isoformat(),url=url)
        except Exception:
            pass  # Missing metrics remain N/A, never synthetic zeroes.
    from .project_metrics import collect as collect_economics
    economics=collect_economics(fetcher,now)
    result=dict(project_economics=economics,metrics=metrics,fetched_at=now.isoformat(),events=sorted(unique.values(),key=lambda x:(not x['scheduled'],x['event_at'] or x.get('event_date') or x['published_at'] or ''))[:200],sources=statuses,
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
