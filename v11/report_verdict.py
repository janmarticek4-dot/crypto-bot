"""Evidence interpretation and presentation; never selects trading actions."""
import re
from . import analyst
from .telegram_text import without_links

FORMAT='verdict-v1'
ACTIONS={'BUY NOW':'NAKÚPIŤ','BUY PULLBACK':'POČKAŤ NA POTVRDENÝ PULLBACK','WAIT':'POČKAŤ','HOLD':'DRŽAŤ','REDUCE':'ZNÍŽIŤ POZÍCIU','SELL':'PREDAŤ'}

def actions(body):
    result=[]
    for line in body.splitlines():
        match=re.match(r'^([A-Z][A-Z0-9]*) .*?— (BUY NOW|BUY PULLBACK|WAIT|HOLD|REDUCE|SELL) \((držba|nový nákup)\):',line)
        if match:result.append(match.groups())
    return result


def interpretation(model,snapshot):
    comp=model.get('comparison',{});cap=comp.get('global_cap_pct') if comp.get('status')=='COMPARED' else snapshot.get('global_data',{}).get('change')
    volume=comp.get('global_volume_pct') if comp.get('status')=='COMPARED' else None
    alts=[c for s,c in snapshot.get('coins',{}).items() if s in analyst.COINS and not c.get('stale',True)]
    strengths=[c.get('relative_strength_btc_7d') for c in alts if analyst.number(c.get('relative_strength_btc_7d'))]
    lagging=sum(s<0 for s in strengths)>len(strengths)/2 if strengths else None
    if analyst.number(cap) and cap<0 and analyst.number(volume) and volume>0 and lagging:
        return 'Pribúdajú indície predajného tlaku: nižšia kapitalizácia, vyšší 24h objem a slabšie altcoiny voči BTC. Objem nie je čistý tok kapitálu ani dôkaz ďalšieho prepadu.'
    if analyst.number(cap) and cap<0:
        return 'Korekcia pokračuje'+('; altcoiny zaostávajú za BTC' if lagging else '')+'. '+('Objemové potvrdenie prehlbovania poklesu chýba.' if not analyst.number(volume) or volume<=0 else 'Vyšší objem zvyšuje význam pohybu; smer ďalšieho vývoja ešte nie je potvrdený.')
    if analyst.number(cap) and cap>0:
        return 'Trh sa zotavuje'+(', ale zaostávanie altcoinov zatiaľ nepotvrdzuje široký obrat.' if lagging else '; udržanie rastu musí potvrdiť štruktúra a objem.')
    return 'Smer trhu nemožno spoľahlivo potvrdiť; chýbajú porovnateľné údaje.'


def verdict(model,snapshot,body,inventory=None):
    change=snapshot.get('global_data',{}).get('change')
    label='KOREKCIA' if analyst.number(change) and change<0 else 'RAST' if analyst.number(change) and change>0 else 'KONSOLIDÁCIA' if analyst.number(change) else 'N/A — nedostatok údajov'
    parsed=actions(body);new=[(s,a) for s,a,c in parsed if c=='nový nákup'];held=[(s,a) for s,a,c in parsed if c=='držba']
    buys=[s for s,a in new if a=='BUY NOW']
    purchase='NAKÚPIŤ '+', '.join(buys) if buys else 'POČKAŤ s novými nákupmi'
    holding='; '.join(s+' '+ACTIONS[a] for s,a in held) if held else 'držba bez bezpečne načítaných pozícií neposúdená' if inventory is None else 'bez evidovaných otvorených pozícií'
    result=['📌 INVESTIČNÝ VERDIKT: '+label,'AKCIA: '+purchase+'. '+holding+'.']
    for horizon in ('24–72 h','7–14 dní'):
        view=model.get('forecasts',{}).get('BTC',{}).get(horizon,{})
        text=view.get('base','výhľad nepotvrdený')
        result.append(horizon+': základný technický scenár — '+text+'; neistota zvýšená.')
    result.append('DÔVOD: '+interpretation(model,snapshot))
    btc=model.get('forecasts',{}).get('BTC',{}).get('24–72 h',{})
    result.append('PODMIENKY: '+btc.get('upside','potvrdenie rastovej štruktúry a objemu')+'; riziko '+btc.get('downside','nové potvrdené narušenie podpory')+'.')
    return result


def fallback(model,snapshot,symbol,horizon,now):
    age=now.timestamp()-snapshot.get('at',0)
    if not 0<=age<=900:return 'technický scenár nedostupný — neaktuálny snapshot'
    label='7–14 dní' if horizon=='7–14 dní' else '24–72 h'
    value=model.get('forecasts',{}).get(symbol,{}).get(label,{})
    if value.get('status')!='CONDITIONAL':return 'technický scenár nedostupný — neúplné údaje'
    return 'náhradný technický scenár: '+value['base']


def contract(text,count):
    return dict(format_version=FORMAT,verdict_first=text.startswith('📌 INVESTIČNÝ VERDIKT:'),
                urls_absent=not bool(re.search(r'https?://|www\.',text,re.I)),
                v2_count=count,technical_fallback_labeled='náhradný technický scenár' in text.lower())
