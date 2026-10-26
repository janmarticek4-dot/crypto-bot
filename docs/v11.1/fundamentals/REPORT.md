# Výsledok vývojovej úpravy fundamentov – 26. 10. 2026

Zmeny výhradne `feature/v11-1-review`. Žiadna aktivácia stratégie, zmena BUY/SELL pravidiel, merge, nasadenie, Telegram odoslanie alebo prístup ku skutočnému portfóliu.

## Čo sa zlepšilo

1. Fundamentálne vyhodnotenie prichádza pred jednotlivými detailnými mincami. Udalosť má zdroj, publikovanie/zber, významnosť, podmienený dopad, dotknuté mince a ďalšie potrebné potvrdenie. Cenový pohyb nedostáva vymyslenú príčinu.
2. Samostatné fundamentálne bloky SOL/TAO/FET/AAVE/ONDO/RENDER; TVL a dostupné denné ekonomické agregáty sa neinterpretujú ako peňažný tok alebo výnos tokenu.
3. Marketing, partnerstvo, GitHub vydanie, governance návrh a titulkové cenové predikcie nie sú automaticky pozitívne alebo významné fundamenty. Rovnaký titulok z viacerých URL nie je nové nezávislé potvrdenie.
4. Doplnená zmena výnosov 2Y/10Y, predchádzajúce revidované makro merania a adaptéry Aave fees/revenue + Solana fees. Tieto adaptéry ešte vyžadujú úspešné živé overenie mimo blokovaného cloudového proxy.
5. AI iba vyberá existujúce ID; zlyhanie/429/nepriraditeľné tvrdenie nemení faktické znenie alebo obchodné rozhodnutie.
6. Opravený nesúlad času snapshotu a neskoršieho zberu správ, ktorý mohol vytvárať falošné N/A; opravené falošné geopolitické zhody `war` vo `warns` a `software` a nesprávne zaradenie každej zmienky ECB ako sadzbového rozhodnutia.
7. Technické čísla sú v prílohe, kapitalizácia/objemy používajú T/B/M a vek dát je zaokrúhlený. Nie všetka duplicita rozsiahlej pôvodnej šablóny je odstránená.

## Skutočne vykonané testy

- `python scripts/test_offline.py`: **275 testov OK**, vrátane 23 nových testov. Bez nezamockovanej siete. Dátové výpadky, staré/budúce udalosti, duplicity naprieč vydavateľmi, nekorektné dáta, AI výpadok/429/fabrikované ID/cache, uzavreté denné agregáty a reportový čas.
- Živý izolovaný zber: **26. 10. 2026 21:01:29 Bratislava**, kompletné aktuálne dáta všetkých šiestich mincí. Príkaz `scripts/v111_shadow.py --phase preview --output shadow-output/fundamentals-final-verified`, bez `--use-groq`.
- Fundamentálne endpointy **8/16 dostupných**: Aave, Ondo, SOL GitHub, TAO GitHub, FET GitHub, RENDER GitHub, CoinDesk, Cointelegraph. Dostupnosť neznamená novú významnú správu.
- Nedostupné: FOMC kalendár, Fed RSS, BLS RSS/ICS, BEA, ECB, CFTC, SEC; primárne a nastavené zálohy blokované tunelom **CONNECT 403 / network_tunnel**, nie preukázaná chyba pôvodných serverov. Treasury/FRED a DeFiLlama metriky tiež nebolo možné načítať z tohto prostredia. Detaily URL a pokusov sú v `LIVE_EVIDENCE.json` a lokálnom `source_availability.json`.
- Očakávania sadzieb, makro výsledky, výnosy, overené toky a ekonomické metriky v tomto konkrétnom zbere nepotvrdené. Matica má **0/10 čiastočne doložených tematických okruhov** podľa prísnych podmienok. Existujú sekundárne kontextové titulky, ale nie overené makro hodnoty či nové potvrdené projektové udalosti. Tento výsledok nie je všeobecný výrok, že pôvodné servery nefungujú.
- Izolované fault-injection kontroly shadow: **PASSED**. Publikačný privacy gate: **PASSED**. Chránené súbory nezmenené; Telegram vypnutý; produkčný stav a portfólio nenačítané; obchody vypnuté.
- Groq živé API nebolo volané: deterministický režim + zamockované chyby; aktuálna reálna kvóta a kvalita AI nie sú overené.

## Ukážky a reprodukovateľnosť

- `MORNING_PREVIEW.txt`, `EVENING_PREVIEW.txt`: živé údaje z jedného času, dve ukážky šablóny. **Nie sú nezávislým ranným a večerným pozorovaním.** Žiadne doplnenie fiktívneho ranného snapshotu.
- `LIVE_EVIDENCE.json`: zdroje, chyby a štruktúrované významové vyhodnotenie pre uvedený zber.
- Lokálny kompletný výstup: `shadow-output/fundamentals-final-verified/`; bezpečne prefiltrovaný: `shadow-public-artifacts/fundamentals-final-verified/`.
- Manuálny GitHub-hosted shadow postup je v `DESIGN.md`. V tejto úlohe nebol spustený GitHub Actions beh; miestny živý shadow skutočne prebehol. Reálne ranné/večerné overenie stále vyžaduje dva časovo oddelené behy.

## Čo ešte chýba

Toto nie je hotová úplná fundamentálna služba. Najväčšia medzera je získavanie a overovanie primárnych dokumentov a kvantitatívnych udalostí, nie jazykový model. Ešte treba úspešne preveriť nové API na GitHub-hosted runneri, rozšíriť spoľahlivé ekonomické metriky a tokenomiku ostatných štyroch projektov, pridať licenčne vhodné unlocky/ETF toky, prvé makro výsledky a konsenzus, dlhšie platné faktory s dátumom expirácie a vyhodnotenie účinnosti udalostí. Presný podiel všetkých významných informácií je **neznámy**.

Pravidlá významnosti sú konzervatívne heuristiky; titulok neoveruje telo dokumentu. Táto verzia dáva vysvetliteľné podmienené hodnotenie, nie potvrdený fundamentálny smer každej mince za každú cenu. Odporúčanie: najskôr runner shadow a kontrola obsahu; **nenasadzovať automaticky**.
