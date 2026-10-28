"""Manual, public-GET-only experiment. Never loads main.py, inventory or delivery."""
import argparse,json,sys,time,hashlib
from pathlib import Path
from datetime import datetime,timezone
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from v11 import prediction_shadow as model
from v11.analyst import relevant_events,price,pct
from v11.state_policy import require_public_data
from v11.fundamental_analysis import analyze,ALIASES
import re
from scripts.v111_shadow import ShadowAPI,protected_hashes
from scripts.fundamental_sources_shadow import run as collect
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'shadow-output/prediction'

def run(reuse=False):
    before=protected_hashes();OUT.mkdir(parents=True,exist_ok=True)
    source=ROOT/'shadow-output/prediction-sources'
    if not reuse:collect(source,False)
    snapshot=json.loads((source/'market_snapshot.json').read_text());fund=json.loads((source/'fundamentals.json').read_text())
    if not 0<=time.time()-snapshot.get('at',0)<=900:raise ValueError('Snapshot older than 15 minutes; collect again')
    api=ShadowAPI(False);results={};views={};history_errors={};journal=[];observations={};records=[]
    now=datetime.now(timezone.utc);now_ms=int(now.timestamp()*1000)
    for symbol in model.COINS:
        coin=snapshot['coins'].get(symbol,{})
        views[symbol]=model.coin_view(coin,snapshot['coins'].get('BTC'))
        try:
            rows=api.http_json('https://data-api.binance.vision/api/v3/klines?symbol='+symbol+'USDT&interval=4h&limit=1000',retries=1,timeout=15)
            history=[dict(timestamp=int(r[0]),open=float(r[1]),high=float(r[2]),low=float(r[3]),close=float(r[4]),volume=float(r[5])) for r in rows if int(r[6])<now_ms]
            results[symbol]=model.evaluate(history)
            for row in history:observations[symbol,row['timestamp']+model.STEP]=row['close']
            results[symbol]['source']='Binance public spot OHLCV 4h; last 1000 closed bars; no survivorship correction'
        except Exception as exc:
            results[symbol]={'status':'NO_DATA'};history_errors[symbol]=type(exc).__name__
        raw=coin.get('raw',{}).get('4h',[])
        if raw and views[symbol]['status']!='NO_DATA':
            origin=raw[-1]['timestamp']+model.STEP
            for label,f in views[symbol]['forecasts'].items():
                if f['status']=='NO_DATA':continue
                due=origin+model.HORIZONS[label]*model.STEP
                records.append(dict(id=f'{symbol}:{origin}:{due}',symbol=symbol,created=origin,due=due,price=f['price'],point=f['point'],low=f['low'],high=f['high'],direction=f['direction'],continuation=f['price']*(1+max(-.95,(raw[-1]['close']/raw[-21]['close']-1)*model.HORIZONS[label]/20))))
    journal_file=OUT/'public-predictions.json'
    public_reference=ROOT/'public-analytics/prediction-shadow.json'
    if journal_file.exists():journal=json.loads(journal_file.read_text())
    elif public_reference.exists():journal=json.loads(public_reference.read_text())
    reference_digest=hashlib.sha256(public_reference.read_bytes()).hexdigest() if public_reference.exists() else None
    journal=model.journal_update(journal,records,observations,now_ms)
    events=relevant_events(fund,now)
    project_evidence=[e for e in analyze(fund,now)['evidence'] if e['material']]
    text=['EXPERIMENTÁLNY VÝSKUM — NEAKTÍVNE; NIE POTVRDENÉ SIGNÁLY',now.strftime('%d.%m.%Y %H:%M UTC'),
          'Nové nákupy: WAIT. Súkromné držby sa v tomto teste nenačítavajú.',
          'Pásma sú historické koncové scenáre, nie očakávané maximum/minimum ani kalibrované intervaly. Istota NÍZKA.']
    if events:
        text+=['OVERENÉ PODKLADY (nepreukazujú príčinu pohybu):']
        for e in events:text.append(f"{e['title']} | {e.get('published_at','čas N/A')} | {e['url']}")
    else:text.append('Relevantný aktuálny fundament nepotvrdený; dôvod dnešného pohybu N/A.')
    for symbol,v in views.items():
        c=snapshot['coins'].get(symbol,{})
        text.append(f"\n{symbol} — {price(c.get('price') if not c.get('stale',True) else None)} | WAIT")
        if v['status']=='NO_DATA':text.append('Nedostatok aktuálnych súvislých dát; scenáre N/A.');continue
        text.append(f"{v['trend']}; {v['reversal']}; objem {v['volume_ratio']:.2f}×; RS/BTC7d {pct(v['relative_strength_btc_7d']*100 if v['relative_strength_btc_7d'] is not None else None)}." if v['volume_ratio'] is not None else 'Objem N/A.')
        for label,f in v['forecasts'].items():
            if f['status']=='NO_DATA':text.append(label+': N/A');continue
            text.append(f"{label} (od uzavretej 4h ceny {price(f['price'])}): {f['direction']}, {price(f['low'])}–{price(f['high'])} ({pct(f['low_pct'])} až {pct(f['high_pct'])}); {f['reason']}.")
        matched=[e for e in project_evidence if re.search(ALIASES[symbol],e['title'],re.I)]
        if matched:
            e=matched[0];text.append(f"Fundament: {e['title']}; {e['impact']}; overiť {e['confirmation']}. {e['url']}")
        else:text.append('Nový významný projektový fundament nepotvrdený; pokrytie čiastočné.')
        text.append(f"Potvrdenie: {v['confirmation']}. Podpora {price(v['invalidates'])}; {v['risk']}. Zóna {'–'.join(price(x) for x in v['zone']) if v['zone'] else 'N/A'} iba na sledovanie.")
    ranked=sorted((s for s in views if views[s]['status']!='NO_DATA'),key=lambda s:sum(views[s]['rank_groups']),reverse=True)
    text+=['\nPoradie na ďalšie sledovanie: '+(', '.join(ranked) or 'N/A')+'. Heuristické skupiny dôkazov, nie pomer overeného výnosu/rizika.',
           'Nová významná udalosť alebo prieraz úrovne ruší scenár; nepreukazuje automaticky BUY/SELL. Makro výsledok lepší/horší než overené očakávanie: posúdiť priaznivý/nepriaznivý variant, smer ani veľkosť dopadu nepotvrdené.',
           'Zmena od predchádzajúcej analýzy N/A bez časovo overenej referencie. Objem a kapitalizácia nie sú čisté toky.']
    artifact=dict(views=views,history=results,errors=history_errors,events=events,production_enabled=False,independent_validation=False)
    require_public_data(artifact);require_public_data(journal)
    for name,value in [('diagnostics.json',artifact),('public-predictions.json',journal),('journal-manifest.json',dict(previous_sha256=reference_digest))]:
        temporary=OUT/(name+'.tmp');temporary.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False));temporary.replace(OUT/name)
    (OUT/'preview.txt').write_text('\n'.join(text))
    assert before==protected_hashes(),'Protected production file changed'
    print('Prediction shadow complete: no Telegram, inventory or production state access.')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--reuse-collected-sources',action='store_true');a=p.parse_args();run(a.reuse_collected_sources)
