"""Presentation only: same approved actions, experimental forecasts do not vote."""
import re
from . import analyst,event_lifecycle
from .telegram_text import without_links
from .fundamental_analysis import ALIASES


def render(model,snapshot,now,kind,inventory=None):
    base=analyst.final_text(model,snapshot,now,kind,inventory)
    head,body=base.split('ODPORÚČANIA:',1)
    header=head.splitlines();lines=header[:2]+['MAKRO A AKTUÁLNE UDALOSTI:']
    lines+=event_lifecycle.lines(model.get('_current_fundamentals',{}),now)
    lines+=header[2:]
    lines+=['','EXPERIMENTÁLNE – PRESNOSŤ NEOVERENÁ. Istota NÍZKA; bez kalibrovaných pravdepodobností. Scenáre nemenia obchodné odporúčania.']
    predictions=model.get('experimental_predictions',{})
    for symbol in analyst.COINS:
        original=next((line for line in body.splitlines() if line.startswith(symbol+' ')),None)
        if original is None:continue
        c=snapshot['coins'].get(symbol,{});t=c.get('frames',{}).get('4h',{});p=c.get('price')
        lines+=['',original]
        volume=t.get('relative_volume');rs=c.get('relative_strength_btc_7d');daily=c.get('frames',{}).get('1d',{})
        trend='rastový' if analyst.number(p) and analyst.number(t.get('ema50')) and p>t['ema50'] else 'slabý/neúplný'
        daily_trend='nad EMA50' if analyst.number(p) and analyst.number(daily.get('ema50')) and p>daily['ema50'] else 'pod EMA50 alebo N/A'
        lines.append(f"Trend 4h {trend}, 1d {daily_trend}; sila {t.get('adx'):.0f} ADX" if analyst.number(t.get('adx')) else 'Sila trendu N/A.')
        lines.append('Objem '+(f'{volume:.2f}× priemer' if analyst.number(volume) else 'N/A')+'; RS/BTC7d '+analyst.pct(rs*100 if analyst.number(rs) else None)+'.')
        e=next((e for e in model.get('project_evidence',[]) if e['material'] and re.search(ALIASES[symbol],e['title'],re.I)),None)
        activity=next((v for v in model.get('project_activity',[]) if v['symbol']==symbol),None)
        if e:lines.append(f"Fundament: {e['title']} ({e['published_at'][:10]}), {e['impact']}.")
        elif activity:lines.append(f"Fundament: {activity['metric']} {analyst.pct(activity['change_pct'])} vs predošlé obdobie; nie čistý prílev ani potvrdenie rastu tokenu.")
        else:lines.append('Fundament: nový významný impulz nepotvrdený; pokrytie čiastočné.')
        for label,short in [('24 h','24 h'),('48–72 h','72 h'),('7–14 dní','14 dní')]:
            f=predictions.get(symbol,{}).get(label)
            if not f:lines.append('Predikcia '+short+': N/A — model alebo aktuálne vstupy nedostupné.');continue
            lines.append(f"{short}: {f['direction']}, {analyst.price(f['low'])}–{analyst.price(f['high'])} ({analyst.pct(f['low_pct'])} až {analyst.pct(f['high_pct'])}).")
        support=t.get('support');resistance=t.get('resistance')
        if analyst.number(support) and analyst.number(p) and support>=p:
            lines.append(f"Predošlá podpora {analyst.price(support)} je už nad cenou; ďalšia podpora N/A.")
        else:lines.append('Riziko pod '+analyst.price(support)+': uzavretie a potvrdenie predajného tlaku menia výhľad.')
        if analyst.number(resistance) and analyst.number(p) and resistance>p:
            lines.append('Alternatíva rastu: uzavretie 4h nad '+analyst.price(resistance)+' s objemom a udržaním novej podpory.')
        else:lines.append('Potvrdenie rastu: nová rezistencia/retest N/A; samotný odraz nestačí.')
    tail=body[body.find('PRÍLEŽITOSŤ:'):] if 'PRÍLEŽITOSŤ:' in body else ''
    lines+=['',tail]
    weekly=model.get('paper_weekly')
    if kind=='evening' and now.weekday()==6 and weekly:lines+=['PAPER – priebežná vzorka: '+weekly]
    return without_links('\n'.join(lines))
