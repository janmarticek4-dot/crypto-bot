"""Time-aware evidence. Official calendars provide dates, not released results."""
import copy,re
from html import unescape
from html.parser import HTMLParser
from datetime import datetime,timedelta,timezone
from zoneinfo import ZoneInfo
from urllib.parse import urlsplit
from . import fundamentals
NY=ZoneInfo('America/New_York')
BL=ZoneInfo('Europe/Bratislava')

class Paragraphs(HTMLParser):
    def __init__(self):super().__init__();self.paragraphs=[];self.active=0;self.buf=[]
    def handle_starttag(self,tag,attrs):
        if tag=='p':self.active+=1;self.buf=[]
    def handle_endtag(self,tag):
        if tag=='p' and self.active:
            self.paragraphs.append(re.sub(r'\s+',' ',''.join(self.buf)).strip());self.active=0
    def handle_data(self,value):
        if self.active:self.buf.append(value)

def rate_number(text):
    text=text.strip().replace('¼',' 1/4').replace('½',' 1/2').replace('¾',' 3/4').replace('−','-')
    match=re.fullmatch(r'(\d+)(?:[- ](\d)/(\d))?',text)
    if match:return int(match[1])+(int(match[2])/int(match[3]) if match[2] else 0)
    if re.fullmatch(r'\d+(?:\.\d+)?',text):return float(text)
    return None

def parse_statement(raw,url,now):
    match=re.fullmatch(r'https://www\.federalreserve\.gov/newsevents/pressreleases/monetary(\d{8})a\.htm',url)
    if not match:raise ValueError('Not an official statement URL')
    day=datetime.strptime(match[1],'%Y%m%d').date();parser=Paragraphs();parser.feed(raw.decode('utf-8'))
    plain=re.sub('<[^>]+>',' ',raw.decode('utf-8'));plain=re.sub(r'\s+',' ',unescape(plain))
    if not re.search(r'Federal Open Market Committee',plain) or not re.search(r'federal funds rate',plain,re.I):raise ValueError('Statement schema missing')
    expected=day.strftime('%B')+f' {day.day}, {day.year}'
    if expected not in plain:raise ValueError('Publication date mismatch')
    release=re.search(r'For release at\s+(\d{1,2}):(\d\d)\s*([ap])\.?m\.?\s*(EDT|EST)',plain,re.I)
    published=None
    if release:
        hour=int(release[1])%12+(12 if release[3].lower()=='p' else 0)
        at=datetime(day.year,day.month,day.day,hour,int(release[2]),tzinfo=NY)
        if at.tzname()!=release[4].upper():raise ValueError('Publication timezone mismatch')
        published=at.astimezone(timezone.utc)
        if published>now:raise ValueError('Statement publication is in the future')
    elif day>now.astimezone(NY).date():raise ValueError('Future statement date')
    decision=next((p for p in parser.paragraphs if re.search(r'(?:decided|decides|maintain|lower|raise).*target range.*federal funds rate',p,re.I)),None)
    if not decision:raise ValueError('No verified decision paragraph')
    pattern=r'(?:at|to)\s+(\d+(?:[.\- ]\d+(?:/\d+)?)?|\d+[¼½¾])\s+to\s+(\d+(?:[.\- ]\d+(?:/\d+)?)?|\d+[¼½¾])\s+percent'
    bounds=re.findall(pattern,decision,re.I)
    values=next(([rate_number(a),rate_number(b)] for a,b in reversed(bounds) if rate_number(a) is not None and rate_number(b) is not None),None)
    if values and not 0<=values[0]<=values[1]<=30:raise ValueError('Invalid official rate interval')
    vote=next((p for p in parser.paragraphs if re.search(r'Voting for .*were|Voting for .*was',p,re.I)),None)
    index=parser.paragraphs.index(decision)
    comments=[p for p in parser.paragraphs[max(0,index-3):index] if re.search(r'inflation|employment|economic activity',p,re.I)][-2:]
    return dict(id='fomc-'+day.isoformat(),event_date=day.isoformat(),title='Fed/FOMC – rozhodnutie',status='RELEASED',
        scheduled_at=published.isoformat() if published else None,published_at=published.isoformat() if published else None,
        retrieved_at=now.isoformat(),source='Federal Reserve',url=url,verified=True,rate_range=values,
        decision=decision,voting=vote,comments=comments,expectation=None,surprise=None,reaction={},
        interpretation='Smer dopadu bez overeného konsenzu nepotvrdený; rozhodnutie samo nedokazuje príčinu pohybu.')

def reaction(snapshot,published):
    if not published:return {}
    at=published.timestamp()*1000;out={}
    for symbol,coin in snapshot.get('coins',{}).items():
        if symbol not in ('BTC','SOL','TAO','FET','AAVE','ONDO','RENDER'):continue
        rows=coin.get('raw',{}).get('1h',[])
        before=[r for r in rows if at-3600000<=r['timestamp']+3600000<=at]
        after=[r for r in rows if at<r['timestamp']+3600000<=snapshot['at']*1000]
        if before and after and before[-1]['close']>0:
            a,b=before[-1],after[-1]
            out[symbol]=dict(before_at=a['timestamp']+3600000,after_at=b['timestamp']+3600000,change_pct=(b['close']/a['close']-1)*100)
    return out

def timing(event,now):
    at=fundamentals.timestamp(event.get('event_at'));day=event.get('event_date')
    if at:return 'UPCOMING' if at>now else 'AWAITING_VERIFICATION'
    if day:return 'UPCOMING' if day>now.astimezone(NY).date().isoformat() else 'TIME_UNVERIFIED' if day==now.astimezone(NY).date().isoformat() else 'AWAITING_VERIFICATION'
    return 'TIME_UNVERIFIED'

def economic_releases(value,now,fetcher):
    """Confirm linked official result pages; no numbers inferred from a calendar."""
    releases=[];attempts=[];seen=set()
    for item in value.get('events',[]):
        if item.get('scheduled'):continue
        cats=set(item.get('categories',[]))&{'CPI','PCE','employment','GDP'}
        pub=fundamentals.timestamp(item.get('published_at'));url=item.get('url','')
        host=urlsplit(url).hostname or ''
        if not cats or not pub or not timedelta(0)<=now-pub<=timedelta(days=2) or not any(host==h or host.endswith('.'+h) for h in ('bls.gov','bea.gov')):continue
        if re.search(r'metropolitan|county|regional|state employment',item.get('title',''),re.I):continue
        if url in seen or len(attempts)>=3:continue
        seen.add(url)
        try:
            raw=fetcher(dict(url=url));paragraphs=Paragraphs();paragraphs.feed(raw.decode('utf-8'))
            useful=[p for p in paragraphs.paragraphs if len(p)>60 and re.search(r'percent|employment|consumer price|gross domestic|personal consumption',p,re.I)]
            if not useful:raise ValueError('Official release content unavailable')
            entry=dict(id=item['id']+'-official-result',event_date=pub.astimezone(NY).date().isoformat(),title=item['title'],status='RELEASED',
                published_at=pub.isoformat(),retrieved_at=now.isoformat(),source=item['source'],url=url,verified=True,kind='economic_release',
                result_excerpt=useful[0][:650],expectation=None,surprise=None,reaction={},time_basis='official_feed_publication_not_exact_release_time',categories=sorted(cats))
            releases.append(entry);attempts.append(dict(url=url,status='VERIFIED'))
            for planned in value.get('events',[]):
                scheduled=fundamentals.timestamp(planned.get('event_at'))
                if planned.get('scheduled') and set(planned.get('categories',[]))&cats and scheduled and timedelta(0)<=pub-scheduled<=timedelta(days=1):
                    planned['lifecycle']='SUPERSEDED'
        except Exception as exc:attempts.append(dict(url=url,status='UNAVAILABLE',error=type(exc).__name__))
    return releases,attempts

def collect(fund,now,snapshot=None,fetcher=None):
    fetcher=fetcher or fundamentals.fetch;value=copy.deepcopy(fund);releases=[];attempts=[]
    days={now.astimezone(NY).date(),(now-timedelta(days=1)).astimezone(NY).date()}
    for event in value.get('events',[]):
        if event.get('scheduled'):event['lifecycle']=timing(event,now)
        if 'FOMC' in event.get('title','') and event.get('event_date'):
            try:day=datetime.fromisoformat(event['event_date']).date()
            except (TypeError,ValueError):continue
            if -2<=(day-now.astimezone(NY).date()).days<=0:days.add(day)
    for day in sorted(days,reverse=True)[:3]:
        url=f'https://www.federalreserve.gov/newsevents/pressreleases/monetary{day:%Y%m%d}a.htm'
        try:
            raw=fetcher(dict(url=url));item=parse_statement(raw,url,now)
            item['reaction']=reaction(snapshot or {},fundamentals.timestamp(item['published_at']))
            if item['reaction'].get('BTC'):item['status']='REACTION'
            releases.append(item);attempts.append(dict(url=url,status='VERIFIED'))
        except Exception as exc:attempts.append(dict(url=url,status='UNAVAILABLE',error=type(exc).__name__,http_status=getattr(exc,'code',None)))
    latest=max(releases,key=lambda r:r['event_date']) if releases else None
    superseded=[]
    for item in releases:
        if latest and item['event_date']<latest['event_date']:item['status']='SUPERSEDED'
    for event in value.get('events',[]):
        if not latest:continue
        is_fed='Fed' in event.get('categories',[]) or 'FOMC' in event.get('title','')
        day=event.get('event_date')
        if is_fed and event.get('scheduled') and day and day<=latest['event_date']:
            event['lifecycle']='SUPERSEDED';superseded.append(event.get('id'))
        elif is_fed and not event.get('scheduled') and re.search(r'ahead of|await|preview|expected|will decide|before.*fed',event.get('title',''),re.I):
            pub=fundamentals.timestamp(event.get('published_at'));released=fundamentals.timestamp(latest.get('published_at'))
            if pub and released and pub<released:event['lifecycle']='SUPERSEDED';superseded.append(event.get('id'))
    extra,checks=economic_releases(value,now,fetcher)
    value['event_lifecycle']=dict(releases=releases+extra,attempts=attempts+checks,superseded_ids=superseded)
    return value

def lines(fund,now):
    lifecycle=fund.get('event_lifecycle',{});current=[e for e in lifecycle.get('releases',[]) if e['status']!='SUPERSEDED']
    out=[]
    for item in current[:2]:
        if item.get('kind')=='economic_release':
            out.extend([item['title']+' – RELEASED ('+item['published_at'][:16]+').',item['result_excerpt'],'Overená publikácia, konsenzus/prekvapenie a presná cenová reakcia N/A.'])
            continue
        at=fundamentals.timestamp(item.get('published_at'));rates=item.get('rate_range')
        out.append('FED '+item['status']+' — '+item['event_date']+(at.astimezone(BL).strftime(' %H:%M Bratislava') if at else ', čas publikácie N/A')+'.')
        out.append('Oficiálne cieľové pásmo: '+(f'{rates[0]:g}–{rates[1]:g} %.' if rates else 'N/A; číselný rozsah nebolo možné bezpečne extrahovať.'))
        if item.get('voting'):out.append('Hlasovanie: '+item['voting'][:280])
        if item.get('comments'):out.append('Komuniké Fedu: '+item['comments'][0][:260])
        out.append('Konsenzus/prekvapenie N/A. '+item['interpretation'])
        changes=item.get('reaction',{})
        if changes:
            out.append('Ceny medzi hodinovými uzavretiami okolo zverejnenia: '+', '.join(f"{s} {v['change_pct']:+.1f}%" for s,v in changes.items())+'. Časový súbeh nie je dôkaz príčiny.')
        else:out.append('Reakcia od overeného času zverejnenia N/A; chýbajú porovnateľné časové body.')
        out.append('Akcie/DXY/výnosy: reakcia od času rozhodnutia N/A bez porovnateľných kotácií.')
    if not current:
        due=[e for e in fund.get('events',[]) if e.get('scheduled') and e.get('lifecycle') in ('AWAITING_VERIFICATION','TIME_UNVERIFIED')]
        if due:out.append('Dnešné/uplynulé udalosti: výsledok N/A — čaká na oficiálne overenie; nejde o potvrdené budúce udalosti.')
    return out
