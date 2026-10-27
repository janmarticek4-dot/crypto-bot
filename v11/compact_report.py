"""Short, evidence-bounded presentation. Never changes a native signal."""
from .fundamental_analysis import analyze
from .fundamentals import timestamp
from datetime import timedelta
import re


def pct(x):
    return 'N/A' if x is None else f'{x:+.1f}%'


def levels(e,p):
    price=e.get('price');support=e.get('support');resistance=e.get('resistance')
    lo=('Prerazený support '+p(support)+' (teraz nad cenou)'
        if price and support and support>price else 'S '+p(support))
    hi=('prekonaná rezistencia '+p(resistance)+' (pod cenou)'
        if price and resistance and resistance<price else 'R '+p(resistance))
    return lo+' / '+hi


def reason(e):
    if e.get('error') or not e.get('price'):return 'Chýbajú spoľahlivé údaje; záver je obmedzený.'
    if e['action'] in ('SELL','REDUCE'):
        return ('Pokles od maxima '+pct(-abs(e['drawdown_pct']))+' a súbeh rizík V10.6.' if e.get('drawdown_pct') is not None else 'Súbeh rizík V10.6; ďalší prepad nie je istý.')
    if e['action']=='HOLD':return 'Pravidlá V10.6 uprednostňujú držanie pred zmenou pozície.'
    if e['action'].startswith('BUY'):return 'Vstup spĺňa pôvodné pravidlá V10.6; náklady a spread treba preveriť.'
    return 'Nový vstup nemá potvrdenie podľa V10.6; WAIT nie je pokyn predať držbu.'


def render(legacy,snapshot,fund,now,kind,ctx,safety,ev,previous=None):
    p=legacy.format_price;change=ctx.get('global_change')
    label=('VYSOKÉ RIZIKO' if safety['state']=='CRITICAL' else
           'KOREKCIA' if change is not None and change < -1 else
           'RAST' if change is not None and change > 1 else 'STABILIZÁCIA' if change is not None else 'N/A')
    lines=[f"📊 V11.1 — {'RÁNO' if kind=='morning' else 'VEČER'} | {label}",
        now.astimezone(legacy.TZ).strftime('%d.%m.%Y %H:%M Bratislava'),
        f"BTC {p(ctx['btc_data'].get('price_usd'))} ({pct(ctx.get('btc_change_24h'))}); trh {legacy.fmt_big(ctx.get('total_market_cap'))} ({pct(change)}).",
        f"BTC dominancia {format(ctx['btc_dominance'],'.1f')+'%' if ctx.get('btc_dominance') is not None else 'N/A'}; Fear & Greed {(ctx.get('fear') or {}).get('value','N/A')}; riziko V10.6 {safety['state']}.",
        'Pohyb cien je pozorovaný; jeho príčina nie je overená.']
    # Scheduled macro releases outrank headlines. Never invent the missing time.
    scheduled=[]
    for e in fund.get('events',[]):
        if not e.get('scheduled'):continue
        at=timestamp(e.get('event_at'));date=e.get('event_date')
        if at and 0 <= (at-now).total_seconds() <= 14*86400:
            when=at.astimezone(legacy.TZ).strftime('%d.%m. %H:%M');order=at.timestamp()
        elif date and now.date().isoformat()<=date<= (now+timedelta(days=14)).date().isoformat():
            when=date+' čas N/A';order=timestamp(date+'T23:59:59+00:00').timestamp()
        else:continue
        cats=set(e.get('categories',[]))
        if not cats & {'Fed','CPI','PCE','employment','GDP','regulation','unlock'}:continue
        if re.search(r'metropolitan|county|state employment|regional',e.get('title',''),re.I):continue
        scheduled.append((order,e,when))
    if any(e['action'] in ('SELL','REDUCE') for e in ev.values()):
        lines.append('SELL/REDUCE = technické riziko V10.6, nie potvrdená predikcia poklesu ani osobný pokyn predať. Držbu posudzuje súkromná časť.')
    lines.append('HLAVNÉ FAKTORY')
    used=0
    for _,e,when in sorted(scheduled,key=lambda x:x[0])[:1]:
        lines.append(f"• {when}: {e['title']}. Význam: môže zmeniť sadzby/očakávania a riziko altcoinov; smer závisí od výsledku. {e.get('url','N/A')}");used+=1
    evidence=analyze(fund,now)['evidence']
    for e in evidence:
        if used>=2:break
        if not e['material']:continue
        # A wallet/protocol incident without named exposure is not a six-coin event.
        if 'hack' in e['categories'] and len(e['symbols'])==6:continue
        lines.append(f"• {e['published_at'][:10]}: {e['title']}. Význam: {e['significance']}. Dopad: {e['impact']}. Overiť: {e['confirmation']}. {e['url']}");used+=1
    y=fund.get('macro_context',{}).get('treasury')
    if y and used<3:
        bp=y.get('change_bp',{}).get('10y')
        lines.append(f"• US 10Y {y['10y']:.2f}% ({y['date']}"+(f", {bp:+g} bp" if bp is not None else '')+
            '): vyššie výnosy môžu brzdiť rizikové aktíva; nedokazujú príčinu pohybu. '+fund['macro_context'].get('url','N/A'));used+=1
    if not used:lines.append('Nová významná správa v dostupných zdrojoch nepotvrdená; pokrytie je neúplné.')
    lines.append('24–72 h: rast potrebuje návrat nad rezistencie; pod podporami hrozí pokračovanie korekcie. Smer neistý; pravdepodobnosti N/A.')
    for s in legacy.PORTFOLIO:
        e=ev[s];c=snapshot['coins'].get(s,{})
        lines.extend(['',f"{s} {p(e.get('price'))} ({pct(c.get('change_24h'))}) — {'TECHNICKÝ ' if e['action'] in ('SELL','REDUCE') else ''}{e['action']}",reason(e),levels(e,p), 'Zmena: '+e.get('flip','N/A')])
        # Only explicitly attributed material project evidence; no marketing/code feed.
        project=next((x for x in evidence if x['material'] and s in x['symbols'] and len(x['symbols'])<6 and 'project' in x['categories']),None)
        if project:lines.append(f"Projekt: {project['title']} ({project['published_at'][:10]}, {project['source']}); {project['impact']}. {project['url']}")
    # Measured economics: compare distinct periods, never infer token cash flows.
    economy=[]
    for symbol,items in fund.get('project_economics',{}).get('observations',{}).items():
        for metric,v in items.items():
            old=v.get('previous_value')
            if old and old>0 and v.get('previous_period')!=v.get('period'):
                economy.append(f"{symbol} {'poplatky' if metric=='fees' else 'príjmy'} {pct((v['value']/old-1)*100)} ({v['period'][:10]})")
    if economy:lines.append('Ekonomická aktivita (DeFiLlama): '+ '; '.join(economy[:3])+'. Nie je to výnos tokenu ani čistý tok; zdroje v diagnostike.')
    if kind=='evening':
        if not previous:lines.append('Od rána: N/A — chýba overený ranný snapshot.')
        else:
            changes=[]
            for s in legacy.PORTFOLIO:
                old=previous.get(s,{});price=ev[s].get('price');base=old.get('price')
                action=old.get('action') if old.get('rule_engine')=='v10.6-original' else 'iný/neoverený pôvod'
                changes.append(f"{s} {pct((price/base-1)*100) if price and base else 'N/A'} {action}→{ev[s]['action']}")
            lines.append('Od rána: '+'; '.join(changes)+'. Kap./objemy v diagnostike.')
            old_context=previous.get('_context',{})
            old_at=timestamp(old_context.get('at'))
            if old_at and old_at<now:
                old_ids=set(old_context.get('event_ids',[]));new_ids={e['id'] for e in evidence if e['material']}
                lines.append(f"Fundamenty od rána: {len(new_ids-old_ids)} nových, {len(old_ids-new_ids)} už mimo aktuálneho výberu (nie dôkaz zániku rizika).")
            else:lines.append('Fundamentálne porovnanie rána N/A — chýba časovo overená referencia.')
    buy=[s for s,e in ev.items() if e['action'].startswith('BUY')]
    hold=[s for s,e in ev.items() if e['action']=='HOLD']
    wait=[s for s,e in ev.items() if e['action'] in ('WAIT','REDUCE','SELL')]
    protection=[s+' '+e['action'] for s,e in ev.items() if e['action'] in ('REDUCE','SELL')]
    lines+=['','PLÁN', 'Kúpiť: '+(', '.join(buy) or 'žiadny potvrdený vstup')+'.',
        'HOLD: '+(', '.join(hold) or 'žiadny výslovný signál')+'; WAIT znamená čakať s novým nákupom.',
        'Zatiaľ nedokupovať: '+(', '.join(wait) or 'podľa podmienok vyššie')+'.',
        'Pre držané pozície preveriť: '+(', '.join(protection) or 'pôvodný ochranný plán')+'. Bez potvrdenej držby nejde o osobný predajný pokyn.',
        'Kontrola: pri prerazení hraníc, makro udalosti alebo ďalšej analýze.',
        'eToro ≈1% nákup + 1% predaj a spread: malá korekcia sama nie je dôvod predať a znovu kúpiť. Signály V10.6 nezmenené; bez automatických obchodov.',
        'Kapitalizácia/objem/TVL ≠ čisté toky; detaily v diagnostike.',
        'Držba N/A — skutočné pozície sa nenačítavajú.']
    return '\n'.join(lines)
