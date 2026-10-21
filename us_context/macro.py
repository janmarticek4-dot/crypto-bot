"""Bounded official macro feeds; publication time is not an event result."""
import re
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo

SOURCES = [
    dict(id='fed',url='https://www.federalreserve.gov/feeds/press_all.xml',official=True),
    dict(id='bls_calendar',url='https://www.bls.gov/schedule/news_release/bls.ics',official=True,format='ics'),
    dict(id='bea',url='https://apps.bea.gov/rss/rss.xml',publisher_host='bea.gov',official=True),
]
PATTERNS = {
    'Fed':r'\bfomc\b|monetary policy|federal funds|interest rates?|economic projections|discount rate|balance sheet',
    'CPI':r'consumer price|\bcpi\b',
    'PCE':r'personal consumption|personal income and outlays|\bpce\b',
    'employment':r'employment situation|nonfarm|unemployment|payroll|job openings|\bjolts\b',
    'GDP':r'gross domestic product|\bgdp\b',
}


def event(title,url,published,source,event_at=None,scheduled=False):
    categories=[k for k,v in PATTERNS.items() if re.search(v,title,re.I)]
    if not categories:
        return None
    return dict(title=title[:500],url=url,source=source['id'],
                published_at=published.isoformat() if published else None,
                event_at=event_at.isoformat() if event_at else None,
                scheduled=scheduled,categories=categories)


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
    req=urllib.request.Request(source['url'],headers={'User-Agent':'CryptoBotUS/10.6 (public-source calendar reader)'})
    with urllib.request.urlopen(req,timeout=8) as r:
        initial=urllib.parse.urlsplit(source['url']).hostname.removeprefix('www.')
        final=urllib.parse.urlsplit(r.geturl()).hostname.removeprefix('www.')
        publisher=source.get('publisher_host',initial)
        if urllib.parse.urlsplit(r.geturl()).scheme!='https' or (final!=initial and final!=publisher and not final.endswith('.'+publisher)):raise ValueError('Unexpected feed redirect')
        raw=r.read(2_000_001)
        if len(raw)>2_000_000:raise ValueError('Feed too large')
        return raw
