"""V11.2 evidence/comparison/presentation, not a new trading strategy.
Private inventory is consumed only by final_text(), after public CAS persistence.
"""
import copy,math,re,os
from datetime import datetime,timedelta,timezone
from .shadow_pair import fingerprint,digest,BL
from .fundamental_analysis import analyze,ALIASES
from .fundamentals import timestamp
from .state_policy import require_public_data

COINS=('SOL','TAO','FET','AAVE','ONDO','RENDER')


def number(x):return type(x) in (int,float) and math.isfinite(x)
def delta(a,b):
    if not number(a) or not number(b) or b<=0:return None
    value=(a/b-1)*100
    return value if math.isfinite(value) else None
def pct(x):return 'N/A' if x is None else f'{x:+.1f}%'
def price(x):
    if not number(x):return 'N/A'
    return f'${x:,.0f}' if x>=1000 else f'${x:.2f}' if x>=10 else f'${x:.4g}'
def compact(x):
    if not number(x):return 'N/A'
    for n,label in ((1e12,'T'),(1e9,'B'),(1e6,'M')):
        if abs(x)>=n:return f'${x/n:.2f}{label}'
    return price(x)


def observation(snapshot,fund,now,quotes):
    economics={s:{k:dict(value=v.get('value'),period=v.get('period')) for k,v in items.items()}
               for s,items in fund.get('project_economics',{}).get('observations',{}).items()}
    obs=dict(schema='public-analysis-v112',at=now.isoformat(),fingerprint=fingerprint(snapshot),global_data=copy.deepcopy(snapshot.get('global_data',{})),
        coins={s:dict(price=c.get('price') if not c.get('stale',True) and number(c.get('price')) and c['price']>0 else None,market_cap=c.get('market_cap'),volume_24h=c.get('volume_24h'),
                technical_score=quotes.get(s,{}).get('trend_score_10'),legacy_action=quotes.get(s,{}).get('action'),risk_points=quotes.get(s,{}).get('risk_points'),
                support_broken=c.get('frames',{}).get('4h',{}).get('support_broken')) for s,c in snapshot.get('coins',{}).items() if s in (*COINS,'BTC')},
        metrics={s:dict(value=v.get('value'),at=v.get('at')) for s,v in fund.get('metrics',{}).items()},economics=economics,event_ids=[e['id'] for e in relevant_events(fund,now)])
    obs['fingerprint']=digest(dict(market=obs['fingerprint'],global_data=obs['global_data'],metrics=obs['metrics'],economics=economics,event_ids=obs['event_ids']))
    require_public_data(obs);return obs


def comparison(old,current):
    if not isinstance(old,dict) or old.get('schema')!='public-analysis-v112':return dict(status='N/A',reason='Chýba predchádzajúca doručená V11.2 analýza.')
    if not all(isinstance(old.get(k,{}),dict) for k in ('global_data','coins','metrics','economics')):return dict(status='N/A',reason='Neplatná verejná referencia.')
    if any(not isinstance(v,dict) for k in ('coins','metrics','economics') for v in old.get(k,{}).values()):return dict(status='N/A',reason='Neplatné položky verejnej referencie.')
    if any(not isinstance(v,dict) for values in old.get('economics',{}).values() for v in values.values()):return dict(status='N/A',reason='Neplatné ekonomické pozorovanie.')
    if not isinstance(old.get('fingerprint'),str) or not re.fullmatch(r'[0-9a-f]{64}',old['fingerprint']):return dict(status='N/A',reason='Chýba overiteľný zdrojový fingerprint.')
    a=timestamp(old.get('at'));b=timestamp(current.get('at'))
    if not a or not b or not timedelta(0)<b-a<=timedelta(days=7) or old.get('fingerprint')==current.get('fingerprint'):
        return dict(status='N/A',reason='Referencia je rovnaká, stará alebo časovo neoveriteľná.')
    g=current['global_data'];og=old.get('global_data',{})
    dominance=g.get('dominance');prior=og.get('dominance')
    result=dict(status='COMPARED',previous_at=a.isoformat(),global_cap_pct=delta(g.get('cap'),og.get('cap')),global_volume_pct=delta(g.get('volume'),og.get('volume')) if number(g.get('volume')) and g['volume']>0 else None,
                dominance_pp=dominance-prior if number(dominance) and number(prior) else None,coins={},metrics={},economics={})
    for s,c in current['coins'].items():
        p=old.get('coins',{}).get(s,{})
        result['coins'][s]=dict(price_pct=delta(c.get('price'),p.get('price')),cap_pct=delta(c.get('market_cap'),p.get('market_cap')),volume_pct=delta(c.get('volume_24h'),p.get('volume_24h')),trend_before=p.get('technical_score'),trend_now=c.get('technical_score'),legacy_before=p.get('legacy_action'),legacy_now=c.get('legacy_action'),risk_before=p.get('risk_points'),risk_now=c.get('risk_points'))
    for s,m in current['metrics'].items():
        p=old.get('metrics',{}).get(s,{})
        result['metrics'][s]=dict(change_pct=delta(m.get('value'),p.get('value')) if p.get('at')!=m.get('at') else None,at=m.get('at'),prior_at=p.get('at'))
    for s,items in current['economics'].items():
        result['economics'][s]={}
        for k,m in items.items():
            p=old.get('economics',{}).get(s,{}).get(k,{})
            result['economics'][s][k]=dict(change_pct=delta(m.get('value'),p.get('value')) if p.get('period')!=m.get('period') else None,period=m.get('period'),prior_period=p.get('period'))
    # Direction needs corroborating price and cap/trend changes; no causal attribution.
    moves=[v['price_pct'] for s,v in result['coins'].items() if s in COINS and v['price_pct'] is not None]
    cap=result['global_cap_pct'];btc=result['coins'].get('BTC',{}).get('price_pct')
    if cap is not None and btc is not None and len(moves)>=4:
        result['direction']='zlepšuje sa' if cap>0 and btc>0 and sum(v>0 for v in moves)>=4 else 'zhoršuje sa' if cap<0 and btc<0 and sum(v<0 for v in moves)>=4 else 'zmiešaný vývoj'
    else:result['direction']='zmenu nemožno spoľahlivo určiť'
    if cap==0 and btc==0 and moves and all(v==0 for v in moves):result['direction']='bez zásadnej cenovej zmeny'
    result['new_events']=len(set(current.get('event_ids',[]))-set(old.get('event_ids',[])))
    return result


def outlook(coin,tf):
    t=coin.get('frames',{}).get(tf,{})
    p=coin.get('price');lo=t.get('support');hi=t.get('resistance');ema=t.get('ema50');macd=t.get('macd_hist')
    if coin.get('stale',True) or not all(number(x) for x in (p,lo,hi,ema,macd)) or min(p,lo,hi,ema)<=0 or lo>=hi:
        return dict(status='N/A',base='Nedostatok spoľahlivých údajov pre tento horizont.')
    support=lo if 0<lo<p else None;resistance=hi if hi>p else None
    bias='oslabenie' if p<ema and macd<0 else 'rastový sklon' if p>ema and macd>0 else 'smer neistý'
    if number(t.get('adx')) and t['adx']<20:bias='smer neistý / slabý trend'
    return dict(status='CONDITIONAL',base=bias,reason=f'{tf}: cena {"pod" if p<ema else "nad"} EMA50, momentum {"kladné" if macd>0 else "záporné" if macd<0 else "neutrálne"}',
        support=support,resistance=resistance,invalidates=ema,confirmation_timeframe=tf,
        upside=f'Uzavretie {tf} nad {price(resistance)}' if resistance else 'Rastová hranica nepotvrdená',
        downside=f'Uzavretie {tf} pod {price(support)}' if support else 'Support je prerazený alebo nemožno určiť ďalšiu podporu',probability=None)


def relevant_events(fund,now):
    out=[]
    for e in analyze(fund,now)['evidence']:
        if e['id'] in fund.get('event_lifecycle',{}).get('superseded_ids',[]):continue
        if not e['material']:continue
        cats=set(e['categories']);title=e['title']
        macro=bool(cats&{'Fed','CPI','PCE','employment','GDP'})
        named=any(re.search(pattern,title,re.I) for pattern in ALIASES.values())
        regulation='regulation' in cats and bool(re.search(r'crypto|bitcoin|ethereum|stablecoin|ETF|MiCA',title,re.I))
        if not (macro or named or regulation):continue
        if 'hack' in cats and not named:continue
        if re.search(r'price prediction|price forecast|digital euro|marketing|sponsor|partnership',title,re.I):continue
        out.append(e)
    out.sort(key=lambda e:0 if set(e['categories'])&{'Fed','CPI','PCE','employment','GDP'} else 1)
    selected=[];seen=set()
    for e in out:
        macro=tuple(sorted(set(e['categories'])&{'Fed','CPI','PCE','employment','GDP'}))
        key=('macro',macro) if macro else ('event',e['id'])
        if key not in seen:selected.append(e);seen.add(key)
    return selected[:2]


def prepare(snapshot,fund,now,quotes,legacy_evaluations,old=None):
    from .strategy import costs,BUY_FEE,SELL_FEE
    configured_spread=os.getenv('SPREAD_ESTIMATE')
    spread=float(configured_spread) if configured_spread else .0025
    if not math.isfinite(spread) or not 0<=spread<1:raise ValueError('Invalid adverse fill estimate')
    obs=observation(snapshot,fund,now,quotes);comp=comparison(old,obs)
    forecasts={s:{'24–72 h':outlook(snapshot['coins'].get(s,{}),'4h'),'7–14 dní':outlook(snapshot['coins'].get(s,{}),'1d')} for s in ('BTC',*COINS)}
    scheduled=[]
    for e in fund.get('events',[]):
        if e.get('lifecycle') in ('SUPERSEDED','RELEASED','REACTION','AWAITING_VERIFICATION'):continue
        if not e.get('scheduled') or not set(e.get('categories',[]))&{'Fed','CPI','PCE','employment','GDP'}:continue
        if re.search(r'metropolitan|county|state employment|regional',e.get('title',''),re.I):continue
        at=timestamp(e.get('event_at'));day=e.get('event_date')
        if at and timedelta(0)<=at-now<=timedelta(days=14):scheduled.append(dict(title=e['title'],when=at.astimezone(BL).strftime('%d.%m. %H:%M'),url=e.get('url'),categories=e.get('categories',[])))
        elif day and now.astimezone(BL).date().isoformat()<=day<=(now+timedelta(days=14)).date().isoformat():scheduled.append(dict(title=e['title'],when=day+' (dátum zdroja; čas nepotvrdený)',url=e.get('url'),categories=e.get('categories',[])))
    model=dict(observation=obs,comparison=comp,forecasts=forecasts,evidence=relevant_events(fund,now),scheduled=scheduled[:3],coins={},macro=copy.deepcopy(fund.get('macro_context',{})),economic_observations=copy.deepcopy(fund.get('economic_observations',{})),metric_sources=copy.deepcopy(fund.get('metric_sources',[])),source_status=copy.deepcopy(fund.get('sources',[])),coverage=analyze(fund,now)['coverage'],missing=fund.get('unavailable',[]),cost_assumptions=dict(buy_fee=BUY_FEE,sell_fee=SELL_FEE,adverse_fill_per_side=spread,source='configured estimate, not verified eToro quote' if configured_spread else 'conservative assumption, not eToro quote'))
    # No new BUY/SELL rule. Legacy outputs remain diagnostic. Unvalidated watch
    # zones are scenarios, not activated investment recommendations.
    for s in COINS:
        c=snapshot['coins'].get(s,{});e=legacy_evaluations.get(s,{})
        obs['coins'].setdefault(s,{})['risk_points']=e.get('risk_pts')
        t=c.get('frames',{}).get('4h',{});p=c.get('price');support=t.get('support');resistance=t.get('resistance')
        valid=not c.get('stale',True) and number(p) and p>0
        zone=support if valid and number(support) and 0<support<p else None
        atr=t.get('atr');stop=zone-1.5*atr if zone and number(atr) and atr>0 else None
        economics=costs(zone,resistance,stop,spread=spread) if zone and number(resistance) and resistance>zone and stop and stop>0 else None
        if not valid:reason='Chýbajú spoľahlivé dáta; nový vstup nepotvrdený.'
        elif number(t.get('ema50')) and p<t['ema50']:
            reason=('Odraz ešte nepotvrdil obrat trendu' if number(t.get('macd_hist')) and t['macd_hist']>0 else 'Momentum a trend sú slabé')+(f'; sleduj podporu {price(zone)}.' if zone else '; ďalšia podpora nepotvrdená.')
        else:reason='Trend treba potvrdiť štruktúrou a objemom; nový vstup zatiaľ nepotvrdený.'
        model['coins'][s]=dict(price=p if valid else None,change_24h=c.get('change_24h'),action='WAIT',context='new_purchase',legacy_action=e.get('action'),zone=zone,invalidates=stop,target=resistance if number(resistance) and valid and resistance>p else None,economics=economics,
            candidate=bool(valid and number(resistance) and resistance>p and e.get('action') in ('BUY NOW','BUY PULLBACK') and economics and economics['net']>0 and (economics['net_rr'] or 0)>=1.5),
            reason=reason,sell_pressure=any('rastúci predajný objem' in r for r in e.get('risk_reasons',[])))
    activity=[]
    for s,items in fund.get('project_economics',{}).get('observations',{}).items():
        for metric,v in items.items():
            change=delta(v.get('value'),v.get('previous_value'))
            if change is not None and v.get('period')!=v.get('previous_period'):
                activity.append(dict(symbol=s,metric=metric,change_pct=change,period=v.get('period'),previous_period=v.get('previous_period'),url=v.get('url')))
    model['data_quality']=dict(current_price_count=sum(not snapshot['coins'].get(s,{}).get('stale',True) and number(snapshot['coins'].get(s,{}).get('price')) and snapshot['coins'][s]['price']>0 for s in COINS),primary_official_current_sources=sum(bool(s.get('official')) and not s.get('fallback') and s.get('freshness')=='CURRENT_RELEVANT' for s in fund.get('sources',[])),provider_asof_unknown_metrics=[s for s,m in fund.get('metrics',{}).items() if not m.get('at')],liquidity_depth=None,verified_etf_flows=None,rate_consensus=None,confidence='kvalitatívna, obmedzená pokrytím; nie kalibrovaná pravdepodobnosť',unavailable_dimensions=['overené ETF toky','likvidácie derivátov','hĺbka orderbooku','DXY','sadzbový konsenzus','úplná geopolitika','projektoví aktívni používatelia','úplný token-unlock kalendár'])
    model['project_activity']=sorted(activity,key=lambda v:abs(v['change_pct']),reverse=True)
    model['comparison']=comparison(old,obs)
    require_public_data(model);return model


def final_text(model,snapshot,now,kind,inventory=None):
    # All modifications are ephemeral and MUST NOT be persisted or exported.
    from .advisory_portfolio import validate
    from .strategy import decide
    rows=copy.deepcopy(model['coins']);private=False
    if inventory is not None:
        private=True
        for position in validate(inventory)['positions']:
            s=position['symbol']
            if s not in rows:
                extra=snapshot.get('coins',{}).get(s,{})
                rows[s]=dict(price=extra.get('price') if not extra.get('stale',True) else None,change_24h=extra.get('change_24h'),action='WAIT',context='held',candidate=False,reason='Posúdenie držby je neúplné.')
            c=snapshot['coins'].get(s,{})
            try:
                t=c.get('frames',{}).get('4h',{})
                required=('ema20','ema50','ema200','support','resistance','atr','rsi14','macd_hist')
                if not all(number(c.get('frames',{}).get('1d',{}).get(k)) and c['frames']['1d'][k]>0 for k in ('ema50','ema200')):raise ValueError('Incomplete daily assessment')
                if not all(number(t.get(k)) for k in required) or any(t[k]<=0 for k in ('ema20','ema50','ema200','support','resistance','atr')) or not 0<=t['rsi14']<=100:raise ValueError('Incomplete held assessment')
                result=decide(c,held=True,approved=False,market_complete=snapshot.get('complete',False))
                if not result.get('data_complete'):raise ValueError('Incomplete held assessment')
                action=result['action']
                reason='Ochranný výstup nie je potvrdený podporou/objemom/denným trendom; samotná korekcia nestačí.' if action=='HOLD' else 'Existujúce pravidlá držby potvrdili narušenie podpory, zvýšený objem a slabý denný trend; prever čiastočné zníženie.'
            except (KeyError,TypeError,ValueError):action='WAIT';reason='Držanú pozíciu nemožno bezpečne posúdiť; chýbajú údaje, nejde o potvrdené HOLD.'
            rows[s].update(action=action,context='held',reason=reason)
            if position['currency']=='USD' and position.get('average_cost') and position.get('quantity') and not c.get('stale',True) and number(rows[s].get('price')) and rows[s]['price']>0:
                rows[s]['position_note']='vs evidovaná nákupná cena '+pct(delta(c['price'],position['average_cost']))+' (nie čistý predaj)'
            if not snapshot.get('complete') and action=='HOLD':rows[s]['reason']='Predbežné HOLD; neúplné trhové pokrytie, ochranný výstup nepotvrdený.'
    g=model['observation']['global_data'];btc=snapshot['coins'].get('BTC',{});comp=model['comparison']
    change=g.get('change');label='Korekcia' if number(change) and change<0 else 'Rast' if number(change) and change>0 else 'Konsolidácia / údaje obmedzené'
    if private and any(c['action'] in ('REDUCE','SELL') for c in rows.values()):label='Zvýšené riziko držby'
    lines=['📊 CRYPTO AI BOT V11.2 — '+('RUČNÁ' if kind=='manual' else 'RÁNO' if kind=='morning' else 'VEČER'),now.astimezone(BL).strftime('%d.%m.%Y %H:%M Bratislava'),'TRH: '+label,
        f"BTC {price(model['observation']['coins'].get('BTC',{}).get('price'))} ({pct(btc.get('change_24h'))}); kap. {compact(g.get('cap'))} ({pct(change)} za24h); dominancia {format(g['dominance'],'.1f')+'%' if number(g.get('dominance')) else 'N/A'}.",'ČO SA DEJE:']
    if comp['status']=='COMPARED':
        lines.append(f"Od {timestamp(comp['previous_at']).astimezone(BL).strftime('%d.%m. %H:%M')}: {comp['direction']}. Kap. {pct(comp['global_cap_pct'])}, objem24h {pct(comp['global_volume_pct'])}, dominancia {format(comp['dominance_pp'],'+.2f')+' p. b.' if comp['dominance_pp'] is not None else 'neporovnateľná'}.")
    else:lines.append('Zmenu od poslednej analýzy zatiaľ nemožno overiť; pokles24h nie je zmena od posledného reportu.')
    good=[c for s,c in snapshot['coins'].items() if s in COINS and not c.get('stale') and c.get('frames',{}).get('4h')]
    broken=sum(bool(c['frames']['4h'].get('support_broken')) for c in good)
    selling=sum(bool(c.get('sell_pressure')) for c in model['coins'].values())
    strength=[c.get('relative_strength_btc_7d') for c in good if number(c.get('relative_strength_btc_7d'))]
    lines.append(f"Podporu prelomilo {broken}/{len(good)} mincí, objemový predajný signál {selling}/{len(good)}; "+(f"silnejších než BTC za7d: {sum(v>0 for v in strength)}/{len(strength)}." if strength else 'relatívna sila voči BTC nie je dostatočne pokrytá.'))
    lines.append('PREČO — príčina cenového pohybu nie je potvrdená:')
    if model['scheduled']:
        e=model['scheduled'][0]
        impact='miernejší/prísnejší výsledok môže podporiť/brzdiť rizikové aktíva; konsenzus neoverený' if 'Fed' in e.get('categories',[]) else 'prekvapenie môže zmeniť výnosy a sadzbové očakávania; smer bez konsenzu neistý'
        lines.append(f"• {e['when']} {e['title']}: {impact}. {e['url']}")
    for e in model['evidence'][:1 if model['scheduled'] else 2]:
        lines.append(f"• {e['published_at'][:10]} {e['title']}: {e['significance']}; {e['impact']}. Zdroj {e['source']}: {e['url']}")
    if not model['evidence'] and not model['scheduled']:lines.append('Kvalitné nové podklady sa nepodarilo overiť; nepodstatné správy ich nenahrádzajú.')
    y=model.get('macro',{}).get('treasury')
    if y and not model['evidence']:
        bp=y.get('change_bp',{}).get('10y')
        lines.append(f"US10Y {y['10y']:.2f}% ({y['date']}"+(f", {bp:+g} bp" if bp is not None else '')+'): vyššie výnosy môžu brzdiť rizikové aktíva; nie je to dôkaz príčiny pohybu. FRED/Treasury.')
    activity=model.get('project_activity',[])
    if activity and abs(activity[0]['change_pct'])>=10:
        a=activity[0]
        lines.append(f"{a['symbol']}: {'poplatky protokolu' if a['metric']=='fees' else 'príjmy protokolu'} {pct(a['change_pct'])} oproti predošlému dostupnému obdobiu ({str(a['period'])[:10]}, DeFiLlama); jednodenná aktivita nie je čistý tok ani potvrdenie rastu tokenu.")
    lines.append('VÝHĽAD BTC:')
    for h,f in model['forecasts']['BTC'].items():
        if f['status']=='N/A':lines.append(h+': '+f['base']);continue
        lines.append(f"{h}: {f['base']} ({f['reason']}). Alternatíva: {f['upside']}; riziko: {f['downside']}. Prehodnotiť pri EMA50 {price(f['invalidates'])} na {f['confirmation_timeframe']}.")
    lines.append('ODPORÚČANIA:')
    for s,c in rows.items():
        tag='držba' if c['context']=='held' else 'nový nákup'
        old=comp.get('coins',{}).get(s,{}).get('price_pct')
        lines.append(f"{s} {price(c['price'])} ({pct(c['change_24h'])} za24h"+(f", od minule {pct(old)}" if old is not None else '')+f") — {c['action']} ({tag}): {c['reason']}"+((' '+c['position_note']) if c.get('position_note') else ''))
    candidates=[(s,c) for s,c in rows.items() if c['candidate'] and c['context']!='held']
    if candidates:
        s,c=max(candidates,key=lambda row:row[1]['economics']['net_rr']);lines.append(f"PRÍLEŽITOSŤ: žiadna potvrdená. Kandidát {s}: zóna {price(c['zone'])}, invalidácia {price(c['invalidates'])}, cieľ {price(c['target'])}; až po potvrdení podpory a realizačných podmienok. Nie aktívny BUY.")
    else:lines.append('PRÍLEŽITOSŤ: žiadna potvrdená; nenakupovať iba preto, že cena klesla.')
    lines.append('RIZIKO: '+('makro prekvapenie pri najbližšej udalosti; prever reakciu BTC a objem.' if model['scheduled'] else 'nepotvrdené zlepšenie štruktúry a neúplné udalostné pokrytie.'))
    lines.append('ZÁVER: nové nákupy zatiaľ WAIT. '+('Držané pozície podľa jedného záveru vyššie; preveriť pri zmene podpory/objemu alebo overenom incidente.' if private else 'Držba sa v tomto verejnom náhľade neposudzuje; osobný predajný pokyn nevzniká.'))
    lines.append('Technické signály V10.6 sú v diagnostike; nepredstavujú potvrdenú predikciu ani osobný predajný pokyn.')
    return '\n'.join(lines)
