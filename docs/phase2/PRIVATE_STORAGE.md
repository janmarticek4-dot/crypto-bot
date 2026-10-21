# Súkromné trvalé úložisko (navrhnuté a implementované, zatiaľ nenasadené)

Použijeme samostatný **private GitHub repozitár** ako malé osobné úložisko
šifrovaných checkpointov. GitHub Free podporuje private repozitáre; nejde o novú
platenú službu, ale stále platia limity GitHub API/úložiska a podmienky účtu.
GitHub Actions artifacts NIE SÚ primárne ani jediné úložisko.

## Čo je implementované

- `v11/secure_state.py`: AES-256-GCM s náhodným 96-bitovým nonce; kompresia pred
  šifrovaním. AAD viaže dáta na konkrétny repo identifikátor a `prod`/`test`.
- Vzdialený obsah má iba verziu formátu, nonce a ciphertext. Žiadne kľúče,
  Telegram tokeny, Groq tokeny ani osobné hodnoty nie sú v commite/logu.
- Pred každým čítaním/zápisom sa overí `private=true`. Public/missing repo,
  chýbajúci stav, zlý kľúč alebo poškodenie sa odmietnu; žiadny automatický reset.
- Optimistický compare-and-swap cez GitHub Contents API `sha`; konflikt
  nesmie prepísať súbežný ledger. Job concurrency zostáva ďalšia vrstva ochrany.
- Pred zmenou checkpointu sa uloží nemenná šifrovaná záloha pod
  `<env>/backups/<previous-content-sha>.enc`. Git commit história uchová aj staré verzie.
- Ledger a Telegram offset sa zapíšu vzdialene **pred potvrdením príkazu**.
  Pri timeout po úspešnom PUT sa presná hodnota overí čítaním namiesto slepého retry.
- Čisto volatilné `last_run`/monitor `checked_at` nevytvárajú nový checkpoint,
  aby sa ciphertext história nezväčšovala každých 15 minút bez zmeny portfólia.
- `.private-state/` je ignorované, lokálny adresár má režim 0700, súbory 0600.
  Workflow odstráni lokálny plaintext; odstránený je starý upload plaintext artifactu
  aj commit portfólia do verejného repo.
- `main.save_state` odmietne portfólio v tracked verejnom `bot_state.json`.
  GitHub Actions bez `STATE_BACKEND=github-private` odmietnu beh.

## Oddelenie prostredí

Produkcia používa `STATE_ENV=prod`, vývoj `STATE_ENV=test`; ide o oddelené paths
aj autentifikované šifrovacie kontexty. Odporúčame navyše samostatné private
repo a odlišné kľúče/tokeny pre test a produkciu, cez GitHub Environments.
Vývojárske testy používajú iba syntetické dáta a mock GitHub API.

Nespúšťajte testovacieho Telegram getUpdates konzumenta s produkčným bot tokenom.
Výskumné CSV v docs/phase2 obsahujú výhradne historické simulované obchody,
nie používateľove nákupy, zostatky alebo živý ledger.

## Čo musí neskôr nastaviť používateľ (bez hodnôt v chate)

Nič z tohto sa počas fázy 2 nevytvorilo ani neodoslalo:

1. Vytvoriť prázdny **private** repo, napr. `owner/crypto-bot-private-state`,
   s počiatočným commitom/default branch. Nepovoľovať v ňom Actions.
2. Fine-grained GitHub PAT alebo GitHub App token iba na tento repo:
   Contents read/write, Metadata read; žiadne iné repozitáre, žiadne broker API.
   Uložiť do Actions Secret `STATE_REPO_TOKEN`. Platnosť musí mať dátum obnovy.
3. Bezpečne lokálne vygenerovať 32 kryptograficky náhodných bytov, base64 uložiť
   do Actions Secret `STATE_ENCRYPTION_KEY`. Kľúč zároveň zálohovať v bezpečnom
   password manageri; strata kľúča znamená neobnoviteľné šifrované dáta.
4. Actions Variable `PRIVATE_STATE_REPO=owner/crypto-bot-private-state`.
5. Explicitne inicializovať test prostredie, až po samostatnom schválení produkciu:
   `STATE_ENV=test python -m v11.secure_state initialize --confirm-empty-portfolio`.
   Hodnoty tokenu/kľúča majú byť bezpečne injektované, nie argumenty príkazu.
   Inicializácia existujúci stav nikdy neprepíše. Nevytvára reálne obchody.
6. Overiť read/encrypt/CAS/backup/restore na test repo pred aktiváciou workflow.
   Produkčný scheduler zatiaľ neaktivovať.

API doména je `api.github.com`; samotné fungujúce Git HTTPS čítanie nedokazuje
oprávnenie na zápis do private state repo. Tieto tri požadované runtime hodnoty
v aktuálnom prostredí chýbajú; živý storage test preto nebol možný.

## Obnova

- Najskôr pozastaviť scheduler a všetkých zapisovačov.
- Vybrať konkrétny commit SHA z private repozitára.
- Stiahnuť a autentifikovane dešifrovať starú verziu výhradne lokálne:
  `python -m v11.secure_state restore --commit <40-hex-sha> --output .private-state/test/recovered.json`.
  Toto nemení aktuálny vzdialený stav a nevypíše obsah do logu.
- Po bezpečnej kontrole a explicitnom rozhodnutí správcu:
  `python -m v11.secure_state rollback --commit <40-hex-sha> --confirm-state-rollback`.
  Obnova vytvorí zálohu aktuálneho stavu a CAS checkpoint; nikdy sa automaticky
  nespúšťa pri chybe API. **Tento príkaz počas implementácie nebol vykonaný.**
- Porovnať transakcie po zálohe s reálne vykonanými obchodmi a Telegram offsetom;
  rollback môže odstrániť neskoršie záznamy. Pred pokračovaním ich treba zosúladiť.
- Až potom obnoviť scheduler. Kľúče a názov repo sa nesmú meniť bez riadnej migrácie.

## Overenie a limity

Testy prešli pre šifrovanie/dešifrovanie, poškodenie, nesprávne prostredie,
odmietnutie public repo, chýbajúci stav, zálohu, súbežný zápis, nejednoznačný
úspech PUT a blokovanie verejného ledgeru. Skutočný súkromný repo nebol vytvorený
ani otestovaný; bez tokenu a kľúča sa nesmie tvrdiť plná prevádzková pripravenosť.

História rastie aj v private repo. Priebežne sledovať veľkosť a zálohovať mimo
aktívneho repo; pri dlhodobej prevádzke môže byť potrebná riadená rotácia archívu.
Kód má 5 MB limit plaintextu a 900 kB limit šifrovaného súboru pre spoľahlivý GitHub Contents read. Nikdy netrimuje finančnú históriu potichu.
GitHub výpadok znamená zastavenie potvrdenia zápisu, nie nebezpečný fallback na
verejný repo. Lokálny súbor nie je jediná trvalá kópia. Žiadne riešenie nenahrádza
bezpečné zálohovanie samotného šifrovacieho kľúča.
