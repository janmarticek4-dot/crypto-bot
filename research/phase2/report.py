import hashlib
import io
import json
import zipfile
from pathlib import Path
import pandas as pd
from engine import ROOT,DATA,DESIGN,features

OUT=ROOT/'docs/phase2'


def number(x,d=2):
    return 'N/A' if x is None or pd.isna(x) else f'{x:.{d}f}'


def verify_run(out=OUT):
    manifest=json.loads((out/'manifest.json').read_text())
    if manifest.get('status')!='complete':raise RuntimeError('Research run did not complete')
    code=Path(__file__).with_name('engine.py')
    if hashlib.sha256(code.read_bytes()).hexdigest()!=manifest['code_sha256']:raise RuntimeError('Engine differs from recorded completed run')
    for name,expected in manifest['artifacts_sha256'].items():
        if hashlib.sha256((out/name).read_bytes()).hexdigest()!=expected:raise RuntimeError('Research artifact changed: '+name)
    return manifest


def main():
    verify_run()
    rows=pd.DataFrame(json.loads((OUT/'comparisons.json').read_text()))
    trades=pd.read_csv(OUT/'research_trades.csv.gz')
    for i,r in rows.iterrows():
        selected=trades[(trades.period==r.period)&(trades['mode']==r['mode'])&(trades.strategy==r.strategy)&(trades.scope==r.scope)]
        duration={'train_2024':366,'seen_2025':365,'holdout_2026':273}[r.period]*24
        initial=8500 if r.scope=='portfolio' else 1000
        nominal=sum((pd.Timestamp(t.exit_at)-pd.Timestamp(t.entry_at)).total_seconds()/3600*t.cash_debit for t in selected.itertuples())
        rows.loc[i,'allocated_capital_time_pct']=nominal/initial/duration*100
    rows.to_csv(OUT/'comparisons.csv',index=False)
    rows[(rows['mode']=='etoro')&(rows.scope!='portfolio')].to_csv(OUT/'single_coin_backtests.csv',index=False)
    legacy=pd.read_csv(OUT/'legacy_2025_by_coin.csv')
    lt=pd.read_csv(OUT/'legacy_2025_trades.csv')
    cohorts=[]
    groups={'RSI >= 70':lt['rsi_at_entry']>=70,'rozšírenie nad EMA20 > 2 ATR':lt['extension_atr_at_entry']>2,'RVOL < 1':lt['rvol_at_entry']<1,'vstup pod dennou EMA200':lt['entry_below_daily200']==True,'reentry do 7 dní':lt['reentry_within_7d']==True}
    for label,mask in groups.items():
        sample=lt[mask]
        cohorts.append(dict(condition=label,trades=len(sample),losses=int((sample.profit_abs<0).sum()),net_pnl=float(sample.profit_abs.sum()),average_pnl=float(sample.profit_abs.mean()) if len(sample) else None))
    pd.DataFrame(cohorts).to_csv(OUT/'legacy_entry_cohorts.csv',index=False)
    fee_sensitivity=json.loads((OUT/'legacy_cost_sensitivity.json').read_text())
    lines=['# V11.0 fáza 2 — diagnostika a výsledky', '',
        'Výskum je na samostatnej lokálnej vetve `research/v11-phase2`. Produkčné BUY/SELL pravidlá sa nemenili a nič nebolo nasadené ani pushnuté.', '',
        '## 1. Diagnostika pôvodnej straty −43,44 % (2025)', '',
        'Pôvodný Freqtrade TrendComponent: 44 obchodov, strata $3692,81 na simulačnom účte $8500, profit factor 0,374. Každý nákup mal tag trend; pozitívny 4H MACD a EMA samy nechránili pred pokračujúcim medvedím denným trendom.', '',
        '| Minca | Obchody | Čistý PnL USD | Priemerný zisk USD | Priemerná strata USD | Poplatky + pôvodná nákladová aproximácia USD | PF | Hold po nákladoch |',
        '|---|---:|---:|---:|---:|---:|---:|---:|']
    for r in legacy.to_dict('records'):
        lines.append(f"| {r['pair']} | {r['trades']} | {r['net_pnl_usd']:.2f} | {number(r['avg_win_usd'])} | {number(r['avg_loss_usd'])} | {r['fees_including_proxy_spread_usd']:.2f} | {number(r['profit_factor'])} | {r['hold_return_pct']:.2f}% |")
    stop=lt[lt.exit_reason=='stop_loss'];protect=lt[lt.exit_reason=='protective_breakdown']
    daily=lt[lt.entry_below_daily200==True]
    whips=protect[(protect.post_exit_7d_last_return_pct>0)&((1/(1+protect.post_exit_7d_max_fall_pct/100)*(1-.012)/(1+.012)-1)<.03)]
    lines += ['',f"- {len(stop)} stop-lossov: ${stop.profit_abs.sum():.2f}; tvoria {stop.profit_abs.sum()/lt.profit_abs.sum():.1%} čistej straty. Jednotlivý stop −20 % nezabezpečuje −20 % limit celého portfólia.",
              f"- {len(protect)} ochranných výstupov: ${protect.profit_abs.sum():.2f}. Ich priemerný nasledujúci 7-dňový pohyb ceny bol {protect.post_exit_7d_last_return_pct.mean():+.2f} %; po stop-lossoch {stop.post_exit_7d_last_return_pct.mean():+.2f} %.",
              f"- {len(daily)} vstupov bolo pod uzavretou dennou EMA200; ich súhrnný PnL ${daily.profit_abs.sum():.2f}. Je to ex-post asociácia, nie nezávislý dôkaz nového filtra.",
              f"- {len(whips)} z {len(protect)} ochranných výstupov malo počas nasledujúcich 7 dní návrat ceny nahor bez 3% čistej príležitosti na lacnejší reentry po nákladoch. Tieto prípady sú kandidáti zbytočného predaja, nie automatický dôkaz chyby. Budúce okná slúžia iba diagnostike, nikdy signálom.",
              '- Trhové podmienky boli výrazne klesajúce (všetky sledované mince mali záporný hold výnos), ale poplatky a opakované vstupy stratu ďalej prehlbovali.',
              f"- Priemerné RSI pri vstupe bolo {lt.rsi_at_entry.mean():.1f}, priemerná vzdialenosť od EMA20 {lt.extension_atr_at_entry.mean():.2f} ATR. To zodpovedá neskorým momentum vstupom, nie dôkazu príčinnosti. Prekrývajúce sa neúspešné kohorty sú v legacy_entry_cohorts.csv; ich počty sa nesčítavajú.",
              '- CSV obsahuje pri každom obchode RSI, RVOL, vzdialenosť od EMA20 v ATR, priaznivý/nepriaznivý pohyb počas obchodu a následné 1/3/7/14-dňové okná.',
              '', '### Citlivosť pôvodnej stratégie na náklady', '',
              '| Obdobie | Celková sadzba na stranu | Výnos | Obchody | PF |', '|---|---:|---:|---:|---:|']
    for r in fee_sensitivity:
        lines.append(f"| {r['period']} | {r['fee_per_side']:.1%} | {r['return_pct']:.2f}% | {r['trades']} | {r['profit_factor']:.3f} |")
    lines += ['', '0 % = bez všetkých nákladov; 0,2 % = ponechaná pôvodná spread/slippage aproximácia bez 1% eToro poplatku; 1,2 % = pôvodný model. V roku 2025 rozdiel medzi 0,2 % a 1,2 % predstavuje približne 10,04 percentuálneho bodu. Samotné odstránenie nákladov stratovú stratégiu nezmení na ziskovú.',
              'Per-coin CSV zahŕňa aj modelovaný priebežný DD peňaženky so zložením zaznamenaných fill výnosov. Je to samostatný normalizovaný odhad, nie rozdelenie portfóliového DD. Nové samostatné backtesty s vlastným cash účtom sú v single_coin_backtests.csv.',
              'Súčet priamo účtovaných nákladov je $1023,91. Účinok na konečný výnos nie je presne rovnaký ako tento súčet: poplatky menia aj neskorší dostupný kapitál a veľkosti objednávok.',
              '', '### Ablácia ochranného predaja (Freqtrade, pôvodné vstupy a 20% stop)', '',
              '| Obdobie | Variant | Výnos | DD z uzavretých obchodov | Mark-to-market wallet DD | Obchody |', '|---|---|---:|---:|---:|---:|']
    ablations=[]
    for file in sorted((ROOT/'backtesting/user_data/backtest_results').glob('*.zip')):
        with zipfile.ZipFile(file) as z:
            n=next(n for n in z.namelist() if n.endswith('.json') and not n.endswith('_config.json'))
            raw=json.loads(z.read(n))
            for name,r in raw.get('strategy',{}).items():
                if name not in ('TrendComponent','LegacyNoProtectiveExit') or r['timerange'] not in ('20240101-20250101','20250101-20260101','20260101-20261001'):continue
                if not r['trades'] or abs(r['trades'][0]['fee_open']-.012)>1e-9:continue
                a=dict(strategy=name,period=r['timerange'],return_pct=r['profit_total']*100,trade_dd=r['max_drawdown_account']*100,
                       wallet_dd=r.get('wallet_stats',{}).get('max_drawdown_account',0)*100,trades=r['total_trades'],archive=file.name)
                ablations.append(a)
    for a in sorted(ablations,key=lambda a:(a['period'],a['strategy'])):
        lines.append(f"| {a['period']} | {a['strategy']} | {a['return_pct']:.2f}% | {a['trade_dd']:.2f}% | {a['wallet_dd']:.2f}% | {a['trades']} |")
    (OUT/'legacy_ablation.json').write_text(json.dumps(ablations,indent=2)+'\n')
    lines += ['', 'Odstránenie ochranných predajov v roku 2025 zhoršilo výsledok z −43,44 % na −60,73 %. Nie je dôvod všeobecne vypnúť predaje. Pôvodná stratégia na holdoute 2026 zarobila +19,09 %, ale wallet drawdown bol približne 25,8 %, čím prekračuje štandardný 20% cieľ rizika.',
              'Pozor na metodiku DD: pôvodná tabuľka Freqtrade uvádzala drawdown uzavretých obchodov; skutočný priebežný pokles wallet môže byť vyšší. V novej porovnávacej tabuľke používame likvidačnú mark-to-market hodnotu každé 4 hodiny.',
              '', '## 2. Prečo kombinácia neobchoduje', '',
              'Nie je to chyba pretypovania ani nefunkčný príkaz na vstup. Skóre ≥5, čistý výnos ≥3 % a čisté R:R ≥1,5 používajú ako cieľ predchádzajúce 20-sviečkové maximum, ako stop support mínus 1,5 ATR. Pri silnom momente je cena často pri tejto rezistencii alebo nad ňou; disponibilná odmena je nízka/záporná a stop ďaleko.',
              'Za celé tri obdobia žiadna sviečka so skóre ≥5 súčasne nedosiahla R:R ≥1,5 po nákladoch. Náklady teda nezablokovali iba finálnu exekúciu; zmenili ekonomický filter. Bez eToro poplatku kombinácia v holdoute urobila iba jeden obchod — nedostatočný dôkaz výhody.',
              'Každá uzavretá sviečka od 2024 po koniec holdoutu, všetkých 6 čiastkových podmienok, skóre, warm-up, čistý výnos, R:R a blokery sú v combined_candidates.csv.gz. Súhrn je v combined_gate_counts.csv.',
              'Pravidlá sme neuvoľnili na základe nulového počtu obchodov. Breakout patrí do samostatnej stratégie D; prerazenie nad doterajší cieľ nedáva kladnú odmenu k tomuto istému cieľu. Alternatívne ciele vyžadujú samostatný vopred definovaný experiment.',
              '', '## 3. Porovnanie A–F: spoločný multi-asset simulátor', '',
              'Vstupy pri nasledujúcom 4H open po uzavretom signále, denná informácia až po uzavretí dňa, stop podľa 1H low s nepriaznivým gap fill. Bez páky. Celý účet $8500, najviac $1000 all-in na vstup; samostatný coin test $1000. Zvyšná hotovosť je zahrnutá do výnosu. Poplatok 1 % každá strana + 0,1 % spread a 0,1 % sklz na každej strane; tieto dodatočné náklady sú predpoklad, nie namerané eToro kotácie.',
              'A: hold; B: potvrdený 4H a denný trend, výstup po dvoch uzavretých denných baroch pod EMA200; C: potvrdený pullback v rastovom dennom trende; D: breakout rezistencie s objemom/ADX; E: B s dodatočným ochranným výstupom support+objem+slabý denný trend; F: pôvodný ekonomický kombinovaný filter + net reentry edge ≥3 % a retest po predaji.',
              'Aktívne varianty majú 20% ochranný stop na pozícii; A ho nemá. B–F nevstupujú pri potvrdených dvoch bearish denných uzavretiach. Žiadny variant nepoužíva AI alebo budúce pravdepodobnosti.',
              'Nový simulátor a nové definície B/E nie sú totožné s pôvodným Freqtrade TrendComponent; pôvodný výsledok sa nereinterpretuje ako výsledok nových pravidiel.',
              '', '| Obdobie | Stratégia | Čistý výnos | MTM max DD | Obchody | PF | Poplatky USD | Kapitál × čas |', '|---|---|---:|---:|---:|---:|---:|---:|']
    portfolio=rows[(rows.scope=='portfolio')&(rows['mode']=='etoro')]
    for r in portfolio.itertuples():
        lines.append(f'| {r.period} | {r.strategy} | {r.return_pct:.2f}% | {r.max_drawdown_pct:.2f}% | {r.trades} | {number(r.profit_factor)} | {r.fees:.2f} | {r.allocated_capital_time_pct:.1f}% |')
    lines += ['', 'Kapitál × čas je časovo vážený nominálny all-in debit / počiatočný účet. Nízky drawdown pri takmer nulovej expozícii nie je dôkaz lepšieho investovania. Napríklad C v holdoute nemala obchody; nulový výnos nie je úspešná validácia.',
              'Úplné metriky: comparisons.csv/json (výnos, DD, priemerný zisk/strata, PF, win rate, Sharpe, Sortino, samostatné poplatky a spread/sklz); single_coin_backtests.csv obsahuje nezávislé samostatné peňaženky pre každú mincu. research_trades.csv.gz obsahuje všetky simulované obchody.',
              '', '## 4. Nezávislé dáta a limity', '',
              '- 2024: návrhové obdobie. 2025: diagnostické, už predtým videné dáta, NIE nezávislá validácia. 2026-01-01 až 2026-10-01: nový časový holdout. Parametre sú v design.json, zdrojové dáta a hash kódu v manifest.json; neprebehol parameter search.',
              '- Jediná oprava po prvom behu sprísnila kontrolu chýbajúcich 1H open cien pri investovanej pozícii. Nemení signály ani prahy; úplný beh bol potom zopakovaný. Causality test mení budúce OHLCV a kontroluje nezmenené minulostné výstupy.',
              '- Binance listingy skracujú históriu TAO/RENDER/ONDO a EMA200 potrebuje 200 uzavretých dní. Chýbajúce dáta sa nevymýšľajú a nenahrádzajú nulou. V 2024 nie je ONDO; nové listingy nemusia byť obchodovateľné podľa indikátorov.',
              '- A hold vstupuje pri prvom celom obchodovateľnom 4H open. ONDO začalo počas 4H sviečky, preto je hold 2025 v novom teste −43,30 % oproti starej aproximácii −42,07 %. Rozdiel je spracovanie listingového vstupu, nie zmena cien na zlepšenie stratégie.',
              '- Zdrojové súbory môžu obsahovať dáta po holdoute; všetky testy majú explicitný exkluzívny koniec 2026-10-01. Chronologické indikátory a test prefixovej invariantnosti chránia pred použitím budúcich barov.',
              '- 2023 obsahuje jednu chýbajúcu 1H sviečku počas burzového výpadku. Nie je v obchodovaných obdobiach; chýbajúca exekučná sviečka počas pozície by test zastavila.',
              '- Súčasné fundamentálne RSS sa nepoužívajú v historických signáloch. Bez point-in-time archívu by také použitie vytvorilo únik budúcich informácií.',
              '- Fixný spread/slippage môže podceniť stresové náklady. Nie sú zahrnuté dane, FX konverzia ani prípadné individuálne poplatky účtu. Neexistuje garancia max 20% straty.',
              '- Jediný holdout nestačí na dôkaz štatistickej prevahy. Časové okná a podobné mince nie sú nezávislé náhodné vzorky.',
              '', '## 5. Odporúčanie', '',
              'Žiadna nová stratégia A–F zatiaľ nepreukázala súčasne konzistentnú výhodu v čistom výnose, prijateľný drawdown a dostatok obchodov na nezávislých dátach. Produkčné pravidlá preto zostávajú nezmenené.',
              'D (breakout) možno ďalej skúmať pre nižší drawdown a menej obchodov, ale na holdoute stratila. Pôvodný TrendComponent s ochrannými výstupmi je tiež kandidát na ďalší nezávislý test: pozitívny holdout nevymaže stratu 2025 ani 25,8% wallet DD. C/F nemajú dostatočnú aktivitu na odporúčanie. Pre ďalší krok navrhujeme vopred definovaný walk-forward a stress test nákladov; nie doladenie na už otvorenom holdoute.',
              '', '## 6. Bezpečný stav a fundamenty', '',
              'Implementácia a obmedzenia sú v PRIVATE_STORAGE.md a FUNDAMENTALS.md. Verejný bot_state.json je chránený proti zápisu portfólia; súkromný backend potrebuje používateľom vytvorený private repo, úzko obmedzený token a šifrovací kľúč. Reálne pripojenie nebolo bez týchto údajov možné overiť. Nič sa automaticky nevytvorilo ani nenasadilo.']
    lines += ['', '## Výstupy na kontrolu', '', '- [Podrobné porovnanie stratégií a nákladov](comparisons.csv)', '- [Samostatné backtesty jednotlivých mincí](single_coin_backtests.csv)', '- [Pôvodné obchody 2025 a následný vývoj](legacy_2025_trades.csv)', '- [Všetky kombinované kandidáty a blokery](combined_candidates.csv.gz)', '- [Súhrn blokujúcich podmienok](combined_gate_counts.csv)', '- [Súkromný stav a obnova](PRIVATE_STORAGE.md)', '- [Fundamentálne zdroje a dostupnosť](FUNDAMENTALS.md)', '- [Overenie a obmedzenia](VALIDATION.md)']
    (OUT/'REPORT.md').write_text('\n'.join(lines)+'\n')
    print('Report written:',OUT/'REPORT.md')

if __name__=='__main__':main()
