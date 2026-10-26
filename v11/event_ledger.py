"""Event observations are separate from verified release values and expectations."""
from datetime import datetime, timezone
from .fundamentals import timestamp


def update(state,events,snapshot):
    now=snapshot['at'];ledger=state.setdefault('event_ledger_v11',{})
    for event in events:
        at=timestamp(event.get('event_at'))
        if not event.get('scheduled') or not at:continue
        identity=event['id']+'|'+at.isoformat()
        ledger.setdefault(identity,dict(id=identity,title=event['title'],url=event['url'],at=at.timestamp(),
            expectation=None,result=None,observations=[]))
    for item in ledger.values():
        if item['at']>now:continue
        # These are report-time observations, explicitly NOT event-time prices.
        observations=item['observations']
        if not observations or now-observations[-1]['at']>=3600:
            observations.append(dict(at=now,prices={s:d['price'] for s,d in snapshot['coins'].items()
                if not d.get('stale') and d.get('price')}))
        item['observations']=observations[-48:]
        item['status']='past_awaiting_verified_result' if item.get('result') is None else 'result_verified'
    state['event_ledger_v11']={k:v for k,v in ledger.items() if now-v['at']<45*86400}


def lines(state,now):
    out=['USKUTOČNENÉ UDALOSTI – KONTROLA VÝSLEDKU']
    items=sorted((v for v in state.get('event_ledger_v11',{}).values() if 0<=now-v['at']<=86400),key=lambda x:x['at'])
    for item in items[:4]:
        out.append(f"{item['title']} | {item['url']} | očakávanie N/A; číselný výsledok N/A — čaká na doložený výsledok, termín sám nepotvrdzuje zverejnenie.")
        observations=item['observations']
        if len(observations)>=2:
            a,b=observations[0],observations[-1]
            price_a=a['prices'].get('BTC');price_b=b['prices'].get('BTC')
            if price_a and price_b:
                out.append(f"BTC medzi pozorovaniami {datetime.fromtimestamp(a['at'],timezone.utc).isoformat()} a {datetime.fromtimestamp(b['at'],timezone.utc).isoformat()}: {(price_b/price_a-1)*100:+.2f} %. Nie reakcia od presného času udalosti ani dôkaz príčiny.")
        else:out.append('Cenová reakcia N/A — chýbajú porovnateľné pozorovania po termíne.')
    if not items:out.append('N/A — v evidencii nie je nedávna plánovaná udalosť s overeným časom.')
    return out
