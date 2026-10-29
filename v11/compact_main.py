"""Decision brief: same authoritative actions, concise V2, new events only."""
from . import analyst,trend_reversal as tr,report_verdict as rv
from .prediction_runtime import current_predictions
from .telegram_text import without_links

LABELS=dict(tr.LABELS,UPTREND_CONFIRMED='POTVRDENÝ RAST')

def render(model,snapshot,now,kind,inventory=None):
    base=analyst.final_text(model,snapshot,now,kind,inventory)
    approved=rv.actions(base);r=model['trend_reversal']
    from .reversal_report import safe_state
    fresh=0<=now.timestamp()-snapshot.get('at',0)<=900
    state=safe_state(r) if fresh else None;f=r.get('failure_evidence',{})
    name='RANNÁ' if kind=='morning' else 'VEČERNÁ' if kind=='evening' else 'RUČNÁ'
    lines=['📊 CRYPTO AI BOT — '+name+' ANALÝZA',now.astimezone(analyst.BL).strftime('%d.%m. %H:%M Bratislava'),
           '🌐 TRH: '+LABELS.get(state,'NEISTOTA')]
    breadth=r.get('breadth',{});up=breadth.get('rising_24h');covered=breadth.get('change_24h_covered',0)
    if state=='RECOVERY_FAILED':text='Predchádzajúci odraz stratil silu. Od poslednej analýzy klesli BTC, kapitalizácia aj väčšina sledovaných mincí; širší rastový trend nie je potvrdený.'
    elif state=='CORRECTION':text='Rastová štruktúra sa nepotvrdila; riziko pokračovania korekcie pretrváva.'
    elif state=='RECOVERY_ATTEMPT':text='Objavil sa cenový odraz, no trvalý rastový trend ešte nie je potvrdený.'
    elif state=='REVERSAL_CONFIRMING':text='Pribúdajú technické potvrdenia obratu; treba overiť ich pokračovanie, nie automaticky nakúpiť.'
    elif state=='UPTREND_CONFIRMED':text='Viaceré skupiny uzavretých dát potvrdili rastový trend; nevylučuje to bežnú korekciu.'
    else:text='Dáta sú neúplné alebo protichodné; smer nemožno spoľahlivo potvrdiť.'
    if f.get('prior_recovery')=='UPTREND_CONFIRMED' and r.get('groups',{}).get('btc_structure') and state=='CORRECTION':text='Krátkodobá korekcia pri zachovanej širšej rastovej štruktúre; sama osebe nie je dôvod na predaj.'
    if covered==6:text+=f' Za 24h rastie {up}/6 mincí.'
    if r.get('groups',{}).get('directional_volume') is False:text+=' Nákupný záujem nie je presvedčivo potvrdený (sviečkový proxy).'
    lines.append(text)
    g=snapshot.get('global_data',{});btc_now=snapshot.get('coins',{}).get('BTC',{})
    if not btc_now.get('stale',True):lines.append('BTC '+analyst.price(btc_now.get('price'))+' | kap. '+analyst.compact(g.get('cap'))+' ('+analyst.pct(g.get('change'))+' za24h).')
    lines+=['','🎯 ODPORÚČANIE']
    held=[s+' '+rv.ACTIONS[a] for s,a,c in approved if c=='držba']
    lines.append('; '.join(held)+'.' if held else 'Držba bez bezpečne načítanej evidencie neposúdená; nejde o pokyn predať.')
    new=[s+' '+a for s,a,c in approved if c=='nový nákup' and a.startswith('BUY')]
    lines.append('Nové nákupy: '+(', '.join(new) if new else 'ČAKAŤ na potvrdenie vstupu a nákladov')+'.')
    lines+=['','🔮 VÝHĽAD']
    for h in ('24–72 h','7–14 dní'):
        view=model.get('forecasts',{}).get('BTC',{}).get(h,{}) if fresh else {}
        if state in ('RECOVERY_FAILED','CORRECTION') and not r.get('groups',{}).get('btc_structure'):
            scenario='riziko oslabenia; obrat až po návrate nad potvrdené hranice' if h=='24–72 h' else 'rast nepotvrdený; rozhodne obnova dennej štruktúry'
        else:scenario=view.get('base','smer neistý')
        lines.append(h+': '+scenario+'.')
        if h=='24–72 h':
            lo=view.get('support');hi=view.get('resistance')
            if analyst.number(lo) and analyst.number(hi):lines.append('Alternatíva rastu: uzavretie BTC nad '+analyst.price(hi)+' s objemom; riziko pod '+analyst.price(lo)+'.')
    lines+=['','💰 KRYPTOMENY','V2 experimentálne, nízka istota; intervaly a vyhodnotenie sú v diagnostike.']
    forecasts=current_predictions(model,int(now.timestamp()*1000))
    rows=base.split('ODPORÚČANIA:',1)[1].splitlines()
    for symbol,action,context in approved:
        coin=snapshot.get('coins',{}).get(symbol,{})
        p=coin.get('price') if not coin.get('stale',True) else None
        profile=r.get('coins',{}).get(symbol,{})
        if action=='HOLD':reason='Ochranný výstup nepotvrdený.' if snapshot.get('complete') else 'Predbežné držanie; pokrytie neúplné.'
        elif action in ('REDUCE','SELL'):reason='Existujúce ochranné pravidlo vyžaduje preveriť '+('zníženie pozície.' if action=='REDUCE' else 'predaj.')
        elif context=='držba':reason='Posúdenie držby neúplné; nejde o potvrdené HOLD.'
        elif profile.get('technical_candidate'):reason='Technický kandidát; realizácia a čisté R:R neoverené.'
        else:reason='Vstup ešte nepotvrdený.'
        lines.append(f'{symbol} {analyst.price(p)} — {action} ({context}): '+reason)
        level=profile.get('entry_level');support=profile.get('support')
        if action in ('REDUCE','SELL','HOLD') and analyst.number(support):boundary='Riziko pod '+analyst.price(support)+' po potvrdení prerazenia.'
        elif profile.get('status')=='AVAILABLE' and not analyst.number(support):boundary='Stará podpora '+analyst.price(profile['four']['support'])+' je pri/nad cenou; preveriť prerazenie.'
        elif context=='držba':boundary='Stará podpora je pri/nad cenou; ďalšia hranica neoverená.' if profile.get('status')=='AVAILABLE' else 'Riziková hranica nie je spoľahlivo overená.'
        elif analyst.number(level):boundary='Vstup preveriť po 2×4h nad '+analyst.price(level)+' s objemom.'
        else:boundary='Platná hranica zatiaľ nepotvrdená.'
        lines.append(boundary)
        if symbol in tr.COINS:
            pieces=[]
            for horizon,label in [('24 h','24h'),('48–72 h','72h'),('7–14 dní','14d')]:
                value=forecasts.get(symbol,{}).get(horizon)
                pieces.append(label+' '+(value['direction'] if value else 'nedostupné'))
            lines.append('V2: '+' | '.join(pieces)+'.')
    if sum(map(len,forecasts.values()))<18:lines.append('Chýbajúce V2: náhradný technický scenár je výhľad vyššie, iba pri aktuálnych technických dátach; nejde o výstup V2.')
    events=model.get('event_notices',{}).get('selected',[])
    if events:lines+=['','📰 NOVÉ DÔLEŽITÉ UDALOSTI',*['• '+e['text'] for e in events[:3]]]
    lines+=['','📌 ZÁVER']
    btc=model.get('forecasts',{}).get('BTC',{}).get('24–72 h',{})
    trigger=btc.get('resistance')
    ending='Držbu riaď pokynmi vyššie; nové vstupy nepotvrdzuje samotný odraz.'
    ending+=' Prehodnotiť po potvrdení hraníc alebo novej významnej udalosti.'
    lines.append(ending)
    from .reversal_report import guard
    text,_=guard(without_links('\n'.join(lines)),base,model,snapshot,now)
    return text
