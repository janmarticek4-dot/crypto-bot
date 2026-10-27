"""Isolated real-source diagnostics and one evening preview; never delivery/state I/O."""
import argparse
import csv
import io
import re
from datetime import datetime,timezone,timedelta
import json
import math
from pathlib import Path
import socket
import ssl
import sys
import threading
import time
import urllib.error
import xml.etree.ElementTree as ET
from urllib.parse import urlsplit,parse_qs
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.v111_shadow import ShadowAPI,SYMBOLS,protected_hashes,render,outage_checks,write_json
from v11 import data,fundamentals,macro_context,project_metrics
from v11.fundamental_analysis import analyze

ROOT=Path(__file__).resolve().parents[1]


def error_details(exc):
    if isinstance(exc,fundamentals.SourcePolicyError):return dict(status='SOURCE_POLICY_ERROR',error_type=type(exc).__name__,http_status=None,error_layer='response_policy',error_code=exc.reason_code)
    reason=getattr(exc,'reason',None)
    if 'Tunnel connection failed: 403' in str(reason):return dict(status='NETWORK_BLOCKED',error_type=type(exc).__name__,http_status=403,error_layer='network_tunnel')
    if isinstance(exc,urllib.error.HTTPError):return dict(status='HTTP_ERROR',error_type=type(exc).__name__,http_status=exc.code,error_layer='origin_or_gateway')
    if isinstance(reason,socket.gaierror):layer='dns'
    elif isinstance(reason,ssl.SSLError):layer='tls'
    elif isinstance(exc,(TimeoutError,socket.timeout)) or isinstance(reason,(TimeoutError,socket.timeout)):layer='timeout'
    else:layer='transport'
    return dict(status='TRANSPORT_ERROR',error_type=type(exc).__name__,http_status=None,error_layer=layer)


def inspect(raw,source,now):
    """Separate HTTP retrieval, schema, freshness and relevance; no raw bodies stored."""
    url=source['url'];host=urlsplit(url).hostname;fmt=source.get('format')
    out=dict(format=fmt or 'rss_atom',latest_observation=None,publication_at=None,publication_status='N/A',relevant_items=0)
    if fmt in ('ics','fomc_html'):
        if fmt=='ics':
            if b'BEGIN:VCALENDAR' not in raw or b'END:VCALENDAR' not in raw:raise ValueError('ICS_SCHEMA_MISSING')
            audit={};items=fundamentals.parse_calendar(raw,source,now,audit);out['calendar_audit']=audit
        else:
            if not re.search(rb'20\d{2}\s+FOMC Meetings',raw):raise ValueError('FOMC_SCHEMA_MISSING')
            items=fundamentals.parse_fomc(raw,source,now)
        out.update(status='OK_CURRENT' if items else 'OK_NO_UPCOMING_PARSED_EVENTS',schema_valid=True,
                   provides='overené dátumy plánovaných udalostí; presný čas len ak uvedený so zónou',
                   relevant_items=len(items),dates=[i.get('event_at') or i.get('event_date') for i in items],
                   freshness='budúce termíny podľa kalendára; publikovanie N/A')
        return out
    if host=='home.treasury.gov' or host=='fred.stlouisfed.org':
        if host=='home.treasury.gov':
            if ET.fromstring(raw).tag.rsplit('}',1)[-1]!='feed':raise ValueError('TREASURY_XML_SCHEMA_MISSING')
            value=macro_context.parse_treasury(raw,now);provides='denné výnosy US 2Y/10Y'
        elif 'DGS2' in url:value=macro_context.parse_fred(raw,now);provides='denné výnosy US 2Y/10Y (FRED záloha)'
        else:
            # Use the same revision-aware parser without another HTTP request.
            observations=macro_context.economic_observations(now,fetcher=lambda _:raw)['observations']
            value=observations;provides='posledné revidované CPI/PCE/UNRATE/PAYEMS, nie konsenzus ani prvý release'
        if host=='fred.stlouisfed.org':
            headers=csv.DictReader(io.StringIO(raw.decode('utf-8-sig'))).fieldnames or []
            required=('DGS2','DGS10') if 'DGS2' in url else ('CPIAUCSL','PCEPI','UNRATE','PAYEMS')
            if not ({'observation_date','DATE'} & set(headers)) or not set(required)<=set(headers):raise ValueError('FRED_CSV_SCHEMA_MISSING')
        out.update(format='treasury_xml' if host=='home.treasury.gov' else 'fred_csv',schema_valid=True,
                   status='OK_CURRENT' if value else 'NO_RECENT_VALID_OBSERVATIONS',provides=provides,
                   latest_observation=value,freshness='výnosy najviac 5 dní; merané makro obdobie najviac 90 dní')
        return out
    if host=='api.llama.fi':
        obj=json.loads(raw)
        if '/tvl/' in url:
            if type(obj) not in (int,float) or not math.isfinite(obj) or obj<0:raise ValueError('TVL_VALUE_SCHEMA_MISSING')
            out.update(format='json_numeric',schema_valid=True,status='OBSERVED_ASOF_UNKNOWN',latest_observation={'value':obj,'provider_asof':None},provides='TVL estimate; čas merania poskytovateľa nie je uvedený',freshness='N/A — čas zberu nie je čas merania')
            return out
        if '/fees/' in url:
            expected=parse_qs(urlsplit(url).query).get('dataType',['dailyFees'])[0]
            if not isinstance(obj,dict) or 'totalDataChart' not in obj:raise ValueError('FEES_CHART_SCHEMA_MISSING')
            if obj.get('dataType') and obj['dataType']!=expected:raise ValueError('METRIC_TYPE_MISMATCH')
            value=project_metrics.parse(raw,now);provides=expected+'; agregát protokolu/siete, nie príjem držiteľa tokenu'
        else:
            rows=obj.get('tvl') if isinstance(obj,dict) else obj
            if not isinstance(rows,list):raise ValueError('TVL_SERIES_SCHEMA_MISSING')
            values=[]
            for row in rows:
                try:
                    at=datetime.fromtimestamp(row['date'],timezone.utc);v=row.get('totalLiquidityUSD',row.get('tvl'))
                    if type(v) in (int,float) and math.isfinite(v) and v>=0 and timedelta(0)<=now-at<=timedelta(hours=48):values.append(dict(period=at.isoformat(),value=v))
                except (ValueError,TypeError,KeyError,OverflowError,OSError):continue
            value=max(values,key=lambda r:r['period']) if values else None;provides='TVL v USD; nie používatelia, príjmy alebo čistý tok'
        out.update(format='json_timeseries',schema_valid=True,status='OK_CURRENT' if value else 'NO_RECENT_VALID_OBSERVATIONS',
                   latest_observation=value,provides=provides,freshness='najviac 48 hodín; fees/revenue iba uzavretý UTC deň')
        return out
    root=ET.fromstring(raw)
    if root.tag.rsplit('}',1)[-1] not in ('rss','feed'):raise ValueError('RSS_ATOM_SCHEMA_MISSING')
    entries=[n for n in root.iter() if n.tag.rsplit('}',1)[-1] in ('item','entry')]
    dates=[fundamentals.timestamp(e.text) for n in entries for e in n.iter() if e.tag.rsplit('}',1)[-1] in ('pubDate','published','updated')]
    dates=[d for d in dates if d and d<=now]
    latest=max(dates) if dates else None
    items=fundamentals.parse_feed(raw,source,now)
    status='OK_CURRENT' if items else 'STALE' if latest and now-latest>timedelta(hours=72) else 'OK_NO_RECENT_RELEVANT_ITEMS'
    out.update(schema_valid=True,status=status,publication_at=latest.isoformat() if latest else None,
               publication_status='latest_feed_timestamp_not_every_event',relevant_items=len(items),
               provides=source.get('kind','publikované správy')+'; '+','.join(source.get('coverage',[])),
               freshness='relevantné správy najviac 72 h; staršie alebo nepriradené správy nie sú použité')
    return out


class Probe:
    def __init__(self,now):self.now=now;self.rows=[];self.lock=threading.Lock()
    def fetch(self,source):
        started=time.monotonic()
        matching=next(((s,k) for s,k,u in project_metrics.SOURCES if u==source['url']),None)
        record=dict(source=source.get('id') or ('_'.join(matching) if matching else urlsplit(source['url']).path),url=source['url'],symbol=source.get('symbol') or (matching[0] if matching else None),
                    retrieved_at=datetime.now(timezone.utc).isoformat(),retrieval='FAILED',schema_valid=False,
                    provides='N/A — zdroj nedostupný; zamýšľaný obsah nie je potvrdený',http_status=None)
        try:
            raw=fundamentals.fetch(source)
            record.update(retrieval='SUCCESS',bytes=len(raw))
            try:record.update(inspect(raw,source,self.now))
            except Exception as exc:record.update(status='INVALID_FORMAT',error_type=type(exc).__name__,error_layer='parser',error_code=str(exc) if str(exc) in ('METRIC_TYPE_MISMATCH','FEES_CHART_SCHEMA_MISSING','TVL_SERIES_SCHEMA_MISSING','FRED_CSV_SCHEMA_MISSING','TREASURY_XML_SCHEMA_MISSING','ICS_SCHEMA_MISSING','FOMC_SCHEMA_MISSING','RSS_ATOM_SCHEMA_MISSING') else 'SCHEMA_OR_PARSE_ERROR')
            return raw
        except Exception as exc:
            record.update(error_details(exc));raise
        finally:
            record['seconds']=round(time.monotonic()-started,3)
            with self.lock:self.rows.append(record)


def diagnostics(rows,fund,ai,now):
    out=['# Fundamental Sources Shadow Test',now.isoformat(),
         'Živý izolovaný zber; žiadny Telegram, súkromný stav alebo obchod. Čas zberu nie je plánovaných 20:00.',
         '', '| Zdroj | Stav | Poskytované údaje | Aktuálnosť / chyba |', '|---|---|---|---|']
    for r in rows:
        freshness=r.get('publication_at') or r.get('freshness') or r.get('error_code') or (r.get('error_layer','')+' '+str(r.get('http_status') or '')+' '+r.get('error_type',''))
        observed=r.get('latest_observation')
        if isinstance(observed,dict):
            periods=[observed.get('date') or observed.get('period')] if observed.get('date') or observed.get('period') else [v.get('period') for v in observed.values() if isinstance(v,dict)]
            if periods:freshness+='; merané '+', '.join(str(x) for x in periods if x)
        out.append('| '+ ' | '.join(str(v).replace('|','/').replace('\n',' ') for v in (r['source'],r['status'],r.get('provides'),freshness))+' |')
    out+=['','## Projektové pokrytie', '| Minca | Projektový feed | TVL | Poplatky | Príjmy | Aktívni používatelia |', '|---|---|---|---|---|---|']
    for symbol in SYMBOLS:
        sources=[s for s in fund.get('sources',[]) if s.get('symbol')==symbol]
        economics=fund.get('project_economics',{}).get('observations',{}).get(symbol,{})
        out.append('| '+ ' | '.join((symbol, ', '.join(s['source']+': '+s['status']+' ('+str(s.get('events',0))+' aktuálnych)' for s in sources) or 'N/A', 'dostupné' if symbol in fund.get('metrics',{}) else 'N/A', 'dostupné' if 'fees' in economics else 'N/A', 'dostupné' if 'revenue' in economics else 'N/A', 'N/A'))+' |')
    out+=['','Úplné URL, fallback pokusy, merané obdobia a časy zberu: `source_diagnostics.json`.',
          'HTTP úspech ≠ správny formát ≠ aktuálna relevantná informácia. Starý softvérový release nie je výpadok servera.',
          'Používanie: TVL je len proxy ekonomickej aktivity, nie počet používateľov. Aktívni používatelia, úplné unlocky a príjmy všetkých šiestich projektov nie sú pokryté.',
          'AI: '+json.dumps(ai,ensure_ascii=False),
          'Každý vykreslený fundamentálny záver obsahuje význam/dopad/potrebné potvrdenie; nejde o nezávislé overenie celého článku.',
          'Výpadok primárneho zdroja a úspech zálohy zostávajú oddelené. Percento všetkých významných informácií je neznáme.']
    return '\n'.join(out)+'\n'


def run(output,use_groq=False,report_phase='preview'):
    out=Path(output).resolve();allowed=(ROOT/'shadow-output').resolve()
    if not out.is_relative_to(allowed):raise ValueError('Shadow output path required')
    out.mkdir(parents=True,exist_ok=True)
    before=protected_hashes();api=ShadowAPI(use_groq)
    try:
        original=data.COINS
        try:
            data.COINS={s:original[s] for s in SYMBOLS};snap=data.collect(api,full=True)
        finally:data.COINS=original
        now=datetime.now(timezone.utc);probe=Probe(now)
        fund=fundamentals.collect({},now,fetcher=probe.fetch)
        fund['macro_context']=macro_context.collect({},now,fetcher=probe.fetch)
        fund['economic_observations']=macro_context.economic_observations(now,fetcher=probe.fetch)
        # Diagnose configured fallback endpoints even when the primary worked.
        # These extra checks do not replace the selected evidence in the report.
        tested={r['url'] for r in probe.rows}
        alternatives=[candidate for choices in fundamentals.FALLBACKS.values() for candidate in choices]
        alternatives.append(dict(id='fred_yield_fallback',url='https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS2,DGS10&cosd='+str((now-timedelta(days=10)).date())))
        for candidate in alternatives:
            if candidate['url'] in tested:continue
            try:probe.fetch(candidate)
            except Exception:pass
            tested.add(candidate['url'])
        # Date of completion, not snapshot start, is the analysis clock.
        completed=datetime.now(timezone.utc)
        reports,evals,ai=render(snap,fund,api,completed,phase=report_phase)
        evidence=analyze(fund,completed)
        faults,_=outage_checks(snap,completed)
        ai_status=dict(requested=use_groq,key_available=bool(api.GROQ_API_KEY),calls=api.groq_attempts,
                       fundamental_ranking=ai.get('fundamental_ranking',{}),technical_selection=ai['available'],
                       requests=[r for r in api.requests if r['host']=='api.groq.com'])
        report_name='morning' if report_phase=='morning' else 'evening'
        evening=reports[report_name].replace('Oba náhľady používajú rovnaký aktuálny snapshot. Reálne ranné/večerné porovnanie N/A.',
                                          'Samostatná večerná ukážka; bez overeného ranného snapshotu sa porovnanie nepredstiera.')
        (out/(report_name+'.txt')).write_text(evening)
        rendered=[e for e in evidence['evidence'] if e['title'] in evening]
        write_json(out/'analysis_validation.json',dict(rendered_evidence=len(rendered),
            source_urls_present=all(e['url'] in evening for e in rendered),
            meaning_and_impact_present=not rendered or all(t in evening for t in ('Význam:', 'Dopad:', 'Overiť:')),
            no_rendered_evidence=not rendered,
            note='Kontrola vysledovateľnosti šablóny; nie nezávislé overenie pravdivosti zdrojového článku.'))
        write_json(out/'fundamentals.json',fund);write_json(out/'fundamental_evidence.json',evidence)
        write_json(out/'market_snapshot.json',snap);write_json(out/'source_diagnostics.json',probe.rows)
        write_json(out/'ai_diagnostics.json',ai_status);write_json(out/'outage_checks.json',faults)
        write_json(out/'summary.json',dict(collected_at=now.isoformat(),completed_at=completed.isoformat(),
            market_complete=snap['complete'],endpoints=len(probe.rows),current=sum(r['status']=='OK_CURRENT' for r in probe.rows),
            protected_files_unchanged=before==protected_hashes(),telegram_enabled=False,real_positions_loaded=False,
            orders_enabled=False,commit=__import__('os').getenv('GITHUB_SHA'),branch=__import__('os').getenv('GITHUB_REF_NAME')))
        (out/'REPORT.md').write_text(diagnostics(probe.rows,fund,ai_status,completed))
        print('Fundamental source shadow completed; diagnostics saved, no delivery.')
        return 0 if snap['complete'] else 2
    finally:
        if protected_hashes()!=before:raise RuntimeError('Protected files changed')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',default='shadow-output/fundamental-sources');p.add_argument('--use-groq',action='store_true')
    args=p.parse_args();raise SystemExit(run(args.output,args.use_groq))
