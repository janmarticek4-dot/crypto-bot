"""Read actual Freqtrade archives and compare a matched cash/stake hold baseline."""
import io
import json
import math
import zipfile
from pathlib import Path
import pandas as pd

ROOT=Path(__file__).resolve().parent
RESULTS=ROOT/'user_data/backtest_results'
DATA=ROOT/'user_data/data/binance'


def baseline(pairs,start,end):
    start,end=pd.Timestamp(start,tz='UTC'),pd.Timestamp(end,tz='UTC')
    index=pd.date_range(start,end,freq='4h',inclusive='left')
    equity=pd.Series(8500.,index=index)
    entered=[]
    for pair in pairs:
        file=DATA/(pair.replace('/','_')+'-4h.feather')
        df=pd.read_feather(file)
        df=df[(df['date']>=start)&(df['date']<end)].set_index('date')
        if df.empty:continue
        entry_date=df.index[0]
        qty=1000/(1+.012)/df['open'].iloc[0]
        prices=df['close'].reindex(index).ffill()
        active=index>=entry_date
        equity.loc[active]+=qty*prices.loc[active]*(1-.012)-1000
        entered.append(pair)
    dd=1-equity/equity.cummax()
    daily=equity.resample('1D').last().pct_change().dropna()
    sharpe=math.sqrt(365)*daily.mean()/daily.std() if daily.std()>0 else None
    downside=daily[daily<0]
    sortino=math.sqrt(365)*daily.mean()/math.sqrt((downside**2).mean()) if len(downside) else None
    return dict(profit_total=equity.iloc[-1]/8500-1,max_drawdown_account=dd.max(),total_trades=len(entered),sharpe=sharpe,sortino=sortino,pairs=entered)


def build():
    results={}
    for file in sorted(RESULTS.glob('*.zip')):
        with zipfile.ZipFile(file) as archive:
            config_name=next((n for n in archive.namelist() if n.endswith('_config.json')),None)
            if not config_name or abs(json.loads(archive.read(config_name)).get('fee',-1)-.012)>1e-9:continue
            for name in archive.namelist():
                if not name.endswith('.json') or name.endswith('_config.json'):continue
                raw=json.loads(archive.read(name))
                for strat,r in raw.get('strategy',{}).items():
                    if strat not in ('TrendComponent','PullbackComponent','CombinedStrategy'):continue
                    if r.get('timeframe_detail') != '1h':continue
                    if r.get('timerange') not in ('20240101-20250101','20250101-20260101'):continue
                    key=(r['timerange'],strat)
                    results[key]=dict(period=r['timerange'],strategy=strat,archive=file.name,
                        **{k:r.get(k) for k in ('profit_total','max_drawdown_account','total_trades','winrate','profit_factor','sharpe','sortino')},
                        baseline=baseline(r['pairlist'],r['backtest_start'],r['backtest_end']))
    expected={(p,s) for p in ('20240101-20250101','20250101-20260101') for s in ('TrendComponent','PullbackComponent','CombinedStrategy')}
    if set(results)!=expected:raise RuntimeError('Missing required current backtest targets: '+str(expected-set(results)))
    out=ROOT.parent/'docs/BACKTEST_RESULTS.json'
    out.write_text(json.dumps(list(results.values()),indent=2,allow_nan=False)+'\n')
    lines=['# Historické výsledky V11', '', 'Freqtrade 2026.9, spot, bez páky. Obdobie 2024 je vývojové; 2025 je oddelená validácia. Parametre sa po výsledkoch netunili.',
           'Poplatok 1,2 % na každej strane modeluje 1 % eToro + 0,2 % spread/sklz. Je to predpoklad, nie nameraný spread. Skutočné náklady môžu byť vyššie.',
           '4H signály, 1H detail exekúcie, uzavreté 1D informative sviečky. Stoploss -20 % je iba simulovaný stop, nie garancia skutočnej straty.',
           'Hold baseline: rovnaký účet $8 500, $1 000 all-in na dostupný pár, zvyšok cash, vstup na začiatku dostupného obdobia a likvidácia na konci. Nové listingy majú kratšiu históriu; nekryté roky sa nevymýšľajú.',
           '', '| Obdobie | Stratégia | Výnos | Max DD | Obchody | Win rate | PF | Sharpe | Hold výnos | Hold DD |', '|---|---|---:|---:|---:|---:|---:|---:|---:|---:|']
    for (period,strat),r in sorted(results.items()):
        b=r['baseline']
        lines.append(f"| {period} | {strat} | {r['profit_total']:.2%} | {r['max_drawdown_account']:.2%} | {r['total_trades']} | {r['winrate']:.1%} | {r['profit_factor']:.2f} | {r['sharpe']:.2f} | {b['profit_total']:.2%} | {b['max_drawdown_account']:.2%} |")
    lines+=['','Detaily vrátane Sortino, baseline Sharpe a názvov zdrojových archívov sú v BACKTEST_RESULTS.json.',
            'Výsledky týchto výskumných stratégií nie sú validáciou celej produkčnej logiky: portfóliové prahy, overovanie eToro a správy sa nesimulujú. V11_RULES_VALIDATED preto zostáva predvolene false.',
            'HYPE: Binance listing 24.09.2026; pre obdobia 2024/2025 neexistujú sviečky. Nie je zahrnuté do výnosov.',
            'Lookahead-analysis TrendComponent 2024: 10 signálov, no bias detected. Nie je to dôkaz ziskovosti.',
            'Lookahead-analysis CombinedStrategy sa skončila ako FAILED/too few trades (menej než 10); nejde o úspešnú kontrolu úniku budúcnosti. Pravidlá preto neaktivovať.',
            'Zero-trade beh nie je dôkaz predikčnej schopnosti. Backtest nepoužíva AI ani percentuálne pravdepodobnosti.']
    (ROOT.parent/'docs/BACKTEST_RESULTS.md').write_text('\n'.join(lines)+'\n')
    print('\n'.join(lines))

if __name__=='__main__':build()
