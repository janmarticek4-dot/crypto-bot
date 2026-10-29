"""US presentation only; consumes the same approved personal actions."""
from . import analyst,event_lifecycle,report_verdict
from .fundamentals import timestamp
from .telegram_text import without_links
from datetime import datetime
from us_context.report import BRATISLAVA,NEW_YORK,fresh,QUOTE_MAX_AGE


def render(context,model,snapshot,fund,now,inventory=None):
    crypto=context['crypto'];btc=crypto['coins']['BTC'];cap=crypto.get('cap_change')
    alts=[c['change'] for s,c in crypto['coins'].items() if s!='BTC' and analyst.number(c.get('change'))]
    b=btc.get('change')
    coherent=analyst.number(cap) and analyst.number(b) and len(alts)>=4
    label='Rast' if coherent and cap>0 and b>0 and sum(x>0 for x in alts)>=4 else 'Korekcia' if coherent and cap<0 and b<0 and sum(x<0 for x in alts)>=4 else 'Neistota'
    reason='BTC, kapitalizácia a väčšina altcoinov rastú.' if label=='Rast' else 'BTC, kapitalizácia a väčšina altcoinov klesajú.' if label=='Korekcia' else 'Signály sú zmiešané alebo chýba dostatok aktuálnych dát.'
    market=context['market'];phase=market['phase']
    lines=['🇺🇸 VERDIKT TRHU: '+label+' — '+reason,
        now.astimezone(BRATISLAVA).strftime('%d.%m.%Y %H:%M Bratislava')+' | '+phase+' | NY '+now.astimezone(NEW_YORK).strftime('%H:%M'),
        'ČO SA DEJE A PREČO:']
    items=[]
    cash=[q for q in context['quotes'].values() if q['kind']=='index' and analyst.number(q.get('change')) and q.get('price') is not None and fresh(q.get('at'),now,QUOTE_MAX_AGE) and q.get('status')!='posledná uzavretá seansa']
    futures=[q for q in context['quotes'].values() if q['kind']=='future' and analyst.number(q.get('change')) and q.get('price') is not None and fresh(q.get('at'),now,QUOTE_MAX_AGE)]
    quotes=cash if phase in ('OPENING','AFTER OPEN') else futures if phase=='PREOPEN' else []
    if quotes and ((label=='Rast' and all(q['change']<0 for q in quotes)) or (label=='Korekcia' and all(q['change']>0 for q in quotes))):
        lines[0]='🇺🇸 VERDIKT TRHU: Neistota — Kryptotrh a americké kotácie majú protichodný smer.'
    if quotes:
        movement='rastú' if all(q['change']>0 for q in quotes) else 'klesajú' if all(q['change']<0 for q in quotes) else 'majú zmiešaný smer'
        values=', '.join(q['name']+' '+analyst.pct(q['change']) for q in quotes)
        at=min(q['at'] for q in quotes).astimezone(BRATISLAVA).strftime('%H:%M')
        items.append(('Futures ' if phase=='PREOPEN' else 'Akcie ')+movement+' ('+values+'; Yahoo '+at+'). '+('Predbežný kontext pred otvorením.' if phase=='PREOPEN' else 'Voči predošlému záveru, nie od dnešného otvorenia.')+' '+('Priaznivý kontext pre rizikové aktíva, nie potvrdený BUY.' if movement=='rastú' else 'Slabší rizikový apetít môže brzdiť altcoiny.' if movement=='klesajú' else 'Vplyv na altcoiny nie je jednotný.'))
    else:items.append('Aktuálny smer amerických akcií nepotvrdený; '+('riadna seansa ešte nezačala.' if phase=='PREOPEN' else 'spoľahlivé porovnateľné kotácie chýbajú.'))
    if coherent:
        items.append('Krypto za 24 h: BTC '+analyst.pct(b)+', kapitalizácia '+analyst.pct(cap)+'. '+('Altcoiny väčšinovo zaostávajú za BTC; široký obrat nepotvrdený.' if sum(x<b for x in alts)>len(alts)/2 else 'Sleduj, či pohyb potvrdí širší trh.')+' Nie je to meranie reakcie po otvorení USA ani čistého toku kapitálu.')
    notices=model.get('event_notices')
    if notices is not None and notices.get('selected'):items.append(notices['selected'][0]['text'])
    releases=event_lifecycle.lines(fund,now) if notices is None else []
    if releases:
        # Structured Slovak result and conditional impact; full source text stays diagnostic.
        selected=[s for s in releases if s.startswith(('Fed ','HDP USA','PCE inflácia','Spotrebiteľská inflácia','Trh práce USA'))]
        if selected:items.append(selected[0]+' Konsenzus/odchýlka a príčina reakcie nepotvrdené; 24–72 h preveriť reakciu BTC, dolára a výnosov.')
    upcoming=[]
    for event in fund.get('events',[]):
        at=timestamp(event.get('event_at'))
        if notices is not None and not any(n.get('state')=='UPCOMING' and timestamp(n.get('event_at'))==at for n in notices.get('selected',[])):continue
        if event.get('scheduled') and event.get('lifecycle','UPCOMING')=='UPCOMING' and at and 0<(at-now).total_seconds()<=72*3600:
            upcoming.append((at,event))
    upcoming.sort(key=lambda row:row[0])
    next_event=None
    if upcoming:
        at,event=upcoming[0]
        cats=set(event.get('categories',[]))
        label=next((name for key,name in [('Fed','Fed/FOMC'),('CPI','CPI USA'),('PCE','PCE USA'),('GDP','HDP USA'),('employment','Trh práce USA')] if key in cats),'Makro udalosť')
        next_event=label+' '+at.astimezone(BRATISLAVA).strftime('%d.%m. %H:%M')+' Bratislava ('+str(event.get('source','overený kalendár'))[:35]+')'
        if len(items)<3:items.append(next_event+'; prekvapenie môže zvýšiť volatilitu BTC a altcoinov. Samotný termín nie je predajný signál.')
    lines += ['• '+s for s in items[:3]]
    comp=model.get('comparison',{})
    if comp.get('status')=='COMPARED':lines.append('Od '+datetime.fromisoformat(comp['previous_at']).astimezone(BRATISLAVA).strftime('%H:%M')+' Bratislava: '+comp.get('direction','zmena nepotvrdená')+'.')
    view=model.get('forecasts',{}).get('BTC',{}).get('24–72 h',{})
    if not 0<=now.timestamp()-snapshot.get('at',0)<=900:view={}
    lines += ['24–72 HODÍN: hlavný technický scenár — '+view.get('base','smer nemožno spoľahlivo určiť')+'. Alternatíva: '+view.get('upside','potvrdenie rastovej štruktúry a objemu')+'; riziko: '+view.get('downside','potvrdené narušenie podpory')+'.', 'ČO ROBIŤ:']
    base=analyst.final_text(model,snapshot,now,'usa',inventory)
    actions=report_verdict.actions(base)
    held={s:a for s,a,c in actions if c=='držba'}
    for s in ('SOL','TAO'):
        lines.append(s+': '+(held[s]+' — podľa existujúcich pravidiel držby.' if s in held else 'držba bezpečne neoverená; osobný pokyn nevzniká.'))
    new=[(s,a) for s,a,c in actions if c=='nový nákup']
    buy=[s+' '+a for s,a in new if a in ('BUY NOW','BUY PULLBACK')]
    lines.append('Nové nákupy: '+(', '.join(buy) if buy else 'WAIT — potvrdený realizovateľný vstup chýba.')+' USA kontext sám nemení obchodné signály.')
    watch=[]
    if view.get('status')=='CONDITIONAL':
        for key,name in [('support','BTC podpora'),('resistance','BTC rastová hranica')]:
            if analyst.number(view.get(key)):watch.append(name+' '+analyst.price(view[key])+' (uzavretie 4h)')
    if next_event:watch=watch[:1]+[next_event]
    lines.append('ČO SLEDOVAŤ: '+('; '.join(watch[:2]) if watch else 'potvrdenie štruktúry BTC a reakciu altcoinov; presné hranice nepotvrdené')+'.')
    text=without_links('\n'.join(lines))
    # No truncation of actions/conditions: fail the contract before any sending.
    if len(text)>2000:raise ValueError('US brief exceeds 2000 characters')
    return text
