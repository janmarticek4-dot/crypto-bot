# Skutočné ranné a večerné shadow pozorovanie

## Rozsah a zistenia

Úpravy iba `feature/v11-1-review`. Produkčná `main`, jej workflow, Telegram, portfólio, súkromné úložisko, monitoring ani obchodné pravidlá sa nemenia. Test nepotrebuje žiadne používateľské Secrets; AI sa v automatických pozorovaniach nevolá.

GitHub verejne potvrdzuje úspech behu **40403126924** na commite **c7707dd**. Obsah jeho ZIP artifactu nebol v tomto pracovnom prostredí stiahnutý; nezamieňame úspech workflow s nezávislou kontrolou každej položky ZIP. Nasledujúce opravy vychádzajú z kontroly kódu a reprodukovateľných regresných testov.

- Výpočet výnosov už používal `(nová sadzba − stará sadzba) × 100`. Označenie je teraz explicitné **bp (bázické body)**. Test 4,65 % → 4,69 % dáva **+4 bp**, teda +0,04 percentuálneho bodu.
- Poplatky/príjmy mali preukázanú chybu: 48-hodinový filter aktuálnosti odstraňoval aj predchádzajúci denný bod. Teraz musí byť čerstvý posledný uzavretý denný bod, predchádzajúci sa hľadá medzi platnými staršími bodmi do 30 dní. Zobrazujú sa konkrétne obdobia; nepredstierame susedné dni, ak chýbajú.
- TVL dostáva posledný a predchádzajúci dostupný bod. Budúce, nečíselné, záporné alebo neplatné body sa nepoužijú. Čerstvosť posledného bodu zostáva do 48 h.
- Deterministické zoskupenie veľmi podobných titulkov zachováva všetky citácie a vydáva jeden záver. Rozdielne numerické výsledky, inštitúcie alebo schválenie vs. návrh/zamietnutie sa nezlučujú. Ide o konzervatívnu heuristiku, nie dokonalé rozpoznanie každej parafrázy.
- Úspešný parser/transport, aktuálny relevantný obsah a tematické pokrytie sú tri samostatné údaje. Starý dostupný feed nie je aktuálny fundament a nová GitHub verzia nie je dôkaz adopcie.
- Skrátené opakované fundamentálne upozornenia a opakovaný makro kalendár pri každej minci; podrobné technické indikátory zostávajú v prílohe.
- Trhová kapitalizácia, TVL a objem nie sú čisté toky kapitálu. Zmena objemu porovnáva dve priebežné 24-hodinové okná. Chýbajúci predchádzajúci bod zostáva N/A.

## Ako fungujú dva nezávislé zbery

`V11.1 Temporal Shadow` zbiera údaje len v skutočných oknách **07:00–08:30** a **20:00–21:30 Europe/Bratislava**. Zobrazuje skutočný čas, nie predstieraných 07:00/20:00. Časové pásmo IANA automaticky rieši letný a zimný čas. GitHub negarantuje presný čas spustenia.

Ranný artifact obsahuje nemeniteľný checkpoint: verejný trhový snapshot, experimentálne odporúčania, fundamentálne podklady, dátum, zdrojový commit, odtlačok zdrojových údajov a kontrolný súčet vrátane fundamentov. Večer sa uskutoční nový sieťový zber. Referencia musí byť z úspešného samostatného behu toho istého dňa a rovnakého zdrojového commitu.

Porovnanie odmietne rovnaký zdrojový fingerprint, krátky odstup, iný deň/commit, poškodený checksum a neaktuálne trhové dáta. Dátum zberu sa nedá zadať CLI prepínačom. Pri chýbajúcom ráne sa večerný zber zachová, ale porovnanie je **N/A**. Neplatná referencia spôsobí N/A a neúspech testu, nie tichú náhradu.

Večerné výstupy porovnávajú ceny, kapitalizáciu, 24h objemy, technický trend a odporúčania všetkých šiestich mincí. Fundamenty rozlišujú nové publikované udalosti, aktualizované publikácie a nezmenené skupiny. Neprítomnosť správy neznamená vyriešenie rizika. TVL/poplatky/príjmy majú samostatné zmeny a označenie **DIFFERENT_PERIODS**, **SAME_PERIOD_UNCHANGED**, **SAME_PERIOD_REVISION** alebo **N/A**.

## Prečo nie schedule vo vývojovej vetve pôvodného repozitára

GitHub spúšťa `schedule` len z predvolenej vetvy. Preto pôvodný repozitár dostáva iba manuálny/reusable workflow, bez cron triggera. **Nepridávaj kvôli testu nič do produkčnej main.**

### Bezpečné automatické spustenie bez produkčného nasadenia

1. Vytvor samostatný repozitár **`crypto-bot-shadow-research`**. Môže byť verejný, pretože obsahuje iba verejné analytické testy; môže byť aj súkromný v rámci dostupnej Actions kvóty. Nepoužívaj žiadny repozitár privátneho stavu.
2. V novom repozitári nastav **Settings → Secrets and variables → Actions → Variables → New repository variable**:
   - Name: `SHADOW_RESEARCH_ONLY`
   - Value: `true`
3. V novom repozitári vytvor súbor **`.github/workflows/shadow-temporal.yml`**. Skopíruj doň celý obsah vedľajšieho súboru **`shadow-temporal.yml.example`**. Použi rovnaký pevný 40-znakový commit na oboch miestach `uses ... @SHA` a `source_sha`. Pripravená verzia po dokončení obsahuje konkrétny commit vývojovej implementácie.
4. Ulož súbor do **predvolenej vetvy nového výskumného repozitára**. Toto nie je main pôvodného kryptobota ani produkčné nasadenie. V nastavení Actions musia byť povolené GitHub Actions a volanie verejného reusable workflow.
5. Nepridávaj Telegram, Groq, PAT ani šifrovacie kľúče. Runtime GitHub token má iba `contents: read` a `actions: read` vo výskumnom repozitári.
6. Prvé skutočné ráno sa uloží pri najbližšom rannom okne; večer sa automaticky načíta z artifactu. Nemeniť zdrojový pin počas jedného dňa — inak bude referencia pre nový pin chýbať a výsledok správne N/A.
7. Výsledky: **Actions → Automated Research Shadow → konkrétny beh → Artifacts**:
   - `v111-temporal-morning-YYYY-MM-DD-<SOURCE_SHA>`
   - `v111-temporal-evening-YYYY-MM-DD-<SOURCE_SHA>`
8. V ZIP otvor **`comparison.txt`**, **`comparison.json`**, **`summary.json`**, **`morning.txt` / `evening.txt`**, **`fundamentals.json`** a **`artifact_privacy.json`**. Uchovanie 14 dní slúži verejným testom, nie skutočnému portfóliu. Automatický test vypneš vypnutím workflow v novom repozitári.

Cron skúša obe UTC sezónne možnosti v hodinách 5–7 a 18–20, vždy :00/:15/:30. Až kontrola skutočného času Bratislava dovolí zber. Opakovaný úspešný slot toho istého dňa/pinu sa preskočí. Concurrency zabráni súbežnému zápisu; ráno sa nikdy neprepisuje. Pri úplne vynechanom behu nie sú vymyslené údaje; večer oznámi chýbajúcu referenciu N/A. Pri neaktivite verejného research repozitára môže GitHub schedule automaticky deaktivovať; stav workflow treba priebežne kontrolovať.

## Manuálne overenie v pôvodnej vývojovej vetve

Počas ranného alebo večerného okna otvor https://github.com/janmarticek4-dot/crypto-bot/actions/workflows/run.yml → **Run workflow → feature/v11-1-review → task: temporal-shadow**. Tento vstup volá rovnaký izolovaný workflow. Mimo reálneho okna sa zber preskočí. Neaktivuj private-state ani advisory import.

Ak formulár vetvy neponúkne nový task:

```sh
gh workflow run run.yml --repo janmarticek4-dot/crypto-bot --ref feature/v11-1-review -f task=temporal-shadow
```

Prípadne spusti priamo **V11.1 Temporal Shadow**, ak ho GitHub už eviduje. Žiadny merge do main nie je potrebný.

## Výsledky a obmedzenia tejto úpravy

- **314 offline testov prešlo**; z toho 18 nových regresných/integračných testov. Kontrolujú presnú jednotku bp, zachovanie staršieho porovnávacieho bodu, TVL, deduplikáciu a nezlučovanie rozdielnych tvrdení, dostupnosť vs. aktuálnosť/pokrytie, obe zmeny DST, checksum fundamentov, chýbajúce ráno a odmietnutie recyklovaného snapshotu.
- YAML oboch workflow a oddelenej šablóny bol overený. Dvojica v unit testoch je jasne syntetická; nie je výkonnostným ani živým časovým overením.
- Jednorazový živý náhľad **26. 10. 2026 22:29 Bratislava** mal kompletné trhové dáta všetkých šiestich mincí a nezmenené chránené súbory. Je to iba náhľad mimo plánovaného slotu, nie skutočná ranná/večerná dvojica. Lokálne proxy obmedzenia makro/DeFiLlama zdrojov trvajú; predchádzajúci úspešný GitHub beh tieto lokálne sieťové podmienky nenahrádza.
- Prvý automatický skutočný pár ešte **neprebehol**: treba vytvoriť výskumný repozitár alebo vykonať dva manuálne behy v reálnych oknách. Dnes nie je možné spätne vyrobiť ranný zber. Neuvádzame úspech deployu, schedule ani porovnania, ktoré sa nestalo.
- Stále nejde o úplné fundamentálne pokrytie ani validáciu obchodnej stratégie. Semantická deduplikácia je konzervatívna a môže vynechať vzdialenejšie parafrázy. Dátové výpadky môžu vytvoriť N/A. Ak chýba celý večerný beh, nebude ani večerný artifact — samotný schedule nezaručuje doručenie.

## Pevný zdroj pripraveného automatického testu

Pripravená šablóna už obsahuje commit **`dedf8427ac83fbfea5daef14078ba95fe2015950`** na oboch miestach. Obsah súboru `shadow-temporal.yml.example` stačí celý skopírovať do výskumného repozitára pod uvedeným názvom. Tento commit obsahuje otestovanú implementáciu; neskoršie čisto dokumentačné úpravy nevyžadujú zmenu pinu.
