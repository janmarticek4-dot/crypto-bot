"""Offline evidence audit only. No alternative strategy, network or state write."""
import argparse,copy,json,sys,zipfile,hashlib
from pathlib import Path
from datetime import datetime,timezone
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import main as legacy
from v11 import integration
from v11.state_policy import require_public_data


def audit(snapshot,state,at):
    class Clock(datetime):
        @classmethod
        def now(cls,tz=None):return at.astimezone(tz) if tz else at.replace(tzinfo=None)
    def run(st):
        with patch.object(legacy,'datetime',Clock):return integration.evaluate(legacy,snapshot,st)
    ctx,metrics,safety,ev=run(state)
    variants={}
    for label,keys in [('without_stored_peaks',('peaks',)),('without_safety_memory',('safety',)),('without_action_memory',('last_actions',)),('without_cached_fundamentals',('fundamentals','alert_research')),('without_any_state',integration.PUBLIC_RULE_KEYS)]:
        st=copy.deepcopy(state)
        for k in keys:st.pop(k,None)
        _,mm,ss,ee=run(st)
        variants[label]=dict(safety=ss,coins={s:dict(action=e['action'],risk_pts=e.get('risk_pts'),peak=mm[s]['peak']) for s,e in ee.items()})
    coins={}
    for symbol,e in ev.items():
        data=ctx['portfolio_data'][symbol];tech=data['technical_4h'];raw=snapshot['coins'][symbol].get('raw',{}).get('4h',[])
        m=metrics[symbol];stored=state.get('peaks',{}).get(symbol,{})
        coins[symbol]=dict(evaluation=e,metrics=m,technical_4h=tech,score_components=data['technical_score_calc'],risk=integration.risk_breakdown(legacy,e),
            candle_last_open=datetime.fromtimestamp(raw[-1]['timestamp']/1000,timezone.utc).isoformat() if raw else None,
            candle_last_close=datetime.fromtimestamp(raw[-1]['timestamp']/1000+14400,timezone.utc).isoformat() if raw else None,
            metadata_at=snapshot['coins'][symbol].get('metadata_at'),price_source=snapshot['coins'][symbol].get('price_source'),
            window_peak=dict(price=data['structure'].get('window_high'),timestamp=data['structure'].get('window_high_ts')),
            stored_peak=stored,support_break_trigger=m['support']*.995 if m.get('support') else None,
            current_price_above_support=m['price']>=m['support'] if m.get('price') and m.get('support') else None,
            sell_pressure=m['sell_pressure'],change_24h=snapshot['coins'][symbol].get('change_24h'),volume_24h=snapshot['coins'][symbol].get('volume_24h'))
    out=dict(as_of=at.isoformat(),clock='frozen at snapshot retrieval; not a current market observation',
             market_context={k:v for k,v in ctx.items() if k not in ('btc_data','portfolio_data')},btc=dict(metrics=metrics['BTC'],technical=ctx['btc_data']['technical_4h']),safety=safety,coins=coins,ablations=variants)
    require_public_data(out);return out

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--artifact',required=True);p.add_argument('--state',required=True);p.add_argument('--output',required=True);a=p.parse_args()
    with zipfile.ZipFile(a.artifact) as z:
        snap=json.loads(z.read('market_snapshot.json'));summary=json.loads(z.read('summary.json'));recorded=json.loads(z.read('risk_diagnostics.json'))
    result=audit(snap,integration.read_rule_state(a.state),datetime.fromisoformat(summary['collected_at']))
    result['provenance']=dict(artifact=Path(a.artifact).name,artifact_sha256=hashlib.sha256(Path(a.artifact).read_bytes()).hexdigest(),state_sha256=hashlib.sha256(Path(a.state).read_bytes()).hexdigest(),state_context='local public baseline; not original runner state',original_recorded_risks=recorded)
    Path(a.output).write_text(json.dumps(result,ensure_ascii=False,indent=2))
