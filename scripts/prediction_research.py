"""Read-only live research, reproducible historical inputs, optional public paper output.
No Telegram, main.py, trading API or private inventory imports.
"""
import argparse,json,math,os,sys,time
from pathlib import Path
from datetime import datetime,timezone
from zoneinfo import ZoneInfo
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from v11 import prediction_research as research,prediction_journal as journal
from v11.prediction_shadow import COINS,HORIZONS,STEP,coin_view
from v11.analyst import price,pct
from v11.fundamental_analysis import analyze,ALIASES
from v11.state_policy import require_public_data
from scripts.v111_shadow import ShadowAPI,protected_hashes
from scripts.fundamental_sources_shadow import run as collect
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'shadow-output/prediction'
CODE_DIGEST=__import__('hashlib').sha256(b''.join((ROOT/p).read_bytes() for p in ('v11/prediction_research.py','v11/prediction_journal.py','scripts/prediction_research.py'))).hexdigest()
SOURCE=ROOT/'shadow-output/prediction-sources'
INPUTS=ROOT/'shadow-output/prediction-inputs'
BL=ZoneInfo('Europe/Bratislava')


def write(path,value):
    require_public_data(value);path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(path.suffix+'.tmp');tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False));tmp.replace(path)


def download_history(api,symbol,cutoff,limit=5000):
    end=cutoff-1;all_rows={}
    for _ in range(6):
        raw=api.http_json(f'https://data-api.binance.vision/api/v3/klines?symbol={symbol}USDT&interval=4h&limit=1000&endTime={end}',retries=2,timeout=15)
        if not isinstance(raw,list) or not raw:break
        for r in raw:
            if not isinstance(r,list) or len(r)<7:raise ValueError('Malformed OHLCV schema')
            if int(r[6])<cutoff:
                row=dict(timestamp=int(r[0]),open=float(r[1]),high=float(r[2]),low=float(r[3]),close=float(r[4]),volume=float(r[5]))
                if row['timestamp'] in all_rows and row!=all_rows[row['timestamp']]:raise ValueError('Conflicting candle')
                all_rows[row['timestamp']]=row
        next_end=int(raw[0][0])-1
        if next_end>=end:raise ValueError('Historical pagination did not progress')
        end=next_end
        if len(all_rows)>=limit:break
    rows=sorted(all_rows.values(),key=lambda r:r['timestamp'])[-limit:]
    if not research.valid(rows):raise ValueError('NO_DATA: malformed/gapped history')
    return rows


def current_vintages(fund,now_ms):
    """Conservative first-seen vintages, NEVER backdate today's revisions."""
    output=[]
    def add(symbol,feature,value,url):
        if not research.finite(value) or not isinstance(url,str) or not url.startswith('https://'):return
        payload=dict(symbol=symbol,feature=feature,value=value,available_at=now_ms,published_at=None,retrieved_at=now_ms,source_url=url)
        # Publication time is unknown; available_at is conservatively first seen now.
        payload['vintage_id']='first-seen:'+research.digest(payload);output.append(payload)
    macro=fund.get('macro_context',{});y=macro.get('treasury') or {}
    for k,name in [('2y','yield_2y'),('10y','yield_10y')]:add('*',name,y.get(k),macro.get('url'))
    names={'CPIAUCSL':'cpi','PCEPI':'pce','UNRATE':'unemployment','PAYEMS':'payrolls'}
    for key,v in fund.get('economic_observations',{}).get('observations',{}).items():
        if key in names:add('*',names[key],v.get('value'),v.get('url') or fund.get('economic_observations',{}).get('url'))
    for symbol,items in fund.get('project_economics',{}).get('observations',{}).items():
        for key,v in items.items():
            if symbol in COINS and key in ('fees','revenue'):add(symbol,key,v.get('value'),v.get('url'))
    # Provider timestamp is required for TVL; collection alone is not observation freshness.
    for symbol,v in fund.get('metrics',{}).items():
        if symbol in COINS and v.get('at'):add(symbol,'tvl',v.get('value'),v.get('url'))
    return output


def collect_endpoints(api,old,now_ms):
    observations={};errors=[]
    pending=[r for r in old['predictions'] if r.get('model_version') and not r.get('result') and r['due']+60000<=now_ms]
    # Bounded requests; exact minute OPEN at declared endpoint, never today's ticker.
    for r in pending[:48]:
        try:
            data=api.http_json(f"https://data-api.binance.vision/api/v3/klines?symbol={r['symbol']}USDT&interval=1m&limit=1&startTime={r['due']}&endTime={r['due']+59999}",retries=1,timeout=12)
            if len(data)!=1 or int(data[0][0])!=r['due']:raise ValueError('Exact paper endpoint missing')
            observations[r['symbol'],r['due']]=float(data[0][1])
        except Exception as exc:errors.append(dict(id=r['id'],error=type(exc).__name__))
    return observations,errors


def refresh_quotes(api,snapshot):
    """Get one bounded fresh quote batch after fitting; never mislabel old tickers."""
    from urllib.parse import urlencode
    query=urlencode({'symbols':json.dumps([s+'USDT' for s in COINS],separators=(',',':'))})
    try:
        ticks=api.http_json('https://data-api.binance.vision/api/v3/ticker/24hr?'+query,retries=1,timeout=12)
        by_symbol={r['symbol']:r for r in ticks};now_ms=time.time()*1000
        for symbol in COINS:
            c=snapshot['coins'].get(symbol,{});q=by_symbol.get(symbol+'USDT',{})
            value=api.safe_float(q.get('lastPrice'));at=api.safe_float(q.get('closeTime'))
            if value is not None and value>0 and at is not None and -1000<=now_ms-at<=60000:
                c.update(price=value,price_at=at,stale=False,paper_quote_confirmed=True)
            else:c['paper_quote_confirmed']=False
    except Exception:
        for c in snapshot['coins'].values():c['paper_quote_confirmed']=False


def paper_summary(state):
    output={}
    for symbol in COINS:
        output[symbol]={}
        for hours in (24,72,336):
            entries=[v for v in state['predictions'] if v.get('model_version')==research.VERSION and v['symbol']==symbol and v['requested_hours']==hours]
            all_completed=sorted((v for v in entries if v.get('result')),key=lambda v:v['created'])
            completed=[];last_due=-1
            for v in all_completed:
                if v['created']>=last_due:completed.append(v);last_due=v['due']
            rows=[]
            for v in completed:
                a=v['result'];rows.append(dict(a,width_pct=(v['high']-v['low'])/v['price']*100))
            baselines={}
            for name,key in [('flat','flat_error_pct'),('trend','trend_error_pct')]:
                e=[v['result'][key] for v in completed if v['result'].get(key) is not None]
                baselines[name]=dict(n=len(e),mae_pct=sum(e)/len(e) if e else None,mae_ci95=research.uncertainty(e))
            output[symbol][str(hours)]=dict(lifetime=state['totals'].get(f'{symbol}:{hours}',{}),status='FORWARD_PAPER' if completed else 'PENDING',pending=len(entries)-len(all_completed),retained_matured=len(all_completed),nonoverlapping_scored=len(completed),model=research.metrics(rows),baselines=baselines)
    return output


def forward_records(results,snapshot,now_ms,run_id):
    records=[]
    for symbol,r in results.items():
        coin=snapshot['coins'].get(symbol,{})
        if r.get('status')!='RESEARCH_ONLY' or coin.get('stale',True) or not research.finite(coin.get('price')) or coin['price']<=0 or not coin.get('paper_quote_confirmed'):continue
        source_close=r['source_end']+STEP
        if not 0<=now_ms-source_close<=STEP:continue
        for label,f in r['live'].items():
            hours=HORIZONS[label]*4;p=coin['price'];ratio=p/f['price'];due=math.ceil((now_ms+hours*3600000)/60000)*60000
            records.append(dict(id=f'{research.VERSION}:{run_id}:{symbol}:{hours}',symbol=symbol,created=now_ms,due=due,price=p,
                point=f['point']*ratio,low=f['low']*ratio,high=f['high']*ratio,direction=f['direction'],
                continuation=p*math.exp(f['trend_log_return']),model_version=research.VERSION,model=f['model'],
                source_digest=r['input_digest'],btc_digest=r['btc_digest'],requested_hours=hours,tolerance_log=math.log1p(f['tolerance_pct']/100),
                source_cutoff=now_ms,source_close=source_close,source_mode='FORWARD_PAPER',
                inputs=dict(features=f['input_features'],volatility_4h=f['volatility_4h'],regime=f['regime'],model_code_digest=CODE_DIGEST,vintage_digest=r['vintage_digest'])))
    return records


def audit_request_numbers(results):
    # Request supplied these values; they are NOT silently treated as verified artifacts.
    supplied={'SOL':[2.68,2.19,4.67,3.68],'TAO':[4.,3.37,8.30,6.17],'FET':[5.39,4.65,10.07,8.30],
              'AAVE':[3.67,3.32,6.60,5.58],'ONDO':[4.26,3.94,8.72,6.96],'RENDER':[3.90,3.52,8.27,6.77]}
    return dict(status='ORIGINAL_RUN_ARTIFACT_UNAVAILABLE',run_id='40695605050',reason='GitHub artifact API Forbidden; new history is a separate experiment, not verification of supplied numbers',supplied_mae_pct=supplied)


def report(results,live,snapshot,fund,source_summary,journal_state):
    lines=['# Prediction research V2 — no production activation','',
        'Historical research, not new independent confirmation. No calibrated probabilities. Every test origin is spaced by its horizon; approximate confidence intervals can still understate serial dependence.',
        '', '|Coin|Horizon|Selected using validation|Test n|MAE %|Flat MAE %|Direction %|Band coverage %|',
        '|---|---|---|---:|---:|---:|---:|---:|']
    for s,r in results.items():
        if r.get('status')!='RESEARCH_ONLY':lines.append(f'|{s}|NO_DATA|||||||');continue
        for h,part in r['results'].items():
            m=part['selected_on_validation'];a=part['models'][m]['test'] if m else {};flat=part['models']['flat']['test']
            if a.get('n'):
                lines.append(f"|{s}|{h}|{m}|{a['n']}|{a['mae_pct']:.3f}|{flat['mae_pct']:.3f}|{100*a['direction_accuracy']:.1f}|{100*a['band_coverage']:.1f}|")
    lines+=['','Complete validation/test metrics, median errors, CIs, confusion matrices, regimes and paired comparisons: diagnostics.json.',
        'Fundamental ablations without valid archived inputs are NO_POINT_IN_TIME_HISTORY, not zero improvement.',
        'Paper results are separate. Legacy forecasts have ambiguous backdated origins and are not future confirmation.',
        f"New-version paper forecasts: {sum(bool(r.get('model_version')) for r in journal_state['predictions'])}; matured: {sum(bool(r.get('result')) for r in journal_state['predictions'] if r.get('model_version'))}.",
        'No automatic production promotion; historical selection is not proof, especially after testing multiple hypotheses.']
    return '\n'.join(lines)+'\n'


def run(reuse=False,reuse_histories=False):
    before=protected_hashes();OUT.mkdir(parents=True,exist_ok=True);INPUTS.mkdir(parents=True,exist_ok=True)
    for symbol in COINS:
        stale=OUT/(symbol+'-origins.json')
        if stale.exists():stale.unlink()
    started=int(time.time()*1000)
    if not reuse:collect(SOURCE,False)
    snapshot=json.loads((SOURCE/'market_snapshot.json').read_text());fund=json.loads((SOURCE/'fundamentals.json').read_text())
    if not 0<=time.time()-snapshot.get('at',0)<=900:raise ValueError('Stale live snapshot; no preview/paper publication')
    reference=ROOT/'public-analytics/prediction-shadow.json'
    old=journal.load(json.loads(reference.read_text()) if reference.exists() else [])
    reference_digest=__import__('hashlib').sha256(reference.read_bytes()).hexdigest() if reference.exists() else None
    api=ShadowAPI(False);histories={};errors={}
    for s in ('BTC',*COINS):
        try:
            cache=INPUTS/(s+'.json')
            rows=json.loads(cache.read_text()) if reuse_histories and cache.exists() else download_history(api,s,started)
            if rows[-1]['timestamp']+STEP>started:raise ValueError('Future/unclosed historical candle')
            histories[s]=rows;write(cache,rows)
        except Exception as exc:errors[s]=type(exc).__name__
    results={}
    for symbol in COINS:
        if symbol not in histories or 'BTC' not in histories:
            results[symbol]=dict(status='NO_DATA',error='HistoricalSourceUnavailable');continue
        try:
            results[symbol]=research.experiment(histories[symbol],histories['BTC'],symbol,old['input_vintages'])
            write(OUT/(symbol+'-origins.json'),results[symbol].pop('records'))
        except ValueError as exc:
            if not str(exc).startswith('NO_DATA:'):raise
            results[symbol]=dict(status='NO_DATA',error='HistoricalValidationFailed');errors[symbol]='HistoricalValidationFailed'
    refresh_quotes(api,snapshot)
    now=datetime.now(timezone.utc);now_ms=int(now.timestamp()*1000)
    if not 0<=now.timestamp()-snapshot.get('at',0)<=900:raise ValueError('Snapshot expired during research; recollect before preview')
    vintage=current_vintages(fund,now_ms)
    run_id=os.getenv('GITHUB_RUN_ID') or 'local-'+str(started)
    records=forward_records(results,snapshot,now_ms,run_id)
    if int(os.getenv('GITHUB_RUN_ATTEMPT','1'))>1:
        existing={r['id'] for r in old['predictions']}
        records=[r for r in records if r['id'] in existing] # no new forecast for an old rerun outside retention
    observations,endpoint_errors=collect_endpoints(api,old,now_ms)
    updated=journal.update(old,records,vintage,observations,now_ms)
    from v11.prediction_runtime import package
    updated['runtime_package']=package(results,now_ms)
    journal.load(updated)
    evidence=analyze(fund,now)
    preview=['VÝSKUM V2 — NEAKTÍVNE, nie potvrdené odporúčania',now.astimezone(BL).strftime('%d.%m.%Y %H:%M Bratislava'),
        'Nové nákupy WAIT; súkromné držby sa nenačítavajú. Istota NÍZKA. Kalibrované pravdepodobnosti N/A.']
    for s,r in results.items():
        c=snapshot['coins'].get(s,{})
        preview.append(f"\n{s} — {price(c.get('price') if not c.get('stale',True) else None)} | WAIT")
        if not r.get('live'):preview.append('Predikcia NO_DATA.');continue
        v=coin_view(c);origin_records=[z for z in records if z['symbol']==s]
        if not origin_records:preview.append('Živé predikcie N/A: chýba čerstvá overená cena alebo uzavretá história; historický test je samostatný.')
        for label,f in r['live'].items():
            p=next((z for z in origin_records if z['requested_hours']==HORIZONS[label]*4),None)
            if p is None:continue
            preview.append(f"{label}: {f['direction']} — {price(p['low'])}–{price(p['high'])} ({pct((p['low']/p['price']-1)*100)} až {pct((p['high']/p['price']-1)*100)}). Model {f['model']}; nejde o preukázaný najpravdepodobnejší smer.")
        if v.get('status')!='NO_DATA':
            preview.append(f"Dôvod: {v['trend']}, {v['reversal']}; objem {v['volume_ratio']:.2f}× priemeru." if v['volume_ratio'] is not None else 'Objem N/A.')
            preview.append(f"Alternatíva: prerazenie rezistencie podporí rast; strata podpory {price(v['invalidates'])} mení výhľad. {v['confirmation']}.")
        relevant=[e for e in evidence['evidence'] if e['material'] and __import__('re').search(ALIASES[s],e['title'],__import__('re').I)]
        if relevant:
            e=relevant[0];preview.append(f"Fundament: {e['title']} ({e['published_at']}); {e['impact']}. {e['url']}")
        else:preview.append('Nový významný projektový fundament nepotvrdený. Fundamentálny prínos modelu zatiaľ neoverený.')
    preview+=['\nModely nie sú produkčne overené. Dôležitá nová udalosť ruší platnosť scenára; žiadny automatický BUY/SELL.']
    source_summary=json.loads((SOURCE/'summary.json').read_text())
    artifact=dict(version=research.VERSION,model_code_digest=CODE_DIGEST,results=results,errors=errors,endpoint_errors=endpoint_errors,
        request_number_audit=audit_request_numbers(results),source_summary=source_summary,
        independent_validation=False,production_enabled=False,paper_created=len(records),paper_matured=sum(bool(r.get('result')) for r in updated['predictions'] if r.get('model_version')),
        truncation_count=max(0,len(old['predictions'])+len(records)-len(updated['predictions'])))
    write(OUT/'paper-results.json',paper_summary(updated))
    write(OUT/'diagnostics.json',artifact);write(OUT/'public-predictions.json',updated)
    write(OUT/'journal-manifest.json',dict(previous_sha256=reference_digest))
    write(OUT/'source-diagnostics.json',json.loads((SOURCE/'source_diagnostics.json').read_text()))
    write(OUT/'input-manifest.json',dict(methodology=research.VERSION,model_code_digest=CODE_DIGEST,numpy=research.np.__version__,python=sys.version.split()[0],started=started,created=now_ms,histories={s:dict(digest=research.digest(r),n=len(r),first=r[0]['timestamp'],last=r[-1]['timestamp']) for s,r in histories.items()}))
    # Reproducibility: public market data only, never private source snapshots.
    write(OUT/'historical-inputs.json',histories)
    write(OUT/'current-public-inputs.json',dict(snapshot=snapshot,fundamentals=fund))
    (OUT/'preview.txt').write_text('\n'.join(preview)+'\n')
    (OUT/'REPORT.md').write_text(report(results,records,snapshot,fund,source_summary,updated))
    assert before==protected_hashes(),'Production files modified'
    if len(results)!=6 or all(r.get('status')=='NO_DATA' for r in results.values()):raise ValueError('NO_DATA: all experiments failed')
    print('V2 research completed; no production activation, Telegram or private data.')
    return artifact

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--reuse-collected-sources',action='store_true');parser.add_argument('--reuse-histories',action='store_true');a=parser.parse_args();run(a.reuse_collected_sources,a.reuse_histories)
