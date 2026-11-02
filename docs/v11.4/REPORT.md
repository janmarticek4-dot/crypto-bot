# V11.4 – overené opravy

## Diagnostika z reálnych behov

Východisková main bola 625d76f, produkčný runtime 05576b4; pôvodné čísla 9a60c7a/05576b4 sa nepredpokladali bez fetch. Verejný doručovací denník a [read-only runner audit](https://github.com/janmarticek4-dot/crypto-bot/actions/runs/41525188722) potvrdili:

| 02.11.2026 večer, Bratislava | Čas |
|---|---|
| cieľ | 20:00 |
| workflow vytvorený aj run_started_at | 20:40:39 |
| prvé joby runnera | 20:40:42 |
| analytický job | 20:41:08 |
| začiatok zberu | 20:41:39.023 |
| dokončenie generovania vrátane súkromnej časti | 20:42:29.473 |
| začiatok Telegram HTTP | 20:42:29.473 |
| potvrdenie Telegram API | 20:42:30.054 |

Približne 40 minút chýbal spustený workflow. Po vytvorení nezostal desiatky minút v rade: runner začal za 3 sekundy. Native/private dependency a setup/testy pridali približne minútu do zberu. Zber/generovanie trvali približne 50 sekúnd, Telegram približne 0,58 sekundy. Hlavná príčina nie je AI generovanie ani Telegram timeout. Konkrétny interný dôvod vynechaného/oneskoreného cron triggera GitHub nezverejnil; netvrdíme konkrétny platformový incident. Beh 41512152559 skutočne odoslal report, zdroj 05576b4 a 18 výstupov V2.

Incident 31.10. je už zdokumentovaný v [predchádzajúcom audite](../incident-20261031/REPORT.md): v rannom okne neexistoval beh, následný beh o 09:08 preskočil pôvodné okno a až recovery o 09:47 odoslal analýzu. Jeho historické časové značky sa spätne nevyrábajú.

**Skutočné tri správy 02.11. neboli jeden Binance incident.** Dve opisovali Mercado Bitcoin (Cointelegraph: `$46M hack`, Decrypt: zastavenie výberov po `$40 Million Hack`), tretia Binance (Decrypt: laundering hack loot). Chyba bola duplicitné Mercado Bitcoin a strata identity/obsahu vo všeobecnom „Kryptotrh – incident“. Zlúčiť všetky tri do jedného Binance incidentu by bolo nepravdivé. Regresný test používa tieto presné overené nadpisy. Rozdiel 40/46 sa prezentuje ako rozdiel publikovaných odhadov, nie nezávisle zistená strata.

Stará podpora vo V11.3 bola minimum posledných približne 20 sviečok. Po páde pod ňu formatter iba zobrazil „stará podpora“. Žiadne hľadanie starších pivotov ani denný fallback neexistovalo. Nie každý dotyk pod podporou bol zároveň potvrdený dvoma uzavretiami.

## Implementácia

### Plánovanie a spoľahlivosť

- Pôvodné ciele 07/15/20 Europe/Bratislava, zimný/letný čas, */15 tichý monitoring a bounded catch-up ostávajú.
- Doplnkový `*/5 5-7,13-15,18-20 * * *` je **ľahký kontrolný trigger** v UTC okolo letných aj zimných cieľov. Pred inštaláciou analytických závislostí a zberom načíta existujúci canonical denník. Ak existuje sent/attempting/uncertain záznam, analytiku nespustí. Extra 5-minútový trigger nespúšťa drahší native monitoring ani súkromný command poller; tie ostávajú v pôvodnej vetve.
- Ďalší CAS pred HTTP zostáva autoritatívny pri závode dvoch behov. Pre-send retry ostáva obmedzený; neisté odoslanie sa nereplayuje. Telegram success vyžaduje ok=true a message_id. Časy zberu/generovania/send/ack sú oddelené.
- Produkčná concurrency sa nemení; zrušenie zastaraných behov sa zaplo iba pre read-only CI/shadow workflow, nie pre odosielanie alebo správu portfólia.
- Častejší cron nie je SLA. Ak GitHub nevytvorí žiadny beh, ani tento kód sa nemá kde vykonať. Nezávislý bezplatný externý cron, ktorý volá existujúci workflow_dispatch, by odstránil závislosť triggera od GitHub cron, ale vyžaduje externé konto a oddelené minimálne Actions-write poverenie. Také poverenie ani služba sa bez samostatného nastavenia nevytvárali.

### Udalosti

- Nové `news_incidents.py`: normalizované burzy vrátane Mercado Bitcoin; všeobecný článok sa priradí iba pri jedinečnej dôkazovej kotve (napr. zhodná suma). Neurčená/nejednoznačná identita sa potlačí, nie doplní domnienkou.
- Odlišný explicitný dátum incidentu alebo označený nový/samostatný incident sa nelepí automaticky na starý prípad tej istej burzy. Časový kontext je obmedzený na 7 dní. Bez dostatočných identifikátorov nie je možné garantovať dokonalé sémantické rozlíšenie.
- Jeden incident obsahuje viac článkov a viac podstatných faktov: breach, zastavenie/obnovenie výberov, presuny, zmrazenie aktív, plán krytia a skutočná náhrada. Nový nadpis s rovnakými faktmi nie je aktualizácia. História importuje už oznámené aspekty zo starej evidencie, aby ich zmena implementácie sama neoznamovala znovu.
- Stav v existujúcom event_notifications_v1: stabilné ID, first_seen_at, last_updated_at, last_announced_at, announced_facts, citácie. Max. 64 incidentov, 6 posledných citácií/incident a pôvodný celkový limit 256 záznamov/90 dní. Článkové texty sa neukladajú do delivery rezervácií; zostávajú v diagnostike. História sa aktualizuje pri potvrdenom hlavnom doručení, nie pri shadow preview.
- RSS/Atom `description/summary/content` sa zachová ako sanitizovaný excerpt. **Nie je to tvrdenie, že sme prečítali a nezávisle overili celý článok.** Diagnostika odlišuje HEADLINE_ONLY a RSS_EXCERPT. Bez konkrétneho zdrojového faktu sa generický filler do Telegramu nedáva.
- Trhová kapitalizácia/objem alebo sumy z tela článku sa neprezentujú ako straty z hacku. Zmrazené aktíva, získané prostriedky a plán krytia nie sú ďalšie straty ani už dokončená náhrada. Čísla sú reportované zdrojmi, nie potvrdené účtovnou závierkou burzy.
- Maximálne tri rôzne nové udalosti; staré Fed výsledky sa znovu nevkladajú. Makro, ETF a projektové zdroje ostávajú; chýbajúce fakty ani príčiny pohybu sa nedopĺňajú AI.

### Podpory a nákupné scenáre

- Prerazenie sa rozlišuje ako dve uzavreté 4H sviečky pod pôvodnou podporou alebo iba intrabar/nepotvrdený pohyb. Proxy rastového/klesajúceho sviečkového objemu nie je skutočný order-flow.
- Ďalšia zóna sa hľadá pod aktuálnou cenou v už potvrdených pivot low (dve pravé sviečky už uzavreté), s najmenej dvoma oddelenými dotykmi. Najprv 4H história, pri jej vyčerpaní 1D. Tolerancia používa existujúce ATR; nejde o výnosovo optimalizované nové obchodné pravidlo.
- Obe vetvy sa počítajú interne: pullback pri historickej zóne so stabilizáciou a objemom; potvrdenie po dvoch uzavretiach nad pevnou predchádzajúcou rezistenciou. Denný/celotrhový kontext a náklady sú stále potrebné. `approved_buy=False` je zámerné: nejde o nasadenie novej stratégie.
- Ak história nestačí alebo nie je nižšia potvrdená zóna, výsledok je neoverená podpora a WAIT, bez vymyslenej ceny. Prerazená stará podpora sa neponúka ako nákup.

### Telegram/V2/portfólio

Neutral/flat V2 sa neopakuje v šiestich trojiciach; zobrazí sa iba dostupný smerový experiment RAST/POKLES, s neistotou. REFERENCIA/NEURČENÉ a všetkých 18 prognóz zostávajú v diagnostike a forward paper denníku. Metadata odlišuje dostupných 18 výstupov od počtu skutočne zobrazených smerových odhadov. V2 nikdy nemení BUY/SELL.

WAIT má dôvod podľa skutočného stavu mince (uzavreté prerazenie, predajný objem, nepotvrdený odraz, chýbajúca štruktúra) a jednu podstatnú hranicu/scenár. Sledované mince sa nemenia; vlastníctvo sa stále načítava iba zo súkromného úložiska. Toto nasadenie nemení pozície, zostatky, Secrets ani portfólio. main.py a v11/strategy.py bez zmien. Žiadne nové potvrdené BUY/SELL pravidlá sa neaktivovali.

## Overenie

Finálne offline testy: **433 prešlo**. Nové regresie: skutočné tri titulky → dva incidenty; všeobecný názov + jedinečná kotva; dve rôzne udalosti rovnakej burzy; reštart, kumulované oznámené fakty a aktualizácia; neidentifikovateľná správa; odhady strát vs. rezervy/zmrazenie; oneskorenie 42 minút a sent/uncertain dedup; SOL/TAO strata podpory; nová historická zóna; denný fallback; chýbajúce dáta/intrabar; všetkých 18 prognóz bez núteného vypisovania do Telegramu. Existujúce časové pásma, Telegram chyby, portfólio a causal model testy ostali.

Shadow je izolovaný, so živými trhovými dátami, bez Telegramu, bez čítania súkromných pozícií a bez zápisu do reálneho stavu. Ranný/večerný formát vytvorený z jedného zberu nie je nezávislé denné porovnanie; skutočné historické porovnanie používa doručené časovo oddelené snapshoty.

## Súbory a zostávajúce riziká

Nové: v11/news_incidents.py, v11/support_scenarios.py, tests/test_v114.py, v114-diagnosis.yml a v114-release.yml. Rozšírené: fundamentals.py, fundamental_analysis.py, event_notices.py, trend_reversal.py, compact_main.py, production_schedule.py, verified_monitor.py (verzia), v111_integrated_delivery.py, v111_trial.py, test runner/regresie a read-only readiness; run.yml a production audit obsahujú pripnutý nový zdroj.

GitHub stále negarantuje čas. Niektoré články a fundamentálne rozmery zostávajú neoveriteľné; RSS ani viac redakcií samy nedokazujú nezávislé potvrdenie reality. Sémantické skupiny sú konzervatívna heuristika s konkrétnymi regresiami, nie univerzálne NLP. Historické support zóny nemusia držať. Nové vstupné scenáre nie sú nezávisle overená zisková stratégia. Príliš málo forward výsledkov V2 stále nepreukazuje investičnú výhodu. Žiadna z týchto neistôt sa neskrýva pravdepodobnosťou alebo automatickým obchodom.


## Dodatočné kontroly zo shadow testov

Živý shadow navyše zachytil, že sumy kapitalizácie/objemu a historických porovnaní v telách článkov sa nesmú miešať do strát incidentu. Finálna verzia obmedzuje menové tvrdenia na kontext nadpisu a potlačí neporovnateľné odhady, namiesto vypísania zavádzajúceho zoznamu. Zmrazené/získané aktíva a rezervy sú samostatné fakty. Heuristika pri nejasnom rozsahu uprednostní vynechanie čísla pred falošnou presnosťou.

Kontrola 433 testov v čistom runneri: https://github.com/janmarticek4-dot/crypto-bot/actions/runs/41529216740 . Posledný úplný živý kandidát: run 41529216786. Predchádzajúci preukázaný shadow 41528714040 mal 18/18, oba formáty po jednej časti, 2157 znakov oproti 5007 detailným (−56,9 %) a žiadnu sekciu starých/nových-neoveriteľných udalostí. Finálne aktuálne údaje sa používajú iba v náhľade; žiadny testovací Telegram.

Nové päťminútové kontroly nemenia potvrdené historické sloty; už doručená správa 02.11. o 20:42 sa neoznačuje spätne za V11.4 ani neposiela znovu. Plánovanie aktívneho runtime po nasadení je predmetom source-verification workflow, nie dôkaz budúceho presného doručenia.


## Finálna kvalifikácia

Runtime kandidát: **52253f270c7ffdaa0f0438abeab634d115bdf90e**.

- [433 testov v čistom CI](https://github.com/janmarticek4-dot/crypto-bot/actions/runs/41529216740): SUCCESS, finálne nula chýb.
- [Úplná pôvodná release regresia](https://github.com/janmarticek4-dot/crypto-bot/actions/runs/41529216676): SUCCESS.
- [Finálny živý shadow](https://github.com/janmarticek4-dot/crypto-bot/actions/runs/41529216786): SUCCESS; 18/18, oba brief-v2 kontrakty platné, bez URL, po jednej časti. Kompaktný náhľad 2156 znakov oproti 5007 detailným (−56,9 %). Žiadne nové obchodné pravidlo ani Telegram sa neaktivovali v teste. Verejný náhľad a contract sú uložené vedľa tohto reportu.

Všetky produkčné analytické/safety/command-reader/slot/health source pins sa menia spoločne. Existujúce V111/V112 environment flags sa zachovávajú kvôli spätnej kompatibilite; nie je potrebný nový Secret. Nové meno workflow je Crypto AI Bot V11.4; audit naďalej sleduje aj historické názvy. História doručenia, skutočné portfólio a bot_state.json sa pri tejto aktivácii nemenia.

Pri návrate sa použije normálny pin-only commit a záložná referencia pred V11.4; nesmie sa resetovať main ani obnovovať starý portfóliový/doručovací snapshot. Nové päťminútové triggery zostávajú lacné, lebo kontrolujú canonical slot pred zberom. Nasledujúce reálne doručenie sa musí overiť samostatne; zelený no-send source check nie je dôkaz, že už nastalo budúce plánované doručenie.
