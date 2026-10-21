"""Ex-post attribution only. Future windows here NEVER feed historical signals."""
import hashlib
import json
import zipfile
from pathlib import Path
import pandas as pd
from engine import ROOT,load,features

OUT=ROOT/'docs/phase2'
ARCHIVES=ROOT/'backtesting/user_data/backtest_results'


def archives():
    rows=[]
    for p in sorted(ARCHIVES.glob('*.zip')):
        with zipfile.ZipFile(p) as z:
            for n in z.namelist():
                if not n.endswith('.json') or n.endswith('_config.json'):continue
                for name,r in json.loads(z.read(n)).get('strategy',{}).items():
                    if name=='TrendComponent' and r['timerange'] in ('20240101-20250101','20250101-20260101') and r.get('timeframe_detail')=='1h':
                        fees=r['trades'][0]['fee_open'] if r['trades'] else None
                        rows.append((p,fees,r))
    return rows


def main():
    runs=archives();selected={}
    for p,fee,r in runs:selected[(r['timerange'],round(fee,3))]=(p,r)
    comparison=[]
    for (period,fee),(p,r) in sorted(selected.items()):
        comparison.append(dict(period=period,fee_per_side=fee,return_pct=r['profit_total']*100,drawdown_pct=r['max_drawdown_account']*100,trades=r['total_trades'],profit_factor=r['profit_factor'],archive=p.name,archive_sha256=hashlib.sha256(p.read_bytes()).hexdigest()))
    p,r=selected[('20250101-20260101',.012)]
    trades=pd.DataFrame(r['trades'])
    rows=[];details=[]
    for pair in ['SOL/USDT','TAO/USDT','ONDO/USDT','RENDER/USDT','AAVE/USDT','FET/USDT']:
        ts=trades[trades['pair']==pair]
        symbol=pair.split('/')[0]
        f=load(symbol,'4h').set_index('date')
        indicators=features(symbol)
        start=pd.Timestamp('2025-01-01',tz='UTC');end=pd.Timestamp('2026-01-01',tz='UTC')
        period=f.loc[(f.index>=start)&(f.index<end)]
        baseline=(period['close'].iloc[-1]/period['open'].iloc[0]*(1-.012)/(1+.012)-1)*100 if len(period) else None
        win=ts.loc[ts['profit_abs']>0,'profit_abs'];loss=ts.loc[ts['profit_abs']<0,'profit_abs']
        fees=float((ts['amount']*ts['open_rate']*ts['fee_open']+ts['amount']*ts['close_rate']*ts['fee_close']).sum())
        # Hypothetical independent $1k wallet compounds the exact recorded fills.
        equity=[1000.]
        prior_sale=None
        for t in ts.sort_values('open_date').to_dict('records'):
            entry=pd.Timestamp(t['open_date']);exit=pd.Timestamp(t['close_date'])
            between=f.loc[(f.index>=entry)&(f.index<exit)]
            base=equity[-1]
            equity.extend((base*(between['close']/t['open_rate']*(1-t['fee_close'])/(1+t['fee_open']))).tolist())
            equity.append(base*(1+t['profit_ratio']))
            detail={k:t.get(k) for k in ('pair','open_date','close_date','open_rate','close_rate','profit_abs','profit_ratio','exit_reason','enter_tag','fee_open','fee_close','amount')}
            detail['reentry_within_7d']=prior_sale is not None and (entry-prior_sale[0]).total_seconds()<7*86400
            detail['reentry_net_edge_pct']=(prior_sale[1]*(1-.012)/(t['open_rate']*(1+.012))-1)*100 if prior_sale else None
            prior_sale=(exit,t['close_rate'])
            observed=indicators.loc[indicators.index<entry]
            if len(observed):
                previous=observed.iloc[-1]
                detail['rsi_at_entry']=float(previous['rsi'])
                detail['entry_below_daily200']=bool(previous['close']<previous['daily200']) if pd.notna(previous['daily200']) else None
                detail['extension_atr_at_entry']=float((previous['close']-previous['ema20'])/previous['atr']) if previous['atr'] else None
                detail['rvol_at_entry']=float(previous['rvol'])
            detail['max_adverse_excursion_pct']=(t['min_rate']/t['open_rate']-1)*100
            detail['max_favorable_excursion_pct']=(t['max_rate']/t['open_rate']-1)*100
            for days in (1,3,7,14):
                future=f.loc[(f.index>=exit)&(f.index<exit+pd.Timedelta(days=days))]
                if len(future)>=days*6:
                    low=future['low'].min();high=future['high'].max();last=future['close'].iloc[-1]
                    detail[f'post_exit_{days}d_max_fall_pct']=(low/t['close_rate']-1)*100
                    detail[f'post_exit_{days}d_max_rise_pct']=(high/t['close_rate']-1)*100
                    detail[f'post_exit_{days}d_last_return_pct']=(last/t['close_rate']-1)*100
                    detail[f'post_exit_{days}d_rebuy_edge_pct']=(t['close_rate']*(1-.012)/(last*(1+.012))-1)*100
            details.append(detail)
        series=pd.Series(equity)
        row=dict(pair=pair,trades=len(ts),net_pnl_usd=float(ts['profit_abs'].sum()),wins=len(win),losses=len(loss),avg_win_usd=float(win.mean()) if len(win) else None,avg_loss_usd=float(loss.mean()) if len(loss) else None,
                 fees_including_proxy_spread_usd=fees,profit_factor=float(win.sum()/-loss.sum()) if len(loss) else None,
                 hold_return_pct=baseline,recorded_fill_compounded_return_pct=(equity[-1]/1000-1)*100,
                 recorded_fill_marked_max_dd_pct=float((1-series/series.cummax()).max()*100),
                 exits=ts['exit_reason'].value_counts().to_dict())
        rows.append(row)
    pd.DataFrame(details).to_csv(OUT/'legacy_2025_trades.csv',index=False)
    (OUT/'legacy_2025_by_coin.json').write_text(json.dumps(rows,indent=2,allow_nan=False)+'\n')
    pd.DataFrame(rows).drop(columns=['exits']).to_csv(OUT/'legacy_2025_by_coin.csv',index=False)
    (OUT/'legacy_cost_sensitivity.json').write_text(json.dumps(comparison,indent=2,allow_nan=False)+'\n')
    print(json.dumps(rows,indent=2))
    print('Cost sensitivity:',json.dumps(comparison,indent=2))

if __name__=='__main__':main()
