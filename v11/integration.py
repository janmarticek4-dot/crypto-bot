"""V11.1 report enrichment around the unchanged V10.6 rule engine.

No state writes, private-state access, delivery, strategy activation or AI facts.
"""
import copy
import json
from datetime import datetime,timezone
from pathlib import Path
from .fundamental_analysis import overview,coin_lines
from .briefing import event_lines
from .state_policy import require_public_data

PUBLIC_RULE_KEYS=('peaks','last_actions','safety','last_analysis','prev_flags','fundamentals','alert_research','alert_research_market')

def rule_state(value):
    if not isinstance(value,dict):raise ValueError('Invalid production rule state')
    require_public_data(value) # refuse private contamination; never silently reset
    return {k:copy.deepcopy(value[k]) for k in PUBLIC_RULE_KEYS if k in value}


def read_rule_state(path):
    path=Path(path)
    if not path.is_file() or path.stat().st_size>4_000_000:raise ValueError('Rule state missing or oversized')
    value=json.loads(path.read_text())
    if not value:raise ValueError('Unexpected empty public rule state')
    return rule_state(value)


def context(legacy,snapshot,state,fear=None):
    def coin(symbol):
        value=snapshot['coins'].get(symbol,{})
        candles=value.get('raw',{}).get('4h',[])
        price=value.get('price') if not value.get('stale',True) else None
        if not price or len(candles)<35:return dict(symbol=symbol,error='Incomplete current data',price_usd=None,technical_4h={},structure={},technical_score_calc={})
        technical=legacy.technical_summary(candles,price)
        structure=legacy.compute_structure(candles,price)
        return dict(symbol=symbol,price_usd=price,market_cap=value.get('market_cap'),volume_24h=value.get('volume_24h'),
                    change_24h=value.get('change_24h'),technical_4h=technical,structure=structure,
                    technical_score_calc=legacy.calculate_technical_score(technical),
                    returns=legacy.recent_returns([c['close'] for c in candles]),data_warnings=[],
                    change_since_last=legacy.pct_change(legacy.previous_coin_map(state).get(symbol,{}).get('price'),price))
    global_data=snapshot.get('global_data',{})
    return dict(btc_data=coin('BTC'),portfolio_data={s:coin(s) for s in legacy.PORTFOLIO},fear=fear or {},
                btc_change_24h=snapshot['coins'].get('BTC',{}).get('change_24h'),btc_dominance=global_data.get('dominance'),
                global_change=global_data.get('change'),total_market_cap=global_data.get('cap'),total_volume=global_data.get('volume'))


def evaluate(legacy,snapshot,state,fear=None):
    working=rule_state(state)
    ctx=context(legacy,snapshot,working,fear)
    cached_fund=legacy.get_usable_fundamentals(working)
    metrics,safety,evaluations=legacy.evaluate_all(ctx,working,cached_fund)
    return ctx,metrics,safety,evaluations


def render_detailed(legacy,snapshot,fundamentals,now,kind,state,previous=None,fear=None):
    ctx,metrics,safety,evaluations=evaluate(legacy,snapshot,state,fear)
    p=legacy.format_price
    def percent(x):return 'N/A' if x is None else f'{x:+.2f}%'
    def delta(a,b):return (a/b-1)*100 if isinstance(a,(float,int)) and isinstance(b,(float,int)) and b>0 else None
    lines=['📊 CRYPTO AI BOT V11.1 | PRAVIDLÁ V10.6 — '+('RÁNO' if kind=='morning' else 'VEČER'),
           now.astimezone(legacy.TZ).strftime('%d.%m.%Y %H:%M Bratislava'),
           'Rozhodnutia: nezmenený kód V10.6; nové fundamenty iba vysvetľujú, nemenia obchodné pravidlá.',
           f"Trh24h {percent(ctx.get('global_change'))}; BTC {p(ctx['btc_data'].get('price_usd'))}; dominancia {format(ctx['btc_dominance'],'.2f') if ctx.get('btc_dominance') is not None else 'N/A'} %; bezpečnostné hodnotenie V10.6 {safety['state']}.",
           'Príčina pohybu nie je preukázaná samotným súbehom správ a cien.']
    lines.append('Režim V10.6: '+legacy.market_regime(ctx,evaluations)+'; Fear & Greed '+str((ctx.get('fear') or {}).get('value') if (ctx.get('fear') or {}).get('value') is not None else 'N/A')+'.')
    lines.append('Kapitalizácia trhu '+legacy.fmt_big(ctx.get('total_market_cap'))+'; objem24h '+legacy.fmt_big(ctx.get('total_volume'))+'; BTC24h '+percent(ctx.get('btc_change_24h'))+'.')
    lines+=overview(fundamentals,now)
    quotes={};appendix=[]
    for symbol in legacy.PORTFOLIO:
        e=evaluations[symbol];c=snapshot['coins'].get(symbol,{})
        lines+=['',f"{symbol} — {e['action']} (V10.6) | {p(e.get('price'))}; 24h {percent(c.get('change_24h'))}",
                f"Trend {e.get('trend_score','N/A')}/10; riziko {e.get('risk_level','N/A')} ({e.get('risk_pts','N/A')} b.); "+'; '.join(e.get('signals',[])[:2])]
        if e.get('entry') and e.get('stop'):
            rr1,rr2=legacy.calculate_rr(e['entry'],e['stop'],e.get('tp1'),e.get('tp2'))
            lines.append(f"Pôvodné hrubé R:R {rr1 if rr1 is not None else 'N/A'} / {rr2 if rr2 is not None else 'N/A'}; čisté R:R N/A bez overeného spreadu.")
            lines.append(f"Pôvodný plán: vstup {p(e['entry'])}, ochranná hranica {p(e['stop'])}, TP1 {p(e.get('tp1'))}, TP2 {p(e.get('tp2'))}.")
        else:lines.append('Potvrdený vstup/ochranný plán N/A.')
        lines.append('Support '+p(e.get('support'))+'; rezistencia '+p(e.get('resistance'))+'; pokles od maxima '+percent(e.get('drawdown_pct'))+'.')
        if e.get('tiers'):lines.append('Nepotvrdené možné vstupné zóny: '+' / '.join(p(v) for v in e['tiers']))
        lines.append('Zmena odporúčania: '+e.get('flip','N/A'))
        audit=risk_breakdown(legacy,e)
        lines.append('Rizikové body V10.6: '+'; '.join(f"{c['points']} b. {c['reason']}" for c in audit['components'])+f"; spolu {audit['sum'] if audit['matched'] else 'N/A — nerozpoznaná položka'} b.; kontrola V10.6 {e.get('risk_pts','N/A')} b.")
        if e['action'] in ('REDUCE','SELL'):lines.append(audit['trigger'])
        lines+=coin_lines(symbol,fundamentals,now)
        lines.append(f"Kapitalizácia {legacy.fmt_big(c.get('market_cap'))}; objem24h {legacy.fmt_big(c.get('volume_24h'))}.")
        old=(previous or {}).get(symbol,{})
        if old:
            action=old.get('action') if old.get('rule_engine')=='v10.6-original' else 'N/A (iný/neoverený pôvod odporúčania)'
            lines.append(f"Od rána: cena {percent(delta(c.get('price'),old.get('price')))}, kap. {percent(delta(c.get('market_cap'),old.get('market_cap')))}, objem {percent(delta(c.get('volume_24h'),old.get('volume_24h')))}; pokyn {action} → {e['action']}.")
        quotes[symbol]=dict(price=c.get('price') if not c.get('stale') else None,market_cap=c.get('market_cap'),volume_24h=c.get('volume_24h'),
                            action=e['action'],trend_score_10=e.get('trend_score'),rule_engine='v10.6-original')
        tech=ctx['portfolio_data'][symbol].get('technical_4h',{})
        appendix.append(f"{symbol}: RSI {round(e['rsi'],1) if e.get('rsi') is not None else 'N/A'}; EMA20/50/100/200 "+' / '.join(p(tech.get(k)) for k in ('ema20','ema50','ema100','ema200'))+'; MACD hist. '+str(round(e['macd_hist'],4) if e.get('macd_hist') is not None else 'N/A')+'; ATR '+p(tech.get('atr14')))
    if kind=='evening' and not previous:lines.append('Ranné porovnanie N/A — nezadávame syntetickú rannú referenciu.')
    lines+=['', 'AKČNÝ ZÁVER', 'V10.6 nákupné signály: '+(', '.join(s for s,e in evaluations.items() if e['action'] in ('BUY NOW','BUY PULLBACK')) or 'žiadne')+'. Existujúce pozície posudzuje iba oddelená súkromná časť.', 'V10.6 ochranné signály: '+(', '.join(s for s,e in evaluations.items() if e['action'] in ('SELL','REDUCE')) or 'žiadne')+'. Nevykonáva sa žiadny obchod.',*event_lines(fundamentals,now.timestamp()),'',
            'Nové udalosti nemenia V10.6 signál. Rizikové vstupy zo staršieho V10.6 cache nie sú týmto znovu overené.',
            'Kapitalizácia, TVL a objem nie sú čisté kapitálové toky. Náklady eToro približne 1 % nákup + 1 % predaj a spread treba posúdiť pred manuálnym obchodom; nejde o nové schválené čisté R:R.',
            'Držba N/A — skutočné pozície sa nenačítavajú.',
            '', 'TECHNICKÁ PRÍLOHA',*appendix]
    text='\n'.join(lines);require_public_data(text);require_public_data(quotes)
    return text,quotes,evaluations


def risk_breakdown(legacy,evaluation):
    weights=(('hlboký pokles',3),('pokles ',1),('prelomený support',2),
             ('rastúci predajný objem',1),('cena pod EMA50',1),('cena pod EMA200',1),
             ('MACD histogram záporný',1),('slabý trend',1),
             ('bezpečnostný stav trhu: WARNING',1),('bezpečnostný stav trhu: CRITICAL',2),
             ('negatívna správa o projekte',1))
    components=[]
    for reason in evaluation.get('risk_reasons',[]):
        points=next((value for prefix,value in weights if reason.startswith(prefix)),None)
        components.append(dict(reason=reason,points=points))
    total=sum(c['points'] for c in components if c['points'] is not None)
    matched=all(c['points'] is not None for c in components) and total==evaluation.get('risk_pts',0)
    return dict(components=components,sum=total,matched=matched,action=evaluation['action'],
                previous_action=evaluation.get('previous_action'),smoothing_note=evaluation.get('action_note'),
                trigger=f"Pôvodné prahy: REDUCE od {legacy.CONFIG['risk_high_pts']} b.; SELL od {legacy.CONFIG['sell_pts']} b. a skóre ≤3.5. "+(evaluation.get('action_note') or '')+' Ide o technické/legacy riziko, nie overenú predikciu ďalšieho prepadu nad 10 %.')


def render(legacy,snapshot,fundamentals,now,kind,state,previous=None,fear=None):
    """Presentation only; the unchanged native evaluations remain authoritative."""
    from .compact_report import render as compact
    ctx,metrics,safety,evaluations=evaluate(legacy,snapshot,state,fear)
    text=compact(legacy,snapshot,fundamentals,now,kind,ctx,safety,evaluations,previous)
    quotes={s:dict(price=c.get('price') if not c.get('stale') else None,
        market_cap=c.get('market_cap'),volume_24h=c.get('volume_24h'),action=evaluations[s]['action'],
        trend_score_10=evaluations[s].get('trend_score'),rule_engine='v10.6-original')
        for s in legacy.PORTFOLIO for c in [snapshot['coins'].get(s,{})]}
    require_public_data(text);require_public_data(quotes)
    return text,quotes,evaluations
