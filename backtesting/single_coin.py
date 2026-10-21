"""Research-only Freqtrade single-asset runs. No trade command or API key."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import zipfile
import pandas as pd

ROOT=Path(__file__).resolve().parent
SYMBOLS=('SOL','TAO','FET','ONDO','AAVE','RENDER')
STRATEGIES=('TrendComponent','PullbackComponent','CombinedStrategy')
PERIODS=('20240101-20250101','20250101-20260101')


def metrics(trades):
    wins=[t['profit_abs'] for t in trades if t['profit_abs']>0]
    losses=[t['profit_abs'] for t in trades if t['profit_abs']<0]
    return dict(trades=len(trades),win_rate=len(wins)/len(trades) if trades else None,
        mean_profit_abs=sum(wins)/len(wins) if wins else None,
        mean_loss_abs=sum(losses)/len(losses) if losses else None,
        profit_factor=sum(wins)/-sum(losses) if losses else None)


def hold(symbol,start,end,fee):
    df=pd.read_feather(ROOT/'user_data/data/binance'/f'{symbol}_USDT-4h.feather')
    df=df[(df.date>=pd.Timestamp(start,tz='UTC')) & (df.date<pd.Timestamp(end,tz='UTC'))]
    if df.empty:return None
    # Same $1500 account, $1000 gross stake; buy fee funded from remaining cash.
    entry=float(df.iloc[0]['open']);qty=1000/entry;cash=1500-1000*(1+fee)
    curve=cash+qty*df['close']*(1-fee)
    peak=curve.cummax().clip(lower=1500)
    return dict(net_return=float(curve.iloc[-1]/1500-1),max_drawdown=float((1-curve/peak).max()),
        first_bar=df.iloc[0]['date'].isoformat(),last_bar=df.iloc[-1]['date'].isoformat())


def run(ft):
    config=json.loads((ROOT/'config.json').read_text());fee=config['fee']
    if not config['dry_run'] or config['exchange']['key'] or config['exchange']['secret']:
        raise RuntimeError('Research configuration must have dry_run=true and no trading credentials')
    output=ROOT/'user_data/v111-single';output.mkdir(parents=True,exist_ok=True)
    records=[]
    for period in PERIODS:
        start,end=period.split('-')
        for symbol in SYMBOLS:
            for strategy in STRATEGIES:
                if hold(symbol,start,end,fee) is None:
                    records.append(dict(symbol=symbol,strategy=strategy,period=period,fee_each_side=fee,trades=0,win_rate=None,mean_profit_abs=None,mean_loss_abs=None,profit_factor=None,net_return=None,max_drawdown=None,hold=None,status='NO_DATA'))
                    print(symbol,strategy,period,'NO_DATA',flush=True)
                    continue
                target=output/f'{symbol}-{strategy}-{period}';target.mkdir(exist_ok=True)
                command=[ft,'backtesting','--config',str(ROOT/'config.json'),'--userdir',str(ROOT/'user_data'),
                    '--datadir',str(ROOT/'user_data/data/binance'),'--strategy-path',str(ROOT/'strategies'),
                    '--strategy',strategy,'--pairs',symbol+'/USDT','--timerange',period,'--cache','none',
                    '--timeframe-detail','1h','--export','trades','--export-directory',str(target),
                    '--dry-run-wallet','1500','--stake-amount','1000','--max-open-trades','1']
                with (target/'run.log').open('w') as log:
                    completed=subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,timeout=240)
                if completed.returncode:raise RuntimeError('Freqtrade failed; inspect ignored research logs')
                archive=max(target.glob('*.zip'),key=lambda p:p.stat().st_mtime)
                with zipfile.ZipFile(archive) as z:
                    payload=next(json.loads(z.read(n)) for n in z.namelist() if n.endswith('.json') and not n.endswith('_config.json') and 'strategy' in json.loads(z.read(n)))
                result=payload['strategy'][strategy]
                records.append(dict(symbol=symbol,strategy=strategy,period=period,fee_each_side=fee,
                    **metrics(result['trades']),net_return=result['profit_total'],max_drawdown=result['max_drawdown_account'],
                    hold=hold(symbol,start,end,fee),status='INSUFFICIENT' if len(result['trades'])<10 else 'RESEARCH_ONLY',
                    archive_sha256=hashlib.sha256(archive.read_bytes()).hexdigest()))
                print(symbol,strategy,period,'trades',len(result['trades']),flush=True)
    report=ROOT.parent/'docs/v11.1';report.mkdir(exist_ok=True)
    (report/'single_coin_results.json').write_text(json.dumps(records,indent=2,allow_nan=False)+'\n')
    lines=['# V11.1 single-asset Freqtrade runs','',
        'Research only. 2024 development; 2025 historical holdout already inspected in prior work, not a fresh untouched sample.',
        'Account $1500, gross stake $1000, one position, same config cost per side as hold. USDT spot proxy, not eToro execution.',
        'Config fee 1.2% models 1% fees + 0.2% spread/slippage each side; this is an assumption, not measured costs.',
        'No new strategy activation. Profit factor N/A when no losses; zero trades is insufficient evidence.',
        '', '| Asset | Strategy | Period | Trades | Net return | Max DD | Win rate | Avg win $ | Avg loss $ | PF | Hold return | Hold DD | Status |',
        '|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|']
    def fmt(v,percent=False):return 'N/A' if v is None else (f'{v:.2%}' if percent else f'{v:.2f}')
    for r in records:
        h=r['hold'] or {}
        lines.append('| '+' | '.join([r['symbol'],r['strategy'],r['period'],str(r['trades']),fmt(r['net_return'],True),fmt(r['max_drawdown'],True),fmt(r['win_rate'],True),fmt(r['mean_profit_abs']),fmt(r['mean_loss_abs']),fmt(r['profit_factor']),fmt(h.get('net_return'),True),fmt(h.get('max_drawdown'),True),r['status']])+' |')
    (report/'SINGLE_COIN.md').write_text('\n'.join(lines)+'\n')

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--freqtrade',default=os.getenv('FREQTRADE_BIN','freqtrade'))
    run(parser.parse_args().freqtrade)
