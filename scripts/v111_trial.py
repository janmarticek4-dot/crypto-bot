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
from v11 import data,fundamentals
from v11.diagnostics import technical
from v11.reporting import chunks
from v11.state_policy import require_public_data

BL=ZoneInfo('Europe/Bratislava')
PATH='trial-public/v111-delivery.json'


def phase(now):
    local=now.astimezone(BL);minute=local.hour*60+local.minute
    for name,start in [('morning',420),('evening',1200)]:
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
    current=observation(snap)
    for symbol in SYMBOLS:
        coin=snap['coins'][symbol];t=coin.get('frames',{}).get('4h',{});diagnostic=technical(coin)
        lines+=['',f"{symbol} — WAIT | {price(coin.get('price'))},24h {pct(coin.get('change_24h'))}",
          f"Technika {diagnostic.get('score','N/A')}/6; RSI {round(t['rsi14'],1) if t.get('rsi14') is not None else 'N/A'}; ADX {round(t['adx'],1) if t.get('adx') is not None else 'N/A'}; support {price(t.get('support'))}, rezistencia {price(t.get('resistance'))}.",
          f"EMA20/50/100/200: {' / '.join(price(t.get('ema'+str(n))) for n in (20,50,100,200))}; MACD hist. {format(t['macd_hist'],'.4g') if t.get('macd_hist') is not None else 'N/A'}; ATR {price(t.get('atr'))}.",
          f"Kap. {price(coin.get('market_cap'))}; objem24h {price(coin.get('volume_24h'))}."]
        if coin.get('stale'):lines.append('Dáta neúplné/zastarané — nové úrovne a výhľad N/A.')
        else:
            for label,tf in [('24–72h','4h'),('7–14d','1d')]:
                frame=coin.get('frames',{}).get(tf,{});lo=frame.get('support');hi=frame.get('resistance');p=coin.get('price')
                if lo and hi and p and lo<p<hi:
                    lines.append(f"{label}: základ pásmo {price(lo)}–{price(hi)}; rast až po uzavretí {tf} nad {price(hi)}, pokles pod {price(lo)}. Uzavretie mimo pásma ruší základ. Neistota vysoká.")
                else:lines.append(label+': N/A — hranice nepotvrdené.')
        events=[e for e in fund.get('events',[]) if e.get('symbol')==symbol and not e.get('scheduled')]
        lines.append('Fundament: '+(events[0]['title'][:110]+' — '+events[0]['url']+'; ekonomický dopad N/A.' if events else 'N/A — bez aktuálneho overeného projektového podkladu.'))
        if previous and symbol in previous:
            old=previous[symbol]
            lines.append(f"Od rána: cena {pct(delta(current[symbol]['price'],old.get('price')))}, kap. {pct(delta(current[symbol]['market_cap'],old.get('market_cap')))}, objem {pct(delta(current[symbol]['volume_24h'],old.get('volume_24h')))}; technika {old.get('technical_score')}→{current[symbol]['technical_score']}/6; WAIT→WAIT.")
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
        body={'message':'Update public analytical pilot delivery journal [skip ci]','branch':'main','content':base64.b64encode(json.dumps(value,allow_nan=False).encode()).decode()}
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


def run():
    now=datetime.now(timezone.utc);kind=phase(now)
    if not kind:return 0
    journal=PublicJournal();state=journal.read();key=now.astimezone(BL).date().isoformat()+'-'+kind
    if key in state['slots']:return 0
    api=ShadowAPI();original=data.COINS
    try:
        data.COINS={s:original[s] for s in SYMBOLS};snap=data.collect(api,full=True)
    finally:data.COINS=original
    now=datetime.now(timezone.utc)
    if phase(now)!=kind:raise RuntimeError('Collection exceeded pilot slot')
    fund=fundamentals.collect({},now)
    morning=state['slots'].get(now.astimezone(BL).date().isoformat()+'-morning',{})
    text,quotes=render(snap,fund,now,kind,morning.get('quotes') if morning.get('status')=='sent' else None)
    require_public_data(quotes)
    state['slots']={k:v for k,v in state['slots'].items() if k[:10]>=(now.astimezone(BL).date().isoformat()[:8]+'01')}
    state['slots'][key]={'status':'attempting','at':now.isoformat(),'quotes':quotes}
    journal.save(state)  # CAS before any Telegram side effect; conflict means no send.
    try:send(text)
    except Exception:
        state['slots'][key]['status']='uncertain';journal.save(state);raise
    state['slots'][key]['status']='sent';journal.save(state)
    print('Analytical pilot sent; no portfolio or trading state accessed.')
    return 0


if __name__=='__main__':
    try:raise SystemExit(run())
    except Exception as exc:
        print('Analytical pilot failed: '+type(exc).__name__,file=sys.stderr)
        raise SystemExit(1)
