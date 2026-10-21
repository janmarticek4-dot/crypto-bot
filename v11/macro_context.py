"""Public Treasury yield observations, not real-time DXY or a macro consensus."""
import math
import xml.etree.ElementTree as ET
from datetime import datetime,timezone,timedelta
from .fundamentals import fetch,timestamp


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
    return max(rows,key=lambda r:r['date']) if rows else None


def collect(state,now=None,fetcher=fetch):
    now=now or datetime.now(timezone.utc)
    cache=state.get('macro_context_v111',{})
    checked=timestamp(cache.get('checked_at'))
    if checked and timedelta(0)<=now-checked<timedelta(hours=1):return cache
    url=f'https://home.treasury.gov/resource-center-data-chart-center/interest-rates/pages/xml?data=daily_treasury_yield_curve&field_tdr_date_value={now.year}'
    result=dict(checked_at=now.isoformat(),treasury=None,url=url)
    try:result['treasury']=parse_treasury(fetcher(dict(url=url)),now)
    except Exception as exc:result['error_type']=type(exc).__name__
    state['macro_context_v111']=result
    return result


def lines(result):
    item=result.get('treasury')
    out=[f"US Treasury {item['date']}: 2Y {item['2y']:.2f} %, 10Y {item['10y']:.2f} %; denné pozorovanie, nie živá kotácia. {result['url']}" if item else 'US Treasury výnosy: N/A.']
    out.append('DXY, overený sadzbový konsenzus a ETF toky: N/A bez dostupného licencovaného/primárneho zdroja.')
    return out
