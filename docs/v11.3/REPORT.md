# V11.3 – produkčná kontrola a opravy

## Overené príčiny

Ranné nedoručenie 31.10.: v 07:00–08:30 Bratislava neexistoval GitHub schedule beh; ďalší bol až 09:08. Pôvodný job analytiky bol SKIPPED, nie zlyhaný Telegram. Presný interný dôvod vynechania GitHub neposkytol. Alert o 09:08 išiel native main.py cestou V10.6 zo SHA cc9e043; 88/13 boli voľné čísla Groq, nie kalibrovaný model. Podrobné job-log dôkazy sú v [predchádzajúcom audite](../incident-20261031/REPORT.md).

Skutočný náhradný report 41185920910 má canonical 2026-10-31-morning SENT o 09:47 Bratislava a 18 výstupov V2. Jeho uložené `at` označuje čas zostavenia reportu, nie presnú milisekundu Telegram acknowledgment; zdroj vyžadoval ok=true + message_id pre každú časť. Historicky neboli oddelene uložené všetky časy zberu/generovania/odoslania. V11.3 ich zaznamenáva samostatne a neprepisuje starú históriu.

Vlastnené pozície sa načítavajú zo súkromnej evidencie, nie watchlistu. Pretrvávajúce SOL/TAO HOLD nebolo možné opraviť iba novým textom: stará evidencia mohla stále obsahovať pozície. Používateľ teraz výslovne potvrdil všetky pozície uzavreté. Jednorazová šifrovaná CAS korekcia vyprázdni iba pozície, zachová hotovosť a všetky ostatné údaje a zneplatní staré čakajúce potvrdenie. Marker zabráni, aby opakované spustenie vymazalo budúci nákup; novší nákup po konzervatívnej hranici 31.10.09:00 UTC blokuje korekciu na kontrolu. Približne uvedený kapitál sa neukladá ako presný zostatok.

Posledný kontrolovaný research package: 10 flat a 8 regime_momentum modelov. Flat dáva nulový log-return zámerne. Ostatné body klasifikuje tolerancia odvodená z volatility; faktory balíka približne 0,35–0,50 násobia sigma × sqrt(horizont). Nie je to pravdepodobnosť. Preto 18× DO STRANY nepreukazuje bočný trh a nemá sa tak prezentovať. Doteraz je len 6 dozretých forward-paper záznamov; nepreukazujú stabilnú výhodu. Historické už skúmané roky nie sú nové nezávislé dáta.

## Zmeny

- Zachované 07/15/20 Europe/Bratislava, */15 tichý monitor, doplnkové off-hour triggery a bounded catch-up. Po poslednej oprave sú main analýzy a monitor zo schváleného immutable SHA. Žiadne exactly-once tvrdenia: timeout je UNCERTAIN a bez automatického replay.
- `delivery_timing`: začiatok zberu, dokončenie celej generácie aj súkromnej personalizácie, začiatok odoslania a posledné potvrdenie Telegram API. `DELIVERY_RUN` loguje štart/koniec aj pri chybe; úspešný návrat funkcie sa výslovne nepovažuje za potvrdenie doručenia. Rovnaký slot zostáva chránený CAS pred HTTP požiadavkou.
- Načítané prázdne portfólio je jasne odlíšené od nedostupnej evidencie. Žiadne HOLD/REDUCE/SELL pre nevlastnené pozície. Existujúce /kupil, /predal, /portfolio, /hotovost a potvrdenia zostávajú.
- V2 zachováva 18 pôvodných matematických prognóz a immutable paper záznamy. Telegram: REFERENCIA pri flat; NEURČENÉ pri neutrálnom ne-flat modeli. Nie je to tvrdenie potvrdeného bočného trhu. Smerové prahy ani výber modelov sa nemenia. Ochrana výstupu kontroluje platný model, cenu/bod, smer a konzistenciu s toleranciou. Poškodený výstup sa nezobrazí.
- Incidentové správy sa porovnávajú podľa entity a konkrétneho faktu: breach, širší prienik, zastavenie/obnovenie výberov, zmrazenie aktív, plán krytia, dokončená náhrada. Iný titulok nie je nový incident. Zmenené známe sumy alebo zmena opatrenia sa nezahodia. Deduplikácia je konzervatívna heuristika, nie dokonale overené NLP.
- Kontext správ odlišuje rezervy/sľub krytia a plán reštartu od skutočnej náhrady/obnovenia. Žiadne URL v Telegrame. Max. 3 udalosti, pri prázdnom výbere žiadna sekcia. Kalendár a oznámené makro výsledky zostávajú v existujúcom životnom cykle.
- Pri absolútnej zmene kapitalizácie aspoň 5 %: rozšírená kontrola dostupných US indexov/futures a makro/ETF/projektových podkladov s časmi, oddelene od udalostnej kauzality. Nedostupné likvidácie/páka nie sú nula. Bez dôkazu sa uvádza „Príčina prudkého pohybu zatiaľ nie je potvrdená.“ Táto vrstva nemení obchodné signály.
- WAIT uvádza potvrdenie 2 uzavretých 4H sviečok a objemu pri konkrétnej hranici, prípadne sledovanú podporu pre pullback po stabilizácii. Ide o informačné podmienky, nie novo aktivovanú stratégiu. Produkčné BUY/SELL výpočty a eToro náklady ostali nedotknuté.

## Testy a živé overenie

416 offline testov: empty inventory + ochrana budúceho nákupu, prechod držba/nový vstup, V2 referencia/neistota/RAST/POKLES a poškodené hodnoty, semantic copies vs nové opatrenie, prudký pohyb bez kauzálnej fikcie; existujúce zimný čas, delayed recovery, API/Telegram timeout, CAS, neisté odoslanie, event TTL a trendové scenáre.

Čistý CI posledného kandidáta: [V11.3 Release Validation](https://github.com/janmarticek4-dot/crypto-bot/actions/runs/41187978454).

Živý izolovaný náhľad: [Readiness](https://github.com/janmarticek4-dot/crypto-bot/actions/runs/41187721881) – 18/18, ranný aj večerný formát brief-v2, bez URL, po jednej časti, približne 2105 znakov oproti 4728 v detailnom reporte. Ide o dve formátové ukážky z jedného aktuálneho zberu, nie nezávislé ráno/večer! Finálny live kandidát: run 41187978448. Testy neposielajú Telegram a nečítajú portfólio na verejný náhľad.

## Zostávajúce obmedzenia

GitHub nemá časové SLA; žiadna bezplatná úprava cron negarantuje 07:00. Verejné zdroje nepokrývajú komplet všetky ázijské/európske trhy, likvidácie, páku, globálne toky ani všetky projektové metriky. Rozšírená kontrola nevyrába chýbajúce príčiny. Redakčná zhoda nie je dôkaz skutočnej nezávislosti pôvodných informácií. V2 zatiaľ nemá nezávisle potvrdenú užitočnosť ani kalibrované pravdepodobnosti. Nové potvrdené BUY pravidlá sa preto neaktivovali. Neistý Telegram pokus vyžaduje kontrolu; bez bezpečného dôkazu sa neopakuje.

## Súbory a rollback

`v11/v113.py`, `v11/compact_main.py`, `v11/event_notices.py`, `v11/prediction_runtime.py`, `v11/verified_monitor.py`, `scripts/v111_trial.py`, `scripts/v111_integrated_delivery.py`, `scripts/v2_production_preview.py`, `scripts/confirm_empty_inventory.py`, príslušné testy; run.yml, release validácia a production audit source pins. main.py a v11/strategy.py bez zmien.

Rollback je normálny pin-only commit, nikdy reset/force-push. Po novej evidencii nesmie obnoviť staré portfólio ani starý nekompatibilný čítač. Canonical sent/uncertain záznamy sa nemažú. Približný kapitál sa nenahrádza tajnou predvolenou sumou. Jednorazovú korekciu po potvrdení vypnúť; marker zostáva v súkromnom šifrovanom stave.
