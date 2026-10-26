"""Evidence-bounded interpretation; no generated facts or trade decisions."""
import re
from datetime import timedelta
from .fundamentals import timestamp,PATTERNS

SYMBOLS = ('SOL','TAO','FET','AAVE','ONDO','RENDER')
ALIASES = {'SOL':r'\bsolana\b|\bSOL\b','TAO':r'\bbittensor\b|\bTAO\b',
           'FET':r'\bfetch.ai\b|\bFET\b|artificial superintelligence alliance',
           'AAVE':r'\baave\b','ONDO':r'\bondo\b','RENDER':r'\brender network\b|\bRENDER\b'}
DIMENSIONS = ('macro_releases','rates_expectations','yields','geopolitics','regulation_etf',
              'verified_flows','project_events','usage_tvl','revenue_fees','unlocks_emissions')


def analyze(result, now):
    evidence=[];seen=set()
    for event in result.get('events',[]):
        if not isinstance(event,dict) or event.get('scheduled'):continue
        at=timestamp(event.get('published_at'));collected=timestamp(event.get('retrieved_at'))
        url=event.get('url','')
        if not isinstance(url,str) or not isinstance(event.get('title'),str) or not event.get('id') or not event.get('source'):continue
        if not at or not collected or not timedelta(0)<=now-at<=timedelta(hours=72) or not timedelta(0)<=now-collected<=timedelta(hours=24):continue
        if not url.startswith('https://'):continue
        title=re.sub(r'\s+',' ',event.get('title','')).strip()
        key=re.sub(r'[^\w]+',' ',title.casefold()).strip()
        if not title or key in seen:continue
        seen.add(key)
        cats={c for c in event.get('categories',[]) if c=='project' or (c in PATTERNS and re.search(PATTERNS[c],title,re.I))};kind=event.get('kind','news')
        if not cats:continue
        symbols=[s for s,p in ALIASES.items() if re.search(p,title,re.I)]
        if event.get('symbol') in SYMBOLS and event['symbol'] not in symbols:symbols.append(event['symbol'])
        low=kind in ('software_release_notice','governance_repository_change') or bool(re.search(r'proposal|proposes|\bfloats\b|digital euro|price risks|price prediction|price forecast|three things|partnership|partner|governance|marketing',title,re.I))
        if low:
            significance='nízka bez potvrdenej aktivácie alebo merateľného používania'
            impact='neutrálny/nepotvrdený';verify='aktiváciu, rozsah nasadenia a nezávislé metriky používania'
        elif 'hack' in cats:
            significance='potenciálne významné bezpečnostné riziko'
            impact='negatívny, iba ak sa potvrdí incident a expozícia';verify='primárne vyjadrenie, stratu a dotknuté protokoly'
        elif 'unlock' in cats:
            significance='možná zmena obchodovateľnej ponuky'
            impact='možný tlak ponuky; unlock nie je predaj';verify='dátum, množstvo, príjemcov a skutočný presun tokenov'
        elif cats & {'Fed','CPI','PCE','employment','GDP'}:
            significance='relevantné pre sadzby a ochotu riskovať'
            impact='obojsmerný; smer bez výsledku voči konsenzu nepotvrdený';verify='prvý výsledok, overený konsenzus, revízie a reakciu výnosov'
        else:
            significance='potenciálna zmena projektového alebo regulačného rizika'
            impact='smer nepotvrdený';verify='primárny dokument, účinnosť a ekonomický rozsah'
        evidence.append(dict(id=event['id'],title=title,source=event['source'],url=url,
            published_at=at.isoformat(),retrieved_at=collected.isoformat(),
            fact_scope='zdroj publikoval uvedené oznámenie; samotný titulok nepotvrdzuje realizáciu',
            symbols=symbols or list(SYMBOLS),significance=significance,impact=impact,
            confirmation=verify,horizon=None,material=not low,categories=sorted(cats)))
    evidence.sort(key=lambda e:(e['material'],e['published_at']),reverse=True)
    available=sum(s.get('status')=='OK' for s in result.get('sources',[]))
    coverage={k:False for k in DIMENSIONS}
    coverage['macro_releases']=bool(result.get('economic_observations',{}).get('observations'))
    coverage['yields']=bool(result.get('macro_context',{}).get('treasury'))
    coverage['usage_tvl']=bool(result.get('metrics'))
    coverage['revenue_fees']=bool(result.get('project_economics',{}).get('observations'))
    coverage['project_events']=any(e['material'] and set(e['categories']) & {'project','hack','unlock'} for e in evidence)
    coverage['regulation_etf']=any('regulation' in e['categories'] for e in evidence)
    return dict(evidence=evidence,coverage=coverage,source_ok=available,source_total=len(result.get('sources',[])),
                coverage_note='Čiastočne pozorované tematické okruhy, nie percento všetkých významných informácií; úplnosť nie je merateľná.')


def event_lines(item):
    return [f"• {item['title']} ({item['published_at']}; {item['source']}).",
            f"Publikované tvrdenie, nie nezávislé potvrdenie realizácie. Význam: {item['significance']}. Dopad: {item['impact']}. Overiť: {item['confirmation']}.",
            f"Dotknuté: {', '.join(item['symbols'])}; horizont dopadu N/A. {item['url']} | zber {item['retrieved_at']}."]


def overview(result,now):
    a=analyze(result,now)
    out=['FUNDAMENTÁLNY SÚHRN', 'Príčina dnešného pohybu: nepreukázaná; nasledujúce faktory nie sú dôkaz príčinnej súvislosti.']
    relevant=[e for e in a['evidence'] if e['material']]
    ranking=result.get('editorial_ranking',{}).get('ids',[])
    relevant.sort(key=lambda e:ranking.index(e['id']) if e['id'] in ranking else len(ranking))
    for item in relevant[:3]:out+=event_lines(item)
    if not relevant:out.append('V dostupných aktuálnych zdrojoch nebola identifikovaná nová významná správa; pokrytie je neúplné.')
    macro=result.get('macro_context',{});y=macro.get('treasury')
    if y:out.append(f"Stále platný faktor: US výnosy {y['date']}: 2Y {y['2y']:.2f} %, 10Y {y['10y']:.2f} %. Zmena a smer tlaku na krypto bez porovnania N/A. {macro['url']}; zber {macro.get('checked_at','N/A')}.")
    if y and y.get('change_bp'):
        out.append(f"Výnosy od {y['previous_date']}: 2Y {y['change_bp']['2y']:+.1f} b. b., 10Y {y['change_bp']['10y']:+.1f} b. b. Rast môže sprísňovať diskontovanie, pokles ho uvoľňovať; samotný rozdiel nedokazuje dôvod pohybu krypta.")
    for item in result.get('economic_observations',{}).get('observations',{}).values():
        out.append(f"{item['label']}: {item['value']:,.2f} {item['unit']}, obdobie {item['period']}; predchádzajúca hodnota {item.get('previous_value','N/A')}. Najnovšie revidované meranie, prvý výsledok a konsenzus N/A.")
    out+=['24–72 h: smer fundamentov nepotvrdený; pri makro prekvapení sledovať výnosy a reakciu BTC, nie samotný titulok.',
          '7–14 dní: podmienený výhľad podľa kalendára, účinnosti oznámení a následných metrík; pravdepodobnosti N/A.',
          f"Dostupnosť zdrojov {a['source_ok']}/{a['source_total']}; čiastočne pokryté okruhy {sum(a['coverage'].values())}/{len(DIMENSIONS)}. Podiel všetkých významných informácií: neznámy."]
    return out


def coin_lines(symbol,result,now,previous=None):
    a=analyze(result,now)
    items=[e for e in a['evidence'] if symbol in e['symbols'] and (len(e['symbols'])<6 or 'project' in e['categories'])]
    out=['Fundamentálny stav: smer nepotvrdený.']
    for item in items[:1]:out+=event_lines(item)
    if not items:out.append('Nová významná projektová zmena v dostupných zdrojoch nepotvrdená; hodnotenie N/A, neznamená to absenciu udalostí.')
    metric=result.get('metrics',{}).get(symbol)
    if metric:out.append(f"Pozorovaný TVL ${metric['value']:,.0f} k {metric['at']}; {metric['url']}; zber {metric['observed_at']}. TVL nie je príjem, adopcia tokenu ani čistý tok kapitálu.")
    prior=(previous or {}).get(symbol,{})
    if metric and prior and prior.get('at')!=metric.get('at') and prior.get('value',0)>0:
        out.append(f"TVL od predošlej analýzy {(metric['value']/prior['value']-1)*100:+.1f} %; porovnanie rôznych pozorovaní, nie čistý prílev kapitálu.")
    economics=result.get('project_economics',{}).get('observations',{}).get(symbol,{})
    for kind,value in economics.items():
        previous=value.get('previous_value');change=(value['value']/previous-1)*100 if previous and previous>0 else None
        out.append(f"{'Poplatky' if kind=='fees' else 'Príjmy'}: ${value['value']:,.0f}/deň, obdobie {value['period']}; zmena {format(change,'+.1f')+'%' if change is not None else 'N/A'} od {value.get('previous_period')}. {value['url']}; zber {value['retrieved_at']}. Čas publikovania N/A; agregát poskytovateľa, nie príjem držiteľa tokenu.")
    out.append('Fundamentálny výhľad 24–72 h / 7–14 dní: bez potvrdeného smerového impulzu; zmení ho overená účinnosť udalosti alebo metriky.')
    return out
