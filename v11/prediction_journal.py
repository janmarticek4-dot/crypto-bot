"""Separate public research journal; strict schema, immutable original forecasts.
Legacy V1 origins were backdated to candle closes, so are NOT prospective evidence.
"""
import copy,math
from .prediction_shadow import COINS
from .prediction_research import VERSION,MACRO,PROJECT,validate_vintage,digest,direction
from .state_policy import require_public_data

SCHEMA='prediction-research-journal-v2'
OLD={'id','symbol','created','due','price','point','low','high','direction','continuation','result'}
NEW={'model_version','model','source_digest','btc_digest','requested_hours','tolerance_log','source_cutoff','source_close','source_mode','inputs'}

def validate_record(row):
    if not isinstance(row,dict) or set(row)-(OLD|NEW):raise ValueError('Unexpected journal field')
    if row.get('symbol') not in COINS or not isinstance(row.get('id'),str) or not 0<len(row['id'])<=180:raise ValueError('Invalid public forecast ID')
    for key in ('created','due','price','point','low','high'):
        if type(row.get(key)) not in (int,float) or not math.isfinite(row[key]):raise ValueError('Invalid forecast value')
    if row['due']<=row['created'] or min(row['price'],row['point'],row['low'])<=0 or row['low']>row['high']:raise ValueError('Invalid horizon or interval')
    if row.get('model_version'):
        if not NEW<=set(row) or row['source_mode']!='FORWARD_PAPER':raise ValueError('Incomplete paper provenance')
        if row['requested_hours'] not in (24,72,336) or row['model_version']!=VERSION:raise ValueError('Unsupported version/horizon')
        if not all(type(row[k]) in (int,float) and math.isfinite(row[k]) for k in ('source_close','source_cutoff')) or not 0<=row['source_close']<=row['source_cutoff']<=row['created']:raise ValueError('Future source in paper forecast')
        # Target is a UTC minute boundary, <= 60s after exact requested horizon.
        lag=row['due']-row['created']-row['requested_hours']*3600000
        if not 0<=lag<60000 or row['due']%60000:raise ValueError('Invalid explicit paper endpoint')
        if not isinstance(row['model'],str) or not isinstance(row['source_digest'],str) or len(row['source_digest'])!=64 or not isinstance(row['btc_digest'],str) or len(row['btc_digest'])!=64:raise ValueError('Invalid model provenance')
        if type(row['tolerance_log']) not in (float,int) or not math.isfinite(row['tolerance_log']) or row['tolerance_log']<0:raise ValueError('Invalid direction tolerance')
    if row.get('model_version'):
        info=row['inputs']
        if not isinstance(info,dict) or set(info)!={'features','volatility_4h','regime','model_code_digest','vintage_digest'}:raise ValueError('Invalid input provenance')
        if len(info['features'])!=10 or not all(type(v) in (int,float) and math.isfinite(v) for v in info['features']):raise ValueError('Invalid feature vector')
        if type(info['volatility_4h']) not in (int,float) or not math.isfinite(info['volatility_4h']) or info['volatility_4h']<=0:raise ValueError('Invalid volatility provenance')
    if row.get('model_version') and row.get('result') is not None:
        answer=row['result']
        required={'actual','actual_at','evaluated_at','actual_direction','predicted_direction','direction_correct','inside','actual_return_pct','abs_error_pct','flat_error_pct','trend_error_pct','tallied'}
        if not isinstance(answer,dict) or set(answer)!=required:raise ValueError('Invalid paper result schema')
        for key in ('actual','actual_at','evaluated_at','actual_return_pct','abs_error_pct','flat_error_pct'):
            if type(answer[key]) not in (float,int) or not math.isfinite(answer[key]):raise ValueError('Invalid paper result')
        if answer['actual']<=0 or answer['actual_at']!=row['due'] or answer['evaluated_at']<row['due']:raise ValueError('Invalid endpoint provenance')
        if type(answer['inside']) is not bool or type(answer['direction_correct']) is not bool or type(answer['tallied']) is not bool:raise ValueError('Invalid hit indicator')
    require_public_data(row)
    return row

def load(value):
    if isinstance(value,list):value=dict(schema=SCHEMA,predictions=value,input_vintages=[],totals={})
    if not isinstance(value,dict) or set(value)!={'schema','predictions','input_vintages','totals'} or value['schema']!=SCHEMA:raise ValueError('Invalid journal schema')
    if not isinstance(value['predictions'],list) or len(value['predictions'])>600 or not isinstance(value['input_vintages'],list) or len(value['input_vintages'])>10000:raise ValueError('Journal limit exceeded')
    totals=value['totals']
    fields={'n','direction_hits','band_hits','error_sum_pct','flat_error_sum_pct','trend_error_sum_pct','trend_n'}
    if not isinstance(totals,dict) or len(totals)>18:raise ValueError('Invalid lifetime totals')
    for key,item in totals.items():
        if key not in {f'{s}:{h}' for s in COINS for h in (24,72,336)} or set(item)!=fields:raise ValueError('Invalid total slot')
        if not all(type(v) in (int,float) and math.isfinite(v) and v>=0 for v in item.values()):raise ValueError('Invalid total value')
        if item['direction_hits']>item['n'] or item['band_hits']>item['n'] or item['trend_n']>item['n']:raise ValueError('Inconsistent totals')
    for r in value['predictions']:validate_record(r)
    ids=[r['id'] for r in value['predictions']]
    if len(ids)!=len(set(ids)):raise ValueError('Duplicate persisted forecast')
    for v in value['input_vintages']:validate_vintage(v)
    require_public_data(value)
    return copy.deepcopy(value)

def update(value,records,vintages,observations,now_ms):
    result=load(value);items={r['id']:r for r in result['predictions']}
    for r in records:
        validate_record(r)
        if r['created']>now_ms:raise ValueError('Future forecast creation')
        # Same intentional run ID retains first forecast even if rerun fetches new data.
        items.setdefault(r['id'],copy.deepcopy(r))
    for r in items.values():
        if r.get('result') or not r.get('model_version') or r['due']>now_ms:continue
        actual=observations.get((r['symbol'],r['due']))
        if actual is None:continue
        if type(actual) not in (float,int) or not math.isfinite(actual) or actual<=0:raise ValueError('Invalid endpoint observation')
        actual_log=math.log(actual/r['price']);predicted_log=math.log(r['point']/r['price'])
        r['result']=dict(actual=actual,actual_at=r['due'],evaluated_at=now_ms,actual_direction=direction(actual_log,r['tolerance_log']),
            predicted_direction=direction(predicted_log,r['tolerance_log']),direction_correct=direction(actual_log,r['tolerance_log'])==direction(predicted_log,r['tolerance_log']),
            inside=r['low']<=actual<=r['high'],actual_return_pct=(actual/r['price']-1)*100,
            abs_error_pct=abs(r['point']-actual)/r['price']*100,flat_error_pct=abs(r['price']-actual)/r['price']*100,
            trend_error_pct=abs(r['continuation']-actual)/r['price']*100 if r.get('continuation') else None,tallied=False)
    for r in items.values():
        if not r.get('model_version') or not r.get('result') or r['result'].get('tallied'):continue
        a=r['result'];key=f"{r['symbol']}:{r['requested_hours']}"
        t=result['totals'].setdefault(key,dict(n=0,direction_hits=0,band_hits=0,error_sum_pct=0.,flat_error_sum_pct=0.,trend_error_sum_pct=0.,trend_n=0))
        t['n']+=1;t['direction_hits']+=int(a['direction_correct']);t['band_hits']+=int(a['inside'])
        t['error_sum_pct']+=a['abs_error_pct'];t['flat_error_sum_pct']+=a['flat_error_pct']
        if a['trend_error_pct'] is not None:t['trend_n']+=1;t['trend_error_sum_pct']+=a['trend_error_pct']
        a['tallied']=True
    # Keep pending forecasts before completed rows; disclose discarded count in run report.
    values=sorted(items.values(),key=lambda r:r['created'])
    pending=[r for r in values if not r.get('result')];done=[r for r in values if r.get('result')]
    if len(pending)>600:raise ValueError('Journal full: refusing to discard pending paper forecasts')
    result['predictions']=(done[-max(0,600-len(pending)):] if len(pending)<600 else [])+pending[-600:]
    def vintage_key(r):return (r['symbol'],r['feature'],r['value'],r['source_url'],int(r['available_at']//86400000))
    v={vintage_key(r):r for r in result['input_vintages']}
    for r in vintages:validate_vintage(r);v.setdefault(vintage_key(r),r)
    result['input_vintages']=sorted(v.values(),key=lambda r:r['available_at'])[-10000:]
    return load(result)
