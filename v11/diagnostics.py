"""Explanation-only diagnostics. Never change strategy decisions or emit alerts."""
import os
from .data import PRIMARY


def technical(data):
    t=data.get('frames',{}).get('4h',{});d=data.get('frames',{}).get('1d',{})
    p=data.get('price')
    if not p or data.get('stale') or any(t.get(k) is None for k in ('ema200','ema50','ema20','rsi14','adx','macd_hist','relative_volume')):
        return dict(available=False,score=None,checks={},failed=['neúplné alebo zastarané dáta'],quality='N/A')
    checks=dict(trend=p>t['ema50'] and t['ema20']>t['ema50'],
        broad=d.get('ema200') is not None and p>d['ema200'],
        momentum=t.get('macd_hist') is not None and t['macd_hist']>0 and 40<=t['rsi14']<=68,
        volume=t.get('relative_volume') is not None and t['relative_volume']>=1.1,
        structure=bool(t.get('higher_structure') or t.get('retest')),
        strength=t.get('adx') is not None and t['adx']>=20)
    score=sum(checks.values())
    return dict(available=True,score=score,checks=checks,failed=[k for k,v in checks.items() if not v],
                quality='silný technický podklad' if score>=5 and checks['broad'] else 'čiastočný technický podklad' if score>=3 else 'slabý technický podklad')


def entry_diagnostic(data,evaluation,approved=False,market_complete=True,risk_normal=True):
    t=technical(data);block=[]
    if not approved:block.append('dostupnosť na eToro neoverená')
    economy=evaluation.get('economics')
    if not economy or not economy.get('estimated'):block.append('spread neznámy')
    if os.getenv('V11_RULES_VALIDATED','false').lower()!='true':block.append('V11 pravidlá nie sú schválené na aktiváciu')
    if not market_complete:block.append('neúplné trhové dáta')
    if not risk_normal:block.append('ochranná technická podmienka nie je NORMAL')
    if economy and (economy['net']<float(os.getenv('MIN_NET_EDGE','.03')) or (economy.get('net_rr') or 0)<1.5):
        block.append('nedostatočná nákladová výhoda alebo čisté R:R')
    return dict(technical=t,entry_blockers=block,actual_action=evaluation['action'],
                ownership='held' if evaluation.get('held') else 'not_held_or_shadow_unknown')


def risk_evidence(snapshot,safety):
    coins=snapshot['coins'];g=snapshot.get('global_data',{})
    def change(s):return coins.get(s,{}).get('change_24h')
    def broken(s):return coins.get(s,{}).get('frames',{}).get('4h',{}).get('support_broken')
    alt_breaks=sum(broken(s) is True for s in PRIMARY)
    alt_drops=sum(change(s) is not None and change(s)<=-5 for s in PRIMARY)
    cap=g.get('change');btc=change('BTC');eth=change('ETH')
    independent_price_weakness=(btc is not None and eth is not None and btc<0 and eth<0 and sum(change(s) is not None and change(s)<0 for s in PRIMARY)>=4) or alt_drops>=4
    label='výrazné cenové oslabenie' if cap is not None and cap<=-5 and independent_price_weakness else 'cenový kontext bez kombinovaného potvrdenia' if snapshot.get('complete') else 'N/A — neúplné dáta'
    return dict(technical_state=safety['state'],price_context=label,cap_change_24h=cap,btc_change_24h=btc,eth_change_24h=eth,
        btc_support_broken=broken('BTC'),eth_support_broken=broken('ETH'),alt_support_breaks=alt_breaks,alt_drops_over5=alt_drops,
        rule='WARNING vyžaduje súčasný support breakdown BTC aj ETH a najmenej4 zo6 altcoinov; neúplné dáta UNKNOWN',
        interpretation='NORMAL znamená iba nesplnený kombinovaný technický breakdown; nie nízke celkové riziko ani potvrdenie absencie incidentov.',
        crash_probability=None,alerts_generated=False)


def action_summary(snap,evals,safety,fund,state):
    r=risk_evidence(snap,safety)
    ranked=sorted(((s,technical(snap['coins'][s])) for s in PRIMARY if s in evals),
                  key=lambda item:item[1]['score'] if item[1]['score'] is not None else -1,reverse=True)
    candidates=[f"{s} {t['score']}/6" for s,t in ranked if t['available'] and t['score']>=3]
    changes=[]
    for s in PRIMARY:
        prior=state.get('morning_plan_v11',{}).get('coins',{}).get(s,{})
        current=snap['coins'].get(s,{})
        if prior.get('price') and current.get('price') and not prior.get('stale') and not current.get('stale'):
            changes.append(f"{s} {(current['price']/prior['price']-1)*100:+.2f}% {prior.get('action','N/A')}→{evals.get(s,{}).get('action','N/A')}")
    cap_text='N/A' if r['cap_change_24h'] is None else f"{r['cap_change_24h']:+.2f}%"
    return ['AKČNÝ SÚHRN',
        f"Trh: technická podmienka {safety['state']}; {r['price_context']}. Kapitalizácia24h {cap_text}.",
        'Overená príčina pohybu: N/A — súbeh správ a ceny nedokazuje príčinu.',
        'Technické príležitosti na preverenie: '+(', '.join(candidates[:3]) or 'žiadna s aspoň3/6 podmienkami')+'. Nie je to povolený BUY.',
        'Riziká: neúplné udalostné pokrytie; nové vstupy majú samostatné bezpečnostné blokovania.',
        'Zmeny od ranného snapshotu: '+(', '.join(changes) or 'N/A — chýba overený časovo oddelený ranný snapshot.'),
        r['interpretation']]
