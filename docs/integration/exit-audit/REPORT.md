# Audit SELL/REDUCE V10.6 — bez zmeny pravidiel

## Záver

Podozrenie je potvrdené: SELL nie je v implementácii podmienený prelomením supportu, predajným objemom, nezávisle potvrdenou udalosťou ani očakávaným čistým prínosom po nákladoch. Znamená dosiahnutie bodového prahu, nie potvrdenie pokračovania výrazného prepadu. Označenie `status="potvrdený"` sa nastavuje pred vyhodnotením a pri SELL zostáva; nejde o historicky kalibrovanú istotu. V tomto zbere sa technicky potvrdzuje oslabenie, nie budúci smer. Všetkých šesť výstupov je preventívna/heuristická ochrana, nie potvrdenie ďalšieho >10 % prepadu.

## Rozsah a pôvod dôkazov

- Audit kódu vychádza z integračnej vetvy na `9d8b540`; `main.py` je nezmenený chránený V10.6 baseline. Nejde o zmenu produkcie.
- Dáta: používateľom dodaný Artifact `v111-integration-40504368871-1.zip`, zber **27.10.2026 13:31:48 Bratislava**. Nie ranná správa o 07:40 ani nový živý zber. Presný vstupný stav ranného behu nebol dodaný; jeho individuálne príčiny nemožno predstierať.
- Trhové ceny Binance, kapitalizácie/objemy z verejného zberača; zodpovedajú zberu, nie času čítania tejto správy. Metadáta 13:30:50 Bratislava; posledná uzavretá 4h sviečka končí 13:00 Bratislava (12:00 UTC). EMA/RSI/MACD sú historické výpočty nad vtedy dostupnými uzavretými sviečkami, nie nové živé hodnoty.
- Reprodukcia používa lokálny verejný `bot_state.json` z baseline, nie pôvodný stav runnera. Hodiny sú zmrazené na čas zberu, aby TTL/maximum nezáviseli od času auditu. Stav sa spracúva iba v kópii; pôvodný súbor sa nemení.
- Zaznamenané pôvodné body a signály runnera sa zhodujú s reprodukciou. Originál však neobsahuje kompletnú kópiu vstupného stavu; zhoda výstupov nedokazuje identický stav. Ablácie nižšie sa vzťahujú na reprodukovaný verejný baseline.
- `EVIDENCE.json` obsahuje presné číselné hodnoty, rozklady skóre, časy, kontrolné súčty archívu/stavu a výsledky ablácií. Zaokrúhlenie v tabuľkách nemení rozhodovanie.

## Presné rozhodovacie pravidlá

`main.py:1424` (`decide_coin`): po odmietnutí chýbajúcej ceny/skóre spočíta body. Vetvenie v `main.py:1552`: **SELL pri body ≥8 a trend ≤3,5; inak REDUCE pri body ≥5**. Až potom sa skúma WAIT/BUY/HOLD. Support nie je povinnou podmienkou výstupu.

| Podmienka | Body |
|---|---:|
| Pokles od vybraného maxima ≥10 % | 3 |
| Inak pokles ≥ adaptívny prah 6–9 % | 1 |
| Živá cena < predchádzajúci support ×0,995 | 2 |
| Pomer objemu ≥1,3 a zmena posledných uzavretých 24 h sviečok <−2 % | 1 |
| Cena pod EMA50 / EMA200 | 1 + 1 |
| MACD histogram <0 | 1 |
| Trendové skóre ≤3 | 1 |
| Trhový stav WARNING / CRITICAL | 1 / 2 |
| Starší použiteľný negatívny projektový fundament pri existujúcom technickom riziku | max. 1 |

Ďalšie vetvenie: drawdown nad kontrolným prahom a (body ≥3 alebo trend ≤4,5) → WAIT; nasledujú pôvodné BUY filtre; body ≥3 alebo trend ≤4 → WAIT; inak HOLD. Nejde o vlastnícky filter: `decide_coin` nečíta skutočné držané množstvá ani nákupné ceny. HOLD/SELL v tomto verejnom výstupe preto nie sú automaticky osobné portfóliové pokyny.

`smooth_action` (`main.py:1407`) môže ponechať staré SELL/REDUCE, keď nový výsledok je HOLD/WAIT a body ≥4, bez kontroly veku `last_actions`. Starý SELL tak môže pretrvať aj pod aktuálnym predajným prahom 8. V tomto konkrétnom zbere odstránenie `last_actions` signály nemení.

## Rozhodujúce hodnoty po minciach

| Minca | Cena | 24 h | Support | R | Support prerazený | Objemový pomer | Predajný tlak | Pokles od maxima | Trend | Body → signál |
|---|---:|---:|---:|---:|---|---:|---|---:|---:|---|
| AAVE | 132.19 | -2.98% | 131.08 | 151.13 | nie | 1.256 | nie | 17.66% | 1.2 | 9 → SELL |
| TAO | 250.1 | -1.26% | 242.6 | 263.9 | nie | 0.591 | nie | 11.12% | 2.1 | 8 → SELL |
| FET | 0.1759 | -0.11% | 0.1695 | 0.1896 | nie | 1.174 | nie | 13.05% | 2.5 | 8 → SELL |
| SOL | 100.45 | -1.30% | 98.62 | 105.28 | nie | 1.010 | nie | 8.01% | 0.9 | 7 → REDUCE |
| ONDO | 0.4114 | -0.84% | 0.3966 | 0.4406 | nie | 0.878 | nie | 12.93% | 2.5 | 8 → SELL |
| RENDER | 1.676 | -3.01% | 1.643 | 1.85 | nie | 0.617 | nie | 13.87% | 2.1 | 8 → SELL |

Objemový pomer = priemer posledných 6 uzavretých 4h sviečok / priemer predchádzajúcich 30; nejde o zmenu 24h objemu. Všetky pomery sú pod 1,3. Ani BTC nemá prerazený support alebo potvrdený predajný tlak.

| Minca | RSI14 | EMA20 | EMA50 | EMA100 | EMA200 | MACD hist. | ATR14 |
|---|---:|---:|---:|---:|---:|---:|---:|
| AAVE | 28.806044 | 136.87181 | 143.11534 | 149.13374 | 149.02844 | -0.019385366 | 2.6614286 |
| TAO | 39.511873 | 252.0091 | 258.24354 | 265.90634 | 269.49556 | 0.32899341 | 4.75 |
| FET | 41.926569 | 0.17651198 | 0.18339091 | 0.19277506 | 0.19621815 | 0.00045879564 | 0.0039928571 |
| SOL | 39.200736 | 101.40255 | 102.99271 | 105.23417 | 107.07699 | -0.012422573 | 1.4471429 |
| ONDO | 42.918071 | 0.41278665 | 0.42476066 | 0.43907265 | 0.43999481 | 0.0014509889 | 0.0093071429 |
| RENDER | 36.188451 | 1.7155786 | 1.7657544 | 1.8157231 | 1.7946354 | 0.00088390643 | 0.037857143 |

Všetky ceny sú pod všetkými štyrmi EMA. MACD je **kladný pri TAO, FET, ONDO a RENDER**: SELL tu nevyžaduje zhoršujúce sa momentum. RSI nie je samostatný predajný bod; vstupuje však do trendového skóre. EMA20/100 majú rovnaký nepriamy vplyv. ADX, denná štruktúra ani relatívna sila sa v natívnom SELL filtri vôbec nevyžadujú. ATR ovplyvňuje kontrolný prah drawdownu, nie dôkaz budúceho prepadu.

### AAVE: presný spúšťač

3 b.: hlboký pokles 17.7% od lokálneho maxima; 1 b.: cena pod EMA50; 1 b.: cena pod EMA200; 1 b.: MACD histogram záporný; 1 b.: slabý trend (skóre 1.2/10); 2 b.: bezpečnostný stav trhu: CRITICAL. Spolu **9**, trend **1.2** → **SELL**.

Aktuálny vtedy pozorovaný stav: cena nad supportom 131.08; prah prerazenia v kóde je 130.4246. Žiadny objemový predajný bod. Je to preventívny výstup pri oslabení, nie potvrdené pokračovanie veľkého prepadu.

### TAO: presný spúšťač

3 b.: hlboký pokles 11.1% od lokálneho maxima; 1 b.: cena pod EMA50; 1 b.: cena pod EMA200; 1 b.: slabý trend (skóre 2.1/10); 2 b.: bezpečnostný stav trhu: CRITICAL. Spolu **8**, trend **2.1** → **SELL**.

Aktuálny vtedy pozorovaný stav: cena nad supportom 242.6; prah prerazenia v kóde je 241.387. Žiadny objemový predajný bod. Je to preventívny výstup pri oslabení, nie potvrdené pokračovanie veľkého prepadu.

### FET: presný spúšťač

3 b.: hlboký pokles 13.1% od lokálneho maxima; 1 b.: cena pod EMA50; 1 b.: cena pod EMA200; 1 b.: slabý trend (skóre 2.5/10); 2 b.: bezpečnostný stav trhu: CRITICAL. Spolu **8**, trend **2.5** → **SELL**.

Aktuálny vtedy pozorovaný stav: cena nad supportom 0.1695; prah prerazenia v kóde je 0.1686525. Žiadny objemový predajný bod. Je to preventívny výstup pri oslabení, nie potvrdené pokračovanie veľkého prepadu.

### SOL: presný spúšťač

1 b.: pokles 8.0% od lokálneho maxima (prah 6.0%); 1 b.: cena pod EMA50; 1 b.: cena pod EMA200; 1 b.: MACD histogram záporný; 1 b.: slabý trend (skóre 0.9/10); 2 b.: bezpečnostný stav trhu: CRITICAL. Spolu **7**, trend **0.9** → **REDUCE**.

Aktuálny vtedy pozorovaný stav: cena nad supportom 98.62; prah prerazenia v kóde je 98.1269. Žiadny objemový predajný bod. Je to preventívny výstup pri oslabení, nie potvrdené pokračovanie veľkého prepadu.

### ONDO: presný spúšťač

3 b.: hlboký pokles 12.9% od lokálneho maxima; 1 b.: cena pod EMA50; 1 b.: cena pod EMA200; 1 b.: slabý trend (skóre 2.5/10); 2 b.: bezpečnostný stav trhu: CRITICAL. Spolu **8**, trend **2.5** → **SELL**.

Aktuálny vtedy pozorovaný stav: cena nad supportom 0.3966; prah prerazenia v kóde je 0.394617. Žiadny objemový predajný bod. Je to preventívny výstup pri oslabení, nie potvrdené pokračovanie veľkého prepadu.

### RENDER: presný spúšťač

3 b.: hlboký pokles 13.9% od lokálneho maxima; 1 b.: cena pod EMA50; 1 b.: cena pod EMA200; 1 b.: slabý trend (skóre 2.1/10); 2 b.: bezpečnostný stav trhu: CRITICAL. Spolu **8**, trend **2.1** → **SELL**.

Aktuálny vtedy pozorovaný stav: cena nad supportom 1.643; prah prerazenia v kóde je 1.634785. Žiadny objemový predajný bod. Je to preventívny výstup pri oslabení, nie potvrdené pokračovanie veľkého prepadu.

## Trhová bezpečnosť a závislosť od pamäte

V reprodukcii: kapitalizácia −2,872 % →1 bod; BTC pod EMA50 →1; BTC pod EMA200 →1; všetkých 6 mincí pod vlastným kontrolným prahom drawdownu →3. **Spolu 6 bodov**. BTC 24h −0,307 %, drawdown 5,53 % pod prahom 6 % →0 ďalších bodov; žiadne zlomené supporty ani potvrdený predajný tlak. BTC cena 80 204,68; support 79 220,74; rezistencia 82 267,79.

Nový surový stav je WARNING (od4; CRITICAL od8). Uložený CRITICAL sa drží už od6 (`safety_exit_critical_below=6`). Pamäť preto pridá minciam 2 namiesto1 bodu, hoci nové skóre nedosahuje prah nového CRITICAL. Bez pamäte safety TAO/FET/ONDO/RENDER klesnú z8 na7 a SELL sa zmení na REDUCE. AAVE zostáva SELL8 a SOL REDUCE6. Hysteréza môže mať rozumný účel proti prepínaniu, ale nie je dôkazom aktuálnej krízy ani prognózou.

| Minca | Baseline | Bez uložených maxím | Bez safety pamäte | Bez pamäte signálu | Bez celého verejného stavu |
|---|---|---|---|---|---|
| AAVE | SELL 9 | SELL 9 | SELL 8 | SELL 9 | SELL 8 |
| TAO | SELL 8 | SELL 8 | REDUCE 7 | SELL 8 | REDUCE 7 |
| FET | SELL 8 | SELL 8 | REDUCE 7 | SELL 8 | REDUCE 7 |
| SOL | REDUCE 7 | REDUCE 7 | REDUCE 6 | REDUCE 7 | REDUCE 6 |
| ONDO | SELL 8 | SELL 8 | REDUCE 7 | SELL 8 | REDUCE 7 |
| RENDER | SELL 8 | SELL 8 | REDUCE 7 | SELL 8 | REDUCE 7 |

Všetky vybrané maximá sú zo **21.10.2026 18:00 Bratislava** (vekom približne 5,8 dňa), v 42×4h okne. Uložené maximá sa rovnajú maximám zo sviečok. Odstránenie uložených maxím preto tu nič nemení: **tento konkrétny SELL nie je spôsobený expirovaným maximom mimo sedemdňového okna**. Bez celého stavu zostávajú staré cenové maximá prítomné v trhových sviečkach; odstrániť stav neznamená odstrániť drawdown.

## Potvrdené riziká implementácie, bez opráv pravidiel

1. **Korelované dôkazy sa počítajú opakovane.** EMA50/200 sú priamo dva rizikové body a zároveň súčasť slabého trendu; RSI a MACD sú v trende, MACD aj samostatne. Drawdown mince navyše prispieva k trhovej šírke a tá cez CRITICAL znova k tej istej minci. Počet bodov nie je počet nezávislých dôkazov.
2. **Nie je povinný dôkaz pokračovania poklesu.** Support/objem môžu byť neporušené; pozitívny MACD neblokuje SELL. Skóre sú prevažne oneskorené merania už uskutočneného poklesu. Pokles sám osebe nie je dôkaz ďalšieho poklesu.
3. **Vek pamäte bezpečnosti a signálov sa neoveruje.** Bez fresh-state kontroly môže starý safety/last_action ovplyvniť nový výstup. V tomto prípade ovplyvňuje kategóriu safety, nie smoothing.
4. **Maximá nemajú spodnú kontrolu veku.** `now - stored_ts <= max_age` prijme aj budúci timestamp; test to preukazuje. Window maximum sa vyberá podľa posledných42 sviečok, bez samostatného overenia súvislosti/aktuálnosti ich časov v `compute_structure`. Integrácia kontroluje `stale` ceny a minimálny počet sviečok, nie úplnú časovú integritu. V zbere nebolo potrebné budúce maximum ani chýbajúce sviečky na vysvetlenie výsledku.
5. **BTC technický strop môže prekročiť komentované 3 body.** Cyklus testuje `running>=3` pred pridaním celej váhy; 1+1+2=4. Charakterizačný test to potvrdzuje. V tomto konkrétnom zbere BTC pridal iba2, preto táto chyba výsledok nevysvetľuje.
6. **TTL fundamentov tiež prijíma budúce dátumy** (kontrola iba `age_h <= limit`). Starší použiteľný cache nie je novo potvrdený aktuálnou analýzou. V skúmanej reprodukcii odstránenie cached fundamentals/alert research nemení žiadny výstup; žiadny projektový fundamentálny bod neprispel.
7. **HOLD/SELL nerozlišujú skutočnú držbu.** Verejná natívna logika je technický signál. Súkromná príloha a reálny manuálny obchod sú oddelené. Odporúčanie nie je záznam vykonaného obchodu.
8. **Chýba výstupný nákladový/úžitkový model.** SELL/REDUCE nemajú predikovanú veľkosť budúceho poklesu, cenu opätovného vstupu, neistotu alebo čistú výhodu po eToro nákladoch. Z takéhoto výstupu nemožno odvodiť ekonomicky podložený sell-and-rebuy plán.

## Náklady eToro a požadované dôkazy

Pri účtovnej konvencii predajná hotovosť = množstvo×cena×(1−f_sell), nový nákup stojí množstvo×cena×(1+f_buy), získa spätný nákup aspoň pôvodné množstvo iba ak `P_rebuy/P_sell <= (1−f_sell)/(1+f_buy)`. Pri 1 % na každej strane to vyžaduje pokles aspoň **1,9802 %**, pri1,2 % **2,3715 %**, ešte **bez spreadu a sklzu**. Sú to matematické hranice nulovej výhody, nie odporúčané ciele ani záruka dostupného opätovného vstupu. Pôvodný nákupný poplatok je pri rozhodovaní z už držanej pozície utopený náklad; v celkovom backteste sa stále účtuje. Pri inej brokerovej konvencii sa model musí zhodovať s výpisom.

Predaj pri významnom potvrdenom riziku môže znížiť drawdown aj bez úspešného načasovania návratu. To sa musí vyhodnocovať oddelene od dobrovoľného sell-and-rebuy, ktorý potrebuje konzervatívnu čistú výhodu s rezervou na spread, sklz, neistotu a zmeškaný rast. Tento snapshot takúto výhodu nepreukazuje.

## Návrh rozlíšenia — iba na schválenie a test

| Kategória pre držanú pozíciu | Navrhované dôkazy (zatiaľ neimplementované) |
|---|---|
| HOLD | Bežná korekcia; support alebo volatilite primeraná ochranná hranica drží; bez nezávisle potvrdeného vážneho rizika. Nezamieňať s BUY. |
| REDUCE | Viac nezávislých aktuálnych dôkazov: potvrdená zmena cenovej štruktúry, objemová/likviditná slabosť alebo doložená relevantná udalosť; odlíšiť pôvod a vek každého dôkazu, zohľadniť náklady a expozíciu. |
| SELL | Potvrdené závažné porušenie ochranného plánu/štruktúry s nezávislým rizikovým potvrdením, alebo doložený priamo relevantný bezpečnostný/systémový incident. Ani táto kategória neznamená istotu budúceho poklesu. Urgentný potvrdený incident nesmie čakať len na technický support. |
| WAIT pre nevlastnenú mincu | Nový nákup nie je potvrdený; žiadny pokyn na predaj neexistujúcej pozície. |

Pred návrhom nových prahov treba overiť čerstvosť cien/sviečok/stavu, kauzálny čas TTL a nezávislosť faktorov. Pri neistých dátach označiť neurčitosť, nie násilne generovať SELL. Zrušenie hysterézy alebo povinný support filter nemožno automaticky považovať za lepšiu stratégiu: môže zvýšiť prepínanie či oneskoriť ochranu.

## Izolovaný experimentálny plán, nie výsledok výkonnosti

- Zmraziť V10.6 ako baseline. Oddelene testovať dátovú validáciu/časovanie, nezávislosť dôkazov, pamäť safety, potvrdenie štruktúry a nákladový výstup. Najprv každú zmenu samostatne, až potom vopred definovanú kombináciu. Žiadne nové produkčné pravidlá v tomto audite.
- Chronologické kauzálne 4h/1d sviečky pre všetkých6 mincí a BTC, zdokumentovaný zdroj/chýbajúce úseky. Signál až po uzavretí dostupnej sviečky, vykonanie na nasledujúcej dostupnej cene s manuálnym oneskorením; nepoužiť high/low budúcej sviečky na voľbu ceny. Oddeliť ochranný stop a dobrovoľný predaj.
- Rovnaký kapitál, vstupná držba/expozícia, oceňovanie otvorených pozícií a koncové poplatky pre baseline, alternatívu a HOLD; samostatne mince aj spoločné portfólio. Oddeliť efekt načasovania vstupu od efektu výstupu pri rovnakých pozíciách.
- Minimálne1 %/strana, konzervatívne1,2 %/strana; explicitne rozpísaný spread/sklz a citlivosť vyšších nákladov, žiadne skryté dvojité účtovanie spreadu. Dokumentovať predpoklad, keď broker historický spread neposkytuje.
- Vopred definovať veľkú korekciu, predčasný predaj a úspešný návrat (horizont a drawdown/ATR kritérium) bez výberu podľa výsledkov. Následný pohyb sa používa len na hodnotenie, nikdy na rozhodovanie. Merania: čistý výnos, maxDD, PF, obchody, čas v hotovosti, zmeškaný rast, drawdown od okamihu výstupu, falošné/predčasné predaje, náklady a návraty.
- Roky2024–2026 sú už skúmané; walk-forward v nich je retrospektívna robustnosť, nie nové nezávislé potvrdenie. Vývojové okná, zamknuté parametre pred každým testovacím oknom, evidencia všetkých skúšaných variantov. Skutočne nové overenie až budúci paper test so zmrazenými pravidlami.
- Pri nízkom počte obchodov/neudržateľnom zlepšení uviesť nedostatok dôkazov. Pokiaľ alternatíva nepreukáže stabilnú výhodu po nákladoch, neodporučiť aktiváciu. Tento audit žiadny nový historický výkonnostný test nespúšťal.

## Testy a bezpečnosť

102 offline testov prešlo s blokovaným nemockovaným sieťovým prístupom. Nové charakterizačné testy dokazujú SELL pri držiacom supporte a kladnom MACD, rozdiel WARNING/CRITICAL, pretrvávanie SELL cez smoothing, prijatie budúceho maxima, prekročenie BTC technického stropu a deterministický audit bez zmeny vstupov. Existujúce testy overujú nezmenené produkčné súbory a verejnú/súkromnú hranicu. Tieto testy dokazujú správanie kódu, nie ziskovosť alebo bezpečnosť stratégie.

Neboli zmenené main.py, bot_state.json, produkčné workflow, Telegram, Secrets, reálne pozície ani obchodné pravidlá. Audit neobsahuje vlastníctvo, množstvá ani nákupné ceny skutočného portfólia. Záznam maxima je verejná analytická cena, nie nákupná cena. Ďalšie opravy stratégie vyžadujú samostatnú validáciu a schválenie.
