"""Generate synthetic previews offline. Never load portfolio or contact Telegram."""
import os
import sys
from pathlib import Path
from datetime import datetime,timezone
from zoneinfo import ZoneInfo
os.environ['BOT_DATA_MODE']='synthetic'
os.environ['BOT_DISABLE_TELEGRAM']='1'
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from v11.briefing import build,remember
from v11.strategy import costs
from v11.event_ledger import update
from us_context.report import render,session,parse_quote,QUOTES,crypto_snapshot
from unittest.mock import patch


def generate():
    now=datetime(2026,10,21,5,tzinfo=timezone.utc);coins={}
    prices=dict(BTC=84000,SOL=200,TAO=100,ONDO=1,RENDER=5,AAVE=150,FET=1.2)
    for i,(symbol,price) in enumerate(prices.items()):
        frames={}
        for tf,span in [('4h',.04+i*.003),('1d',.10+i*.005)]:
            frames[tf]=dict(support=price*(1-span),resistance=price*(1+span),atr=price*span/3,
                ema20=price*.99,ema50=price*.97,ema100=price*.95,ema200=price*.90,
                rsi14=50+i,adx=21+i,macd_hist=price*.001,relative_volume=1+i*.05)
        coins[symbol]=dict(price=price,change_24h=2-i*.7,frames=frames,raw={},stale=False,
            market_cap=price*(i+1)*1000000,volume_24h=price*100000,price_source='SYNTHETIC',age_seconds=0,
            relative_strength_btc_7d=(i-2)*.01)
    snap=dict(at=now.timestamp(),coins=coins,synthetic=True,global_data=dict(at=now.timestamp(),cap=2.82e12,volume=83e9,dominance=59.6,change=-.15))
    ev={s:dict(action='HOLD' if s in ('SOL','AAVE') else 'WAIT',held=s in ('SOL','AAVE'),reasons=['Syntetický test; výskumné pravidlá neaktivované.'],data_complete=True,score=3,confidence='nízka',
        entry=p,stop=p*.9,tp1=p*1.25,tp2=p*1.4,economics=costs(p,p*1.25,p*.9,.002)) for s,p in prices.items() if s!='BTC'}
    state={};fund=dict(events=[dict(id='fixture',scheduled=True,event_at='2026-10-21T12:30:00+00:00',title='SYNTHETICKÁ UDALOSŤ – nejde o skutočný makrotermín',url='https://example.invalid/test-only',categories=['CPI'])],sources=[])
    state['fundamentals_v11']=fund
    header='# V11.1 synthetic previews\n\nAll prices, events, holdings and times are test fixtures. No real portfolio/state is loaded. No Telegram/network calls. Each asset uses independent fixture prices and boundaries.\n'
    morning='\n'.join(build(snap,ev,{},dict(state='NORMAL',reasons=['Testovacie údaje.']),fund,state,'BRATISLAVA_2026-10-21_07:00',now.astimezone(ZoneInfo('Europe/Bratislava'))))
    remember(state,snap,ev,'BRATISLAVA_2026-10-21_07:00')
    usnow=now.replace(hour=13)
    # USA renderer receives deliberately unavailable source payloads.
    us=dict(market=session(usnow),quotes={s:parse_quote({},s,usnow,session(usnow)) for s in QUOTES},
        crypto=crypto_snapshot([],[],{},usnow),macro=[],sources={})
    usa=render(us,usnow,'BRATISLAVA_2026-10-21_15:00')
    evening_time=now.replace(hour=18);snap['at']=evening_time.timestamp()
    for i,d in enumerate(coins.values()):
        d['price']*=1+(i-3)*.004;d['market_cap']*=1+(i-3)*.004;d['volume_24h']*=1.03
    snap['global_data']['at']=snap['at'];update(state,fund['events'],snap)
    evening='\n'.join(build(snap,ev,{},dict(state='NORMAL',reasons=['Testovacie údaje.']),fund,state,'BRATISLAVA_2026-10-21_20:00',evening_time.astimezone(ZoneInfo('Europe/Bratislava'))))
    target=Path(__file__).resolve().parents[1]/'docs/v11.1/EXAMPLES.md';target.parent.mkdir(exist_ok=True)
    target.write_text(header+'\n'.join('\n## '+label+'\n\n```text\n'+text+'\n```\n' for label,text in [('Morning',morning),('USA',usa),('Evening',evening)]))

if __name__=='__main__':
    with patch('socket.socket.connect',side_effect=RuntimeError('No network in examples')):generate()
