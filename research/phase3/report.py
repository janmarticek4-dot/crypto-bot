"""Build reviewable Slovak report from frozen simulation outputs."""
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd
from data import ROOT

OUT=ROOT/'docs/phase3'
ENTRY={'pullback':'Pullback','breakout':'Breakout + objem','retest':'Retest','momentum':'Momentum'}
EXIT={'fixed':'pevný 20 %','atr':'3 × ATR','trailing':'trailing 20 %','regime':'režim','hybrid':'20 % + režim'}
STATE={-1:'BEAR',0:'NEUTRAL',1:'BULL'}

def f(v,d=2):return 'N/A' if pd.isna(v) else f'{v:.{d}f}'
def table(headers,rows):
    return '\n'.join(['| '+' | '.join(headers)+' |','| '+' | '.join(['---']*len(headers))+' |']+['| '+' | '.join(map(str,r))+' |' for r in rows])+'\n'

def build():
    r=pd.read_csv(OUT/'results.csv');main=r[r.category=='main'];base=r[r.category=='baseline'].set_index('period')
    stability=pd.read_csv(OUT/'strategy_stability.csv');wf=pd.read_csv(OUT/'walk_forward.csv')
    summary=json.loads((OUT/'walk_forward_summary.json').read_text());final=json.loads((OUT/'final_policy.json').read_text())
    quality=pd.read_csv(OUT/'regime_quality.csv');ex=pd.read_csv(OUT/'exit_diagnostics.csv')
    bear=pd.read_csv(OUT/'bear_transitions.csv');manifest=json.loads((OUT/'manifest.json').read_text())
    goals=json.loads((OUT/'goal_windows.json').read_text())
    hours=(pd.to_datetime(wf.test_end)-pd.to_datetime(wf.test_start)).dt.total_seconds()/3600
    wf_exposure=float((wf.mean_exposure_pct*hours).sum()/hours.sum())
    lines=[f'''# V11 – fáza 3: režim trhu a validácia stratégií

**Záver: stabilná výhoda sa nepreukázala. Produkčné BUY/SELL pravidlá ponechať nezmenené.**

Samostatná lokálna vetva `research/v11-phase3`, základ `e4c610d` z fázy 2. Výskum nevolá produkčný bot, Telegram ani obchodné API. Nič sa nepushuje, nezlučuje ani nenasadzuje. Všetky sumy a obchody v tejto správe sú simulácie, nie súkromné portfólio.

Preddefinovaný walk-forward postup skončil od 1. 1. 2022 do 1. 10. 2026 na **{f(summary['return_pct'])} %**, maximálny hodinový drawdown **{f(summary['max_drawdown_pct'])} %**. Kontinuálne držanie s rovnakými počiatočnými slotmi: **{f(summary['hold_continuous']['return_pct'])} %**, drawdown **{f(summary['hold_continuous']['max_drawdown_pct'])} %**. Menšia strata a pokles v tomto konkrétnom intervale nestačia na dôkaz stabilnej výhody: postup vynechal rastové polroky, šesť z desiatich testovacích úsekov vybral CASH a aj tak stratil kapitál.

Priemerná hodinová expozícia walk-forward bola iba **{f(wf_exposure)} %** oproti **{f(summary['hold_continuous']['mean_exposure_pct'])} %** pri kontinuálnom HOLD-sloty. Veľká časť ochrany pochádza z hotovosti. Úplná hotovosť bez úroku by v tomto modeli mala **0 % výnos a 0 % DD** a prekonala by oba postupy; aktívny výber preto nepreukázal ani prínos oproti tejto jednoduchej obrane.

Na poslednom krátkom bloku 1.–20. 10. 2026 vybral rovnaký tréningový selektor **{final['chosen']}**; výsledok **{f(final['metrics']['return_pct'])} %**, drawdown **{f(final['metrics']['max_drawdown_pct'])} %**, oproti držaniu so slotmi **{f(base.loc['2026_short_holdout','return_pct'])} %**. Dvadsať dní nie je dôkaz dlhodobej spoľahlivosti.

![Čistý kapitál a drawdown walk-forward oproti kontinuálnemu držaniu](walk_forward.png)

Graf pokrýva bežný walk-forward do 1. 10. 2026; posledný 20-dňový blok sa hodnotí samostatne. Vektorová verzia: [walk_forward.svg](walk_forward.svg).

## 1. Rozsah a kvalita dát

- Binance spot OHLCV cez CCXT/Freqtrade, UTC, BTC + SOL, TAO, ONDO, RENDER, AAVE, FET. Denné dáta od roku 2020 slúžia aj na rozohriatie indikátorov; výsledky od roku 2021. Načítaný ETH sa archivuje v manifeste, ale do klasifikátora ani signálov nevstupuje.
- Oddelená lokálna kópia `backtesting/user_data/phase3/binance`; pôvodné dáta fázy 2 zostali zachované. Dáta sa necommitujú. Presné SHA-256, počty riadkov a medzery: [manifest.json](manifest.json).
- Posledný testovaný deň je **20. 10. 2026**. Neskoršie stiahnuté sviečky sa nepoužívajú na historické signály ani obchody.
- Roky 2024 až september 2026 boli prezerané už vo fáze 2. **Nie sú novým nezávislým holdoutom.** Roky 2021–2023 sú nová historická kontrola tejto fázy, nie dokonale zaslepený experiment. Posledný októbrový blok je od tréningu časovo oddelený; všetky jeho výsledky sa zverejňujú vrátane neúspešných.
- Parametre, rozsah vstupov/výstupov, náklady a tréningový selektor boli zapísané v [design.json](../../research/phase3/design.json) pred prvým vyhodnotením matice. Po výsledkoch sa nemenili na dosiahnutie +100 %. Následne sa doplnili technické diagnostiky, samostatné vyhodnotenie posledného bloku tým istým selektorom a plne investovaný benchmark; nejde o externú preregistráciu.
- Pevne vybraných šesť dnešných mincí vytvára **survivorship a výberové skreslenie**. Chýbajú vyradené projekty a pôvodná dobová investovateľná množina. Ani staršie obdobie preto nedokazuje univerzálnu výhodu na kryptotrhu.
- Binance ceny nie sú realizácie na eToro; USDT berieme ako USD. Historický spread eToro, hĺbka knihy, dane a zmena kurzu USD/EUR nie sú dostupné. Nákladový model je explicitný odhad so záťažovým testom, nie potvrdenie skutočných realizačných nákladov.

### Dostupnosť požadovaných indikátorov

| Vstup | Stav | Historická reprezentácia |
| --- | --- | --- |
| BTC denný trend, EMA50/200, momentum | Implementované | Uzavreté denné sviečky, sklon EMA50 za 5 dní, momentum 30 dní |
| ADX, volatilita | Implementované | Denný ADX14 a ATR14/BTC close |
| Objem | Implementované čiastočne | BTC volume × close voči minulému 20-dňovému priemeru; objem jednotlivých altcoinov pri vstupe; nejde o celotrhový objem |
| Relatívna sila altcoinov | Implementované čiastočne | Podiel dostupných sledovaných mincí s 30-dňovým výnosom nad BTC; minimálne dve mince |
| Celková kapitalizácia | **N/A v teste** | Historický CoinGecko endpoint v tomto prostredí vrátil HTTP 401; nie je spoľahlivá dobová séria |
| BTC dominancia | **N/A v teste** | Spoľahlivá časovo označená historická séria nie je dostupná; neodvodzuje sa z ceny BTC ani z týchto šiestich mincí |

Voliteľný adaptér `global_history()` prijíma denné CSV s `date`, `available_at`, `total_cap_usd`, `btc_dominance_pct`, `source_url`, `vintage_type=first_release`. Vyžaduje UTC/časové pásmo, uzavretý deň, prvé vydanie, spojitú dennú sériu a rastúce časy publikácie. Prepisované súčasné hodnoty nepovažuje za historické prvé vydania. Adaptér neoveruje pravdivosť deklarácie poskytovateľa; tú treba doložiť pri získaní zdroja. V tomto behu sa žiadny taký súbor nepoužil. **Úplná požadovaná kombinácia vrátane kapitalizácie a dominancie zostáva neoverená.** Ich dostupnosť sa nenahrádza nulou ani hlasom do klasifikácie.

''' ]
    data_rows=[]
    for symbol in ['BTC','SOL','AAVE','FET','TAO','RENDER','ONDO']:
        d=manifest['source_files'][symbol+'_USDT-1d.feather'];h=manifest['source_files'][symbol+'_USDT-1h.feather']
        data_rows.append([symbol,d['first'][:10],h['rows'],h['missing_intervals']])
    lines.append(table(['Minca','Prvý dostupný deň','Hodinové sviečky v archíve','Počet behov chýbajúcich hodín'],data_rows))
    lines.append('''Nezalistované mince nemajú pred prvými dátami cenu, objem ani signál. Denná EMA200 navyše potrebuje 200 uzavretých dní; ONDO preto väčšinu roku 2025 nespĺňa rozohriatie. História RENDER nezačína starým RNDR a nie je s ním dodatočne spojená. Medzera v hodinových dátach nevytvára obchod: chýbajúca realizačná cena čaká na skutočnú sviečku. Ocenenie otvorenej pozície používa poslednú známu cenu a počíta `stale_position_hours`; drawdown v medzere nemusí zachytiť skutočný priebeh. Výstup na hranici okna so zastaranou cenou je zakázaný.

Zdroje: [Binance spot klines](https://developers.binance.com/docs/binance-spot-api-docs/rest-api/market-data-endpoints#klinecandlestick-data), [Freqtrade download-data](https://www.freqtrade.io/en/stable/data-download/), [CoinGecko historická globálna kapitalizácia](https://docs.coingecko.com/reference/global-market-cap-chart).

## 2. Režim trhu a pravidlá

**BULL jadro:** BTC close > EMA200 × 1,02, EMA50 > EMA200 a kladný 5-dňový sklon EMA50. **BEAR jadro:** close < EMA200 × 0,98 a zároveň aspoň jedna z podmienok: EMA50 < EMA200, alebo momentum30 < −10 % spolu s close < EMA50. Bez jadra je NEUTRAL.

Doplňujúce smerové hlasy: znamienko BTC momentum30, ADX ≥20 v smere jadra, relatívny BTC objem ≥1,1 spolu so znamienkom denného výnosu a altcoinová relatívna šírka ≥60 % / ≤40 %. Potrebná je aspoň polovica dostupných hlasov zaokrúhlená nahor. ATR/BTC close >6 % blokuje nové zaradenie BULL, neblokuje BEAR. Ak raz budú doložené globálne série, adaptér pridá znamienko 30-dňového rastu kapitalizácie a 30-dňovú zmenu dominancie ≤−0,5 / ≥+0,5 percentuálneho bodu. Tieto dva hlasy boli v celom tomto teste N/A.

Režim sa zmení až po **troch po sebe idúcich denných potvrdeniach** a minimálne **piatich dňoch od poslednej zmeny**. Denný signál je dostupný až na začiatku nasledujúceho dňa. Stav sa počíta priebežne od rozohriatia, nie nanovo podľa výsledku jednotlivého testovacieho okna.

| Režim | Nové nákupy | Existujúce pozície |
| --- | --- | --- |
| BULL | Všetky štyri potvrdené vstupy; horná hranica novej expozície 70 % | HOLD pri bežnej korekcii; výstup podľa testovaného variantu |
| NEUTRAL | Iba breakout/retest s RVOL ≥1,8, ADX ≥25, nad dennou EMA200 a RSI 50–68; nová expozícia najviac 25 % | Bez núteného zníženia len kvôli NEUTRAL; hotovosť má prednosť pri nových vstupoch |
| BEAR | Žiadne nové nákupy | Režimový a hybridný variant vykoná ochranný výstup; ostatné varianty držia do svojho stopu |

Limity platia pri prijímaní nákupov, nie ako každohodinové rebalansovanie. Rast ceny môže zvýšiť váhu existujúcej pozície nad limit. Nové nákupy berú do úvahy ostatné pozície a zostávajúcu hotovosť. Náklady sa odpočítavajú z hotovosti; páka, short a pôžička nie sú povolené. Expozícia sa oceňuje čistou likvidačnou hodnotou, preto sa nerovná súčtu hrubých debetov.

### Vstupy na uzavretej 4H sviečke

- **Pullback:** low ≤ EMA20, close > EMA20 > EMA50, RSI 40–65, zlepšenie MACD histogramu a close nad dennou EMA200.
- **Breakout + objem:** prvý close nad maximom predchádzajúcich 20 sviečok, RVOL ≥1,5, ADX ≥20, close nad 4H EMA200.
- **Retest:** návrat k už skôr prerazenej 20-sviečkovej rezistencii do 12 sviečok, low do 1 % nad úrovňou, rastová sviečka s close nad úrovňou, RVOL ≥1 a close nad dennou EMA200. Prerazenie a jeho retest nesmú byť tá istá sviečka; close viac než 0,5 ATR pod úrovňou nastavenie ruší.
- **Momentum:** EMA20 > EMA50 > EMA200, RSI 50–68, kladný MACD histogram, RVOL ≥1,2 a vzdialenosť close od EMA20 najviac 2 ATR.

Všetky vstupy potrebujú rozohriatu 4H aj dennú EMA200 a kladný objem. Opätovný nákup vyžaduje nový platný vstup, aktuálny povolený režim a aspoň 24 hodín od výstupu. Samotný návrat ceny hore nákup nevytvára.

### Výstupy

| Variant | Pravidlo |
| --- | --- |
| Pevný | 20 % pod skutočnou stredovou vstupnou cenou |
| ATR | Vstupná cena − 3 × posledný dostupný 4H ATR14; pevný po vstupe |
| Trailing | 20 % pod maximom už uzavretých hodinových high; počiatočný stop tiež 20 % |
| Režim | Odchod pri potvrdenom BEAR, bez cenového stopu; zámerne rizikový kontrolný variant |
| Hybrid | Pevný 20 % stop alebo potvrdený BEAR, podľa toho, čo sa začne vykonávať skôr |

Stop nie je garantovaná realizačná cena ani limit straty celého portfólia. Malé korekcie samy osebe nevytvárajú SELL. Konkrétny 20 % stop, ATR či trailing je experiment na porovnanie, nie nové produkčné odporúčanie.

## 3. Náklady, manuálne vykonanie a metriky

Simulačný kapitál **8500 USD**, maximálny debet jedného nového nákupu **1000 USD**, najviac jedna pozícia na mincu; súbežný spoločný účet. Základný benchmark **HOLD-sloty** má rovnaký maximálny prvý vklad 1000 USD do každej zo šiestich mincí a zvyšok v hotovosti; pri neskoršom zalistovaní použije rezervovaný slot. **HOLD-100 %** investuje celý počiatočný kapitál rovnakým dielom len do mincí s cenou na začiatku okna; ďalšie listingy nepridáva. Oba držia do plánovaného konca a platia rovnaké náklady. HOLD-100 % má vyššiu rizikovú expozíciu; zníženie drawdownu oproti nemu samo osebe nie je dôkaz lepšej selekcie.

- Poplatok 1 % z nákupného plnenia a 1 % z predajného plnenia, zvlášť spread **0,10 % na každú stranu** a sklz **0,10 % na každú stranu**. Celý nákupný debet obsahuje poplatok; pri predaji sa odpočíta z výnosu. Nákup a okamžitý predaj za rovnaký mid stráca približne 2,37 %.
- Základné oneskorenie **1 hodina** od dostupnosti signálu; test 0, 4 a 12 hodín. Nula je idealizovaná referencia. Používa sa skutočný neskorší hodinový open, nikdy cena pred dostupnosťou signálu. Vstup po 24 hodinách expiruje, pri plnení sa režim znovu preveruje.
- Stop z hourly low je známy až po uzavretí hodiny: výstup na open po uzavretí + manuálne oneskorenie. Gap sa zistí na jeho open a čaká na oneskorené vykonanie. Trailing z aktuálneho high sa zvýši až po uzavretí hodiny, platí od ďalšej hodiny; nepredpokladá poradie high/low.
- Výnos je konečný čistý kapitál / počiatočný kapitál −1. **DD** je maximálny hodinový pokles od dovtedajšieho maxima celého účtu vrátane otvorených pozícií, po odhadovaných výstupných nákladoch. Intrahodinový drawdown môže byť väčší.
- Počet obchodov je počet uzavretých pozícií vrátane plánovanej likvidácie na konci okna. **PF** je súčet čistých kladných PnL / absolútny súčet čistých záporných PnL. N/A znamená žiadne stratové obchody alebo žiadne obchody, nie nekonečnú kvalitu stratégie.
- Každé samostatné okno začína novým kapitálom a bez pozícií. Konečná likvidácia je vopred daná hranicou testu; nejde o predpoveď obratu. Ročné výsledky sa nesčítavajú ako jeden účet. Len walk-forward krivka prenáša realizovaný kapitál medzi úsekmi.

## 4. Všetky stratégie: výsledky po obdobiach

Δ HOLD znamená rozdiel výnosu oproti HOLD-sloty v percentuálnych bodoch. Záporná delta znamená horší výsledok. Všetkých 20 kombinácií je zverejnených; žiadna sa neoznačuje za víťaza podľa najlepšieho roka. Kompletné strojové výsledky a náklady: [results.csv](results.csv), [results.json](results.json).
''')
    for period in base.index:
        label='Nová historická kontrola, mimo tréningu budúcich walk-forward úsekov' if period in ('2021','2022','2023') else 'Už prezerané dáta fázy 2' if period!='2026_short_holdout' else 'Časovo oddelený krátky holdout, 1.–20. 10. 2026'
        lines.append(f'### {period}\n\n{label}. Samostatné tabuľkové kombinácie sú opisné; záväzný výber len z minulosti je v časti walk-forward.\n')
        rows=[]
        for category,name in [('baseline','HOLD-sloty'),('baseline_fully_allocated','HOLD-100 %')]:
            x=r[(r.period==period)&(r.category==category)].iloc[0]
            rows.append([name,int(x.trades),f(x.return_pct),f(x.max_drawdown_pct),f(x.profit_factor),f(x.return_pct-base.loc[period,'return_pct'])])
        rows.append(['CASH (bez úroku)',0,'0.00','0.00','N/A',f(-base.loc[period,'return_pct'])])
        for _,x in main[main.period==period].iterrows():rows.append([ENTRY[x.entry]+' / '+EXIT[x.exit],int(x.trades),f(x.return_pct),f(x.max_drawdown_pct),f(x.profit_factor),f(x.return_pct-base.loc[period,'return_pct'])])
        lines.append(table(['Stratégia','Obchody','Čistý výnos %','DD %','PF','Δ HOLD p. b.'],rows))
    lines.append('''### Stabilita medzi rokmi

Šesť úsekov 2021–2025 a január–september 2026 má rozdielnu dĺžku. Mediány nižšie nie sú anualizovaný výnos ani štatistický test; ukazujú, či výhoda pretrváva medzi obdobiami. Posledný krátky holdout sa do tejto sumarizácie nepoužíva.
''')
    lines.append(table(['Stratégia','Lepšia než HOLD /6','Kladný výnos /6','Medián Δ HOLD p. b.','Medián zníženia DD p. b.','Najhorší DD %'],[[ENTRY[x.entry]+' / '+EXIT[x.exit],x.beat_hold_periods,x.positive_periods,f(x.median_hold_alpha_pp),f(x.median_dd_reduction_pp),f(x.max_drawdown_pct)] for _,x in stability.iterrows()]))
    lines.append('''Príznak **nestabilná** platí pre všetkých 20 kombinácií: menia sa výnosy aj relatívne poradie podľa obdobia a krátky holdout nepriniesol potvrdenie. Záporná delta počas silných rastov je cena za nižšiu expozíciu, neskoršie vstupy a výstupy; neznamená automaticky programátorskú chybu. Ani kladný rozdiel v medveďom roku nedokazuje všeobecnú nadvýkonnosť.

## 5. Porovnanie režimov a prínosu indikátorov

Nasledujúce priemery sú **retrospektívna diagnostika**, nikdy vstup do klasifikátora, výberu modelu či obchodov. Dopredné okná sa musia celé zmestiť do daného obdobia. Prekrývajú sa, preto nejde o nezávislé vzorky ani odhad budúceho výnosu. Nie je k dispozícii objektívny označený „pravý režim“; neuvádzame zavádzajúcu percentuálnu presnosť.
''')
    rows=[]
    for _,x in quality[quality.spec.eq('full')].iterrows():rows.append([x.period,STATE[x.regime],x.days,f(x.mean_forward7_pct),f(x.mean_forward30_pct)])
    lines.append(table(['Obdobie','Režim','Dní','BTC ďalších 7 dní priemer %','BTC ďalších 30 dní priemer %'],rows))
    switches=quality[quality.spec.eq('full')].drop_duplicates('period')
    lines.append(table(['Obdobie','Surové prepnutia','Potvrdené prepnutia'],[[x.period,x.raw_switches,x.switches] for _,x in switches.iterrows()]))
    lines.append(f"Hysterézia znížila počet prepnutí z {int(switches.raw_switches.sum())} na {int(switches.switches.sum())}. Nezaručila však predikciu smeru: v roku 2021 mal BULL záporný priemerný nasledujúci 30-dňový výnos BTC, zatiaľ čo BEAR kladný; v poslednom krátkom bloku bol režim celý čas BULL napriek strate portfólia. Model prevažne rozpoznáva už existujúci trend a niekedy zaostáva za obratom.\n")
    lines.append('''### Ablácia: odstránenie jednotlivých vstupov

Zmena oproti plnému dostupnému modelu, vždy rovnaký vstup, hybridný výstup, kapitál a obdobie. 24 párov na variant (4 vstupy × 6 období), nie 24 nezávislých trhov. Kladná Δ výnosu znamená, že **odstránenie** indikátora zlepšilo výnos; kladná Δ DD znamená väčší pokles po odstránení. Global cap/dominance sa abláciou netestujú, pretože boli N/A. Žiadny parameter sa po tejto tabuľke nezavádza do produkcie.
''')
    ab=pd.read_csv(OUT/'ablation_pairs.csv');rows=[]
    for name,g in ab.groupby('spec'):rows.append([name,f(g.delta_return_pp.median()),f(g.delta_return_pp.min()),f(g.delta_return_pp.max()),f(g.delta_drawdown_pp.median()),f'{int(g.delta_return_pp.gt(0).sum())}/{len(g)}'])
    lines.append(table(['Odstránený vstup / model','Medián Δ výnosu p. b.','Min Δ','Max Δ','Medián Δ DD p. b.','Lepší výnos po odstránení'],rows))
    lines.append('''`trend_only` používa len jadro trendu; `no_entry_regime_filter` ruší iba režimové obmedzenie vstupov, hybridný BEAR výstup zostáva. Nesmie sa interpretovať ako stratégia úplne bez trhu. Ak indikátor nezmení výsledky, znamená to nulový realizovaný prínos v tejto konfigurácii, nie dôkaz jeho univerzálnej zbytočnosti. Rozdiely jednotlivých vstupov sú v [ablation_pairs.csv](ablation_pairs.csv).

V tomto experimente majú **momentum a ADX najsľubnejší čiastkový prínos**: ich odstránenie zhoršilo medián čistého výnosu, no účinok nie je rovnaký v každom období. Relatívna sila altcoinov a objem majú medián rozdielu nulový a zmiešané výsledky. Odstránenie volatility zvýšilo výnos v niektorých scenároch a inde ho nezmenilo; súčasný prah preto nemá preukázaný stabilný výnosový prínos. Ani jeden z týchto ex-post výsledkov nie je nezávislým potvrdením optimálnej kombinácie.

### Oneskorená detekcia a prudké pohyby

V [bear_transitions.csv](bear_transitions.csv) je pri každom potvrdenom prechode do BEAR pokles BTC od dovtedy známeho 30-dňového maxima. Ide o zaostávanie oproti minulému vrcholu, nie odhad skutočného začiatku medvedieho trhu. Dodatočný záťažový test posúva **všetky** režimové zmeny o 3 alebo 7 dní; nemá privilégium včasného BEAR výstupu.
''')
    lines.append(f"Počet potvrdených BEAR prechodov v celej rozohriatej histórii: {len(bear)}. Medián už prebehnutého 30-dňového poklesu pri prechode: **{f(bear.past30_peak_drawdown_pct.median())} %**, najhlbší **{f(bear.past30_peak_drawdown_pct.min())} %**. Tieto hodnoty zahŕňajú aj rok 2020 a slúžia iba diagnostike.\n")
    lines.append('''## 6. Diagnostika výstupov a stratových obchodov

Nasledujúce počty združujú všetky štyri vstupy a šesť dlhších období v rámci daného typu výstupu. Rovnaký trhový pohyb sa môže objaviť vo viacerých stratégiách; **súčty PnL naprieč variantmi nie sú výnos jedného portfólia**. Detail každej simulovanej transakcie: [trades.csv.gz](trades.csv.gz), [trade_diagnostics.csv.gz](trade_diagnostics.csv.gz). Príspevky mincí v spoločnej hotovosti: [coin_contributions.csv](coin_contributions.csv); nie sú nezávislé plne investované sólo účty.

„Odraz bez pokrytia nákladov“ znamená rast close po 7 dňoch a zároveň žiadne dostupné hourly low nižšie než nákladová hranica pre zachovanie rovnakého množstva pri predaji a opätovnom nákupe (približne −2,37 % od výstupného mid). Požaduje sa úplných 168 hodín aj dozretý budúci close v tom istom okne. Je to kandidát zbytočného predaja pri krátkej korekcii, **nie dôkaz**, že obchodník mal vopred vedieť, kedy držať či nakúpiť späť.
''')
    rows=[]
    for _,x in ex.iterrows():rows.append([EXIT[x.exit],x.reason,x.trades,x.losing_trades,f(x.mean_net_return_pct),f(x.median_initial_stop_pct),f(x.mean_cost_usd),f'{int(x.rebounded7)}/{int(x.mature7)}',f'{int(x.rebound_without_cost_recovery)}/{int(x.complete7)}'])
    lines.append(table(['Výstup','Dôvod','Obchody','Stratové','Priem. čistý obchod %','Medián pôv. stopu %','Priem. náklady USD','Odraz 7d / dozreté','Odraz bez pokrytia / úplné'],rows))
    lines.append('''Príčiny, ktoré treba rozlišovať:

1. **Úzke ATR stop-lossy v pokojnom trhu.** Ich šírka sa odvodzuje od 4H ATR, zatiaľ čo pozície sa držia celé dni. Náhodná krátka korekcia môže prevýšiť túto šírku. Následný odraz a náklady opakovaných vstupov môžu zhoršiť čistý výsledok. Širší stop však zároveň zvyšuje riziko; jeho automatické rozšírenie z týchto pozorovaní nevyplýva.
2. **Trailing odovzdáva časť zisku a predčasne ukončuje volatilné rastúce pozície.** Vysoký počet ziskových uzavretých obchodov alebo menšia priemerná strata neznamená vyšší výnos portfólia. Rozhodujúce sú tabuľky výnos/DD oproti pevnému a režimovému variantu.
3. **Pevný stop nerešpektuje spoločný trhový režim.** Môže dlhšie držať zhoršujúci sa trend; hybrid sa snaží odísť skôr. Naopak BEAR klasifikácia zaostáva a niekedy odíde po značnej časti poklesu.
4. **Poplatky, spread a sklz.** Každé ukončenie a nový vstup spotrebujú kapitál aj bez nesprávneho smeru. Čistý stratový obchod môže mať kladnú zmenu mid ceny, ak nepokryla náklady. Záverečné plánované uzavretia sú v tabuľke oddelené od skutočných ochranných signálov.
5. **Manuálne čakanie a korelované straty viacerých mincí.** Skutočný neskorší open môže byť horší než stop; 20 % stop na pozícii nie je zárukou 20 % limitu účtu. Tréningové DD ≤20 % nezabránilo testovaciemu DD nad 30 %.

Nie je správne odstrániť stop len preto, že po niektorých predajoch prišiel odraz. Porovnanie režimového variantu bez cenového stopu s hybridom ukazuje kompromis výnosu a otvoreného rizika; ani jeden nemá nezávisle potvrdenú stabilnú výhodu. Predaj má v ďalšom výskume zmysel posudzovať podľa čistého portfóliového výsledku a poklesu oproti HOLD, nie podľa počtu úspešných výstupov.

### Príspevky mincí v roku 2025: hybrid

Toto sú štyri alternatívne simulácie jedného spoločného účtu, nie štyri časti jedného kombinovaného portfólia.
''')
    coins=pd.read_csv(OUT/'coin_contributions.csv');rows=[]
    for _,x in coins[coins.period.eq('2025')&coins.exit.eq('hybrid')].iterrows():rows.append([ENTRY[x.entry],x.symbol,int(x.trades),f(x.pnl_usd),f(x.fees_usd+x.friction_usd),f(x.profit_factor)])
    lines.append(table(['Vstup','Minca','Obchody','Čistý PnL USD','Náklady USD','PF'],rows))
    lines.append('''Nulový príspevok chýbajúcej mince znamená žiadny uzavretý obchod, nie nulovú trhovú výkonnosť. Starú stratu −43,44 % pôvodného TrendComponent rieši [fáza 2](../phase2/REPORT.md); táto fáza testuje iný, oddelený výskumný engine a nesmie jej výsledok spätne premenovať na opravenú produkčnú históriu.

## 7. Walk-forward a posledné nezávislé časové okno

Šesť mesiacov tréningu → nasledujúcich šesť mesiacov testu; posledný bežný úsek júl–september 2026 je skrátený dostupnými dátami. Výber len z 20 vopred uvedených kombinácií: aspoň päť uzavretých tréningových obchodov, čistý výnos >0, tréningové DD ≤20 %, PF ≥1 a aspoň jeden stratový obchod na definovanie PF. Spomedzi spôsobilých maximum **výnos − 0,5 × DD**; deterministické riešenie zhody. Bez spôsobilého kandidáta CASH, nie dodatočné uvoľnenie pravidiel.

Na začiatku každého testovacieho úseku je kapitál z konca predchádzajúceho; veľkosť slotu je stále rovnaký podiel 1000/8500 z tohto počiatočného kapitálu. Na hranici úseku sa pozície plánovane zlikvidujú vrátane nákladov; žiadne predstieranie bezplatného presunu. HOLD pri každom úseku v tabuľke tiež začína nanovo; kontinuálny HOLD v úvodnom porovnaní sa nelikviduje každých šesť mesiacov.
''')
    lines.append(table(['Tréning','Test do (bez)','Vybraný model','Obchody','Čistý výnos %','DD %','PF','HOLD-sloty %'],[[x.train_start+' → '+x.train_end,x.test_start+' → '+x.test_end,x.chosen,int(x.trades),f(x.return_pct),f(x.max_drawdown_pct),f(x.profit_factor),f(x.hold_return_pct)] for _,x in wf.iterrows()]))
    lines.append(f"Celý bežný walk-forward: **{summary['trades']} obchodov**, čistý PF **{f(summary['profit_factor'])}**, poplatky **{f(summary['fees'])} USD**, spread a sklz **{f(summary['spread_slippage'])} USD**. Jednotlivé realizácie z vybraných modelov: [walk_forward_trades.csv](walk_forward_trades.csv).\n")
    lines.append(f'''Časová separácia walk-forward je implementovaná, ale historické výsledky 2024–september 2026 už boli skúmané vo fáze 2. Označenie „out-of-sample“ tu znamená mimo konkrétneho tréningového úseku, **nie úplne nepoznaný trh pri navrhovaní výskumu**. Tréningové skóre nepredpovedalo spoľahlivo budúce poradie. Hotovosť obmedzila straty v medveďom trhu, ale vynechala silný rast v roku 2023 a v časti 2024.

Posledný blok používa rovnaký selektor natrénovaný **1. 4.–30. 9. 2026**, model **{final['chosen']}**, výsledok **{f(final['metrics']['return_pct'])} %**, PF **{f(final['metrics']['profit_factor'])}**, obchodov **{final['metrics']['trades']}**. Tento výsledok nebol použitý na zmenu parametrov. Verejne uvedených všetkých 20 variantov krátkeho bloku neslúži na dodatočný výber víťaza. Skutočná dlhšia budúca validácia od 21. 10. 2026 ešte len musí prebehnúť bez zmien pravidiel.

Detaily: [walk_forward.csv](walk_forward.csv), [walk_forward_training.csv](walk_forward_training.csv), [walk_forward_summary.json](walk_forward_summary.json), [final_policy.json](final_policy.json), [final_holdout_training.csv](final_holdout_training.csv).

### Ambícia +100 % za 3–6 mesiacov

Cieľ nebol optimalizačná podmienka. Na jednej spojitej walk-forward krivke majú kĺzavé denné konce 90/180-dňových okien tieto výsledky; okná sa silno prekrývajú a nie sú pravdepodobnosťou budúceho úspechu.
''')
    lines.append(table(['Okno dní','Prekrývajúce sa okná','Aspoň +100 %','Medián výnosu %','Najhorší výnos %'],[[x['window_days'],x['overlapping_windows'],x['windows_at_least_100_pct'],f(x['median_return_pct']),f(x['worst_return_pct'])] for x in goals]))
    lines.append('''Tento experiment neposkytuje podklad očakávať +100 % za 3–6 mesiacov. Najlepší historický rok alebo obchod nie je očakávaný budúci výnos.

## 8. Robustnosť, náklady a manuálne oneskorenie

Jedna zmena parametra oproti zodpovedajúcemu základnému variantu, bez nového vyberania na holdoute. Parametre režimu, stopu a náklady používajú pullback; ATR2/4 sa porovnávajú s ATR3 a trailing15/25 s trailing20, ostatné s hybridom. Číselný rozsah je naprieč šiestimi dlhšími obdobiami, nie interval spoľahlivosti. Kladná Δ DD je zhoršenie.
''')
    rob=pd.read_csv(OUT/'robustness_pairs.csv');rows=[]
    for name,g in rob[rob.variant.ne('manual_delay')].groupby('variant'):rows.append([name,f(g.delta_return_pp.median()),f(g.delta_return_pp.min()),f(g.delta_return_pp.max()),f(g.delta_drawdown_pp.median())])
    lines.append(table(['Zmena','Medián Δ výnosu p. b.','Min Δ','Max Δ','Medián Δ DD p. b.'],rows))
    lines.append('''`confirm2/5`: počet denných potvrdení; `dwell3/10`: minimálne trvanie stavu; `band0/4`: pásmo EMA200 0/4 %; `vol4/8`: ATR/BTC limit 4/8 %; `regime_lag3/7`: ďalšie oneskorenie všetkých režimov; `raw`: potvrdenie aj dwell po 1 dni. `high_cost`: spread 0,2 % + sklz 0,3 % na stranu; `extreme_cost`: 0,5 % + 0,5 % na stranu. Poplatok 1 % na každú stranu sa zachováva.

### Manuálne vykonanie hybridných výstupov

Každý riadok sumarizuje šesť období; základ je 1 hodina. Aj čakanie ovplyvňuje dostupnosť hotovosti, súbeh mincí a zrušenie vstupu po zmene režimu, nejde iba o mechanické posunutie ceny.
''')
    rows=[]
    for (entry,setting),g in rob[rob.variant.eq('manual_delay')].groupby(['entry','settings']):rows.append([ENTRY[entry],json.loads(setting)['delay'],f(g.delta_return_pp.median()),f(g.delta_return_pp.min()),f(g.delta_return_pp.max()),f(g.delta_drawdown_pp.median())])
    lines.append(table(['Vstup','Oneskorenie h','Medián Δ výnosu p. b.','Min Δ','Max Δ','Medián Δ DD p. b.'],rows))
    lines.append('''Niektoré oneskorenia náhodou zlepšia cenu alebo vynechajú obchod. To nie je návod čakať na konkrétnu hodinu. Výsledky závislé od presného času, prahu či niekoľkých veľkých obchodov sa nepovažujú za robustné. Chýba nezávislá validácia zvoleného oneskorenia aj skutočný záznam manuálneho vykonávania.

## 9. Odporúčanie a ďalší postup

1. **Ponechať produkčné pravidlá nezmenené.** Žiadny z 20 variantov nedokázal stabilnú čistú výhodu naprieč rastom, poklesom, walk-forward a krátkym holdoutom. Nižší drawdown v niektorých úsekoch je užitočný výsledok výskumu, nie oprávnenie nasadiť stratový či nestabilný model.
2. Ďalej testovať **režim ako obmedzenie nových vstupov**, hysteréziu a konzervatívny hybridný ochranný výstup. Porovnávať aj s jednoduchým HOLD so zhodnou rizikovou expozíciou. Žiadny konkrétny vstup tu nezískal právo byť produkčným víťazom.
3. **ATR a trailing nepovažovať za automatické zlepšenie.** Potrebujú ďalšie skúmanie pomeru šírky stopu k volatilite a horizontu držania, nákladov reentry a korelovaných strát. Variant bez cenového stopu zostáva riziková kontrola.
4. Doplniť dôveryhodné historické prvé vydania celkovej kapitalizácie/dominancie a širší dobový univerzum vrátane neúspešných projektov. Až potom zopakovať nezmenený postup na novej časovej vzorke. Súčasný stav sa musí označovať ako čiastočný dostupný režimový model.
5. Od **21. 10. 2026** viesť dopredný paper denník bez reálnych objednávok, s časom signálu, skutočným časom manuálneho rozhodnutia a dostupnou cenou. Nové dáta ponechať mimo výberu parametrov; kritériá prijatia určiť pred ich vyhodnotením. Rozumný ďalší cieľ je dôveryhodný kompromis čistého výnosu a DD, nie vynútenie +100 %.

## 10. Reprodukcia a kontrola

Použiť Python 3.12 a verzie z `manifest.json` vo výskumnom prostredí Freqtrade. Samostatný adresár dát, verejné trhové dáta, žiadne API oprávnenia na obchodovanie ani súkromné portfólio:

```bash
/workspace/.venvs/freqtrade/bin/freqtrade download-data \\
  --config backtesting/config.json --userdir backtesting/user_data \\
  --datadir backtesting/user_data/phase3/binance --timeframes 1h 4h 1d \\
  --pairs SOL/USDT TAO/USDT ONDO/USDT RENDER/USDT AAVE/USDT FET/USDT BTC/USDT ETH/USDT \\
  --timerange 20200101-20261021
/workspace/.venvs/freqtrade/bin/python -m unittest discover -s research/phase3 -p 'test_*.py' -v
/workspace/.venvs/freqtrade/bin/python research/phase3/run.py
/workspace/.venvs/freqtrade/bin/python research/phase3/diagnose.py
/workspace/.venvs/freqtrade/bin/python research/phase3/plot.py
/workspace/.venvs/freqtrade/bin/python research/phase3/report.py
/workspace/.venvs/freqtrade/bin/python research/phase3/verify.py
```

Ak adresár už obsahuje kratšiu históriu, staršiu časť treba doplniť prvým príkazom aj s `--prepend` a potom ho spustiť bez `--prepend` na novšie dni. Neskorší download môže poskytovať revidované dáta; presná reprodukcia vyžaduje zhodné hashované súbory. Verejné OHLCV nie sú nezmeniteľný archív prvých vydaní.

**Rozsah behu:** 508 portfóliových porovnaní vrátane benchmarkov, ablácií a citlivosti; 200 tréningových behov bežného walk-forward, desať testovacích úsekov (šesť CASH), ďalších 20 tréningových behov pred krátkym holdoutom a jeho jeden výber. Počty neznamenajú nezávislé experimenty.

Testy overujú uzavretie a čas dostupnosti sviečok, invarianciu minulosti pri zmene budúcich cien, potvrdenie/dwell, retest bez rovnakobarového lookaheadu, manuálne plnenia a gapy, causal trailing, čakanie na skutočnú cenu, zákazy nákupov, hotovostné limity, benchmark bez budúcich listingov a tréningový selektor. Hashy výstupov a zdrojov sú v `manifest.json`; diagnostika a táto správa majú samostatný `analysis_manifest.json`.

Overenie tejto verzie: **60 existujúcich testov bota + 11 testov fázy 2 + 22 testov fázy 3 = 93 úspešných testov**. Samostatný `verify.py` navyše prepočítal PnL, náklady, skutočné ceny plnení, časovanie, tréningové výbery a hashy všetkých vstupov/výstupov.

Žiadne zmeny `main.py`, `v11/strategy.py`, runtime, workflowov ani produkčného ukladania nevznikli v tejto fáze. Predchádzajúce funkčné úpravy z fázy 2 zostali zachované. Vetva je pripravená na kontrolu; push, zlúčenie a nasadenie vyžadujú osobitné schválenie.
''')
    (OUT/'REPORT.md').write_text('\n'.join(lines))
    names=['REPORT.md','strategy_stability.csv','ablation_pairs.csv','robustness_pairs.csv','trade_diagnostics.csv.gz','exit_diagnostics.csv','coin_contributions.csv','bear_transitions.csv','goal_windows.json','walk_forward.png','walk_forward.svg']
    analysis={'source_manifest_sha256':hashlib.sha256((OUT/'manifest.json').read_bytes()).hexdigest(),
        'code_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(Path(__file__).parent.glob('*.py'))},
        'artifacts_sha256':{name:hashlib.sha256((OUT/name).read_bytes()).hexdigest() for name in names}}
    (OUT/'analysis_manifest.json').write_text(json.dumps(analysis,indent=2)+'\n')
    print('Report generated')

if __name__=='__main__':build()
