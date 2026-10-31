"""Evidence interpretation only. No trades, portfolio defaults or model refitting."""
import re

def prediction_label(f):
    if not f:return 'nedostupné'
    if f.get('model')=='flat':return 'REFERENCIA'
    return 'NEURČENÉ' if f.get('direction')=='DO STRANY' else f.get('direction','nedostupné')

def incident_fact(title):
    text=title.lower()
    entity=next((e for e in ('binance','coinbase','bybit','kraken','okx') if re.search(r'\b'+e+r'\b',text)),None)
    if not entity or not re.search(r'hack|exploit|breach|withdrawal|asset freez|frozen assets|losses|reimburse',text):return None
    # Distinct facts, not optimistic/negative rewording. Commentary is not a new event.
    fact='breach'
    if re.search(r'withdrawals? (?:resumed|restored|reopened)|resumes? withdrawals',text):fact='withdrawals_resumed'
    elif re.search(r'losses.*fully covered|fully reimbursed',text):fact='losses_repaid'
    elif re.search(r'wider breach|additional breach|new vulnerability',text):fact='breach_expanded'
    elif re.search(r'withdrawals? (?:halted|suspended|paused)|halts? withdrawals',text):fact='withdrawals_paused'
    elif re.search(r'freez|frozen',text):fact='asset_freeze'
    elif re.search(r'cover|matching tokens|safu|reimburse',text):fact='coverage_plan'
    # A verified changed amount must not be erased by semantic deduplication.
    from decimal import Decimal
    amounts=[format(Decimal(n)*(1000000000 if unit.startswith('b') else 1000000),'f') for n,unit in re.findall(r'(\d+(?:\.\d+)?)\s*(billion|million|bn\b|[bm]\b)',text)]
    return entity,fact,tuple(amounts)

def movement_review(snapshot,fund):
    """Coverage checklist; co-occurrence never establishes causation."""
    g=snapshot.get('global_data',{});change=g.get('change')
    if type(change) not in (int,float) or abs(change)<5:return {'required':False}
    extensions=fund.get('extensions',{})
    return dict(required=True,observed_cap_change_24h=change,causal_attribution='UNCONFIRMED',
                checks={'crypto_and_altcoins':bool(snapshot.get('coins')),'macro':bool(fund.get('macro_context')),
                        'etf_flows':bool(extensions.get('etf_flows')),'liquidations':False,'equity_fx_yields':'SEE_SOURCE_DIAGNOSTICS',
                        'project_and_security_news':bool(fund.get('events'))},
                missing='Liquidations, leverage and complete global capital flows are not verified; unavailable is not zero.')
