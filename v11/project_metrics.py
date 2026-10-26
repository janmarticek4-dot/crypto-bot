"""Free DeFiLlama observations. Fees/revenue are protocol/network, not token cashflow."""
import json
import math
from datetime import datetime,timezone,timedelta

SOURCES=(
    ('AAVE','fees','https://api.llama.fi/summary/fees/aave?dataType=dailyFees'),
    ('AAVE','revenue','https://api.llama.fi/summary/fees/aave?dataType=dailyRevenue'),
    ('SOL','fees','https://api.llama.fi/overview/fees/Solana?excludeTotalDataChart=false&excludeTotalDataChartBreakdown=true&dataType=dailyFees'),
)

def parse(raw,now,expected_type=None):
    obj=json.loads(raw)
    if not isinstance(obj,dict) or not isinstance(obj.get('totalDataChart'),list):raise ValueError('FEES_CHART_SCHEMA_MISSING')
    if expected_type and obj.get('dataType') and obj['dataType']!=expected_type:raise ValueError('METRIC_TYPE_MISMATCH')
    rows=obj['totalDataChart']
    if not isinstance(rows,list):raise ValueError('Unexpected chart')
    values={}
    for row in rows:
        try:
            if not isinstance(row,list) or len(row)!=2 or isinstance(row[0],bool) or isinstance(row[1],bool):continue
            day=datetime.fromtimestamp(float(row[0]),timezone.utc)
            value=float(row[1])
            # Daily aggregates are admissible only after the complete UTC day.
            if day.hour or day.minute or not math.isfinite(value) or value<0 or not timedelta(days=1)<=now-day<=timedelta(days=2):continue
            values[day.isoformat()]=value
        except (ValueError,TypeError,OverflowError,OSError):continue
    dates=sorted(values)
    if not dates:return None
    latest=dates[-1]
    return dict(metric_type=obj.get('dataType') or expected_type,metric_type_confirmation='response_metadata' if obj.get('dataType') else 'request_query_only',period=latest,value=values[latest],unit='USD/day',previous_period=dates[-2] if len(dates)>1 else None,
                previous_value=values[dates[-2]] if len(dates)>1 else None,
                status='latest_provider_aggregate_not_final_audited_revenue')


def collect(fetcher,now):
    observations={};statuses=[]
    for symbol,kind,url in SOURCES:
        status=dict(symbol=symbol,metric=kind,url=url,retrieved_at=now.isoformat(),status='N/A')
        try:
            value=parse(fetcher(dict(url=url)),now,expected_type='dailyRevenue' if kind=='revenue' else 'dailyFees')
            if value:
                observations.setdefault(symbol,{})[kind]=dict(value,url=url,retrieved_at=now.isoformat(),published_at=None)
                status['status']='OK'
            else:status['error']='NO_RECENT_CLOSED_DAILY_AGGREGATE'
        except Exception as exc:status['error']=type(exc).__name__
        statuses.append(status)
    return dict(observations=observations,sources=statuses)
