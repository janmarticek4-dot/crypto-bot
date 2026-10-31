"""Full production-format dry run. No Telegram, private storage or research write."""
import json,sys,os
from pathlib import Path
from datetime import datetime,timezone
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.fundamental_sources_shadow import run as collect
from scripts.v111_shadow import protected_hashes
from scripts.v2_context import enrich
from v11 import analyst,integration,event_lifecycle,prediction_runtime,prediction_journal
from v11.integrated_report import render
from v11.reporting import chunks,units
from v11.state_policy import require_public_data
import main as legacy
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'shadow-output/production-v2'

class ReadOnlyStore:
    def read(self):
        # Same public package selection as delivery, with read-only credentials
        # and no append path. A frozen preview must not expire while daily paper
        # has already published a fresh package.
        if os.getenv('GH_TOKEN') and os.getenv('GITHUB_REPOSITORY'):
            from scripts.public_prediction_store import PublicPredictionStore
            value=PublicPredictionStore().read()
        else:value=prediction_journal.load(json.loads((ROOT/'public-analytics/prediction-shadow.json').read_text()))
        if not value.get('runtime_package'):value['runtime_package']=json.loads((ROOT/'v11/frozen_prediction_package.json').read_text())
        return value
    def append(self,*a):raise AssertionError('Preview cannot write')

def run(reuse=False):
    before=protected_hashes();source=ROOT/'shadow-output/prediction-sources';OUT.mkdir(parents=True,exist_ok=True)
    if not reuse:collect(source,False)
    snap=json.loads((source/'market_snapshot.json').read_text());fund=json.loads((source/'fundamentals.json').read_text())
    now=datetime.now(timezone.utc)
    if not 0<=now.timestamp()-snap['at']<=900:raise ValueError('Stale preview input')
    fund=event_lifecycle.collect(fund,now,snap)
    state=integration.read_rule_state(ROOT/'bot_state.json')
    _,quotes,evaluations=integration.render(legacy,snap,fund,now,'evening',state,fear=legacy.get_fear_greed())
    previous=json.loads((ROOT/'trial-public/v111-delivery.json').read_text()).get('last_analysis_v112')
    model=analyst.prepare(snap,fund,now,quotes,evaluations,previous)
    enrich(snap,fund,now,model,persist=False,store=ReadOnlyStore())
    from v11 import trend_reversal
    trend_reversal.attach(model,snap,fund,now,json.loads((ROOT/'trial-public/v111-delivery.json').read_text()))
    from v11 import event_notices
    model['event_notices']=event_notices.plan(fund,json.loads((ROOT/'trial-public/v111-delivery.json').read_text()),now)
    reports={kind:render(model,snap,now,kind) for kind in ('morning','evening')}
    from v11.integrated_report import render_detailed
    from v11.v113 import movement_review,expanded_market_context
    model['movement_review']=movement_review(snap,fund)
    model['expanded_market_context']=expanded_market_context(snap,now)
    detailed=render_detailed(model,snap,now,'morning')
    (OUT/'morning-detailed.txt').write_text(detailed)
    from v11.report_verdict import contract
    current=prediction_runtime.current_predictions(model,int(now.timestamp()*1000))
    count=sum(len(v) for v in current.values())
    from v11.reversal_report import guard
    model['report_consistency']={k:guard(t,analyst.final_text(model,snap,now,k),model,snap)[1] for k,t in reports.items()}
    contracts={k:contract(t,count) for k,t in reports.items()}
    for details in contracts.values():assert details['verdict_first'] and details['urls_absent']
    if os.getenv('REQUIRE_V2_PREDICTIONS')=='1':assert count==18,model.get('prediction_diagnostics')
    details=model.get('prediction_diagnostics',{})
    proof=dict(predictions=count,per_coin={s:len(v) for s,v in current.items()},contracts=contracts,
        generated_at=details.get('generated_at'),package_created=details.get('package_created'),package_age_ms=details.get('package_age_ms'),
        snapshot_age_ms=details.get('snapshot_age_ms'),missing_predictions=details.get('missing_predictions',{}),
        parts={k:len(chunks(v)) for k,v in reports.items()},reversal_state=model.get('trend_reversal',{}).get('state'),consistency_checks=model['report_consistency'],v2_mechanism=model.get('prediction_review',{}).get('mechanism'),paper_matured=model.get('prediction_review',{}).get('matured'),length_comparison=dict(detailed=len(detailed),compact=len(reports['morning']),reduction_pct=round((1-len(reports['morning'])/len(detailed))*100,1)),new_buy_sell_activated=False,telegram_sent=False)
    print('::notice title=Live report contract::'+json.dumps(proof))
    (OUT/'live-contract.json').write_text(json.dumps(proof,ensure_ascii=False,allow_nan=False))
    for kind,text in reports.items():
        assert 'https://' not in text and 'http://' not in text and 'www.' not in text
        require_public_data(text);(OUT/(kind+'.txt')).write_text(text)
        assert all(units(part)<=3800 for part in chunks(text))
        if kind=='morning':
            # Public market preview only: never load or publish private inventory.
            blocks=[text[i:i+1700] for i in range(0,len(text),1700)]
            for i,block in enumerate(blocks):
                print('::notice title=Morning public preview::'+json.dumps(dict(preview_part=i+1,preview_parts=len(blocks),text=block),ensure_ascii=False))
    require_public_data(model)
    (OUT/'public-analysis.json').write_text(json.dumps(model,ensure_ascii=False,allow_nan=False))
    audit=dict(releases=fund['event_lifecycle']['releases'],attempts=fund['event_lifecycle']['attempts'],
        protected_unchanged=before==protected_hashes(),telegram_sent=False,private_inventory_loaded=False,
        predictions={s:len(v) for s,v in model.get('experimental_predictions',{}).items()},parts={k:len(chunks(v)) for k,v in reports.items()})
    require_public_data(audit);(OUT/'audit.json').write_text(json.dumps(audit,ensure_ascii=False,allow_nan=False))
    assert audit['protected_unchanged']
    extensions=fund.get('extensions',{})
    summary=dict(flows={symbol:{k:item.get(k) for k in ('date','net_flow_usd','previous_date','previous_net_flow_usd','latest_incomplete_date')} for symbol,item in extensions.get('etf_flows',{}).items()},
        forecasts=[{k:item.get(k) for k in ('title','event_at','forecast','previous','official_schedule')} for item in extensions.get('consensus',[])],
        unlocks=[{k:item.get(k) for k in ('symbol','event_date','amount','event_at','status')} for item in extensions.get('unlocks',[])],
        metrics=[dict(metric=key,value=item['value'],unit=item.get('unit'),period=item.get('period'),previous_value=item.get('previous_value')) for key,item in extensions.get('project_metrics',{}).items()])
    require_public_data(summary)
    (OUT/'extension-audit.json').write_text(json.dumps(summary,ensure_ascii=False,allow_nan=False))
    print('::notice title=Extended fundamentals validated::'+json.dumps(summary,ensure_ascii=False,separators=(',',':')))
    print('::notice title=Production V2 readiness::'+json.dumps(audit,ensure_ascii=False))
    return audit

if __name__=='__main__':run('--reuse' in sys.argv)
