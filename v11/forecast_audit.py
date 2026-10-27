"""Public scenario journal. Endpoint outcomes are not executed trades or accuracy guarantees."""
from datetime import datetime,timezone
from .briefing import remember,evaluate
from .event_ledger import update as update_events


def update(state,snapshot,fundamentals,slot):
    forecasts=state.setdefault('analysis_forecasts_v11',[])
    eligible=[f for f in forecasts if f.get('delivery_confirmed')]
    evaluate(dict(state,analysis_forecasts_v11=eligible),snapshot)
    totals=state.setdefault('forecast_totals_v1',{'evaluated':0,'inside':0,'outside':0})
    for item in eligible:
        outcome=item.get('outcome')
        if outcome and not outcome.get('counted'):
            totals['evaluated']+=1;totals['inside' if outcome['inside'] else 'outside']+=1
            outcome['counted']=True
    remember(state,snapshot,{s:{'action':'WAIT'} for s in snapshot['coins']},slot)
    update_events(state,fundamentals.get('events',[]),snapshot)
    pending=[];completed=[]
    for item in state['analysis_forecasts_v11']:
        if item.get('outcome'):completed.append(item)
        elif snapshot['at']>item['due'] and not item.get('delivery_confirmed'):
            state['forecast_unscored_v1']=state.get('forecast_unscored_v1',0)+1
        elif snapshot['at']-item['at']>45*86400:
            state['forecast_unscored_v1']=state.get('forecast_unscored_v1',0)+1
        else:pending.append(item)
    state['analysis_forecasts_v11']=pending+completed[-90:]
    for item in state['event_ledger_v11'].values():item['observations']=item['observations'][-8:]
    state['event_ledger_v11']=dict(sorted(state['event_ledger_v11'].items(),key=lambda pair:pair[1]['at'])[-30:])
    # No private fills, balances or ownership are read or written here.
    return state


def lines(state):
    forecasts=state.get('analysis_forecasts_v11',[])
    ready=[f for f in forecasts if f.get('outcome')]
    out=['KONTROLA PROGNÓZ — až po horizonte, nie výsledky obchodov:']
    if state.get('forecast_unscored_v1'):out.append(f"Nevyhodnotiteľné záznamy (chýbajúce potvrdenie doručenia alebo historická cena): {state['forecast_unscored_v1']}. Nie sú rátané ako úspech.")
    if not ready:return out+['N/A — ešte nemáme dozreté vyhodnotiteľné scenáre; úspešnosť zatiaľ neznáma.']
    totals=state.get('forecast_totals_v1',{})
    success=totals.get('inside',sum(bool(f['outcome']['inside']) for f in ready));failed=totals.get('outside',len(ready)-success)
    out.append(f'Vyhodnotené {success+failed}; základné pásmo pri konci horizontu: {success} potvrdených, {failed} nepotvrdených. Nie kalibrovaná pravdepodobnosť ani kontrola každej vetvy.')
    for item in ready[-3:]:
        result=item['outcome'];change=result['return_pct']
        # Conservative illustrative holding benchmark, not a claimed strategy fill.
        gross=1+change/100
        net=(gross*(1-.012)/(1+.012)-1)*100
        out.append(f"{item['symbol']} {item['horizon']}: {'v pásme' if result['inside'] else 'mimo pásma'}; cena {change:+.2f}%; hypotetické držanie po1.2% na každej strane {net:+.2f}%. Nie skutočný obchod ani stratégia vs HOLD.")
    return out
