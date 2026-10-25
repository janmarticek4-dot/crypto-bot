# Audit uchovávania stavu V11.1

Dátum: 25.10.2026. Vetva: feature/v11-1-review. Iba vývojové zmeny.
Žiadna migrácia, žiadny zásah do produkčného stavu, portfólia alebo Telegramu.

## Rozsah a dôkazy

Skontrolované: main.py (iba perzistencia), v11/secure_state.py, delivery.py,
portfolio.py, shadow runner, všetky aktuálne workflow a neaktívny dokumentovaný
návrh produkčného workflow. Prečítané aktuálne bot_state.json checkoutu a
origin/main bez vypísania ich obsahu. Aktuálne sledované textové súbory skontrolované
na známe vzory prístupových údajov. Výsledok s hashmi, nie hodnotami: EXPOSURE_CHECK.json.
Snapshot origin/main je da12eaa; nejde o audit každého neskoršieho produkčného behu.
História všetkých commitov, všetky už publikované Artifacts, externé logy ani
skutočné secrets účtu neboli kompletne auditované. Žiadny skutočný token/kľúč
sa nevytvoril, nevypísal ani neposlal. Testovacie kľúče sú verejné deterministické
syntetické vektory; nonce nie je prihlasovací kľúč.

## Konkrétne riziká

| Oblasť | Zistenie | Stav |
|---|---|---|
| Produkčný verejný stav | main workflow V10.6 commit/push bot_state.json do verejného repozitára | NEOPRAVENÉ V PRODUKCII; súkromná evidencia tam nesmie byť migrovaná |
| Aktuálne kontrolované stavy |0 detegovaných súkromných polí,0 známych vzorov tokenov | Nie dôkaz, že celá história alebo ľubovoľný voľný text je bez citlivých údajov |
| Artifacts | Shadow nahrával celý pracovný adresár | Opravené vo vývojovej vetve: povoľovací zoznam + kontrola + oddelený staging |
| Summary | JSON/porovnanie sa mohli zverejniť aj pri odmietnutí uploadu | Summary teraz číta iba overený staging |
| Verejný zápis V11 | Strážil iba portfolio_v11, inak pomenované vnorené súkromné polia mohli prejsť | Doplnená kontrola dátovej hranice pri zápise do verejného checkoutu |
| Lokálny tmp súbor | Predvídateľné meno a nasledovanie symlinku mohli prepísať iný súbor | Náhodný exkluzívny tmp0600, atomická výmena, odmietnutie symlinkov |
| Chýbajúca lokálna privátna kópia | load_state mohol vrátiť{} aj pri aktívnom privátnom backend-e | Fail-closed, žiadna tichá inicializácia |
| Existujúca záloha | Kontrolovalo sa len to, či existuje | Overenie jej obsahu voči pôvodnému checkpointu a autentifikácia |
| Obnova po korupcii | Pôvodný rollback predpokladal čitateľný aktuálny stav | Samostatná explicitná restore_backup s presným očakávaným aktuálnym SHA |
| Prostredie | Chýbajúce STATE_ENV implicitne vyberalo prod | Backend aj lokálna privátna cesta teraz vyžadujú explicitné test/prod |
| Replay/rollback | AES-GCM nebráni opätovnému použitiu starého platného ciphertextu oprávneným zapisovateľom | Zostáva: ochrana oprávnení, presná evidencia SHA a manuálne schválenie obnovy |
| Lokálny plaintext | Runtime musí dešifrovať údaje do pamäte/lokálnej privátnej kópie |0600/0700; budúci produkčný workflow musí zabezpečiť cleanup; teraz nie je nasadený |

## Oddelenie dát

**Verejné:** ceny, sviečky, technické indikátory, časované zdroje, všeobecné
scenáre, experimentálne odporúčania bez väzby na skutočnú držbu. Shadow nečíta
reálny ledger. Verejná nákupná zóna nie je skutočná nákupná cena používateľa.

**Súkromné:** celý reálny stav bota vrátane transakcií, nákladovej bázy,
pozícií, cash, zostatkov, príkazov Telegramu, offsetov a doručovacieho journalu.
Ukladať iba šifrovane v samostatnom PRIVATE repozitári, test/prod namespace,
oddelené oprávnenia a najlepšie samostatné kľúče. Celý stav možno uchovávať
súkromne; do verejných reportov sa nesmie automaticky serializovať celý stav.

**Prihlasovacie údaje:** len GitHub Secrets/ochránené prostredie, nie stav,
konfigurácia, report, .env v histórii alebo Artifact. Token stačí obmedziť na
metadata:read/contents:write konkrétneho privátneho stavového repozitára.
Žiadne obchodné oprávnenia ani burzové kľúče.

## Kontrola Artifacts

scripts/stage_shadow_artifacts.py pripraví iba schválené názvy súborov do
shadow-public-artifacts/. Odmieta symlinky, neznáme súbory, súkromné JSON polia,
známe tokenové/PEM vzory a prítomné hodnoty relevantných secretov prostredia.
Celú sadu overí pred kopírovaním. Pri chybe ponechá len artifact_privacy.json
s pevnou správou bez citlivého obsahu. Obnovené vstupné reference sa opäť nenahrávajú.
Kontrolný morning checkpoint ostáva dostupný, ale bez súkromného portfólia.

Toto nie je úplná sémantická DLP ochrana: ľubovoľná veta o súkromnej držbe,
zakódovaný údaj alebo úplne nový názov poľa nemusí byť rozpoznaný. Primárnou
hranicou je to, že shadow nemá privátne secrets/stav a reporty sa tvoria iba
z verejných dát. Kód s prístupom k privátnym secrets musí byť dôveryhodný a schválený.
Macro/research workflow v tomto audite nedostali portfólio ani stavové secrets;
ikdy sa do ich upload globov nesmie pridať privátna cesta/config s kľúčmi.

## Šifrovanie, zálohy a obnova

AES-256-GCM, náhodný12-bajtový nonce pri každom šifrovaní, AAD viazané na
repozitár a test/prod. Bounded dekódovanie/dekompresia, odmietnutie neplatného
nonce/verzie/NaN a nadmerného payloadu. GitHub base64 zalomenia riadkov sú
podporované; neplatné znaky nie. Zálohy sú autentifikované a nesmú sa ticho prepísať.
GitHub Contents SHA chráni proti zastaranému aj súbežnému zápisu.

read_backup(backup_sha) iba overí a prečíta zálohu. restore_backup(backup_sha,
expected_current_sha) je explicitná opravná operácia pre budúcu riadenú obnovu,
nevolá ju runtime ani workflow a nebola volaná na reálnom účte. Dokáže obnoviť
aj pri nečitateľnom aktuálnom ciphertext-e. Pri zmene aktuálneho SHA zastaví zápis.
Git história privátneho repozitára zachová predošlú verziu; pred reálnou opravou
sa musí overiť aj jej dostupnosť a bezpečne zaznamenať SHA pre forenznú obnovu.
Po timeoute počas obnovy sa nesmie slepo opakovať PUT: najprv overiť vzdialený SHA
aj dešifrovaný výsledok. Automatické riešenie tohto nejednoznačného výsledku nie je
súčasťou recovery metódy. Strata šifrovacieho kľúča znamená stratu obnoviteľnosti;
key escrow/rotácia ešte neboli prevádzkovo overené.

## Vykonané overenia

- AES-GCM roundtrip, odlišné nonce; nesprávny kľúč/repozitár/prostredie,
  poškodený ciphertext/nonce/verzia a limit veľkosti sú odmietnuté.
- Šifrované zálohovanie a obnova pôvodného syntetického ledgeru aj s legacy poľami.
- Aktuálny poškodený stav: bežné čítanie sa zastaví, bez resetu, zápisu alebo logu
  s plaintextom; riadená obnova z autentifikovanej zálohy funguje.
- Zmenený SHA, druhý zapisovateľ, súbeh medzi recovery GET a PUT a poškodená/cudzia
  existujúca záloha nesmú prepísať aktuálny stav. Opätovný initialize je odmietnutý.
- Verejný repo odmietnutý; explicitné prostredie; oddelené lokálne test/prod cesty.
- Lokálny zápis0600, adresáre0700, žiadne nasledovanie tmp/target/parent symlinku;
  neúspešná serializácia zachová pôvodný stav a uprace iba syntetický tmp súbor.
- Syntetické portfólio/credentials v Artifact-e, voľné súbory a symlinky vyvolajú
  odmietnutie celej sady; secret canary sa neobjaví ani v hlásení validátora.
- Morning checkpoint z reálnej kódovej cesty so syntetickými dátami prejde stagingom.
- Dodaný verejný shadow ZIP40233646376:17 súborov prešlo novou kontrolou, bez
  načítania reálneho portfólia. Výsledok je v VALIDATION.json.
- Lokálny bot_state.json po testoch má rovnaký hash ako pred zmenami; nie je v diff-e.

Testy používajú iba falošný GitHub transport a deterministické testovacie kľúče,
nie privátne GitHub API, reálne konto, Telegram alebo obchodné API. To nepreukazuje
prevádzkovú dostupnosť súkromného úložiska, nastavenie permissions ani disaster recovery
na skutočnom GitHub-hosted runneri. Tieto kroky ostávajú pred nasadením.
