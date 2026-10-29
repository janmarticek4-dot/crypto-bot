"""Attributed public measurements and forecasts; never trading or private state.
ETF aggregator rows are not issuer audits; calendar forecasts are not FedWatch.
"""
import concurrent.futures
import hashlib
import json
import math
import re
import urllib.request
from datetime import datetime,timezone,timedelta
from html.parser import HTMLParser
from zoneinfo import ZoneInfo
from .fundamentals import fetch,timestamp
from .project_metrics import parse as parse_daily

BL=ZoneInfo('Europe/Bratislava')
FLOW_URLS={
 'BTC':('https://farside.co.uk/btc/','https://farside.co.uk/bitcoin-etf-flow-all-data/'),
 'ETH':('https://farside.co.uk/eth/','https://farside.co.uk/ethereum-etf-flow-all-data/')}
CALENDAR='https://nfs.faireconomy.media/ff_calendar_thisweek.json'
DEX='https://api.llama.fi/overview/dexs/Solana?excludeTotalDataChart=false&excludeTotalDataChartBreakdown=true'
STABLE='https://stablecoins.llama.fi/stablecoincharts/Solana'
RPC='https://api.mainnet-beta.solana.com'

class TableReader(HTMLParser):
    def __init__(self):
        super().__init__();self.rows=[];self.row=None;self.cell=None;self.text=[];self.ignore=0
    def handle_starttag(self,tag,attrs):
        if tag in ('script','style'):self.ignore+=1
        if tag=='tr':self.row=[]
        if tag in ('td','th'):self.cell=[]
    def handle_endtag(self,tag):
        if tag in ('script','style'):self.ignore=max(0,self.ignore-1)
        if tag in ('td','th') and self.cell is not None:
            if self.row is not None:self.row.append(re.sub(r'\s+',' ',' '.join(self.cell)).strip())
            self.cell=None
        if tag=='tr' and self.row is not None:self.rows.append(self.row);self.row=None
    def handle_data(self,text):
        if not self.ignore:
            self.text.append(text)
            if self.cell is not None:self.cell.append(text)


def finite(value):return type(value) in (int,float) and math.isfinite(value)

def flow_number(raw):
    value=raw.strip()
    if value.lower() in ('','-','—','n/a','na','tbd'):return None
    if value.startswith('(')!=value.endswith(')'):raise ValueError('Unbalanced ETF parentheses')
    negative=value.startswith('(')
    if negative:value=value[1:-1]
    if not re.fullmatch(r'-?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?',value) or (negative and value.startswith('-')):raise ValueError('Non-numeric ETF cell')
    if negative:value='-'+value
    result=float(value.replace(',',''))
    if not math.isfinite(result) or abs(result)>1000000:raise ValueError('Invalid ETF magnitude')
    return result


def parse_flows(raw,symbol,now):
    reader=TableReader();reader.feed(raw.decode('utf-8'))
    text=' '.join(reader.text)
    asset='Bitcoin' if symbol=='BTC' else 'Ethereum' if symbol=='ETH' else None
    if not asset or not re.search(asset+r'\s+ETF Flow',text,re.I) or not re.search(r'US\$\s*m(?:illion)?\b',text,re.I):raise ValueError('ETF identity or USD-million unit missing')
    if ('IBIT' if symbol=='BTC' else 'ETHA') not in text or not any('Total' in row for row in reader.rows):raise ValueError('ETF table header missing')
    widths={len(row) for row in reader.rows if ('IBIT' if symbol=='BTC' else 'ETHA') in row}
    if len(widths)!=1:raise ValueError('Ambiguous ETF column schema')
    width=next(iter(widths))
    rows={}
    for row in reader.rows:
        if not 4<=len(row)<=40:continue
        try:day=datetime.strptime(row[0],'%d %b %Y').date()
        except ValueError:continue
        if not 0<=(now.date()-day).days<=30:continue
        if len(row)!=width:raise ValueError('ETF row has missing or extra columns')
        values=[flow_number(v) for v in row[1:]];total=values[-1]
        if total is None:continue
        parts=values[:-1];complete=all(v is not None for v in parts)
        reconciled=abs(sum(v for v in parts if v is not None)-total)<=len(parts)*0.06+0.01
        if not reconciled:raise ValueError('ETF total fails component reconciliation')
        item=dict(date=day.isoformat(),net_flow_usd=round(total*1000000,2),complete=complete,
                  reported_funds=sum(v is not None for v in parts),fund_columns=len(parts),reconciled=True)
        if item['date'] in rows and rows[item['date']]!=item:raise ValueError('Conflicting ETF rows')
        rows[item['date']]=item
    ordered=sorted(rows.values(),key=lambda r:r['date']);complete=[r for r in ordered if r['complete']]
    if not complete or (now.date()-datetime.fromisoformat(complete[-1]['date']).date()).days>5:raise ValueError('No recent complete ETF observation')
    result=dict(complete[-1]);result.update(provider='Farside Investors',unit='USD',scope='US spot '+symbol+' ETF daily net flows',
        published_at=None,provider_audited=False,latest_incomplete_date=ordered[-1]['date'] if ordered and not ordered[-1]['complete'] else None,
        previous_date=complete[-2]['date'] if len(complete)>1 else None,previous_net_flow_usd=complete[-2]['net_flow_usd'] if len(complete)>1 else None)
    return result


def parse_forecasts(raw,now):
    rows=json.loads(raw)
    if not isinstance(rows,list):raise ValueError('Calendar must be a list')
    result=[];seen={}
    for row in rows:
        if not isinstance(row,dict) or row.get('country')!='USD':continue
        title=row.get('title');at=timestamp(row.get('date'))
        if not isinstance(title,str) or not at or not now<at<=now+timedelta(days=14):continue
        if not re.search(r'GDP|PCE|CPI|payroll|employment|unemployment|claims|Federal Funds|retail sales|ISM|PMI',title,re.I):continue
        forecast=row.get('forecast','');previous=row.get('previous')
        if not isinstance(forecast,str) or not re.fullmatch(r'-?\d+(?:\.\d+)?(?:%|K|M|B)?',forecast.strip()):continue
        ident=hashlib.sha256((title+'|'+at.isoformat()).encode()).hexdigest()
        value=dict(id=ident,title=title[:200],event_at=at.isoformat(),forecast=forecast.strip(),previous=previous[:64] if isinstance(previous,str) else None,
                   provider='Forex Factory / Fair Economy calendar',forecast_captured_at=now.isoformat(),published_at=None,
                   methodology='provider-reported forecast; survey method and sample unavailable',actual=None,surprise=None,
                   event_time_status='third_party_schedule_not_official_confirmation')
        if ident in seen and seen[ident]['forecast']!=value['forecast']:raise ValueError('Conflicting calendar forecasts')
        seen[ident]=value
    return sorted(seen.values(),key=lambda r:r['event_at'])


def parse_stablecoins(raw,now):
    rows=json.loads(raw)
    if not isinstance(rows,list):raise ValueError('Stablecoin series must be a list')
    values={}
    for row in rows:
        try:
            at=datetime.fromtimestamp(int(row['date']),timezone.utc);parts=row['totalCirculatingUSD']
            if not isinstance(parts,dict) or not parts or any(not finite(v) or v<0 for v in parts.values()):continue
            if not timedelta(0)<=now-at<=timedelta(days=30):continue
            value=sum(parts.values())
            if at.isoformat() in values and values[at.isoformat()]!=value:raise ValueError('Conflicting stablecoin observation')
            values[at.isoformat()]=value
        except (KeyError,TypeError,OverflowError,OSError):continue
    dates=sorted(values)
    if not dates or now-datetime.fromisoformat(dates[-1])>timedelta(hours=48):raise ValueError('Stablecoin observation stale')
    return dict(period=dates[-1],value=values[dates[-1]],unit='USD stock',previous_period=dates[-2] if len(dates)>1 else None,
                previous_value=values[dates[-2]] if len(dates)>1 else None,scope='Solana stablecoin circulating supply, USD valuation; not net cash inflow')


def parse_supply(raw,now):
    data=json.loads(raw)
    if 'error' in data or data.get('jsonrpc')!='2.0':raise ValueError('RPC error')
    value=data['result']['value'];slot=data['result']['context']['slot']
    amounts=[value[k] for k in ('total','circulating','nonCirculating')]
    if type(slot) is not int or slot<=0 or any(type(v) is not int or v<0 for v in amounts) or amounts[0]!=sum(amounts[1:]):raise ValueError('Invalid Solana supply reconciliation')
    return dict(value=amounts[1]/1000000000,total=amounts[0]/1000000000,unit='SOL',slot=slot,period=None,observed_at=now.isoformat(),
                scope='Finalized Solana RPC circulating supply; not adoption or token unlock schedule')


def parse_tvl(raw,now):
    data=json.loads(raw);rows=data.get('tvl') if isinstance(data,dict) else None
    if not isinstance(rows,list):raise ValueError('TVL series missing')
    mapped=[]
    for row in rows:
        try:
            at=datetime.fromtimestamp(row['date'],timezone.utc);value=row['totalLiquidityUSD']
            if not finite(value) or value<0 or not timedelta(0)<=now-at<=timedelta(days=30):continue
            mapped.append((at,value))
        except (KeyError,TypeError,ValueError,OverflowError,OSError):continue
    mapped=sorted(dict(mapped).items())
    if not mapped or now-mapped[-1][0]>timedelta(hours=48):raise ValueError('No current TVL period')
    return dict(period=mapped[-1][0].isoformat(),value=mapped[-1][1],unit='USD stock',previous_period=mapped[-2][0].isoformat() if len(mapped)>1 else None,previous_value=mapped[-2][1] if len(mapped)>1 else None)


def parse_inflation(raw,chain,now):
    data=json.loads(raw)
    if chain=='SOL':
        if data.get('jsonrpc')!='2.0' or 'error' in data:raise ValueError('RPC inflation error')
        value=data['result']['total'];epoch=data['result']['epoch']
        if type(epoch) is not int or epoch<0:raise ValueError('Invalid epoch')
    else:value=float(data['inflation']);epoch=None
    if not finite(value) or not 0<=value<=1:raise ValueError('Invalid annualized inflation fraction')
    return dict(value=value*100,unit='% annualized protocol parameter',epoch=epoch,period=None,observed_at=now.isoformat(),
                scope=chain+' native-chain reported inflation; not a dated unlock, global token issuance or guaranteed future rate')


UNLOCK_PAGES={
 'ONDO':('https://tokenomist.ai/ondo-finance/unlock-events','Ondo'),
 'FET':('https://tokenomist.ai/fetch-ai/unlock-events','Artificial Superintelligence Alliance'),
 'AAVE':('https://tokenomist.ai/aave/unlock-events','Aave')}


def parse_unlock(raw,symbol,now):
    if symbol not in UNLOCK_PAGES:raise ValueError('Unsupported public schedule')
    name=UNLOCK_PAGES[symbol][1];reader=TableReader();reader.feed(raw.decode('utf-8'))
    text=re.sub(r'\s+',' ',' '.join(reader.text));target=re.escape(name)
    pattern=r'When is the next '+target+r' unlock\?\s*The next unlock for '+target+r' is scheduled for ([A-Z][a-z]+ \d{1,2}, 20\d{2})\.'
    dates=re.findall(pattern,text)
    if not dates:
        if re.search(target+r' is fully unlocked',text,re.I):raise ValueError('No dated event; unlocked claim not independently verified')
        raise ValueError('No asset-specific dated public schedule')
    if len(set(dates))!=1:raise ValueError('Conflicting public unlock dates')
    date=datetime.strptime(dates[0],'%B %d, %Y').date()
    if not 0<=(date-now.astimezone(BL).date()).days<=730:raise ValueError('Outdated or distant schedule')
    return dict(symbol=symbol,event_date=date.isoformat(),event_at=None,amount=None,unit='tokens',
                provider='Tokenomist public FAQ',published_at=None,time_zone=None,observed_at=now.isoformat(),
                status='PROVIDER_SCHEDULE_NOT_ONCHAIN_CONFIRMED',scope='next event reported by public page; not full vesting schedule',
                confirmation_required='official project schedule, quantity, timestamp/timezone and any revisions')


def parse_render(raw,now):
    obj=json.loads(raw)
    if obj.get('name')!='Render Network BME' or not isinstance(obj.get('methodology'),dict):raise ValueError('Render adapter identity/methodology missing')
    fees=obj['methodology'].get('Fees','')
    if not isinstance(fees,str) or not re.search(r'burn',fees,re.I):raise ValueError('Unknown Render fee methodology')
    value=parse_daily(raw,now,expected_type='dailyFees')
    if value:value['provider_methodology']=fees[:2500]
    return value


def collect(now,fetcher=fetch):
    out=dict(etf_flows={},consensus=[],unlocks=[],project_metrics={},sources=[],retrieved_at=now.isoformat(),
             unavailable=['complete token unlock schedules','CME FedWatch probabilities','independently verified consensus survey'])
    def attempt(name,url,parser,symbol=None):
        row=dict(source=name,url=url,retrieved_at=now.isoformat(),status='N/A')
        try:
            raw=fetcher(dict(url=url,id=name));row.update(retrieval='SUCCESS',input_sha256=hashlib.sha256(raw).hexdigest())
            value=parser(raw)
            if not value:
                row['status']='OK_NO_UPCOMING_ITEMS' if isinstance(value,list) else 'NO_RECENT_VALID_OBSERVATIONS'
                return value,row
            row['status']='OK';return value,row
        except Exception as exc:
            row.update(error_type=type(exc).__name__,http_status=getattr(exc,'code',None),error_code=getattr(exc,'reason_code',None))
            if row.get('retrieval')=='SUCCESS':row['status']='INVALID_OR_UNVERIFIED_DATA'
            return None,row
    def flow(symbol):
        records=[]
        for url in FLOW_URLS[symbol]:
            value,status=attempt(symbol+'_etf_flows',url,lambda b:parse_flows(b,symbol,now));records.append(status)
            if value:return symbol,dict(value,url=url,retrieved_at=now.isoformat()),records
        return symbol,None,records
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        for symbol,value,statuses in pool.map(flow,('BTC','ETH')):
            out['sources'].extend(statuses)
            if value:out['etf_flows'][symbol]=value
    forecasts,status=attempt('economic_forecasts',CALENDAR,lambda b:parse_forecasts(b,now));out['sources'].append(status)
    if forecasts:out['consensus']=[dict(v,url=CALENDAR) for v in forecasts]
    for key,url,parser in [('SOL_dex_volume',DEX,lambda b:parse_daily(b,now)),('SOL_stablecoin_supply',STABLE,lambda b:parse_stablecoins(b,now))]:
        value,status=attempt(key,url,parser);out['sources'].append(status)
        if value:
            value.update(url=url,retrieved_at=now.isoformat())
            if key=='SOL_dex_volume':value.update(scope='Solana DEX trading volume; not fees, users, or net capital inflow',unit='USD/day')
            out['project_metrics'][key]=value
    try:
        value=parse_supply(fetcher(dict(url=RPC,id='SOL_supply',rpc_method='getSupply')),now);out['project_metrics']['SOL_circulating_supply']=dict(value,url=RPC)
        out['sources'].append(dict(source='solana_rpc_supply',url=RPC,status='OK',retrieved_at=now.isoformat()))
    except Exception as exc:out['sources'].append(dict(source='solana_rpc_supply',url=RPC,status='N/A',error_type=type(exc).__name__,retrieved_at=now.isoformat()))
    extras=[
        ('TAO_subnet_liquidity','https://api.llama.fi/protocol/bittensor-dtao',lambda b:parse_tvl(b,now),'TAO reserves of dTAO AMM pools; excludes root staking and some separately tracked subnets; not global TAO TVL or adoption'),
        ('RENDER_job_fees','https://api.llama.fi/summary/fees/render-network-bme?dataType=dailyFees',lambda b:parse_render(b,now),'Render BME provider estimate of job spend from token burns; includes modeled off-chain fee component; not audited revenue or tokenholder cashflow'),
        ('FET_native_inflation','https://rest-fetchhub.fetch.ai/cosmos/mint/v1beta1/inflation',lambda b:parse_inflation(b,'FET',now),'Fetchhub native reported annualized inflation parameter; not global FET/ASI supply or unlock timing')]
    for key,url,parser,scope in extras:
        value,status=attempt(key,url,parser);out['sources'].append(status)
        if value:out['project_metrics'][key]=dict(value,url=url,retrieved_at=now.isoformat(),scope=scope)
    try:
        value=parse_inflation(fetcher(dict(url=RPC,id='SOL_inflation',rpc_method='getInflationRate')),'SOL',now)
        out['project_metrics']['SOL_native_inflation']=dict(value,url=RPC)
        out['sources'].append(dict(source='solana_inflation',url=RPC,status='OK',retrieved_at=now.isoformat()))
    except Exception as exc:out['sources'].append(dict(source='solana_inflation',url=RPC,status='N/A',error_type=type(exc).__name__,retrieved_at=now.isoformat()))
    def unlock(symbol):
        url,name=UNLOCK_PAGES[symbol]
        value,status=attempt(symbol+'_public_unlock',url,lambda b:parse_unlock(b,symbol,now))
        return value,status,url
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        for value,status,url in pool.map(unlock,UNLOCK_PAGES):
            out['sources'].append(status)
            if value:out['unlocks'].append(dict(value,url=url,retrieved_at=now.isoformat()))
    from .state_policy import require_public_data
    require_public_data(out);return out


def lines(value,now,event_limit=3):
    out=[]
    for symbol,item in value.get('etf_flows',{}).items():
        out.append(f"{symbol} ETF, {item['date']}: {item['net_flow_usd']/1e6:+,.1f} mil. USD čistý tok (Farside, úplný riadok poskytovateľa)."+
            (f" {item['latest_incomplete_date']}: údaje ešte neúplné." if item.get('latest_incomplete_date') else ''))
    for row in value.get('consensus',[])[:event_limit]:
        at=timestamp(row['event_at'])
        if at and at>now and row.get('official_schedule')!='CONFLICT':out.append(f"{at.astimezone(BL):%d.%m. %H:%M} Bratislava — {row['title']}: prognóza kalendára {row['forecast']}, predchádzajúce {row.get('previous') or 'N/A'} (Forex Factory; metodika prieskumu N/A).")
    for item in value.get('unlocks',[]):
        days=(datetime.fromisoformat(item['event_date']).date()-now.astimezone(BL).date()).days
        if 0<=days<=14:out.append(f"{item['symbol']} unlock {item['event_date']} podľa verejného Tokenomist prehľadu; presný čas/množstvo N/A, projektové potvrdenie chýba. Unlock neznamená predaj.")
    if value.get('etf_flows'):out.append('ETF tok nie je dôkaz príčiny pohybu BTC/altcoinov; úplnosť všetkých svetových ETF nepotvrdená.')
    return out


def tokenomics(coin,now):
    at=timestamp(coin.get('metadata_at'));circ=coin.get('circulating_supply');total=coin.get('total_supply')
    if not at or not -60<=(now-at).total_seconds()<=900 or not finite(circ) or not finite(total) or not 0<circ<=total:return None
    return dict(circulating=circ,total=total,circulating_percent=100*circ/total,period=at.isoformat(),provider='CoinGecko',
                scope='reported supply, not locked allocation, emission forecast, or confirmed unlock date')


def project_lines(symbol,value,coin,now):
    result=[];metrics=value.get('project_metrics',{})
    for key,label in [('SOL_dex_volume','DEX objem'),('SOL_stablecoin_supply','Stablecoin ponuka'),('TAO_subnet_liquidity','dTAO likvidita'),('RENDER_job_fees','Odhad poplatkov za výpočty')]:
        if not key.startswith(symbol+'_') or key not in metrics:continue
        row=metrics[key];previous=row.get('previous_value');change=(row['value']/previous-1)*100 if finite(previous) and previous>0 else None
        delta=f" ({change:+.1f}% vs predošlé meranie)" if change is not None else ''
        result.append(f"{label}: ${row['value']/1e6:,.2f} mil.{delta}; meranie {row['period'][:10]}.")
    if symbol=='TAO' and result:result.append('dTAO: rezervy subnetových AMM, nie celkové používanie siete ani čistý prílev.')
    if symbol=='RENDER' and result:result.append('BME: model výdavkov z burnov vrátane odhadu off-chain poplatku; nie auditovaný príjem držiteľa tokenu.')
    if symbol=='SOL' and result:result.append('Objem a ponuka stablecoinov nie sú čistým prílevom kapitálu.')
    key=symbol+'_native_inflation'
    if key in metrics:
        row=metrics[key];result.append(f"Natívna protokolová inflácia: {row['value']:.2f}% ročne; vykázaný parameter, nie dátum unlocku ani čisté zriedenie všetkých tokenov.")
    for event in value.get('unlocks',[]):
        if event['symbol']==symbol and 0<=(datetime.fromisoformat(event['event_date']).date()-now.astimezone(BL).date()).days<=14:result.append(f"Najbližší uvádzaný unlock: {event['event_date']} (Tokenomist); čas/množstvo a primárne potvrdenie N/A, nie potvrdený predaj.")
    supply=tokenomics(coin,now)
    if supply and supply['circulating_percent']<90:result.append(f"V obehu {supply['circulating_percent']:.1f}% vykázanej celkovej ponuky (CoinGecko); zvyšok nie je automaticky potvrdený unlock.")
    return result


def verify_calendar(value,events):
    # A provider forecast can be quoted, but a contradictory official schedule
    # must never be silently replaced by its timestamp.
    for row in value.get('consensus',[]):
        category=next((key for key,pattern in [('GDP',r'GDP'),('PCE',r'PCE'),('CPI',r'CPI'),('Fed',r'Federal Funds')] if re.search(pattern,row['title'],re.I)),None)
        matches=[e for e in events if e.get('scheduled') and category in e.get('categories',[])] if category else []
        dates=[(timestamp(e.get('event_at')),e.get('event_date')) for e in matches]
        at=timestamp(row['event_at'])
        if not dates:row['official_schedule']='UNCONFIRMED'
        elif any((time and time==at) or (day and day==at.date().isoformat() and not time) for time,day in dates):row['official_schedule']='MATCHED'
        else:row['official_schedule']='CONFLICT'
    return value
