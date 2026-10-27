"""Public-data analytical pilot. No real ledger, AI, broker or private state access."""
import base64
from datetime import datetime,timezone
import json
import math
import os
from pathlib import Path
import re
import sys
import urllib.request
import urllib.error
from zoneinfo import ZoneInfo
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.v111_shadow import ShadowAPI, SYMBOLS
from v11 import data,fundamentals,macro_context,forecast_audit
from v11.diagnostics import technical
from v11.reporting import chunks
from v11.state_policy import require_public_data

BL=ZoneInfo('Europe/Bratislava')
PATH='trial-public/v111-delivery.json'
# Optional presentation hook; never persisted and unused by V11.1.
personalize=None


def phase(now):
    local=now.astimezone(BL);minute=local.hour*60+local.minute
    for name,start in [('morning',420),('usa',900),('evening',1200)]:
        if start<=minute<=start+90:return name
    return None


def price(value):
    if value is None:return 'N/A'
    return f'${value:,.2f}' if abs(value)>=1 else f'${value:.6f}'.rstrip('0').rstrip('.')


def pct(value):return 'N/A' if value is None else f'{value:+.2f}%'


def delta(a,b):return (a/b-1)*100 if isinstance(a,(int,float)) and isinstance(b,(int,float)) and b>0 else None


def observation(snap):
    return {s:dict(price=None if snap['coins'][s].get('stale') else snap['coins'][s].get('price'),market_cap=None if snap['coins'][s].get('stale') else snap['coins'][s].get('market_cap'),
                   volume_24h=None if snap['coins'][s].get('stale') else snap['coins'][s].get('volume_24h'),technical_score=technical(snap['coins'][s]).get('score'),
                   action='WAIT') for s in SYMBOLS}


def render(snap,fund,now,kind,previous=None):
    g=snap.get('global_data',{});btc=snap['coins'].get('BTC',{})
    lines=['📊 V11.1 — SKÚŠOBNÁ ANALÝZA '+('RÁNO' if kind=='morning' else 'VEČER'),
        now.astimezone(BL).strftime('%d.%m.%Y %H:%M Bratislava'),
        'Analytický pilot: žiadny nový potvrdený BUY/SELL. Držba N/A — skutočné pozície sa nenačítavajú.',
        f"Trh24h {pct(g.get('change'))}; BTC {price(btc.get('price'))} ({pct(btc.get('change_24h'))}); dominancia {format(g['dominance'],'.2f')+'%' if g.get('dominance') is not None else 'N/A'}.",
        'Príčina pohybu N/A bez potvrdenia. Riziko: neúplné udalostné pokrytie; menšia korekcia sama neodôvodňuje predaj.',
        'Ceny Binance, kapitalizácia/objemy CoinGecko; nejde o eToro realizačné ceny.']
    from v11.fundamental_analysis import overview,coin_lines
    lines += overview(fund,now)
    technical_appendix=[]
    current=observation(snap)
    for symbol in SYMBOLS:
        coin=snap['coins'][symbol];t=coin.get('frames',{}).get('4h',{});diagnostic=technical(coin)
        lines+=['',f"{symbol} — WAIT | {price(coin.get('price'))},24h {pct(coin.get('change_24h'))}",
          f"Technika {diagnostic.get('score','N/A')}/6; RSI {round(t['rsi14'],1) if t.get('rsi14') is not None else 'N/A'}; ADX {round(t['adx'],1) if t.get('adx') is not None else 'N/A'}; support {price(t.get('support'))}, rezistencia {price(t.get('resistance'))}.",
          f"Kap. {price(coin.get('market_cap'))}; objem24h {price(coin.get('volume_24h'))}; obeh tokenov {coin.get('circulating_supply') if coin.get('circulating_supply') is not None else 'N/A'}. Unlocky/emisie N/A bez kalendára."]
        technical_appendix.append(symbol+': EMA20/50/100/200 '+ ' / '.join(price(t.get('ema'+str(n))) for n in (20,50,100,200)))
        if coin.get('stale'):lines.append('Dáta neúplné/zastarané — nové úrovne a výhľad N/A.')
        else:
            for label,tf in [('24–72h','4h'),('7–14d','1d')]:
                frame=coin.get('frames',{}).get(tf,{});lo=frame.get('support');hi=frame.get('resistance');p=coin.get('price')
                if lo and hi and p and lo<p<hi:
                    lines.append(f"{label}: základ pásmo {price(lo)}–{price(hi)}; rast až po uzavretí {tf} nad {price(hi)}, pokles pod {price(lo)}. Uzavretie mimo pásma ruší základ. Neistota vysoká.")
                else:lines.append(label+': N/A — hranice nepotvrdené.')
        lines += coin_lines(symbol,fund,now)
        if previous and symbol in previous:
            old=previous[symbol]
            lines.append(f"Od rána: cena {pct(delta(current[symbol]['price'],old.get('price')))}, kap. {pct(delta(current[symbol]['market_cap'],old.get('market_cap')))}, objem {pct(delta(current[symbol]['volume_24h'],old.get('volume_24h')))}; technika {old.get('technical_score')}→{current[symbol]['technical_score']}/6; WAIT→WAIT.")
    for symbol,metric in fund.get('metrics',{}).items():
        lines.append(f"{symbol} TVL {price(metric['value'])}, pozorovanie {metric['at']}; {metric['url']}. Nie čistý tok ani adopcia tokenu.")
    lines+=macro_context.lines(fund.get('macro_context',{}))[:1]
    lines+=['','KALENDÁR — čas Bratislava, konsenzus a smer dopadu N/A bez overenia:']
    for title,lower,upper in [('24h',0,1),('ďalšie dni do7d',1,7),('ďalšie dni do14d',7,14)]:
        selected=[]
        for e in fund.get('events',[]):
            if not e.get('scheduled'):continue
            at=fundamentals.timestamp(e.get('event_at'));day=e.get('event_date')
            distance=(at-now).total_seconds()/86400 if at else (datetime.fromisoformat(day).date()-now.astimezone(BL).date()).days if day else -1
            if lower<=distance<upper:selected.append(e)
        lines.append(title+': '+(' | '.join(e['title'][:90]+'; '+(fundamentals.timestamp(e['event_at']).astimezone(BL).strftime('%d.%m. %H:%M') if e.get('event_at') else e.get('event_date','N/A')+' čas N/A')+'; '+e['url'] for e in selected[:2]) or 'N/A v dostupných kalendároch; nie potvrdenie absencie udalostí.'))
    if kind=='evening' and not previous:lines.append('Porovnanie rána N/A — chýba úspešne odoslaný ranný zber.')
    lines+=['','ZÁVER: nový nákup WAIT; HOLD/REDUCE/SELL pre tvoje pozície N/A. Vstup, stop, TP a čisté R:R pre povolený obchod N/A. Poplatky približne1%+1%, spread neoverený.',
      'Udalosť sama nevytvára obchodný signál. Pravdepodobnosti N/A; dlhodobé prognózy zatiaľ nehodnotené. Kapitalizácia a objem nie sú čisté toky kapitálu.']
    lines += ['', 'TECHNICKÁ PRÍLOHA',*technical_appendix]
    text='\n'.join(lines);require_public_data(text);return text,current


class PublicJournal:
    def __init__(self):
        self.repo=os.environ['GITHUB_REPOSITORY'];self.token=os.environ['GH_TOKEN'];self.sha=None
        if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',self.repo):raise ValueError('Invalid repository')
    def request(self,method,body=None):
        url='https://api.github.com/repos/'+self.repo+'/contents/'+PATH+('?ref=main' if method=='GET' else '')
        req=urllib.request.Request(url,method=method,data=json.dumps(body).encode() if body else None,
            headers={'Authorization':'Bearer '+self.token,'Accept':'application/vnd.github+json','Content-Type':'application/json','User-Agent':'crypto-bot-analytical-pilot'})
        with urllib.request.urlopen(req,timeout=20) as r:return json.load(r)
    def read(self):
        try:response=self.request('GET')
        except urllib.error.HTTPError as e:
            if e.code==404:return {'schema':1,'slots':{}}
            raise
        self.sha=response['sha'];value=json.loads(base64.b64decode(response['content']))
        require_public_data(value)
        if value.get('schema')!=1 or not isinstance(value.get('slots'),dict):raise ValueError('Invalid trial journal')
        return value
    def save(self,value):
        require_public_data(value)
        raw=json.dumps(value,allow_nan=False).encode()
        if len(raw)>800_000:raise RuntimeError('Public analytical journal requires archival; refusing oversized write')
        body={'message':'Update public analytical pilot delivery journal [skip ci]','branch':'main','content':base64.b64encode(raw).decode()}
        if self.sha:body['sha']=self.sha
        response=self.request('PUT',body);self.sha=response['content']['sha']


def send(text):
    token=os.environ['TELEGRAM_TOKEN'];chat=os.environ['TELEGRAM_CHAT_ID']
    # Exactly one HTTP attempt per part. Timeout is uncertain, never retried.
    for part in chunks(text):
        req=urllib.request.Request('https://api.telegram.org/bot'+token+'/sendMessage',
            data=json.dumps({'chat_id':chat,'text':part,'disable_web_page_preview':True}).encode(),headers={'Content-Type':'application/json'})
        with urllib.request.urlopen(req,timeout=25) as response:
            if not json.load(response).get('ok'):raise RuntimeError('Telegram refused pilot report')


def run(manual_key=None):
    if manual_key is not None and not re.fullmatch(r'github-run-[0-9]+',manual_key):raise ValueError('Invalid manual delivery key')
    now=datetime.now(timezone.utc);kind='manual' if manual_key else phase(now)
    if not kind:return 0
    if kind=='usa' and now.astimezone(BL).date().isoformat()<os.getenv('US_PILOT_START_DATE','2026-10-27'):return 0
    journal=PublicJournal();state=journal.read();key=manual_key or now.astimezone(BL).date().isoformat()+'-'+kind
    records=state.setdefault('manual_slots',{}) if manual_key else state['slots']
    if key in records:return 0
    if kind=='usa':
        from us_context import report as us
        started=datetime.now(timezone.utc)
        context=us.collect(us.PublicUSAPI(),started)
        now=datetime.now(timezone.utc);us.refresh(context,now)
        target='BRATISLAVA_'+now.astimezone(BL).date().isoformat()+'_15:00'
        previous=next((entry.get('quotes') for slot,entry in sorted(state['slots'].items(),reverse=True) if slot.endswith('-usa') and entry.get('status')=='sent'),None)
        text=us.render(context,now,target,previous,(now-started).total_seconds())
        fundamental=fundamentals.collect({},now)
        upcoming=[e for e in fundamental.get('events',[]) if e.get('scheduled')]
        text+='\nNajbližšie plánované: '+(' | '.join(e['title'][:80]+'; '+(fundamentals.timestamp(e['event_at']).astimezone(BL).strftime('%d.%m. %H:%M Bratislava') if e.get('event_at') else e.get('event_date','N/A')+' čas N/A')+'; '+e['url'] for e in upcoming[:2]) or 'N/A v dostupných zdrojoch.')
        text+='\n'+macro_context.lines(macro_context.collect({},now))[0]
        require_public_data(text)
        quotes={'at':context['crypto']['global_at'].isoformat() if context['crypto']['global_at'] else None,
                'dominance':context['crypto']['dominance'],
                'us_data':{symbol:{'status':q['status'],'price':q['price'],'at':q['at'].isoformat() if q['at'] else None,'kind':q['kind']} for symbol,q in context['quotes'].items()},
                'sources':context['sources'],'phase':context['market']['phase']}
        print('US pilot source status: '+json.dumps({'quotes':{k:v['status'] for k,v in quotes['us_data'].items()},'sources':context['sources'],'phase':quotes['phase']}))
    else:
        api=ShadowAPI();original=data.COINS
        try:
            data.COINS={s:original[s] for s in SYMBOLS};snap=data.collect(api,full=True)
        finally:data.COINS=original
        now=datetime.now(timezone.utc)
        fund=fundamentals.collect({},now)
        fund['macro_context']=macro_context.collect({},now)
        economic=macro_context.economic_observations(now)
        fund['economic_observations']=economic
        if not manual_key:
            history=state.setdefault('macro_observation_history_v1',[])
            history.append(economic);state['macro_observation_history_v1']=history[-100:]
        morning=state['slots'].get(now.astimezone(BL).date().isoformat()+'-morning',{})
        reference=state.get('last_analysis_v112') if os.getenv('V112_ANALYTICS_ENABLED','false').lower()=='true' else morning.get('quotes') if morning.get('status')=='sent' else None
        text,quotes=render(snap,fund,now,kind,reference)
        slot=None
        if not manual_key:
            slot=now.astimezone(BL).date().isoformat()+('_07:00' if kind=='morning' else '_20:00')
            forecast_audit.update(state,snap,fund,slot)
        if os.getenv('V111_INTEGRATION_ENABLED','false').lower()!='true':
            text+='\n'+'\n'.join(forecast_audit.lines(state))+'\n'+'\n'.join(macro_context.economic_lines(economic))
    if not manual_key and phase(now)!=kind:raise RuntimeError('Collection exceeded pilot slot')
    require_public_data(quotes)
    pending_observation=quotes.pop('_v112_observation',None) if os.getenv('V112_ANALYTICS_ENABLED','false').lower()=='true' else None
    if manual_key:
        records[key]={'status':'attempting','at':now.isoformat()}
    else:
        state['slots']={k:v for k,v in state['slots'].items() if k[:10]>=(now.astimezone(BL).date().isoformat()[:8]+'01')}
        records=state['slots']
        records[key]={'status':'attempting','at':now.isoformat(),'quotes':quotes}
    journal.save(state)  # CAS before any Telegram side effect; conflict means no send.
    if kind!='usa' and os.getenv('PRIVATE_ADVISORY_ENABLED','false')=='true':
        private_stage='storage_or_inventory'
        try:
            from v11.advisory_portfolio import load,advice
            inventory=load()
            private_stage='assessment'
            if os.getenv('V112_ANALYTICS_ENABLED','false').lower()=='true' and personalize is not None:
                text=personalize(inventory,snap,now,kind)
                private_text=''
            else:private_text=advice(inventory,snap)
            text=text.replace('Držba N/A — skutočné pozície sa nenačítavajú.','Držba je posúdená v súkromnej časti nižšie.').replace('HOLD/REDUCE/SELL pre tvoje pozície N/A.','Posúdenie existujúcich pozícií je v súkromnej časti nižšie.')
            text+='\n'+private_text  # Telegram only; NEVER persisted in public journal.
        except Exception as exc:
            if os.getenv('V112_ANALYTICS_ENABLED','false').lower()=='true':
                print('V112 private context unavailable: '+private_stage+'/'+type(exc).__name__)
                text+='\nPosúdenie držby sa nepodarilo bezpečne overiť; nejde o prázdne portfólio ani potvrdené HOLD.'
            else:text+='\nSúkromné portfólio N/A — úložisko alebo evidencia sa nedali bezpečne overiť; nie je to prázdne portfólio.'
    if manual_key:
        if os.getenv('V112_ANALYTICS_ENABLED','false').lower()=='true':text=text.replace('— RUČNÁ','— RUČNÁ | '+manual_key,1)
        else:text='RUČNÁ ANALÝZA V11.1 | '+manual_key+'\n'+text
    try:send(text)
    except Exception:
        records[key]['status']='uncertain';journal.save(state);raise
    records[key]['status']='sent'
    if pending_observation is not None and kind!='usa':
        require_public_data(pending_observation)
        state['last_analysis_v112']=pending_observation
    if kind!='usa' and not manual_key:
        for forecast in state.get('analysis_forecasts_v11',[]):
            if forecast['id'].startswith(slot+'|'):forecast['delivery_confirmed']=True
    journal.save(state)
    print('Analytical report delivered; no orders executed.')
    return 0


if __name__=='__main__':
    try:raise SystemExit(run())
    except Exception as exc:
        print('Analytical pilot failed: '+type(exc).__name__,file=sys.stderr)
        raise SystemExit(1)
