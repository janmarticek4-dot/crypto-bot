"""Deterministic analytical reports. Events never alter trade decisions."""
import os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from .data import PRIMARY
from .fundamentals import timestamp
from .strategy import costs

BL=ZoneInfo('Europe/Bratislava')

def money(value):
    if value is not None:
        for divisor,suffix in ((1e12,'T'),(1e9,'B'),(1e6,'M')):
            if abs(value)>=divisor:return f'${value/divisor:,.2f}{suffix}'
    return 'N/A' if value is None else f'${value:,.2f}' if abs(value)>=1 else f'${value:.6f}'.rstrip('0').rstrip('.')

def pct(value):
    return 'N/A' if value is None else f'{value:+.2f}%'

def delta(new,old):
    return (new/old-1)*100 if new is not None and old and old>0 else None

def scenarios(data):
    """Conditional technical paths, not statistically calibrated forecasts."""
    p=data.get('price');frames=data.get('frames',{})
    out=[]
    for label,tf,hours in [('24–72 h','4h',72),('7–14 dní','1d',336)]:
        t=frames.get(tf,{})
        lo,hi=t.get('support'),t.get('resistance')
        atr=t.get('atr')
        if data.get('stale') or not p or not lo or not hi or not atr or not lo<p<hi:
            out.append(dict(horizon=label,hours=hours,available=False,text=f'{label}: N/A — chýbajú spoľahlivé obojstranné hranice.'))
            continue
        trend='rastový' if t.get('ema200') and p>t['ema200'] else 'nepotvrdený/slabý'
        text=(f'{label}: základ konsolidácia {money(lo)}–{money(hi)}; rast po uzavretí {tf} nad {money(hi)} → {money(hi+atr)}; '
              f'pokles po uzavretí pod {money(lo)} → {money(max(0,lo-atr))}. '
              f'Neplatnosť základného scenára: uzavretie mimo pásma. Dôvod: {tf} štruktúra, trend {trend}. '
              'Neistota vysoká; pravdepodobnosti N/A.')
        out.append(dict(horizon=label,hours=hours,available=True,low=lo,high=hi,text=text))
    return out

def evaluate(state,snapshot):
    """Mature only at horizon end; missing exact closed bar stays pending."""
    now=snapshot['at']
    items=state.setdefault('analysis_forecasts_v11',[])
    identities={i.get('id') for i in items}
    for legacy in state.get('predictions_v11',[]):
        identity='legacy:'+str(legacy.get('at'))+'|'+str(legacy.get('symbol'))+'|'+str(legacy.get('horizon'))
        if identity not in identities and all(legacy.get(k) is not None for k in ('due','price','low','high','symbol','at','horizon')):
            items.append(dict(legacy,id=identity,method='legacy-volatility-envelope',sources={'status':'legacy source metadata unavailable'}))
            identities.add(identity)
    for item in items:
        if item.get('outcome') is not None or now<item['due']:continue
        rows=snapshot['coins'].get(item['symbol'],{}).get('raw',{}).get('1h',[])
        # Last complete bar at/before due, at most one hour away; no later price.
        bars=[r for r in rows if item['due']-3600 < r['timestamp']/1000+3600 <= item['due']]
        if not bars:continue
        price=bars[-1]['close']
        inside=item['low']<=price<=item['high']
        item['outcome']=dict(price=price,return_pct=delta(price,item['price']),inside=inside,
            status='base_confirmed' if inside else 'base_failed',evaluated_at=now,
            note='Endpoint evaluation; alternate path activation is not proven by endpoint alone.')

def remember(state,snapshot,evals,slot):
    now=snapshot['at'];items=state.setdefault('analysis_forecasts_v11',[])
    # A slot retry must not create a second forecast with revised boundaries.
    key=str(slot) if slot else str(now)
    for symbol in ('BTC',*PRIMARY):
        for f in scenarios(snapshot['coins'].get(symbol,{})):
            if not f['available']:continue
            identity=f"{key}|{symbol}|{f['horizon']}"
            if any(i['id']==identity for i in items):continue
            items.append(dict(id=identity,symbol=symbol,at=now,due=now+f['hours']*3600,
                horizon=f['horizon'],price=snapshot['coins'][symbol]['price'],low=f['low'],high=f['high'],
                action=evals.get(symbol,{}).get('action','CONTEXT'),
                text=f['text'],method='closed-structure-v1',data_at=now,
                sources=dict(price=snapshot['coins'][symbol].get('price_source'),
                    metadata_at=snapshot['coins'][symbol].get('metadata_at'),
                    ohlcv='Binance public closed candles',
                    last_closed_bars={tf:rows[-1]['timestamp'] for tf,rows in snapshot['coins'][symbol].get('raw',{}).items() if rows}),
                outcome=None))
    state['analysis_forecasts_v11']=items[-4000:]
    local=datetime.fromtimestamp(now,BL)
    if slot and str(slot).endswith('07:00'):
        state['morning_plan_v11']=dict(date=local.date().isoformat(),at=now,
            coins={s:{k:d.get(k) for k in ('price','market_cap','volume_24h','stale')} |
                   dict(action=evals.get(s,{}).get('action'),trend=d.get('frames',{}).get('4h',{}).get('higher_structure'))
                   for s,d in snapshot['coins'].items()},
            events=[e['id'] for e in state.get('fundamentals_v11',{}).get('events',[])])

def event_lines(result,now):
    events=result.get('events',[]);out=[]
    for title,start,end in [('NAJBLIŽŠÍCH 24 HODÍN',0,1),('NAJBLIŽŠÍCH 7 DNÍ',1,7),('RIZIKOVÉ UDALOSTI DO 14 DNÍ',7,14)]:
        out.append(title+(' (ďalšie dni, bez opakovania)' if start else ''))
        selected=[]
        for e in events:
            at=timestamp(e.get('event_at'))
            date_only=e.get('event_date')
            if not e.get('scheduled') or (not at and not date_only):continue
            if at:
                days=(at.timestamp()-now)/86400
            else:
                days=(datetime.fromisoformat(date_only).date()-datetime.fromtimestamp(now,BL).date()).days
            if not (start<=days<end or (end==14 and days==14)):continue
            if start==7 and not set(e.get('categories',[])) & {'Fed','CPI','PCE','GDP','employment','unlock','regulation','hack'}:continue
            selected.append((at or datetime.fromisoformat(date_only).replace(tzinfo=BL),e))
        for at,e in sorted(selected,key=lambda x:x[0])[:5]:
            when=at.astimezone(BL).strftime('%d.%m.%Y %H:%M')+' Bratislava' if e.get('event_at') else e['event_date']+' (dátum zdroja) | presný čas Bratislava N/A'
            out.extend([f"{when} | {e['title']} | {e['url']}",
                'Očakávanie trhu N/A; predchádzajúca hodnota N/A; výsledok N/A. '+('Dotknuté: '+e['symbol'] if e.get('symbol') else 'Dotknuté: BTC a sledované altcoiny')+'.',
                'Overený cenový dopad: N/A. Možný mechanizmus (nie predikcia): '+(' '.join(e.get('mechanisms',[])) or 'N/A')+' Priaznivý/nepriaznivý scenár závisí od výsledku voči overeným očakávaniam; bez konsenzu N/A.',
                'Po zverejnení: overiť výsledok a revízie, potom reakciu BTC/altcoinov. Horizont hodiny až dni; volatilita môže vzrásť. Existujúce pozície: preveriť ochranné hranice; nové: neprekročiť plánované riziko. Udalosť nevytvára BUY/SELL.'])
        if not selected:out.append('N/A — žiadna dostupná overená udalosť v pokrytých kalendároch; úplnosť kalendára nie je potvrdená.')
    bad=[s['source'] for s in result.get('sources',[]) if s['status']!='OK']
    if bad:out.append('Nedostupné zdroje: '+', '.join(bad))
    out.append('Konsenzus, FedWatch, ETF toky, unlock kalendár a geopolitické pokrytie: N/A, ak nie sú doložené konkrétnym zdrojom.')
    return out

def fundamental_lines(symbol,result,state,now):
    from .fundamental_analysis import coin_lines
    return coin_lines(symbol,result,datetime.fromtimestamp(now,timezone.utc) if isinstance(now,(int,float)) else now,state.get('fundamental_metrics_v11',{}))

def build(snap,evals,book,safety,fundamentals,state,slot,local):
    evening=bool(slot and str(slot).endswith('20:00'));now=snap['at']
    analysis_now=max(datetime.fromtimestamp(now,timezone.utc),local.astimezone(timezone.utc)) if local.tzinfo else datetime.fromtimestamp(now,timezone.utc)
    out=[f"📊 V11.1 — {'VEČERNÉ VYHODNOTENIE' if evening else 'RANNÝ PLÁN' if slot else 'RUČNÁ ANALÝZA'}",
        local.strftime('%d.%m.%Y %H:%M Bratislava'),
        'Vývojový analytický report. V11 signály sú experimentálne; žiadny nový potvrdený produkčný signál sa týmto neaktivuje.',
        f"Technické riziko {safety['state']}; udalostné pokrytie neúplné. "+' '.join(safety['reasons'])]
    from .diagnostics import action_summary
    out=out[:2]+action_summary(snap,evals,safety,fundamentals,state)+out[2:]
    from .fundamental_analysis import overview
    g=snap.get('global_data',{});oldg=state.get('global_previous_v11',{})
    out.append(f"TRH: kapitalizácia {money(g.get('cap'))}, 24h {pct(g.get('change'))}; objem {money(g.get('volume'))}; BTC dominancia {pct(g.get('dominance'))}; zmena dominancie od analýzy {format(g['dominance']-oldg['dominance'],'+.2f')+' p. b.' if g.get('dominance') is not None and oldg.get('dominance') is not None else 'N/A'}.")
    from .portfolio import valuation
    val=valuation(book,{s:d.get('price') if not d.get('stale') else None for s,d in snap['coins'].items()}) if 'positions' in book else None
    if val and not book.get('transactions') and not any(p.get('qty',0)>0 for p in book.get('positions',{}).values()):
        out.append('Evidencia nemá potvrdené obchody; východisková hotovosť nie je potvrdený zostatok účtu eToro.')
        val=None
    if val and val['complete']:out.append(f"Portfólio po predajnom poplatku, pred spreadom {money(val['equity'])}; drawdown {pct(val['drawdown'])}; hotovosť {money(book['cash'])}. Iba potvrdené manuálne záznamy.")
    out.append('Globálne dáta: '+(datetime.fromtimestamp(g['at'],BL).isoformat()+' CoinGecko' if g.get('at') else 'N/A'))
    btc=snap['coins']['BTC'];t=btc.get('frames',{}).get('1d',{})
    out.append(f"BTC {money(btc.get('price'))}, 24h {pct(btc.get('change_24h'))}; denná EMA50 {money(t.get('ema50'))}, EMA200 {money(t.get('ema200'))}; volatilita ATR {pct(t['atr']/btc['price']*100) if t.get('atr') and btc.get('price') else 'N/A'}.")
    if not btc.get('stale') and btc.get('change_24h') is not None and g.get('change') is not None and btc['change_24h']*g['change']<0 and abs(btc['change_24h']-g['change'])>=1:
        out.append('⚠️ Divergencia BTC a kapitalizácie trhu. Nejde o dôkaz toku kapitálu ani príčiny pohybu.')
    out += overview(fundamentals,analysis_now)
    held=[s for s,e in evals.items() if e['held']]
    upcoming=sorted((e for e in fundamentals.get('events',[]) if e.get('scheduled')),key=lambda e:e.get('event_at') or e.get('event_date') or '')
    out += ['Najdôležitejšie riziko: '+('neúplné trhové dáta' if safety['state']=='UNKNOWN' else 'neúplné udalostné pokrytie; technické riziko '+safety['state']),
        'Najlepšia potvrdená produkčná príležitosť: N/A — výskumné signály nie sú schválené.',
        'Držané pozície: '+('N/A — shadow test nenačítava skutočnú evidenciu' if state.get('shadow_mode') else ', '.join(s+': '+evals[s]['action']+' (analytické posúdenie)' for s in held) or 'žiadne v potvrdenej evidencii'),
        'Najbližšia udalosť: '+((upcoming[0]['title']+' | '+str(upcoming[0].get('event_at') or upcoming[0].get('event_date'))+' | '+upcoming[0]['url']) if upcoming else 'N/A')]
    out += [f['text'] for f in scenarios(btc)]
    out.append('Makro/fundamentálny smer BTC N/A; blížiace sa overené udalosti sú v kalendári nižšie a môžu zneplatniť technický plán.')
    morning=state.get('morning_plan_v11',{})
    compare=evening and morning.get('date')==local.date().isoformat()
    if evening:out.append('POROVNANIE S RÁNOM' if compare else 'Ranný plán pre dnešný deň N/A; neporovnávame s iným dňom.')
    technical_appendix=[]
    for symbol in PRIMARY:
        d=snap['coins'][symbol];e=evals[symbol];tf=d.get('frames',{}).get('4h',{})
        label='experimentálny kandidát (neaktivovaný)' if any('čakajú na historickú validáciu' in r for r in e.get('reasons',[])) else 'experimentálny kandidát' if e['action'].startswith('BUY') else 'experimentálne ochranné posúdenie' if e['action'] in ('SELL','REDUCE') else 'analytický stav'
        out += ['',f"{symbol}: {e['action']} ({label}); {'DRŽBA N/A (SHADOW)' if state.get('shadow_mode') else 'VLASTNÍŠ' if e['held'] else 'BEZ POZÍCIE'}",
            f"Cena {money(d.get('price'))}; 24h {pct(d.get('change_24h'))}; zdroj {d.get('price_source','N/A')}; vek {round(d['age_seconds']) if isinstance(d.get('age_seconds'),(int,float)) else 'N/A'} s; {'NEAKTUÁLNE' if d.get('stale') else 'aktuálne'}.",
            f"Kapitalizácia {money(d.get('market_cap'))}; objem {money(d.get('volume_24h'))}; "+' '.join(e.get('display_reasons') or e['reasons'])]
        from .diagnostics import entry_diagnostic
        diag=e.get('entry_diagnostic') or entry_diagnostic(d,e,approved=symbol in {x.strip().upper() for x in os.getenv('ETORO_VERIFIED_SYMBOLS','').split(',')},market_complete=snap.get('complete',False),risk_normal=safety['state']=='NORMAL')
        tech=diag['technical']
        out.append(f"Technická príležitosť: {tech['quality']}; skóre {tech['score'] if tech['score'] is not None else 'N/A'}/6; nesplnené: {', '.join({'trend':'trend4h','broad':'denný trend','momentum':'momentum','volume':'objem','structure':'štruktúra','strength':'sila ADX'}.get(k,k) for k in tech['failed']) or 'žiadne'}.")
        out.append('Samostatné blokovania nového vstupu: '+('; '.join(diag['entry_blockers']) or 'žiadne z diagnostikovaných')+'. Signál zostáva '+e['action']+'.')
        old=state.get('snapshots_v11',{}).get(symbol,{})
        out.append(f"Od predošlej analýzy: kap. {pct(delta(d.get('market_cap'),old.get('market_cap')))}, objem {pct(delta(d.get('volume_24h'),old.get('volume_24h')))}.")
        correction='prehlbuje sa' if tf.get('support_broken') else 'lokálny obrat technicky potvrdený' if tf.get('breakout') and (tf.get('relative_volume') or 0)>=1.1 else 'stabilizácia/nepotvrdený obrat' if tf else 'N/A'
        technical_appendix.append(f"{symbol} — Korekcia: {correction}; RSI {tf.get('rsi14','N/A')}; MACD hist. {tf.get('macd_hist','N/A')}; ADX {tf.get('adx','N/A')}; ATR {money(tf.get('atr'))}.")
        technical_appendix.append('EMA20/50/100/200 4h: '+' / '.join(money(tf.get('ema'+str(n))) for n in (20,50,100,200)))
        technical_appendix.append(f"Relatívna sila vs BTC 7 dní {pct(d.get('relative_strength_btc_7d')*100) if d.get('relative_strength_btc_7d') is not None else 'N/A'}; RVOL {tf.get('relative_volume','N/A')}.")
        out += fundamental_lines(symbol,fundamentals,state,analysis_now)
        out += [f['text'] for f in scenarios(d)]
        related=[x['title'] for x in fundamentals.get('events',[]) if x.get('scheduled') and x.get('symbol')==symbol]
        if related:out.append('Projektové udalosti: '+'; '.join(related[:2])+'. Dopad vyžaduje potvrdenie.')
        if d.get('relative_strength_alt_median_7d') is not None:out.append(f"Relatívna sila nad medián hlavnej šestice: {pct(d['relative_strength_alt_median_7d']*100)}.")
        if e.get('economics') and e.get('stop',0)>0:
            c=e['economics'];c2=costs(e['entry'],e['tp2'],e['stop'],c['spread'])
            out.append(f"Experimentálny plán: vstup {money(e['entry'])}; stop {money(e['stop'])}; TP1 {money(e['tp1'])}, TP2 {money(e['tp2'])}; čisté R:R {c['net_rr']:.2f}/{c2['net_rr']:.2f}. Poplatky {c['buy_fee']:.1%} + {c['sell_fee']:.1%}; spread {c['spread'] if c['spread'] is not None else 'N/A — R:R optimistická hranica'}. Výnos pri cieli nie je očakávaný výnos; manuálne vykonanie môže zhoršiť cenu.")
        else:out.append('Spoľahlivý vstup/stop/TP/R:R: N/A.')
        if compare:
            old=morning['coins'].get(symbol,{})
            out.append(f"Od rána: cena {pct(delta(d.get('price'),old.get('price'))) if not d.get('stale') and not old.get('stale') else 'N/A'}; kap. {pct(delta(d.get('market_cap'),old.get('market_cap')))}; objem {pct(delta(d.get('volume_24h'),old.get('volume_24h')))}; pokyn {old.get('action','N/A')} → {e['action']}. Odporúčanie nie je uskutočnený obchod.")
    out.append('Spoločné medzery fundamentov: nepokryté príjmy, aktivita, emisie/unlocky a adopcia sú N/A. Marketing nie je dôkaz ekonomického výsledku.')
    out += ['', 'DOPLNKOVÝ WATCHLIST (mimo hlavnej šestice):']
    out += [f"{s}: {e['action']}, {money(snap['coins'][s].get('price'))}; experimentálny, nie potvrdený produkčný signál." for s,e in evals.items() if s not in PRIMARY]
    from .diagnostics import risk_evidence
    evidence=risk_evidence(snap,safety)
    out.extend(['VYSVETLENIE TECHNICKÉHO STAVU',evidence['rule'],f"BTC support prelomený: {evidence['btc_support_broken']}; ETH: {evidence['eth_support_broken']}; altcoiny: {evidence['alt_support_breaks']}/6.",evidence['interpretation'],'Cenová pravdepodobnosť ďalšieho prepadu: N/A; táto diagnostika negeneruje alert ani BUY/SELL.'])
    from .macro_context import lines as macro_lines
    out += macro_lines(fundamentals.get('macro_context',{}))
    from .event_ledger import lines as result_lines
    out += ['',*event_lines(fundamentals,now),*result_lines(state,now),'KONTROLA DOZRETÝCH SCENÁROV']
    matured=[i for i in state.get('analysis_forecasts_v11',[]) if i.get('outcome')]
    for i in matured[-7:]:
        r=i['outcome'];out.append(f"{i['symbol']} {i['horizon']} od {datetime.fromtimestamp(i['at'],BL):%d.%m. %H:%M}: {'v základnom pásme' if r['inside'] else 'MIMO pásma – scenár sa nenaplnil'}; pohyb {pct(r['return_pct'])}. Nie je to zisk obchodu.")
    if not matured:out.append('N/A — žiadny vyhodnotiteľný dozretý scenár. Otvorené horizonty nehodnotíme predčasne.')
    pending=sum(i.get('outcome') is None and i['due']<=now for i in state.get('analysis_forecasts_v11',[]))
    if pending:out.append(f'{pending} dozretých záznamov čaká na presnú historickú cenu; neskoršiu cenu nedosadzujeme.')
    ranked=sorted((s for s in PRIMARY if evals[s].get('data_complete')),key=lambda s:evals[s].get('score',-1),reverse=True)
    out += ['', 'AKČNÝ ZÁVER', '1. Potvrdený produkčný BUY: žiadny nový signál z tejto experimentálnej vrstvy.',
        '2. Technické poradie na preverenie: '+(' > '.join(ranked) or 'N/A')+'; vstupné a ochranné úrovne vyššie, poradie nie je pokyn na nákup.',
        '3. Držané/HOLD: '+('N/A — skutočné pozície sa nenačítali' if state.get('shadow_mode') else ', '.join(s for s,e in evals.items() if e['held'] and e['action']=='HOLD') or 'žiadne'),
        '4. Preveriť ochranu: '+(', '.join(s for s,e in evals.items() if e['held'] and e['action'] in ('SELL','REDUCE')) or 'bez potvrdeného experimentálneho upozornenia')+'. Nevykonané predaje nemenia evidenciu.',
        '5. Pred významnou udalosťou neprekročiť vlastný rizikový rozpočet; pri neúplnom kalendári vhodnú výšku hotovosti nemožno spoľahlivo určiť.',
        'Malá korekcia sama neodôvodňuje predaj a opätovný nákup po nákladoch. Bot nikdy nevykonáva obchody. Monitoring neposiela rutinné správy.']
    out += ['', 'TECHNICKÁ PRÍLOHA']+technical_appendix
    return out
