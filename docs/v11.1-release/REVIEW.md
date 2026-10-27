# Analytická integrácia V11.1 — návrh, nenasadené

## Hranice

Jeden existujúci bot/repozitár. Žiadny E1/AdaptiveHold/backtesting, nové BUY/SELL filtre, burzové príkazy alebo výkonnostné predikcie. `main.py` a obchodné výpočty sú identické s produkčnou main. PR neobsahuje zmenu bot_state.json, denníka doručovania, skutočného portfólia ani Secrets. Súkromný modul je rovnaký ako v pôvodnom pilote; jeho údaje sa pripájajú až po uložení verejného denníka a nejdú do Artifacts.

## Kontrola produkcie 27.10.2026

Overená main `87a3143` (fetch počas prípravy). Od pôvodného baseline `3f21337` sa zmenili iba bot_state.json a trial-public/v111-delivery.json; produkčný main.py/workflow zostali rovnaké. Žiadny živý stav sa nevracia na starší snapshot. Konfigurácia pilota stále používa `929bd6389216be1b4eefcd1be61be89d944abf33`, environment production-advisory a existujúci denník `trial-public/v111-delivery.json`. Skutočný obsah Secrets ani súkromného repozitára sa nečítal; ich platnosť či nastavenie Repository Variables preto nie je týmto znovu potvrdené.

Workflow beží každých15 minút, s jednou concurrency skupinou. Natívna V10.6 pri zapnutom existujúcom pilote potláča vlastné plánované reporty; jej bezpečnostný monitor zostáva nezmenený. Pilot má Bratislava okná07:00–08:30,15:00–16:30 a20:00–21:30. USA fázu určuje New York a burzový kalendár, nie samotná bratislavská hodina. GitHub negarantuje presnú minútu spustenia; existujúci zdravotný dohľad zostáva, nevytvára sa ďalší odosielateľ.

## Zmeny na kontrolu

- Stručný analytický renderer, nie aktivácia novej stratégie. Pôvodné V10.6 signály sa zobrazujú ako TECHNICKÝ SELL/REDUCE s výslovným upozornením, že nejde o potvrdenú predikciu ďalšieho poklesu ani osobný pokyn predať. Nevlastnená minca neznamená osobný pokyn na predaj. Súkromné predbežné posúdenie držby zostáva samostatné a nezmenené.
- Overiteľné fundamenty, kalendáre a ekonomické metriky s dátumom/zdrojom, klasifikácia aktuálnosti a fallbackov, zoskupenie duplicitných udalostí. Marketing/kód/governance bez ekonomického dôkazu nie sú hlavné fundamenty. Výnosy v bp, kapitalizácia/objemy/TVL nie sú čisté toky.
- Ranné verejné quotes obsahujú čas a fingerprint zdrojových dát. Večer sa referencia prijme iba z rovnakého bratislavského dňa, s odstupom8–16h a rozdielnym fingerprintom. Stará schéma, chýbajúce ráno alebo rovnaký snapshot →N/A. Ceny, kapitalizácie, objemy, trend a signály ostávajú v podrobnej diagnostike; stručná správa obsahuje cenu/pokyn a zmeny fundamentálneho výberu. Vypadnutie z výberu nie je potvrdením zániku rizika.
- Žiadne nové experimentálne prognózy sa neukladajú/neaktivujú. Staršie doručené prognózy sa môžu vyhodnotiť až po horizonte, bez propagácie úspešnosti.
- Podrobné verejné diagnostiky sa vytvárajú pred načítaním súkromných pozícií: analysis_details.txt, risk_diagnostics.json, fundamental_evidence.json, market_snapshot.json. Pred zápisom prejdú verejnou dátovou kontrolou. Artifacts nikdy neobsahujú raw bot_state, súkromný text ani celý verejný doručovací denník.
- Navrhovaný workflow použije nový analytický zdroj iba pri výslovnom zapnutí V111_INTEGRATION_ENABLED=true; inak ponechá presne starý pripnutý zdroj/entrypoint/testy. Žiadna nová tajná hodnota nie je potrebná. Existujúci V111_TRIAL_ENABLED musí zostať true.
- Pre/post kontrola verejného stavu odmieta poškodenie, prázdny reset, súkromné polia a stratu pôvodných koreňových sekcií. Metadata obsahujú iba názvy sekcií v RUNNER_TEMP, nie hodnoty. Rebase konflikt sa prestane ignorovať. Kontrola nie je úplný dôkaz sémantickej správnosti každého poľa; natívny kód stavu sa nemení.

## Deduplikácia a zostávajúce riziká

Existujúci pilot zapíše slot so statusom attempting cez GitHub SHA/CAS ešte pred Telegramom. Sent, attempting aj uncertain sa pri ďalšom behu neposielajú. Konflikt pri zápise zastaví odoslanie. Telegram má jeden pokus na časť; po timeout sa neodosiela automaticky znova. To uprednostňuje neprítomnosť duplicít pred garantovaným doručením. Čiastočne odoslanú správu/uncertain musí človek preveriť, slot sa automaticky nemaže. Starý journal sa nesmie resetovať pri nasadení ani rollbacku.

Natívny V10.6 monitoring/manual analysis má vlastný pôvodný retry mechanizmus a pri neurčitom Telegram timeoute môže duplicitu vytvoriť. Táto integrácia ho nemení; nemožno tvrdiť absolútnu exactly-once garanciu celej produkcie. Nespúšťať ručnú natívnu analýzu v časových oknách plánovaného pilota.

Posledný dodaný runner Artifact `40504368871` ukázal úplné ceny6 mincí, no len14 aktuálnych výsledkov z32 endpoint pokusov. AAVE TVL prekračuje limit payloadu, ONDO primárny zdroj404 a chýbajúce aktuálne TVL, Treasury timeout so zálohou FRED; starší RSS nie je sieťový výpadok. ETF toky, úplná geopolitika, unlocky a používatelia všetkých projektov nie sú pokryté. Zostáva N/A alebo časovo označené obmedzenie; tieto nedostatky sa vydávajú za nedostatky, nie za dokončené pokrytie. Nový commit sa ešte netestoval živým runnerom ani reálnou rannou/večernou dvojicou. Groq nie je potrebný pre rozhodovanie ani deterministické vysvetlenie a v tomto releasi sa nezapína nový platený/AI krok.

## Overenie a aktivácia

Presné kroky v ACTIVATION.md. Offline testy sa spúšťajú bez nemockovanej siete. Zahŕňajú paritu V10.6, ochranu stavu, súkromný canary mimo verejného denníka, doručovací CAS/deduplikáciu, warning, neúplné dáta, fundamenty, DST/sviatky USA a odmietnutie rovnakého ranného snapshotu. Testy USA sú adaptované na reálny pilotný routing; nepoužíva sa novší review-only main.py runtime. Samotná produkčná stratégia sa nevaliduje ako zisková.
