"""Compact interpretation; approved action lines are copied byte for byte."""
import re
from . import analyst,event_lifecycle,fundamental_extensions as ext,report_verdict as rv
from .telegram_text import without_links
from .fundamental_analysis import ALIASES
from .prediction_runtime import current_predictions


def render(model,snapshot,now,kind,inventory=None):
    base=analyst.final_text(model,snapshot,now,kind,inventory)
    head,body=base.split('ODPORÚČANIA:',1);header=head.splitlines()
    predictions=current_predictions(model,int(now.timestamp()*1000));count=sum(len(v) for v in predictions.values())
    lines=rv.verdict(model,snapshot,body,inventory)+['',*header[:2]]
    market=next((line for line in header if line.startswith('BTC ')),None)
    if market:lines.append(market)
    compared=next((line for line in header if line.startswith('Od ')),None)
    if compared:lines.append(compared)
    fund=model.get('_current_fundamentals',{});extensions=fund.get('extensions',{})
    macro=event_lifecycle.lines(fund,now)+ext.lines(extensions,now,event_limit=2)
    critical=[e for e in model.get('evidence',[]) if set(e.get('categories',[]))&{'hack','geopolitics','regulation'}]
    for item in critical[:2]:macro.append('Dôležitá správa '+item['published_at'][:10]+' ('+item['source']+'): '+item['title'][:120]+' — '+item['impact']+'.')
    if macro:lines+=['','MAKRO / UDALOSTI:',*macro]
    lines+=['','V2: EXPERIMENTÁLNE – PRESNOSŤ NEOVERENÁ; nízka istota, bez percentuálnych pravdepodobností.']
    if count<18:lines.append('Časť výstupov V2 je N/A; nahrádzajú ich označené technické scenáre, nie výstupy modelu.')
    for symbol in analyst.COINS:
        original=next((line for line in body.splitlines() if line.startswith(symbol+' ')),None)
        if original is None:continue
        lines+=['',original]
        c=snapshot['coins'].get(symbol,{});t=c.get('frames',{}).get('4h',{});p=c.get('price')
        if not predictions.get(symbol):
            short=rv.fallback(model,snapshot,symbol,'24 h',now).replace('náhradný technický scenár: ','')
            medium=rv.fallback(model,snapshot,symbol,'7–14 dní',now).replace('náhradný technický scenár: ','')
            lines.append('Náhradný technický scenár (nie V2): 24–72h '+short+'; 7–14 dní '+medium+'.')
        else:
            pieces=[]
            for horizon,label in [('24 h','24h'),('48–72 h','72h'),('7–14 dní','14d')]:
                f=predictions.get(symbol,{}).get(horizon)
                if f:pieces.append(f"{label} {f['direction']} {analyst.price(f['low'])}–{analyst.price(f['high'])} ({analyst.pct(f['low_pct'])}/{analyst.pct(f['high_pct'])})")
                else:pieces.append(label+' '+rv.fallback(model,snapshot,symbol,horizon,now))
            lines.append('V2: '+' | '.join(pieces))
        support=t.get('support');resistance=t.get('resistance');invalid=model['coins'].get(symbol,{}).get('invalidates')
        s=analyst.price(support) if analyst.number(support) and analyst.number(p) and support<p else 'predošlá pri/nad cenou; ďalšia nepotvrdená' if analyst.number(support) and analyst.number(p) else 'N/A'
        r='rast potvrdiť uzavretím nad '+analyst.price(resistance)+' s objemom' if analyst.number(resistance) and analyst.number(p) and resistance>p else 'nová rastová hranica nepotvrdená'
        lines.append('Hranice: podpora '+s+'; '+r+'.'+((' Neplatnosť vstupného scenára pod '+analyst.price(invalid)+'.') if analyst.number(invalid) else ''))
        activity=next((v for v in model.get('project_activity',[]) if v['symbol']==symbol and abs(v['change_pct'])>=10),None)
        if activity:lines.append(f"Fundament: {('poplatky' if activity['metric']=='fees' else 'príjmy')} protokolu {analyst.pct(activity['change_pct'])} vs predošlé obdobie; nie čistý prílev kapitálu.")
        extra=ext.project_lines(symbol,extensions,c,now)
        # Supply/periodic parameter detail remains in the diagnostic artifact;
        # main report highlights only an upcoming event or a material measured change.
        selected=[line for line in extra if 'unlock:' in line or re.search(r'\([+-](?:[1-9]\d|\d{3,})\.',line)]
        if selected:lines.append(selected[0])
        e=next((e for e in model.get('project_evidence',[]) if e.get('material') and re.search(ALIASES[symbol],e['title'],re.I)),None)
        if e and not activity and not selected:
            title=e['title'].lower()
            note='Hlásený bezpečnostný incident; rozsah a expozíciu treba potvrdiť.' if 'hack' in e.get('categories',[]) else 'Správa o tokenizácii; reálne používanie a ekonomický dopad treba potvrdiť.' if re.search(r'tokeniz',title) else 'Projektová/regulačná udalosť; ekonomický dopad zatiaľ nepotvrdený.'
            lines.append('Fundament '+e['published_at'][:10]+': '+note)
    extras=[line for line in body.splitlines() if re.match(r'^[A-Z][A-Z0-9]* .*?— (?:BUY NOW|BUY PULLBACK|WAIT|HOLD|REDUCE|SELL) \(',line) and line.split()[0] not in analyst.COINS]
    if extras:lines+=['','ĎALŠIE POZÍCIE / WATCHLIST:',*extras]
    tail='\n'.join(line for line in body.splitlines() if line.startswith('ZÁVER:') or line.startswith('Technické signály') or (line.startswith('PRÍLEŽITOSŤ:') and 'Kandidát' in line))
    lines+=['',tail,'Kontrola: pri potvrdení hraníc alebo po najbližšej významnej udalosti; plánované reporty pokračujú.']
    if kind=='evening' and now.weekday()==6 and model.get('paper_weekly'):lines+=['PAPER: '+model['paper_weekly']]
    return without_links('\n'.join(lines))
