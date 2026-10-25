# Súkromné šifrované úložisko — integračný test pred migráciou

**PRIPRAVENÉ, ZATIAĽ NESPUSTENÉ PROTI SKUTOČNÉMU GITHUB ÚLOŽISKU.**
Repozitár ani Secrets tento vývojový krok nevytvára. Nasledujúce nastavovacie
kroky sa vykonajú až po schválení používateľom. main, bot_state.json, Telegram
ani reálne portfólio sa nemenia. Test nie je produkčná migrácia.

## Čo test urobí po schválení

Workflow: **Private Encrypted State Integration Test**.
Skript: scripts/private_state_integration.py. Iba cryptography a štandardná knižnica;
neimportuje main, portfólio, trhové API, Telegram ani Groq.

1. Vyžaduje výslovný súhlas so syntetickým zápisom/corruption testom.
2. Vyžaduje cieľ owner/crypto-bot-state-integration-test, PRIVATE a nearchivovaný;
   cieľ nesmie byť verejný kódový repozitár. Overí full_name aj povinný marker.
3. Odmieta neočakávané koreňové súbory/cesty vrátane prod. Marker je výslovné
   vyhlásenie správcu, nie kryptografický dôkaz obsahu celého repozitára.
4. Vytvorí nový stav iba v test/integration/run-<run_id>-<attempt>/state.enc;
   staré testy, test/state.enc a prod/state.enc nie sú cieľom žiadneho zápisu.
   Namespace je viazaný aj AES-GCM AAD. Bez namespace ostáva pôvodný backend
   kompatibilný; produkčné cesty ani AAD sa nemenia.
5. Inicializuje syntetický ledger, overí ciphertext a nezávislé opätovné čítanie,
   odmietne opätovnú inicializáciu, zapíše zmenu a overí šifrovanú zálohu.
6. Dvaja paralelní zapisovatelia načítajú rovnaký SHA: musí uspieť presne jeden,
   druhý skončiť konfliktom. Výsledok sa znovu načíta a porovná s víťazom.
7. Negatívny test prístupu: skutočný HTTPS GET s úmyselne neplatným syntetickým
   tokenom musí byť odmietnutý401/403/404; platný testovací token sa NERUŠÍ.
   Strata oprávnenia počas PUT je samostatne INJEKTOVANÁ a tak aj označená;
   netvrdíme, že bol skutočnému tokenu odobratý scope alebo zrušený účet.
8. Nesprávny dešifrovací kľúč sa odmietne. Potom sa úmyselne poškodí výlučne
   ciphertext nového syntetického behu. Bežné čítanie musí zastaviť bez resetu.
9. Obnova proti nesprávnemu SHA sa odmietne; riadená obnova autentifikovanej
   zálohy proti presnému aktuálnemu SHA musí obnoviť pôvodný syntetický ledger.
10. Výstup obsahuje iba pevné názvy kontrol a booleany/stav. Žiadny ciphertext,
    API odpoveď, zostatok, množstvo, nákupná cena, canary alebo kľúč sa neukladá
    do logu, Summary ani Artifactu. Plaintext zostáva iba v pamäti procesu.

Testovacie vzory sú syntetické a ich konštrukcia je verejná v kóde; žiadna
časť sa nepreberá z reálneho bot_state.json. Ani šifrované testovacie súbory sa
neexportujú z privátneho repozitára do verejného Actions Artifactu.
Po zlyhaní môže zostať v danom run namespace poškodený syntetický súbor; neobnovuje
sa potichu ani nemaže. Ďalší run_attempt dostane novú cestu. Vzdialené testovacie
verzie/zálohy ostávajú privátne na kontrolu. Retenciu/mazanie schváli správca zvlášť.

## A. Vytvorenie osobitného PRIVATE repozitára — až po schválení

V GitHube pod účtom janmarticek4-dot:

1. Klikni vpravo hore **+ → New repository**.
2. Owner: janmarticek4-dot. Repository name: **crypto-bot-state-integration-test**.
3. Vyber **Private**. Zaškrtni **Add a README file**. Create repository.
4. Over v záhlaví označenie **Private**. Nezapínaj Pages ani verejné zrkadlenie.
5. **Add file → Create new file**, názov presne **STATE_INTEGRATION_ONLY.json**.
   Vlož tento NECITLIVÝ marker, Commit changes do predvolenej vetvy test repo:

```json
{
  "schema": 1,
  "purpose": "crypto-bot-state-integration-only",
  "synthetic_only": true,
  "allow_destructive_tests": true
}
```

Repozitár musí zostať vyhradený iba pre syntetické testy. Nedávaj sem produkčný
stav, produkčné kľúče alebo skutočné investície. Samotný test nevytvára repo,
nenastavuje jeho viditeľnosť a nedokáže túto deklaráciu nahradiť.

## B. Fine-grained token — iba k tomuto testovaciemu repozitáru

1. GitHub profil → **Settings → Developer settings → Personal access tokens →
   Fine-grained tokens → Generate new token**.
2. Token name napr. **crypto-bot-state-integration-only**, krátka expirácia
   napr.7 dní. Resource owner: janmarticek4-dot.
3. **Repository access → Only select repositories → crypto-bot-state-integration-test**.
   NEVYBER crypto-bot ani budúce produkčné stavové repo; nie All repositories.
4. **Repository permissions → Contents: Read and write**.
   **Metadata: Read-only** je potrebné/štandardné. Ostatné oprávnenia nepridávaj.
   Nepotrebuje Administration, Actions, Workflows, Secrets, účet ani obchodné API.
5. Generate token. Hodnotu kopíruj priamo do GitHub Environment Secret podľa C.
   Neposielaj ju do chatu, issue, súboru, screenshotu, terminálového príkazu ani logu.
   Organizácia môže vyžadovať samostatné schválenie tokenu správcom.

Token má zápisové právo iba v dedikovanom test repo; workflow GITHUB_TOKEN má
v repozitári s kódom len contents:read. Kód nepoužíva token na vytvorenie repo
ani na zmenu oprávnení. Negatívny auth test nemení ani nezneplatňuje skutočný PAT.

## C. Chránené testovacie prostredie a Secrets — v repozitári S KÓDOM

Otvor **janmarticek4-dot/crypto-bot → Settings → Environments → New environment**.
Názov presne **state-storage-integration**.

1. **Deployment branches and tags → Selected branches and tags**: povoľ iba
   branch **feature/v11-1-review**. Nepouži pravidlo, ktoré omylom povoľuje ľubovoľné PR.
2. Nastav required reviewer na dôveryhodného kontrolóra, ak to tvoj plán podporuje.
   Pred schválením behu treba skontrolovať commit a diff workflow. Pri jednom
   správcovi zohľadni nastavenie prevent self-review, aby schvaľovanie nebolo nemožné.
   Secrets ochrana nenahrádza review: schválený kód s tokenom môže čítať jeho scope.
3. **Environment variables → Add variable**:

| Názov | Hodnota |
|---|---|
| TEST_STATE_REPOSITORY | janmarticek4-dot/crypto-bot-state-integration-test |

4. **Environment secrets → Add environment secret**:

| Názov | Čo vložiť |
|---|---|
| TEST_STATE_TOKEN | Fine-grained token z B, iba pre test repo |
| TEST_STATE_ENCRYPTION_KEY | Base64 kódovanie32 kryptograficky náhodných bajtov; nový výlučne testovací kľúč |

Nejde o STATE_REPO_TOKEN/STATE_ENCRYPTION_KEY produkcie. Nepoužívaj produkčný
kľúč ani token. Secrets nastav v Environment verejného KÓDOVÉHO repo, nie iba
v testovacom stavovom repo; inak ich tento workflow nebude mať k dispozícii.
Kľúč neukladaj do repozitára, markeru, Artifacts ani používateľských premenných.

### Testovací AES kľúč vo Windows — bez vypísania hodnoty

Nasledujúci príkaz je iba postup pre neskorší SCHVÁLENÝ nastavovací krok. Codex
ho nevykonal a žiadny skutočný kľúč nevygeneroval. V dôveryhodnom lokálnom
PowerShelli skopíruje nový testovací kľúč priamo do schránky, nevypíše ho:

```powershell
$stateTestBytes = New-Object byte[] 32
$stateTestRng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
$stateTestRng.GetBytes($stateTestBytes)
Set-Clipboard -Value ([Convert]::ToBase64String($stateTestBytes))
[Array]::Clear($stateTestBytes, 0, $stateTestBytes.Length)
$stateTestRng.Dispose()
```

Vlož cez Ctrl+V iba do hodnoty TEST_STATE_ENCRYPTION_KEY v GitHub Secrets a ulož.
Ak potrebuješ uchovať kľúč na neskoršiu kontrolu syntetických záloh, použi svoj
súkromný správca hesiel; nie toto vlákno. Schránku potom vyčisti:

```powershell
Set-Clipboard -Value ''
```

Do histórie terminálu nevkladaj príkaz obsahujúci doslovnú hodnotu kľúča alebo
PAT. Nepoužívaj deterministické jednotkové testovacie vektory ako Secrets.

## D. Manuálne spustenie — iba po dokončení a schválení A–C

Nový workflow nemusí byť viditeľný v Actions, kým nie je na predvolenej vetve.
Kvôli tomu NEMEŇ main. Použi existujúcu registrovanú vstupnú cestu:

https://github.com/janmarticek4-dot/crypto-bot/actions/workflows/run.yml

1. **Run workflow → branch feature/v11-1-review** (nie main).
2. **task = private-state**.
3. Zaškrtni **confirm_private_state_test** iba ak A–C sú skontrolované a cieľ
   je naozaj samostatné syntetické PRIVATE úložisko. phase/morning_run_id sa nepoužijú.
4. Run workflow. Ak sa zobrazí Review deployments, skontrolovať a schváliť
   **state-storage-integration** pre konkrétny commit.
5. V behu beží reusable workflow **Private Encrypted State Integration Test**.
   Bez potvrdenia skončí authorize job pred prístupom k testovacím Secrets.
6. Výsledok: **Summary → Artifacts → private-state-integration-<ID>-<pokus>**.
   ZIP obsahuje iba **report.json**, nie ledger, šifrované zálohy alebo raw logy.
   PASSED vyžaduje kompletné kontroly; FAILED + failure_stage uvádza prvú
   nedokončenú kontrolu. api_requested=true iba pri reálnom spustení runnera.

Pri priamom prístupe k novému workflow z vývojovej vetvy možno použiť jeho
workflow_dispatch s confirm_synthetic_writes=true, ak už GitHub dovolí registráciu.
Žiadne automatické spúšťanie, Telegram, produkčný deploy ani migrácia sa nepridávajú.
Nepoužívaj Re-run starého kódu; nový beh spusti na poslednom schválenom commite.

## E. Čo úspech nepreukazuje

- Nejde o migráciu/obnovu skutočného portfólia ani test produkčných credentials.
- Negatívny auth GET je live; write access loss je explicitne injektovaný scenár.
  Zrušenie reálneho tokenu/odobratie oprávnení počas PUT sa nerobí.
- Žiadny automatizovaný test nedokazuje, že kompromitovaný runner, závislosť alebo
  budúca zmena workflow nemôže exfiltrovať secrets. Vyžaduje sa dôveryhodný commit,
  kontrola oprávnení a schvaľované testovacie prostredie.
- Strata kľúča, globálna nedostupnosť GitHubu, disaster recovery mimo GitHubu a
  rotácia kľúčov sú ďalšie prevádzkové kroky, nie výsledok tohto testu.
- GitHub rate-limit/výpadok môže test ukončiť. Chyba sa neprezentuje ako úspech
  a výnimka/API telo sa nevypisujú. V report.json je iba bezpečný názov fázy.
