# V11.0 fáza 2 — diagnostika a výsledky

Výskum je na samostatnej lokálnej vetve `research/v11-phase2`. Produkčné BUY/SELL pravidlá sa nemenili a nič nebolo nasadené ani pushnuté.

## 1. Diagnostika pôvodnej straty −43,44 % (2025)

Pôvodný Freqtrade TrendComponent: 44 obchodov, strata $3692,81 na simulačnom účte $8500, profit factor 0,374. Každý nákup mal tag trend; pozitívny 4H MACD a EMA samy nechránili pred pokračujúcim medvedím denným trendom.

| Minca | Obchody | Čistý PnL USD | Priemerný zisk USD | Priemerná strata USD | Poplatky + pôvodná nákladová aproximácia USD | PF | Hold po nákladoch |
|---|---:|---:|---:|---:|---:|---:|---:|
| SOL/USDT | 7 | -181.14 | 214.70 | -122.11 | 167.83 | 0.70 | -35.72% |
| TAO/USDT | 10 | -921.36 | 216.66 | -169.33 | 231.72 | 0.32 | -51.47% |
| ONDO/USDT | 5 | -485.41 | 158.89 | -161.08 | 115.56 | 0.25 | -50.31% |
| RENDER/USDT | 7 | -793.85 | 84.33 | -192.50 | 160.39 | 0.18 | -81.50% |
| AAVE/USDT | 7 | -357.04 | 650.43 | -167.91 | 165.67 | 0.65 | -53.84% |
| FET/USDT | 8 | -954.00 | 369.66 | -189.09 | 182.74 | 0.28 | -84.76% |

- 16 stop-lossov: $-3543.08; tvoria 95.9% čistej straty. Jednotlivý stop −20 % nezabezpečuje −20 % limit celého portfólia.
- 28 ochranných výstupov: $-149.73. Ich priemerný nasledujúci 7-dňový pohyb ceny bol -8.13 %; po stop-lossoch +2.25 %.
- 23 vstupov bolo pod uzavretou dennou EMA200; ich súhrnný PnL $-741.02. Je to ex-post asociácia, nie nezávislý dôkaz nového filtra.
- 5 z 28 ochranných výstupov malo počas nasledujúcich 7 dní návrat ceny nahor bez 3% čistej príležitosti na lacnejší reentry po nákladoch. Tieto prípady sú kandidáti zbytočného predaja, nie automatický dôkaz chyby. Budúce okná slúžia iba diagnostike, nikdy signálom.
- Trhové podmienky boli výrazne klesajúce (všetky sledované mince mali záporný hold výnos), ale poplatky a opakované vstupy stratu ďalej prehlbovali.
- Priemerné RSI pri vstupe bolo 69.5, priemerná vzdialenosť od EMA20 2.38 ATR. To zodpovedá neskorým momentum vstupom, nie dôkazu príčinnosti. Prekrývajúce sa neúspešné kohorty sú v legacy_entry_cohorts.csv; ich počty sa nesčítavajú.
- CSV obsahuje pri každom obchode RSI, RVOL, vzdialenosť od EMA20 v ATR, priaznivý/nepriaznivý pohyb počas obchodu a následné 1/3/7/14-dňové okná.

### Citlivosť pôvodnej stratégie na náklady

| Obdobie | Celková sadzba na stranu | Výnos | Obchody | PF |
|---|---:|---:|---:|---:|
| 20240101-20250101 | 0.0% | 25.30% | 35 | 1.547 |
| 20240101-20250101 | 0.2% | 23.61% | 35 | 1.499 |
| 20240101-20250101 | 1.2% | 15.12% | 35 | 1.288 |
| 20250101-20260101 | 0.0% | -31.40% | 44 | 0.479 |
| 20250101-20260101 | 0.2% | -33.41% | 44 | 0.460 |
| 20250101-20260101 | 1.2% | -43.44% | 44 | 0.374 |

0 % = bez všetkých nákladov; 0,2 % = ponechaná pôvodná spread/slippage aproximácia bez 1% eToro poplatku; 1,2 % = pôvodný model. V roku 2025 rozdiel medzi 0,2 % a 1,2 % predstavuje približne 10,04 percentuálneho bodu. Samotné odstránenie nákladov stratovú stratégiu nezmení na ziskovú.
Per-coin CSV zahŕňa aj modelovaný priebežný DD peňaženky so zložením zaznamenaných fill výnosov. Je to samostatný normalizovaný odhad, nie rozdelenie portfóliového DD. Nové samostatné backtesty s vlastným cash účtom sú v single_coin_backtests.csv.
Súčet priamo účtovaných nákladov je $1023,91. Účinok na konečný výnos nie je presne rovnaký ako tento súčet: poplatky menia aj neskorší dostupný kapitál a veľkosti objednávok.

### Ablácia ochranného predaja (Freqtrade, pôvodné vstupy a 20% stop)

| Obdobie | Variant | Výnos | DD z uzavretých obchodov | Mark-to-market wallet DD | Obchody |
|---|---|---:|---:|---:|---:|
| 20240101-20250101 | LegacyNoProtectiveExit | 30.09% | 31.27% | 50.14% | 17 |
| 20240101-20250101 | TrendComponent | 15.12% | 21.36% | 40.71% | 35 |
| 20250101-20260101 | LegacyNoProtectiveExit | -60.73% | 60.73% | 63.34% | 24 |
| 20250101-20260101 | TrendComponent | -43.44% | 43.44% | 50.39% | 44 |
| 20260101-20261001 | LegacyNoProtectiveExit | 11.80% | 26.05% | 33.49% | 15 |
| 20260101-20261001 | TrendComponent | 19.09% | 14.51% | 25.80% | 31 |

Odstránenie ochranných predajov v roku 2025 zhoršilo výsledok z −43,44 % na −60,73 %. Nie je dôvod všeobecne vypnúť predaje. Pôvodná stratégia na holdoute 2026 zarobila +19,09 %, ale wallet drawdown bol približne 25,8 %, čím prekračuje štandardný 20% cieľ rizika.
Pozor na metodiku DD: pôvodná tabuľka Freqtrade uvádzala drawdown uzavretých obchodov; skutočný priebežný pokles wallet môže byť vyšší. V novej porovnávacej tabuľke používame likvidačnú mark-to-market hodnotu každé 4 hodiny.

## 2. Prečo kombinácia neobchoduje

Nie je to chyba pretypovania ani nefunkčný príkaz na vstup. Skóre ≥5, čistý výnos ≥3 % a čisté R:R ≥1,5 používajú ako cieľ predchádzajúce 20-sviečkové maximum, ako stop support mínus 1,5 ATR. Pri silnom momente je cena často pri tejto rezistencii alebo nad ňou; disponibilná odmena je nízka/záporná a stop ďaleko.
Za celé tri obdobia žiadna sviečka so skóre ≥5 súčasne nedosiahla R:R ≥1,5 po nákladoch. Náklady teda nezablokovali iba finálnu exekúciu; zmenili ekonomický filter. Bez eToro poplatku kombinácia v holdoute urobila iba jeden obchod — nedostatočný dôkaz výhody.
Každá uzavretá sviečka od 2024 po koniec holdoutu, všetkých 6 čiastkových podmienok, skóre, warm-up, čistý výnos, R:R a blokery sú v combined_candidates.csv.gz. Súhrn je v combined_gate_counts.csv.
Pravidlá sme neuvoľnili na základe nulového počtu obchodov. Breakout patrí do samostatnej stratégie D; prerazenie nad doterajší cieľ nedáva kladnú odmenu k tomuto istému cieľu. Alternatívne ciele vyžadujú samostatný vopred definovaný experiment.

## 3. Porovnanie A–F: spoločný multi-asset simulátor

Vstupy pri nasledujúcom 4H open po uzavretom signále, denná informácia až po uzavretí dňa, stop podľa 1H low s nepriaznivým gap fill. Bez páky. Celý účet $8500, najviac $1000 all-in na vstup; samostatný coin test $1000. Zvyšná hotovosť je zahrnutá do výnosu. Poplatok 1 % každá strana + 0,1 % spread a 0,1 % sklz na každej strane; tieto dodatočné náklady sú predpoklad, nie namerané eToro kotácie.
A: hold; B: potvrdený 4H a denný trend, výstup po dvoch uzavretých denných baroch pod EMA200; C: potvrdený pullback v rastovom dennom trende; D: breakout rezistencie s objemom/ADX; E: B s dodatočným ochranným výstupom support+objem+slabý denný trend; F: pôvodný ekonomický kombinovaný filter + net reentry edge ≥3 % a retest po predaji.
Aktívne varianty majú 20% ochranný stop na pozícii; A ho nemá. B–F nevstupujú pri potvrdených dvoch bearish denných uzavretiach. Žiadny variant nepoužíva AI alebo budúce pravdepodobnosti.
Nový simulátor a nové definície B/E nie sú totožné s pôvodným Freqtrade TrendComponent; pôvodný výsledok sa nereinterpretuje ako výsledok nových pravidiel.

| Obdobie | Stratégia | Čistý výnos | MTM max DD | Obchody | PF | Poplatky USD | Kapitál × čas |
|---|---|---:|---:|---:|---:|---:|---:|
| train_2024 | A_hold | 39.52% | 45.38% | 5 | 44.17 | 133.95 | 48.9% |
| train_2024 | B_trend | 7.74% | 41.14% | 30 | 1.20 | 606.71 | 25.9% |
| train_2024 | C_pullback | 5.15% | 16.50% | 9 | 1.34 | 184.44 | 14.9% |
| train_2024 | D_breakout | 20.92% | 36.39% | 18 | 1.80 | 377.99 | 23.6% |
| train_2024 | E_protective | 4.07% | 37.78% | 38 | 1.09 | 763.57 | 23.9% |
| train_2024 | F_combined_reentry | 0.00% | 0.00% | 0 | N/A | 0.00 | 0.0% |
| seen_2025 | A_hold | -43.30% | 49.77% | 6 | 0.00 | 82.83 | 67.3% |
| seen_2025 | B_trend | -47.91% | 48.94% | 59 | 0.01 | 1138.98 | 15.9% |
| seen_2025 | C_pullback | -12.25% | 14.57% | 6 | 0.00 | 109.49 | 5.5% |
| seen_2025 | D_breakout | -28.91% | 29.19% | 23 | 0.01 | 435.23 | 12.8% |
| seen_2025 | E_protective | -37.93% | 39.13% | 62 | 0.13 | 1207.56 | 14.0% |
| seen_2025 | F_combined_reentry | 0.00% | 0.00% | 0 | N/A | 0.00 | 0.0% |
| holdout_2026 | A_hold | 14.89% | 36.53% | 6 | 17.93 | 132.80 | 70.6% |
| holdout_2026 | B_trend | -18.32% | 32.58% | 54 | 0.45 | 1051.06 | 10.4% |
| holdout_2026 | C_pullback | 0.00% | 0.00% | 0 | N/A | 0.00 | 0.0% |
| holdout_2026 | D_breakout | -7.13% | 19.27% | 26 | 0.60 | 513.93 | 7.6% |
| holdout_2026 | E_protective | -18.43% | 32.68% | 54 | 0.45 | 1050.62 | 10.3% |
| holdout_2026 | F_combined_reentry | 0.00% | 0.00% | 0 | N/A | 0.00 | 0.0% |

Kapitál × čas je časovo vážený nominálny all-in debit / počiatočný účet. Nízky drawdown pri takmer nulovej expozícii nie je dôkaz lepšieho investovania. Napríklad C v holdoute nemala obchody; nulový výnos nie je úspešná validácia.
Úplné metriky: comparisons.csv/json (výnos, DD, priemerný zisk/strata, PF, win rate, Sharpe, Sortino, samostatné poplatky a spread/sklz); single_coin_backtests.csv obsahuje nezávislé samostatné peňaženky pre každú mincu. research_trades.csv.gz obsahuje všetky simulované obchody.

## 4. Nezávislé dáta a limity

- 2024: návrhové obdobie. 2025: diagnostické, už predtým videné dáta, NIE nezávislá validácia. 2026-01-01 až 2026-10-01: nový časový holdout. Parametre sú v design.json, zdrojové dáta a hash kódu v manifest.json; neprebehol parameter search.
- Jediná oprava po prvom behu sprísnila kontrolu chýbajúcich 1H open cien pri investovanej pozícii. Nemení signály ani prahy; úplný beh bol potom zopakovaný. Causality test mení budúce OHLCV a kontroluje nezmenené minulostné výstupy.
- Binance listingy skracujú históriu TAO/RENDER/ONDO a EMA200 potrebuje 200 uzavretých dní. Chýbajúce dáta sa nevymýšľajú a nenahrádzajú nulou. V 2024 nie je ONDO; nové listingy nemusia byť obchodovateľné podľa indikátorov.
- A hold vstupuje pri prvom celom obchodovateľnom 4H open. ONDO začalo počas 4H sviečky, preto je hold 2025 v novom teste −43,30 % oproti starej aproximácii −42,07 %. Rozdiel je spracovanie listingového vstupu, nie zmena cien na zlepšenie stratégie.
- Zdrojové súbory môžu obsahovať dáta po holdoute; všetky testy majú explicitný exkluzívny koniec 2026-10-01. Chronologické indikátory a test prefixovej invariantnosti chránia pred použitím budúcich barov.
- 2023 obsahuje jednu chýbajúcu 1H sviečku počas burzového výpadku. Nie je v obchodovaných obdobiach; chýbajúca exekučná sviečka počas pozície by test zastavila.
- Súčasné fundamentálne RSS sa nepoužívajú v historických signáloch. Bez point-in-time archívu by také použitie vytvorilo únik budúcich informácií.
- Fixný spread/slippage môže podceniť stresové náklady. Nie sú zahrnuté dane, FX konverzia ani prípadné individuálne poplatky účtu. Neexistuje garancia max 20% straty.
- Jediný holdout nestačí na dôkaz štatistickej prevahy. Časové okná a podobné mince nie sú nezávislé náhodné vzorky.

## 5. Odporúčanie

Žiadna nová stratégia A–F zatiaľ nepreukázala súčasne konzistentnú výhodu v čistom výnose, prijateľný drawdown a dostatok obchodov na nezávislých dátach. Produkčné pravidlá preto zostávajú nezmenené.
D (breakout) možno ďalej skúmať pre nižší drawdown a menej obchodov, ale na holdoute stratila. Pôvodný TrendComponent s ochrannými výstupmi je tiež kandidát na ďalší nezávislý test: pozitívny holdout nevymaže stratu 2025 ani 25,8% wallet DD. C/F nemajú dostatočnú aktivitu na odporúčanie. Pre ďalší krok navrhujeme vopred definovaný walk-forward a stress test nákladov; nie doladenie na už otvorenom holdoute.

## 6. Bezpečný stav a fundamenty

Implementácia a obmedzenia sú v PRIVATE_STORAGE.md a FUNDAMENTALS.md. Verejný bot_state.json je chránený proti zápisu portfólia; súkromný backend potrebuje používateľom vytvorený private repo, úzko obmedzený token a šifrovací kľúč. Reálne pripojenie nebolo bez týchto údajov možné overiť. Nič sa automaticky nevytvorilo ani nenasadilo.

## Výstupy na kontrolu

- [Podrobné porovnanie stratégií a nákladov](comparisons.csv)
- [Samostatné backtesty jednotlivých mincí](single_coin_backtests.csv)
- [Pôvodné obchody 2025 a následný vývoj](legacy_2025_trades.csv)
- [Všetky kombinované kandidáty a blokery](combined_candidates.csv.gz)
- [Súhrn blokujúcich podmienok](combined_gate_counts.csv)
- [Súkromný stav a obnova](PRIVATE_STORAGE.md)
- [Fundamentálne zdroje a dostupnosť](FUNDAMENTALS.md)
- [Overenie a obmedzenia](VALIDATION.md)
