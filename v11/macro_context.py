"""Public Treasury yield observations, not real-time DXY or a macro consensus."""
import math
import csv
import io
import xml.etree.ElementTree as ET
from datetime import datetime,timezone,timedelta
from .fundamentals import fetch,timestamp


def yield_comparison(rows):
    ordered=sorted({r['date']:r for r in rows}.values(),key=lambda r:r['date'])
    if not ordered:return None
    latest=dict(ordered[-1])
    if len(ordered)>1:
        previous=ordered[-2]
        latest.update(previous_date=previous['date'],change_bp={k:round((latest[k]-previous[k])*100,3) for k in ('2y','10y')})
    return latest


def parse_treasury(raw,now):
    rows=[]
    for node in ET.fromstring(raw).iter():
        if node.tag.rsplit('}',1)[-1]!='properties':continue
        fields={c.tag.rsplit('}',1)[-1]:c.text for c in node}
        try:
            date=datetime.fromisoformat(fields['NEW_DATE']).date()
            lag=(now.date()-date).days
            if not 0<=lag<=5:continue
            values={}
            for name,key in [('2y','BC_2YEAR'),('10y','BC_10YEAR')]:
                value=float(fields[key])
                if not math.isfinite(value) or not -5<=value<=30:raise ValueError('invalid yield')
                values[name]=value
            rows.append(dict(date=date.isoformat(),**values))
        except (ValueError,KeyError,TypeError):continue
    return yield_comparison(rows)


def parse_fred(raw,now):
    rows=[]
    for row in csv.DictReader(io.StringIO(raw.decode('utf-8-sig'))):
        try:
            day=datetime.fromisoformat(row.get('observation_date',row.get('DATE',''))).date()
            if not 0<=(now.date()-day).days<=5:continue
            a,b=float(row['DGS2']),float(row['DGS10'])
            if not all(math.isfinite(x) and -5<=x<=30 for x in (a,b)):continue
            rows.append(dict(date=day.isoformat(),**{'2y':a,'10y':b}))
        except (ValueError,KeyError,TypeError):continue
    return yield_comparison(rows)


def collect(state,now=None,fetcher=fetch):
    now=now or datetime.now(timezone.utc)
    cache=state.get('macro_context_v111',{})
    checked=timestamp(cache.get('checked_at'))
    if checked and timedelta(0)<=now-checked<timedelta(hours=1):return cache
    monthly=f'https://home.treasury.gov/resource-center-data-chart-center/interest-rates/pages/xml?data=daily_treasury_yield_curve&field_tdr_date_value_month={now:%Y%m}'
    fred='https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS2,DGS10&cosd='+str((now-timedelta(days=10)).date())
    result=dict(checked_at=now.isoformat(),treasury=None,url=monthly,attempts=[])
    for source,parser in [(dict(url=monthly),parse_treasury),(dict(url=fred),parse_fred)]:
        try:
            value=parser(fetcher(source),now)
            result['attempts'].append(dict(url=source['url'],status='OK' if value else 'N/A'))
            if value:
                result.update(treasury=value,url=source['url']);break
        except Exception as exc:
            result['attempts'].append(dict(url=source['url'],status='N/A',error_type=type(exc).__name__))
    if not result['treasury']:result['error_type']='SourcesUnavailable'
    state['macro_context_v111']=result
    return result


def lines(result):
    item=result.get('treasury')
    out=[f"US Treasury {item['date']}: 2Y {item['2y']:.2f} %, 10Y {item['10y']:.2f} %; denné pozorovanie, nie živá kotácia. {result['url']}" if item else 'US Treasury výnosy: N/A.']
    out.append('DXY, overený sadzbový konsenzus a ETF toky: N/A bez dostupného licencovaného/primárneho zdroja.')
    return out


def economic_observations(now,fetcher=fetch):
    """Latest revised monthly levels, NOT consensus or first-release vintages."""
    names={'CPIAUCSL':('CPI index','index'),'PCEPI':('PCE index','index'),
           'UNRATE':('Nezamestnanosť','%'),'PAYEMS':('Nonfarm zamestnanosť','tisíc osôb')}
    url='https://fred.stlouisfed.org/graph/fredgraph.csv?id='+','.join(names)+'&cosd='+str((now-timedelta(days=500)).date())
    result={'url':url,'checked_at':now.isoformat(),'observations':{},'consensus':None,'first_release':False}
    try:
        rows=list(csv.DictReader(io.StringIO(fetcher(dict(url=url)).decode('utf-8-sig'))))
        for series,(label,unit) in names.items():
            valid=[]
            for row in rows:
                try:
                    day=datetime.fromisoformat(row.get('observation_date',row.get('DATE',''))).date();value=float(row[series])
                    if math.isfinite(value) and value>=0 and 0<=(now.date()-day).days<=500:valid.append((day,value))
                except (ValueError,TypeError,KeyError):continue
            valid.sort()
            if not valid or (now.date()-valid[-1][0]).days>90:continue
            day,value=valid[-1]
            result['observations'][series]={'label':label,'unit':unit,'period':day.isoformat(),'value':value,
                'previous_period':valid[-2][0].isoformat() if len(valid)>1 else None,
                'previous_value':valid[-2][1] if len(valid)>1 else None,
                'release_at':None,'consensus':None,'vintage':'latest_revised_not_first_release'}
    except Exception as exc:result['error_type']=type(exc).__name__
    return result


def economic_lines(result):
    out=['Makro merania (najnovšie dostupné revidované hodnoty, nie konsenzus):']
    for item in result.get('observations',{}).values():
        out.append(f"{item['label']}: {item['value']:,.2f} {item['unit']}; obdobie {item['period']}. Čas prvého zverejnenia N/A.")
    if not result.get('observations'):out.append('N/A — aktuálne overiteľné merania nedostupné.')
    out.append('Zdroj: '+result['url']+'; načítané '+result['checked_at']+'. Merané obdobie nie je dátum zverejnenia; prekvapenie voči trhu N/A.')
    return out
