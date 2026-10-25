# Plán budúcej migrácie — NEVYKONANÝ

Žiadny z nasledujúcich zápisových krokov sa v tomto audite nevykonal.
Produkčný bot_state.json sa nemení, nemaže ani nekopíruje do verejného reportu.

## A. Predpoklady a potrebné schválenie

1. Schváliť cieľový samostatný PRIVATE stavový repozitár a jeho správcov.
   Kód zostáva verejný, stav/šifrované zálohy nikdy nie v jeho Artifacts.
2. Schváliť GitHub Environment pre produkčné secrets, obmedzené dôveryhodné vetvy
   a pravidlá manuálnej kontroly workflow, ktoré secrets čítajú. Verejný PR/research
   job nesmie dostať stavové credentials. Ochrana GitHub Secrets nie je náhradou
   za dôveryhodný kód: držiteľ write oprávnenia môže meniť workflow.
3. Vygenerovať skutočný32-bajtový AES kľúč AŽ v schválenom bezpečnom procese,
   mimo chatu/logov/shell histórie/Artifactov. Nikdy nepoužiť testovací vektor.
   Oddelené test/prod kľúče; obmedzený token iba k stavovému repozitáru.
4. Schváliť zálohu/escrow kľúča, práva na obnovu, rotáciu a retenčnú politiku.
   Token a dešifrovací kľúč neukladať spolu so zálohami do verejného kódu.
5. Schváliť údržbové okno, zastavenie produkčných writerov a zmenu produkčného
   workflow. Bez tohto schválenia sa main/schedule/produkčné secrets nemenia.

## B. Skúška v test prostredí

- Najprv STATE_ENV=test s výlučne syntetickým ledgerom a testovacím secrets scope.
- Na GitHub-hosted runneri overiť private-repo kontrolu, šifrovanie, initialize
  iba ak stav neexistuje, opakovaný initialize refusal, CAS konflikt a zotavenie.
- Overiť obnovu po korupcii, rollback presného commit SHA, chýbajúci/nesprávny
  kľúč, nedostupné API a timeout po úspešnom zápise bez slepého opakovania.
- Skontrolovať Artifacts/Summary/logy iba so syntetickými canary hodnotami.
- Priamy restore alebo rollback nesmie byť súčasťou pravidelného workflow.

## C. Inventúra a snapshot pred produkciou

- Na schválenom izolovanom runneri/lokálnom zabezpečenom stroji identifikovať
  autoritatívny produkčný stav a prípadnú manuálnu evidenciu vykonaných obchodov.
- Uchovať pôvodný bot_state.json nezmenený. Zapísať jeho hash a presný git SHA
  do privátneho migračného protokolu; obsah nevypisovať.
- Zaistiť, že žiadny writer nebeží. Preniesť celý stav so spätnou kompatibilitou,
  nevydávať odporúčania za vykonané obchody. Chýbajúce skutočné údaje nedoplniť
  demo hotovosťou alebo syntetickými pozíciami.
- Existujúci CLI initialize vytvára predvolený nový ledger; NIE JE import reálneho
  portfólia. Na reálnu migráciu ho nepoužiť. Pripraviť osobitný kontrolovaný import
  s porovnaním obsahu, až po samostatnom schválení konkrétneho migračného kroku.

## D. Riadený import a overenie

- Explicitné STATE_ENV=prod a prázdny cieľ: import musí odmietnuť existujúci stav.
- Šifrovať a uložiť celý schválený snapshot vrátane neznámych legacy polí.
- Znovu vzdialene prečítať, dešifrovať a súkromne porovnať transakcie, cash,
  množstvá/nákladovú bázu, offsety Telegramu a pokusy o doručenie. Verejne iba
  úspech/neúspech; nikdy sumy alebo príkazy používateľa.
- Overiť zálohu a obnovu do oddeleného privátneho testovacieho cieľa. Zachovať
  starý stav a nový ciphertext. Nemažú sa historické dáta automaticky.
- Ak sa zistí nezhoda, migráciu zastaviť. Nesynchronizovať starú/novú verziu
  obojstranne, nevytvárať ďalšie obchody ani nepotvrdzovať fiktívne fill-y.

## E. Až potom schválenie nasadenia

- Schváliť konkrétny commit/workflow; neprenášať celý historický výskum bez review.
- STATE_BACKEND=github-private, STATE_ENV=prod, contents:read pre verejný kód;
  bez git add/push bot_state.json a bez uploadu privátnych ciest.
- Produkcia načíta privátny checkpoint fail-closed; žiadny automatický reset.
  Write-through journal pred Telegramom, concurrency a CAS zostávajú aktívne.
- Zabezpečiť cleanup lokálneho plaintextu po každom výsledku na ephemeral hosted
  runneri; na trvalom disku overiť šifrovanie a mazanie podľa vlastnej politiky.
- Oprávnenie obchodovať sa nikdy nepridáva. Aktivácia nových stratégií má vlastné
  schválenie a nie je súčasťou tejto migrácie.

## F. Obnova / incident

- Zastaviť writerov, zaznamenať aktuálny SHA a privátne uchovať poslednú verziu.
- Overiť konkrétnu zálohu AES-GCM s jej pôvodným kľúčom/prostredím/repozitárom.
- Obnovu na aktuálny stav povoliť iba proti presnému očakávanému SHA; konflikt
  znamená STOP. Nejednoznačný timeout najprv overiť, nie automaticky opakovať.
- Po obnove zosúladiť skutočné manuálne obchody, Telegram offsety a delivery
  journal; stará záloha môže chýbať nové fill-y a môže obnoviť už odoslané sloty.
- Schváliť reštart schedulera až po tejto kontrole. Nikdy nejde o vykonanie obchodu.
- Ak sa zistí starší únik vo verejnej histórii alebo Artifactoch, osobitne schváliť
  reakciu: rotáciu kompromitovaných credentials a posúdenie odstránenia historických
  údajov. Tento audit nič neprepisuje a nezaručuje odstránenie existujúcich kópií.
