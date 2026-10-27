# Jediný experiment E1: bezpečnejšie ochranné výstupy

**Odporúčanie: alternatívu nenasadzovať.** Výrazne obmedzuje počet výstupov a v prvom polroku2026 zlepšila výnos aj drawdown oproti HOLD, ale v druhom polroku2025 bola horšia v oboch a v júli–októbri2026 zaostala za HOLD vo výnose. Stabilná výhoda po nákladoch nebola preukázaná. Pôvodné produkčné pravidlá nemeníme; ich nemenenie nie je potvrdením ich kvality. HOLD zostáva povinným výskumným referenčným základom, nie novým osobným obchodným pokynom.

## Čo bolo skutočne testované

- Jeden vopred zapísaný experiment E1, nie optimalizátor. Žiadny výber najlepších parametrov podľa výsledku. Celý predpis: `research/exit_experiment/PLAN.md`; implementácia: `research/exit_experiment/experiment.py`.
- V10.6 používa pôvodné nezmenené funkcie `technical_summary`, `compute_structure`, `evaluate_all`, vrátane pôvodného bodovania a hysterézy. **Chýbajú historické globálne kapitalizácie, F&G, pôvodné bot_state snapshoty a overené udalosti.** Výsledok sa preto označuje **V10.6_technical**, nie presný historický produkčný bot. Tieto vstupy sa nedoplňujú nulou ani vymyslenými udalosťami.
- Izolujeme výstupy: všetci začínajú rovnakou plnou pozíciou; oba aktívne modely majú rovnaké opätovné vstupy, nie natívne BUY V10.6. Reentry: dve uzavreté4h sviečky nad EMA20/50, MACD>0 a neporušený support. V10.6 SELL/REDUCE sa nemenia. Toto nie je hodnotenie celej vstupnej stratégie produkcie.
- Alternatíva: cenové oslabenie/EMA/drawdown sa nepočítajú ako nezávislé hlasy. Cenová rodina vyžaduje dve uzavretia pod už známym supportom s0,5% rezervou, cenu pod EMA50/200 a skóre≤3,5. REDUCE potrebuje navyše objemový predajný tlak **alebo** narušenie štruktúry BTC s negatívnym MACD. SELL vyžaduje všetky tri rodiny. BTC nie je štatisticky nezávislý od altcoinov; ide o odlišný vstup, nie tri nezávislé vedecké potvrdenia.
- Starý CRITICAL sa v E1 nepoužíva vôbec. Všetky rodiny sa prepočítavajú z aktuálnych uzavretých sviečok, časová kontinuita súborov sa overuje. Pri bežnej/nepotvrdenej korekcii HOLD.
- Ochranný SELL pred supportom je možný iba cez explicitný overený závažný incident s priamou expozíciou, primárnym HTTPS zdrojom a kauzálnym časom najviac1h. **Historická vetva incidentov nebola otestovaná na udalostiach** — archív chýba. Je unit testovaná, žiadne incidenty sa nevymýšľali. Ochrana pred všetkými náhlymi prepadmi preto nie je preukázaná.
- Dobrovoľný predaj s prísľubom lacnejšieho spätného nákupu je vypnutý: chýba overená predikcia čistej výhody. Spätný nákup po ochrannom výstupe môže byť drahší a táto nevýhoda je vo výsledku aj diagnostike.
- Každé obdobie:6×1 000 USDT modelového kapitálu, rovnaké počiatočné pozície, bez páky, bez presunov medzi mincami, bez priebežného rebalansovania. REDUCE zníži expozíciu na50% raz do ďalšieho plného nákupu; SELL na0%. Zostatky nenesú úrok, žiadny staking. USDT sa berie ako USD proxy, kurzové/depeg riziko ani dane nie sú modelované.
- Signál až po uzavretí4h sviečky; vykonanie na nasledujúcom open. Tento variant je optimistický pre ručné vykonanie, preto sa testuje aj ďalšia4h sviečka oneskorenia. Rozhodovanie nepoužíva budúce high/low; tie sa využívajú až na následné diagnostické hodnotenie.
- Poplatok1% pri každom nákupe aj predaji, navyše nepriaznivá cena0,25% na každej strane (predpoklad polovice spreadu0,20% + sklz0,05%). Citlivosť1,2% a0,50% nepriaznivej ceny. **Nie sú to namerané historické kotácie eToro.** Koncová hodnota všetkých modelov vrátane HOLD je po rovnakých hypotetických likvidačných nákladoch; drawdown zahŕňa počiatočné náklady.
- Histórie existujúcich Binance spot dát cez CCXT/Freqtrade. SHA256, rozsah a počet sviečok v `coverage.json`. Dáta prešli kontrolou OHLC, konečnosti hodnôt, duplicitných a chýbajúcich4h intervalov; ich pôvodné stiahnutie nebolo nezávisle znovu overené.
- ONDO začína11.04.2025; spoločný začiatok po300 sviečkach warmupu je01.06.2025. ONDO2024: **NO_DATA**; RENDER pred listingom tohto tickeru nie je nahradený neoverenou RNDR históriou. Všetky skúmané roky2024–2026 sú už známe. Chronologicky oddelené testy nižšie **nie sú nové nezávislé holdouty ani walk-forward optimalizácia**. Parametre sa medzi oknami nemenili; budúci paper test je potrebný.

## Portfólio: čistý výnos / maximálny drawdown

Základný nákladový a oneskorovací scenár. Každé obdobie je samostatný test s rovnakým počiatočným kapitálom; výsledky sa nesčítavajú. Portfóliový drawdown je zo súčtu súčasných hodnôt šiestich pozícií, nie priemer mincových drawdownov.

| Obdobie | V10.6 technická časť | Alternatíva E1 | HOLD |
|---|---:|---:|---:|
| 01.06.–31.12.2025 (vývoj, už skúmané) | -61.17% / 61.41% | -62.44% / 64.53% | -52.47% / 60.23% |
| 01.01.–30.06.2026 (retrospektívny test) | -35.37% / 50.08% | -4.20% / 34.87% | -18.83% / 47.66% |
| 01.07.–20.10.2026 (retrospektívny test) | -8.39% / 21.32% | +32.59% / 18.96% | +37.49% / 19.54% |

## Jednotlivé mince: čistý výnos / maxDD

### 01.06.–31.12.2025 (vývoj, už skúmané)

| Minca | V10.6 technická časť | E1 | HOLD |
|---|---:|---:|---:|
| AAVE | -46.76% / 53.32% | -55.50% / 64.73% | -42.37% / 60.10% |
| TAO | -75.39% / 75.42% | -67.43% / 67.51% | -50.31% / 60.80% |
| FET | -71.11% / 71.11% | -76.75% / 78.57% | -74.34% / 78.00% |
| SOL | -49.11% / 52.88% | -40.46% / 56.13% | -22.29% / 52.67% |
| ONDO | -65.56% / 68.99% | -67.03% / 69.51% | -57.88% / 68.59% |
| RENDER | -59.11% / 64.08% | -67.47% / 74.46% | -67.62% / 74.30% |
### 01.01.–30.06.2026 (retrospektívny test)

| Minca | V10.6 technická časť | E1 | HOLD |
|---|---:|---:|---:|
| AAVE | -51.26% / 63.56% | -41.11% / 62.47% | -43.11% / 66.44% |
| TAO | +6.52% / 35.23% | +5.09% / 46.32% | -10.03% / 51.07% |
| FET | -18.36% / 41.61% | +9.50% / 40.18% | -15.67% / 54.47% |
| SOL | -50.89% / 58.12% | -25.62% / 38.70% | -42.35% / 58.09% |
| ONDO | -61.82% / 67.21% | +2.84% / 33.94% | -16.26% / 50.94% |
| RENDER | -36.40% / 65.82% | +24.07% / 44.69% | +14.43% / 53.21% |
### 01.07.–20.10.2026 (retrospektívny test)

| Minca | V10.6 technická časť | E1 | HOLD |
|---|---:|---:|---:|
| AAVE | +22.05% / 24.16% | +67.23% / 20.56% | +77.04% / 20.56% |
| TAO | -39.87% / 39.87% | +25.25% / 28.60% | +32.16% / 24.66% |
| FET | -23.51% / 30.27% | -0.34% / 37.32% | +11.54% / 36.45% |
| SOL | +9.20% / 27.18% | +43.73% / 13.86% | +41.05% / 18.76% |
| ONDO | -8.10% / 28.49% | +43.41% / 29.30% | +43.37% / 29.30% |
| RENDER | -10.11% / 23.68% | +16.23% / 20.30% | +19.75% / 23.43% |

## Predaje, zmeškaný rast, návraty a prudké korekcie

| Obdobie | Model | Aktívne transakcie | Plné SELL | REDUCE | Predčasné SELL / zrelé14d | Ziskové spätné vstupy / návraty | Pokles ≥10% do7d po SELL / zrelé7d | Max. zmeškaný rast po SELL |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| development_seen | V10.6_technical | 380 | 96 | 135 | 26/94 | 32/93 | 48/94 | 35.24% |
| development_seen | Alternative | 99 | 17 | 35 | 7/17 | 6/17 | 10/17 | 36.07% |
| development_seen | HOLD | 0 | 0 | 0 | 0/0 | 0/0 | 0/0 | 0.00% |
| test_seen_H1 | V10.6_technical | 355 | 81 | 134 | 35/72 | 19/78 | 23/79 | 14.68% |
| test_seen_H1 | Alternative | 46 | 7 | 19 | 4/7 | 6/7 | 6/7 | 11.63% |
| test_seen_H1 | HOLD | 0 | 0 | 0 | 0/0 | 0/0 | 0/0 | 0.00% |
| test_seen_H2 | V10.6_technical | 183 | 39 | 71 | 14/28 | 4/33 | 4/35 | 13.73% |
| test_seen_H2 | Alternative | 19 | 1 | 9 | 0/0 | 0/0 | 0/1 | 4.45% |
| test_seen_H2 | HOLD | 0 | 0 | 0 | 0/0 | 0/0 | 0/0 | 0.00% |

„Aktívne transakcie“ počítajú každý BUY/REDUCE/SELL po počiatočnom nákupe. `orders` v CSV pridáva aj úvodný nákup a koncovú hypotetickú likvidáciu (2 na mincu); nejde o počet uzavretých obchodných párov. HOLD má0 aktívnych transakcií, ale stále platí vstupné a výstupné náklady.

Predčasný SELL: cena na konci14 dní je nad predajnou referenciou; počítajú sa iba dozreté prípady. Nie je to tvrdenie, že každé také rozhodnutie bolo ex ante chybné. Zmeškaný rast: maximálny high do14 dní alebo do prvého reentry, iba keď pozícia zostala predaná; ide o maximum jedného mincového prípadu, nie portfóliový výnos. Čiastočné REDUCE majú vplyv na čistý výnos, ale nie sú zahrnuté v diagnostike plných SELL.

Ziskový návrat = po nákladoch sa za hotovosť z predaja kúpi viac jednotiek; pri každom SELL sa skúma prvý nasledujúci BUY. Ochranný výstup môže mať zmysel aj bez ziskového návratu, ale nie je to dôkaz lacnejšieho spätného nákupu. Počty „zachytených korekcií“ sú udalosti po výstupoch, môžu sa prekrývať; **nie je to recall všetkých trhových prepadov** ani dokázaná predikcia. Nízky počet SELL v E1 najmä v júli–októbri2026 znamená slabú štatistickú oporu;0/0 nie je100% úspešnosť.

## Citlivosť nákladov a ručného oneskorenia

| Obdobie | Poplatok/strana | Spread+sklz/strana | Extra oneskorenie | V10.6 čistý výnos | E1 čistý výnos | HOLD čistý výnos |
|---|---:|---:|---:|---:|---:|---:|
| development_seen | 1% | 0.25% | 4h | -61.06% | -63.14% | -52.47% |
| development_seen | 1.2% | 0.25% | 0h | -64.24% | -63.38% | -52.66% |
| development_seen | 1.2% | 0.5% | 0h | -67.73% | -64.51% | -52.89% |
| development_seen | 1.2% | 0.5% | 4h | -67.67% | -65.17% | -52.89% |
| test_seen_H1 | 1% | 0.25% | 4h | -37.58% | -4.93% | -18.83% |
| test_seen_H1 | 1.2% | 0.25% | 0h | -39.90% | -5.39% | -19.16% |
| test_seen_H1 | 1.2% | 0.5% | 0h | -45.11% | -6.86% | -19.56% |
| test_seen_H1 | 1.2% | 0.5% | 4h | -47.07% | -7.57% | -19.56% |
| test_seen_H2 | 1% | 0.25% | 4h | -7.53% | +32.07% | +37.49% |
| test_seen_H2 | 1.2% | 0.25% | 0h | -11.75% | +31.72% | +36.94% |
| test_seen_H2 | 1.2% | 0.5% | 0h | -15.77% | +30.64% | +36.25% |
| test_seen_H2 | 1.2% | 0.5% | 4h | -15.00% | +30.14% | +36.25% |

Všetkých378 riadkov (3 obdobia ×3 modely ×3 náklady ×2 oneskorenia ×7 agregácií) vrátane drawdownov a individuálnych diagnostík je v `results.csv`/`results.json`. Všetky aktívne transakcie základného scenára sú v `orders.json` s časom dostupnosti signálu a vykonania. Nie sú to skutočné obchody.

## Interpretácia a rozhodnutie

- E1 odstránila veľkú časť zbytočného obratu oproti bodovej V10.6 technickej časti. **Menej predajov neznamená spoľahlivejšiu stratégiu**: v druhom polroku2025 mala horší výnos aj drawdown než HOLD. V tejto fáze je odmietnutá ako pripravená produkčná náhrada.
- Prvý polrok2026 je povzbudivý: nižšia strata a nižší drawdown než oba základy, pri malom počte plných SELL. Sám o sebe nestačí. Od júla2026 E1 obmedzila drawdown iba mierne, ale obetovala časť rastu oproti HOLD.
- V10.6 technická časť bola v tomto výstupnom experimente slabšia než HOLD vo všetkých troch portfóliových oknách. **Nie je to presné hodnotenie kompletnej produkcie** kvôli chýbajúcim makro/stavovým vstupom a spoločnému reentry. Napriek tomu je to dôvod nepovažovať pôvodné SELL automaticky za ekonomicky výhodné.
- Neodporúčam nasadiť E1 ani optimalizovať ďalší variant na tieto výsledky. Ponechať produkciu nezmenenú podľa zadania, výskumný baseline zachovať a pred budúcim schválením požadovať nové paper pozorovania s overenými udalosťami a meranými spreadmi. Ani HOLD nie je ochranou pred veľkými prepadmi; v týchto dátach dosiahol portfóliový drawdown až60,23%.

## Testy, reprodukcia a technická kontrola

112 offline testov prešlo so zablokovaným nemockovaným sieťovým prístupom. Zahŕňajú nerozlišovanie korelovaných indikátorov ako nezávislých hlasov, HOLD pri samotnom oslabení, REDUCE/SELL podľa rodín, overený incident pred supportom, odmietnutie budúcej/starej udalosti, ignorovanie starého CRITICAL, kauzálne vykonanie, náklady pri plochej cene, jednorazové REDUCE, portfóliový drawdown a zachovanie skorších transakcií pri zmene budúcich cien. Prefix testy a časová konvencia sú kauzálne kontroly; nejde o natívny Freqtrade lookahead-analysis ani o dôkaz neprítomnosti každej chyby.

Po prvom výpočte kontrola odhalila opakované drobné REDUCE pri cenovom driftovaní váhy, čo odporovalo plánu bez rebalansovania. Opravená bola iba vykonávacia západka „raz do ďalšieho nákupu“, nie signál ani prahy. Prvý beh bol vyradený; jeho SHA256, portfóliové výsledky a dôvod sú v `IMPLEMENTATION_CHECK.json`. Nebol vybraný výnosnejší variant. Všetky tabuľky vyššie pochádzajú z opraveného prepočtu.

```bash
/workspace/.venvs/crypto-bot/bin/python research/exit_experiment/experiment.py \
  --data /workspace/crypto-bot/backtesting/user_data/data/binance \
  --out docs/integration/exit-experiment
/workspace/.venvs/crypto-bot/bin/python scripts/test_integration_offline.py
```

Experiment vyžaduje pandas a pyarrow iba na načítanie existujúcich Feather súborov; produkčné requirements sa nemenia. Lokálne historické dátové súbory sa nekopírovali do verejnej vetvy. Pri chýbajúcom súbore/warmupe končí `NO_DATA`, pri neplatnej histórii chybu neskrýva.

Žiadna zmena main.py, bot_state.json, produkčného workflow, Telegramu, súkromného portfólia, Secrets ani produkčných BUY/SELL. Všetok výskum je izolovaný a bez sieťových/burzových obchodných príkazov.
