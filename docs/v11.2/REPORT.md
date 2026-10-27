# V11.2 — analytická oprava, pripravené na kontrolu

**Nenasadené. Žiadna nová stratégia, aktivácia E1, automatické obchody ani deklarovaná výhoda oproti HOLD.** Nová vetva vznikla z main `b367f54`. V11.2 je vypnutá, kým nebude samostatne schválená.

## 1. Identifikované problémy a príčiny

Presný obsah používateľovej správy18:43 nebol priložený. Nižšie sú príčiny doložené aktuálnym kódom a izolovanými reprodukciami, nie predstieraný audit konkrétnej súkromnej Telegram správy.

| Problém | Príčina V11.1 | Skutočne vykonaná oprava |
|---|---|---|
| Technický REDUCE a osobný HOLD v tej istej správe | Verejný renderer používa bodovanie main.py; súkromná príloha má iné, existujúce podmienky držby a pripája sa neskôr | Nový renderer dáva jeden hlavný akčný záver podľa držby. Pôvodný technický signál zostáva v diagnostike. Existujúce pravidlá držby sa neprepisujú |
| Ručné reporty sa neporovnávajú | manual_slots úmyselne ukladajú len status/čas, ráno sa používalo len pre večer | Samostatný kompaktný verejný last_analysis_v112 po poslednom úspešnom odoslaní; platí pre ranný, večerný aj ručný report |
| Denná zmena zamieňaná za zmenu od reportu | Chýbali spoločné referencie globálnych a projektových metrík | Explicitné rozdiely cien/kapitalizácií/objemov/dominancie medzi pozorovaniami; osobitne uvedené24h hodnoty |
| Nevhodné hlavné fundamenty | Aktuálny GitHub release či cudzí wallet incident nemusí ovplyvňovať watchlist; témy rovnakého Fedu sa opakovali | Materiálnosť + makro, relevantná regulácia alebo konkrétne pomenovaný projekt; rutinný kód/marketing/nezaradené hacky sa nepropagujú. Rovnaká makro téma iba raz |
| Všeobecný výhľad | Pôvodný text uvádzal všeobecnú podporu/rezistenciu bez časového rámca | BTC a všetkých6 mincí majú osobitné4h/1d scenáre pre24–72h/7–14d; základ, dôvod, alternatíva, hranice a invalidácia. Žiadne percentuálne pravdepodobnosti |
| Zastaraný CRITICAL pôsobí ako osobný predajný pokyn | Legacy hysteréza a korelované technické body | Legacy výpočet zachovaný iba ako technická diagnostika; samotné body/EMA/drawdown sa neprekladajú na nové osobné SELL. Nejde o preukázanie lepšej predajnej stratégie |
| Chýbajú zrozumiteľné nákupné možnosti | Zablokovaný nový obchod sa miešal s technickým kandidátom | Oddelené WAIT a neaktivovaný kandidát: individuálna zóna, invalidácia, cieľ a model čistého R:R. Nenúti sa kandidát pri slabých/neúplných dátach |
| Príliš veľa opakovaní a poplatkov v hlavnej správe | Technické skóre plus súkromná príloha plus upozornenia | Jeden akčný blok; náklady, úplné indikátory, zdroje a historické porovnania v Artifakte. Prípadný súkromný výsledok pozície iba vo finálnom Telegrame |
| Nejasná dostupnosť a čerstvosť zdrojov | Úspešný fallback alebo formát sa mohol zameniť za aktuálne pokrytie | Kompletné source_status/attempts, data_quality a zoznam chýbajúcich oblastí. Počet čerstvých endpointov nie je percento pokrytia významných udalostí |
| AAVE TVL veľký payload | /protocol/aave prekračuje bezpečný limit | Malý bezplatný fallback /tvl/aave. Numerický výsledok bez as-of sa označí ASOF_UNKNOWN, nie meraním v čase zberu. Bez vymysleného historického porovnania |
| Chyby súkromného posúdenia boli popísané len ako úložisko | Pôvodný široký except pokrýval načítanie aj renderer | Pri V11.2 diagnostika rozlíši storage_or_inventory a assessment, vypíše iba názov triedy výnimky, nikdy hodnoty alebo text tajnej výnimky |

## 2. Hranica investičných pravidiel

Pôvodný main.py, natívne BUY/SELL, bezpečnostný monitoring a súkromné kritériá držby zostávajú. E1 ani AdaptiveHold nie sú súčasťou práce. V11.2 nezavádza nový osobný SELL alebo BUY prah.

- Držba sa číta iba zo schváleného súkromného úložiska, nie zo syntetických príkladov, watchlistu alebo minulého odporúčania.
- Pre držanú mincu sa používa existujúce `strategy.decide(...held=True, approved=False...)`, ktoré používala súkromná príloha V11.1. Existujúci REDUCE pri kombinácii support breakdownu, objemu a slabého denného trendu nie je potlačený. Pri nedostatočných denných dátach sa nepredstiera potvrdené HOLD.
- Bez vlastníckeho kontextu je hlavný záver WAIT pre nový nákup. Natívny BUY ostáva diagnostickým vstupom a môže vybrať cenový kandidát; **nenastavuje sa tým nový schválený osobný BUY**. Informačný screen kandidátov nie je overená stratégia.
- Náklady používajú existujúce BUY_FEE/SELL_FEE (predvolene1%/strana) a SPREAD_ESTIMATE, prípadne konzervatívny nepriaznivý fill0,25%/strana. Predpoklad nie je overená eToro kotácia; kompletné ekonomické výpočty/proveniencia sú v diagnostike, nie opakovane v hlavnej správe.
- Dobrovoľný plán „predať a určite nakúpiť lacnejšie“ sa nevytvára. Ochranný výstup nie je tvrdením výhodného spätného nákupu.
- Mimoriadne alerty pred prerazením podpory zostávajú v pôvodnom overovacom monitoringu. Nový event-to-SELL model bez historickej a budúcej nezávislej validácie sa neaktivuje. Nemožno tvrdiť, že report odhalí každý prudký prepad.

## 3. Pamäť, konzistentnosť a súkromie

last_analysis_v112 obsahuje iba verejné trhové hodnoty, časy, zdrojový fingerprint, technické signály/skóre a projektové metriky. Je to jeden obmedzený posledný záznam, nie rastúci archív. Podklady nového reportu sa zapíšu až po úspešnom send spolu so sent. Attempting, uncertain, CAS konflikt alebo neúspešný finálny zápis nepostúpia referenciu. Opakované odoslanie rovnakého GitHub behu sa neumožní.

Referencia sa odmietne pri rovnakom zdrojovom fingerprinte, budúcom/rovnakom čase, veku nad7 dní alebo neplatnej schéme. Odlišný samotný collector timestamp nedokazuje nové údaje. Globálna zmena bez zmeny cien sa tiež dá rozlíšiť. Denné/revidované meranie sa nevydáva za nové denné obdobie len preto, že sa report zozbieral neskôr.

Model/Artifact sa vytvárajú pred načítaním súkromnej evidencie. Finálna personalizácia pracuje s kópiou, nevpisuje vlastníctvo, množstvá, nákupné ceny ani osobné odporúčania do verejného modelu alebo denníka. Porovnanie technických odporúčaní v histórii je dostupné; **historická zmena osobného odporúčania nie je predstieraná**, keďže osobné odporúčania sa bez samostatne schváleného súkromného auditu neukladajú.

Ranný shadow checkpoint môže niesť verejné v112_observation zahrnuté do kontrolného súčtu. Skutočný večerný test prijme iba overenú nezávislú rannú referenciu; samotné náhľady nie sú dôkazom časovo oddeleného pozorovania.

## 4. Ukážky a porovnanie

V `examples/morning.txt` a `examples/manual.txt` sú **výslovne syntetické** ukážky. Ceny, modelová udalosť na example.org a hypotetická držba AAVE nie sú tvrdením o skutočnom trhu ani používateľovom portfóliu.

| Výstup | Dĺžka bez označenia syntetických dát |
|---|---:|
| Nová ranná analýza | 2 015 znakov |
| Nová ručná analýza | 2 157 znakov |
| Pôvodný V11.1 formát s modelovou súkromnou prílohou, rovnaké vstupy | 2 908 znakov |

`examples/v111-original-format.txt` je kontrolný pôvodný renderer, nie skutočný zachytený report18:43. `examples/public-diagnostics.json` obsahuje všetky modelové horizonty a porovnania. `examples/live-public-preview.txt` je ďalší reálny izolovaný preview bez čítania portfólia; nie odoslaný Telegram ani skutočné ranné/večerné meranie.

## 5. Živé zdroje a zostávajúce obmedzenia

Izolovaný reálny preview27.10.2026 o19:21 Bratislava: ceny a technické dáta6 mincí úplné,33 endpoint pokusov,4 označené ako aktuálne. **4/33 nie je miera kvalitného fundamentálneho pokrytia** — niektoré aktuálne formáty obsahujú len kód/governance. Významný podiel informácií o celom svete sa nedá z toho vyčísliť.

V tomto Codex prostredí Fed/FOMC/BLS/BEA/ECB/SEC/CFTC, Treasury/FRED a DeFiLlama blokuje sieťový tunel HTTP403. Nie je to dôkaz výpadku pôvodných serverov ani výsledok GitHub-hosted runnera. AAVE malý fallback je implementovaný a unit testovaný, ale živú dostupnosť tu nebolo možné potvrdiť. Odpoveď bez času merania sa nikdy neprezentuje ako preukázane aktuálny TVL.

ONDO fallback načíta formát, ale bez relevantných čerstvých položiek; AAVE/FET feedy mali starý obsah. Rutinné SOL/RENDER GitHub udalosti sa preto nestali hlavnými dôvodmi rastu/poklesu. Zostáva neúplné primárne makro pokrytie, overený sadzbový konsenzus/FedWatch, ETF toky, DXY, orderbook/hĺbka likvidity, derivátové likvidácie, systematická geopolitika, unlocky a aktívni používatelia/príjmy všetkých6 projektov. Nepridávali sa platené API ani nedoložené endpointy na tieto údaje.

`SOURCE_DIAGNOSTICS.json` obsahuje URL, čas, formát, aktuálnosť a konkrétnu vrstvu chýb. `LIVE_CHECK.json` potvrdzuje bez odoslania, bez pozícií/obchodov, bez zápisu stavu, ochranu16 verejných súborov a neoverený časový pár. Potrebný je ešte nový zdrojový test z GitHub runnera; nemožno predstierať, že všetky fundamenty už fungujú.

## 6. Testy a význam výsledkov

166 offline testov v izolovanom Python3.12: pôvodných149 a17 nových. Sieťové volania testov sú blokované/mockované. Pokrytie zahŕňa:

- Jeden zrozumiteľný záver pre držbu, nepredpokladanie držby, zachovanie pôvodného súkromného REDUCE a odmietnutie falošného HOLD pri chýbajúcich dátach.
- Predchádzajúce verejné pozorovanie, skutočné delty namiesto24h zmien, dominanciu v percentuálnych bodoch, rovnakú/budúcu/neplatnú referenciu.
- Oddelené individuálne horizonty/úrovne, žiadne vymyslené pravdepodobnosti, nevydávanie podpory nad cenou za držanú podporu.
- Materiálnosť, budúce/neaktuálne správy, duplicitnú makro tému, nesúvisiace hacky a rutinný kód, vypnutý/nefunkčný AI fallback pôvodných testov.
- AAVE current-value fallback bez nepravdivej časovej pečiatky, nedostupné zdroje nie sú nuly, interné náklady vylúčia ekonomicky slabý watch kandidát, headline/legacy BUY neaktivuje nový osobný BUY.
- Uloženie referencie iba po doručení, CAS/timeout/final-save failure, deduplikáciu a súkromné hodnoty iba v mockovanom Telegrame, mimo verejných Artifacts.
- Pôvodné testy rozvrhu, USA DST/sviatkov, manuálneho spustenia,10 nových behov a opakovaného toho istého run_id zostávajú.

Úspešné softvérové testy nedokazujú kvalitu predikcií, investičnú výhodu ani ochranu pred všetkými prepadmi. Nový backtest stratégie sa nevykonával, pretože sa nevyberal/nezavádzal nový obchodný model. E1 zostáva uzavretý.

## 7. Nasadenie, schvaľovanie a rollback

Presný postup je v `DEPLOYMENT.md`. Aktuálne main.py, bot_state.json, trial-public/v111-delivery.json, skutočné portfólio a Secrets nie sú zmenené. Navrhovaný workflow vyberie V11.2 zdroj len s výslovným novým prepínačom; inak ponechá presný existujúci V11.1 pin. Automatické07/15/20, ručná kompletná analýza, concurrency a tichý15-minútový monitoring zostávajú.
