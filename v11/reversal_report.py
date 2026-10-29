"""Deterministic interpretation and final contradiction guard; no trade selection."""
import re
from . import analyst,trend_reversal as tr
from .report_verdict import actions,ACTIONS

MISSING={'btc_structure':'štruktúra BTC 4h/1d','capitalization':'rast kapitalizácie medzi meraniami','directional_volume':'objem rastových sviečok (proxy)','breadth':'šírka potvrdených trendov','multi_analysis_stability':'pokračovanie cez nové sviečky a analýzy'}

def intro(model,snapshot,body,inventory):
    r=model['trend_reversal'];state=r.get('state');breadth=r.get('breadth',{});comp=r.get('comparisons',{})
    label=tr.LABELS.get(state,'NEISTOTA — nedostatočné potvrdenia')
    parsed=actions(body);held=[s+' '+ACTIONS[a] for s,a,c in parsed if c=='držba'];new=[s for s,a,c in parsed if c=='nový nákup' and a=='BUY NOW']
    holding='; '.join(held) if held else 'držba bezpečne neoverená' if inventory is None else 'bez evidovaných otvorených pozícií'
    out=['📌 INVESTIČNÝ VERDIKT: '+label,'AKCIA: '+('NAKÚPIŤ '+', '.join(new) if new else 'POČKAŤ s novými nákupmi')+'. '+holding+'.']
    n=breadth.get('change_24h_covered',0);up=breadth.get('rising_24h',0)
    if n:out.append(f'Za 24h rastie {up}/{n} mincí; potvrdený 4h profil {breadth.get("confirmed_4h",0)}/{breadth.get("covered",0)}; silnejších než BTC za7d {breadth.get("stronger_than_btc_7d",0)}/{breadth.get("relative_strength_covered",0)}. Odraz nie je potvrdený trend.')
    latest=comp.get('latest',{});positive=[];negative=[]
    if latest.get('status')=='COMPARED':
        at=tr.timestamp(latest['at'])
        # Explicit reference clock; 24h is never used as a since-analysis delta.
        from .shadow_pair import BL
        cap=latest.get('cap_pct');moves=[c['price_pct'] for c in latest.get('coins',{}).values() if tr.finite(c.get('price_pct'))]
        if cap is not None and abs(cap)>=.1:(positive if cap>0 else negative).append('kap. '+analyst.pct(cap))
        decliners=[s for s,c in latest.get('coins',{}).items() if tr.finite(c.get('price_pct')) and c['price_pct']<0]
        if decliners:negative.append('nižšie ceny '+', '.join(decliners))
        if moves:
            rising=sum(m>0 for m in moves);(positive if rising>len(moves)/2 else negative).append(f'ceny {rising}/{len(moves)} vyššie')
        out.append('Od '+at.astimezone(BL).strftime('%d.%m. %H:%M')+': zlepšilo '+(', '.join(positive) or 'nepotvrdené')+'; zhoršilo '+(', '.join(negative) or 'bez potvrdeného nového zhoršenia')+'.')
    for name,label in (('morning','RÁNO'),('evening','VEČER')):
        ref=comp.get(name,{})
        if ref.get('status')=='COMPARED':
            moves=[c['price_pct'] for c in ref.get('coins',{}).values() if tr.finite(c.get('price_pct'))]
            if moves:
                from .shadow_pair import BL
                stamp=tr.timestamp(ref['at']).astimezone(BL).strftime('%d.%m. %H:%M')
                out.append(label+' '+stamp+f': odvtedy vyššie ceny {sum(v>0 for v in moves)}/{len(moves)}'+('; kap. '+analyst.pct(ref['cap_pct']) if ref.get('cap_pct') is not None else '; stará kapitalizácia neoverená')+'.')
    confirmed=[MISSING[k] for k,v in r.get('groups',{}).items() if v]
    if confirmed:out.append('POTVRDENÉ: '+', '.join(confirmed)+'. '+r.get('proximity','')+'.')
    missing=r.get('missing',[])
    out.append('ČO CHÝBA: '+(', '.join(MISSING[m] for m in missing[:3]) if missing else 'základné technické skupiny sú splnené; budúci výnos nie je zaručený')+'.')
    for h in ('24–72 h','7–14 dní'):
        f=model.get('forecasts',{}).get('BTC',{}).get(h,{})
        out.append(h+': technický scenár — '+f.get('base','smer neistý')+'.'+(' Alternatíva: '+f.get('upside','potvrdenie rastu')+'; riziko '+f.get('downside','narušenie podpory')+'.' if h=='24–72 h' else ''))
    triggers=[]
    for s in ('BTC','SOL','TAO'):
        p=r.get('coins',{}).get(s,{})
        if p.get('status')=='AVAILABLE':triggers.append(s+' '+analyst.price(p['entry_level'])+' (2×4h + objem)')
    if triggers:out.append('SPÚŠŤAČE: '+'; '.join(triggers)+'.')
    if state=='REVERSAL_CONFIRMING':out.append('Možno preveriť čiastočný technický vstup; nejde o schválený BUY. Veľkosť bez kapitálu, rizika a nákladov neurčujeme.')
    return out

def coin_line(symbol,model):
    r=model['trend_reversal'];p=r.get('coins',{}).get(symbol,{})
    if p.get('status')!='AVAILABLE':return 'Obrat: neúplné uzavreté dáta; nový vstup nepotvrdený.'
    f=p['four'];d=p['daily'];prior=r.get('comparisons',{}).get('latest',{}).get('coins',{}).get(symbol,{})
    before=prior.get('trend_before');transition=('; '+tr.LABELS.get(before,before)+' → '+tr.LABELS[p['state']]) if before and before!=p['state'] else ''
    if not before and tr.finite(prior.get('price_pct')):transition='; cena od minule '+analyst.pct(prior['price_pct'])+' (nie zmena 24h)'
    trend='4h '+('rastový' if f['bull'] else 'odraz' if f['rebound'] else 'slabý')+', 1d '+('rastový' if d['bull'] else 'nepotvrdený')+transition
    candidate=p.get('technical_candidate')
    level=analyst.price(p['entry_level']);support=analyst.price(p['support']) if p.get('support') else 'predošlá pri/nad cenou; nová neoverená'
    plan=('Technický kandidát '+candidate+'; realizácia/čisté R:R neoverené, nový nákup WAIT. ' if candidate else 'Nový nákup WAIT; potvrdiť 2 uzavretia 4h nad '+level+' s objemom. ')
    return 'Obrat: '+trend+'. '+plan+'Podpora/invalidácia '+support+'.'

def guard(text,baseline,model,snapshot):
    # Actions are authoritative upstream outputs, never repaired by the detector.
    if actions(text)!=actions(baseline):raise ValueError('Report action mismatch; new trade instruction refused')
    values=[c.get('change_24h') for s,c in snapshot.get('coins',{}).items() if s in tr.COINS and not c.get('stale',True)]
    all_up=len(values)==6 and all(tr.finite(v) and v>0 for v in values)
    fixed=text;reasons=[]
    r=model.get('trend_reversal',{});state=r.get('state')
    if state=='UPTREND_CONFIRMED' and (not all(r.get('groups',{}).get(k) for k in ('btc_structure','capitalization','directional_volume','breadth')) or not r.get('stable')):state=None
    expected='📌 INVESTIČNÝ VERDIKT: '+tr.LABELS.get(state,'NEISTOTA — nedostatočné potvrdenia')
    if not fixed.startswith(expected):
        fixed=re.sub(r'^📌 INVESTIČNÝ VERDIKT:.*$',expected,fixed,count=1,flags=re.M);reasons.append('UNSUPPORTED_VERDICT_REPAIRED')
    patterns=[]
    if all_up:patterns.append((r'^.*(?:plošný pokles altcoinov|všetky altcoiny klesajú|všetkých šesť altcoinov klesá).*$', 'Za 24h rastie 6/6 sledovaných mincí; potvrdenie trendu sa hodnotí oddelene.','BREADTH_COMMENT_CONTRADICTION'))
    patterns.append((r'^Od [^\n]*(?:za\s*24\s*h|24-hodinová výkonnosť).*$','Časové porovnanie neoverené; 24h vývoj nie je zmena od predchádzajúcej analýzy.','AMBIGUOUS_TIME_BASIS'))
    patterns.append((r'^.*(?:Fed|inflácia|makro|FOMC) (?:spôsobil|spôsobila|spôsobili|zapríčinil).*$','Príčina cenového pohybu nie je preukázaná; makro je rizikový kontext.','UNSUPPORTED_MACRO_CAUSE'))
    for pattern,replacement,code in patterns:
        if re.search(pattern,fixed,re.I|re.M):
            # Never rewrite authoritative action lines, even on a malformed report.
            lines=fixed.splitlines()
            fixed='\n'.join(replacement if re.match(pattern,line,re.I) and not actions(line) else line for line in lines)
            reasons.append(code)
    if actions(fixed)!=actions(baseline):raise ValueError('Report action mismatch after comment repair')
    return fixed,dict(passed=True,corrected_comments=reasons,actions_unchanged=True,time_basis_checked=True,causal_claims_checked=True,return_probabilities_invented=False)
