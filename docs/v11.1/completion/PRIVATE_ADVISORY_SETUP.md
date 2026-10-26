# Skutočné pozície — samostatné súkromné úložisko

Bot poskytuje rady a zaznamenáva iba údaje potvrdené používateľom. Žiadny
príkaz v tomto postupe nevytvára burzovú objednávku. Testovacie úložisko sa
nepoužíva na skutočné pozície. Produkčný bot_state.json sa neimportuje ani nemaže.

## Nastavenie, ktoré musí urobiť vlastník GitHub účtu

Codex v tomto prostredí nemá funkčný prístup ku GitHub API na vytvorenie repo
alebo Secrets. Pripravený kód ich nevytvára a nesmie zobrazovať ich hodnoty.

1. Vytvor nový PRIVATE repozitár **crypto-bot-state-production**, pridaj README.
2. V ňom vytvor **PRODUCTION_ADVISORY_ONLY.json** s týmto NECITLIVÝM obsahom:

```json
{"schema":1,"purpose":"crypto-bot-private-advisory","trading_enabled":false}
```

3. Vytvor nový fine-grained PAT iba pre tento PRIVATE repozitár. **Contents:
   Read and write**, **Metadata: Read-only**, ostatné práva nepridávať. Nepoužívaj
   token testovacieho repo ani žiadny burzový obchodný kľúč.
4. V **crypto-bot → Settings → Environments → production-advisory** povoľ iba
   deployment branch **main**. Pravidelné analýzy vyžadujú možnosť automatického
   behu; povinný manuálny reviewer na každý run by automatické správy zastavil.
   Zmeny dôveryhodného produkčného workflow a jeho pinov preto kontrolovať pri review.
5. Environment variable **PROD_STATE_REPOSITORY** nastav na owner/crypto-bot-state-production.
6. Environment secrets: **PROD_STATE_TOKEN**, **PROD_STATE_ENCRYPTION_KEY**.
   Kľúč musí byť nový a výlučne produkčný, base64 z32 náhodných bajtov. Bez výpisu
   ho možno vytvoriť lokálne do schránky týmto PowerShell postupom:

```powershell
$advisoryBytes = New-Object byte[] 32
$advisoryRng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
$advisoryRng.GetBytes($advisoryBytes)
Set-Clipboard -Value ([Convert]::ToBase64String($advisoryBytes))
[Array]::Clear($advisoryBytes, 0, $advisoryBytes.Length)
$advisoryRng.Dispose()
```

Vlož do PROD_STATE_ENCRYPTION_KEY, bezpečne uchovaj pre obnovu a vyčisti schránku
`Set-Clipboard -Value ''`. Nikdy nevkladaj kľúč/PAT do chatu, logu, Variables alebo
kódu. Tento návod kľúč sám negeneruje ani migráciu nevykonáva.

## Počiatočný import vlastníctva

V tom istom Environment vytvor Secret **INITIAL_ADVISORY_PORTFOLIO** obsahujúci
JSON so skutočnými údajmi zadanými používateľom. Nasledujúci príklad je iba
schéma s FIKTÍVNYM symbolom príkladu; uprav podľa vlastnej evidencie:

```json
{
  "positions": [
    {"symbol":"AAVE","quantity":null,"average_cost":null,"currency":"USD"}
  ],
  "cash": null
}
```

- Pridaj jeden objekt pre každú skutočne otvorenú pozíciu. `quantity` je aktuálne
  množstvo tokenov, `average_cost` priemerný all-in náklad na jednotku vrátane
  vstupných poplatkov. USD/EUR je mena tejto evidencie, nie odvodená domnienka.
- Ak množstvo/náklad nepoznáš, nechaj null. Nevkladaj fiktívne čísla. Hotovosť
  zostáva null, ak nebola výslovne zadaná. Nevytvára sa demo zostatok8500.
- Tento Secret je citlivý. Neposielaj ho do issue, verejného workflow inputu,
  Artifactu alebo screenshotu. Návod úmyselne neobsahuje tvoje konkrétne pozície.

Otvor Actions → existujúci **Crypto AI Bot V10.6 / run.yml → Run workflow → main**.
Zaškrtni iba **advisory_import**, ostatné ručné analýzy nechaj vypnuté. Import
načíta uvedený Secret, zašifruje do prod/state.enc a nezávisle overí obsah.
Nevytvorí žiadnu objednávku a odmietne už existujúci stav. Verejne vypíše iba
úspech/neúspech, bez súm, tickerov vlastníctva alebo kľúčov. Žiadny Artifact.
Po úspechu môžeš INITIAL_ADVISORY_PORTFOLIO Secret odstrániť — ide iba o vstupný
kanál importu; autoritatívna evidencia už je v šifrovanom PRIVATE repo.

Až po dostupnosti Secrets/úložiska sa súkromná časť načítava do Telegram analýzy.
Je oddelená od verejného cenového journalu: verejný stav nikdy nezíska držané
symboly používateľa, množstvá, náklady alebo výsledky pozícií. Súhrn portfólia
sa nevytvára, ak dešifrovanie/validácia zlyhá; zobrazuje sa N/A, nie prázdna držba.

## Neskoršie manuálne aktualizácie v súkromnom Telegrame

Spracúvajú sa na plánovaných kontrolách, nie okamžite v reálnom čase:

- `POZICIE` — vypíše potvrdenú súkromnú evidenciu.
- `POZICIA AAVE 2 100 USD` — FIKTÍVNY príklad oznámenia aktuálneho množstva a
  priemerného nákladu. Nahrádza evidenciu, NEVYKONÁVA nákup.
- `POZICIA AAVE ? ? USD` — používateľ potvrdzuje držbu, množstvo/náklad neznáme.
- `UZAVRETA AAVE` — oznámenie, že používateľ pozíciu už sám uzavrel. Nie predajný príkaz.

Príkazy sa prijímajú len z nakonfigurovaného chatu. Predvolene musí ísť o private
chat a rovnaké from.id/chat.id. Pre skupinu treba navyše Environment Secret
ADVISORY_TELEGRAM_USER_ID; bez neho sa skupinové príkazy odmietajú. Staré správy
spred importu sa nezreplayujú. Offset a zmena sa zapíšu šifrovane pred potvrdením.
Súbežný konflikt sa nesmie prepísať, výpadok API nesmie resetovať evidenciu.
História zmien je súkromná a označená ako oznámenia používateľa, nie burzové fill-y.

Čistý výsledok v EUR sa bez overeného FX kurzu nevypočítava. Neznámy spread nie
je nula. Odporúčanie HOLD/REDUCE sa opiera o dáta a je stále analytické posúdenie,
nie dôkaz budúcej výkonnosti. Na predaj/uzavretie používateľ používa vlastné eToro.
