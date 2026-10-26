# Fundamental Sources Shadow Test

Samostatný **manuálny** workflow `.github/workflows/fundamental-sources-shadow.yml`, iba vo vetve `feature/v11-1-review`. Žiadny plánovač/push trigger, zapisovacie oprávnenia repozitára, Telegram alebo privátny stav. Výsledky testu nemajú vplyv na produkčné signály.

## Presný postup v GitHube

1. Otvor https://github.com/janmarticek4-dot/crypto-bot/actions .
2. Vľavo vyber **Fundamental Sources Shadow Test**, ak sa zobrazuje. Priamy odkaz: https://github.com/janmarticek4-dot/crypto-bot/actions/workflows/fundamental-sources-shadow.yml .
3. Klikni **Run workflow**, vyber **feature/v11-1-review**.
4. `use_groq` zapni iba ak chceš použiť existujúci Groq kľúč s dostupnou bezplatnou kvótou. Bez neho test stále vytvorí plnú deterministickú analýzu. Žiadny nový/platený poskytovateľ sa nepoužíva. Aktuálny billing/bezplatnosť účtu sa z existencie kľúča nedá overiť.
5. Potvrď zeleným **Run workflow**.
6. Po dokončení otvor konkrétny beh, úplne dole **Artifacts → fundamental-sources-shadow-<run_id>-<attempt>**. ZIP obsahuje `REPORT.md`, `evening.txt`, `source_diagnostics.json`, `ai_diagnostics.json`, `analysis_validation.json`, `fundamentals.json`, `fundamental_evidence.json`, `market_snapshot.json`, `outage_checks.json`, `summary.json`, `artifact_privacy.json`.

### Ak nový workflow vo vývojovej vetve GitHub neponúka

GitHub nemusí nový `workflow_dispatch` workflow zaregistrovať, kým neexistuje na predvolenej vetve. **Nevkladaj ho preto do produkčnej main.**

Použi už registrovanú cestu https://github.com/janmarticek4-dot/crypto-bot/actions/workflows/run.yml :

- **Run workflow → feature/v11-1-review**.
- `task`: **fundamental-sources**.
- `use_groq`: voliteľne true.
- `confirm_private_state_test`: false. Ostatné vstupy nemenia tento test.

Vo vývojovej verzii `run.yml` ide o odkaz na rovnaký samostatný workflow z rovnakého commitu. Produkčné úlohy sa nespúšťajú; žiadny `secrets: inherit`, ďalej sa explicitne odovzdáva iba voliteľný Groq kľúč. Nepoužívaj main ani `advisory_import`.

Ak GitHub formulár stále ukazuje iba vstupy produkčnej main a neponúkne `task`, prihlásený GitHub CLI vie odoslať udalosť existujúcemu workflow priamo na vývojovú vetvu:

```sh
gh workflow run run.yml --repo janmarticek4-dot/crypto-bot --ref feature/v11-1-review -f task=fundamental-sources -f use_groq=true
```

Bez AI zmeň poslednú hodnotu na `false`. Toto nie je merge ani deployment. Nie je potrebné vytvárať nový PAT pre privátny stav; bežné prihlásenie GitHub CLI musí mať oprávnenie spúšťať Actions v kódovom repozitári.

## Čo test skutočne overuje

- Fed press RSS a monetary záloha, FOMC HTML, BLS RSS a oba ICS kalendáre, BEA oba RSS endpointy, ECB press/blog, SEC oba endpointy, CFTC.
- Treasury mesačný XML a FRED yield CSV (overené aj ako záloha), FRED CPI/PCE/UNRATE/PAYEMS.
- Aave governance a AIP záloha, Ondo blog a sekundárna záloha, SOL Agave/TAO Subtensor/FET Fetchd vydania a RENDER RNP governance. Tieto zdroje **nepreukazujú adopciu**.
- DeFiLlama TVL Aave/Solana/Ondo, denné poplatky Aave/Solana, príjmy Aave. Časové rady musia mať správny formát, konečné nezáporné čísla a aktuálny bod; fees/revenue iba uzavretý UTC deň do 48 h. Ak API deklaruje nesprávny `dataType`, záznam sa odmietne. Ak typ v metadátach chýba, `metric_type_confirmation=request_query_only` transparentne uvádza slabšiu úroveň potvrdenia typu.
- TVL nie je meranie aktívnych používateľov. Aktívni používatelia, transakcie, používanie a ekonomika všetkých šiestich tokenov nie sú predstierané ako pokryté.

`source_diagnostics.json` obsahuje URL, čas zberu, schému, aktuálnosť, posledné dostupné publikovanie/merané obdobie, relevantné záznamy a konkrétnu triedu chyby. Bez zdrojových tiel, tokenov alebo promptov.

Stavy: `OK_CURRENT`, `OK_NO_RECENT_RELEVANT_ITEMS`, `OK_NO_UPCOMING_PARSED_EVENTS`, `STALE`, `NO_RECENT_VALID_OBSERVATIONS`, `NETWORK_BLOCKED`, `HTTP_ERROR`, `INVALID_FORMAT`, `TRANSPORT_ERROR`. HTTP 403 z pôvodného servera alebo gateway sa nedá vždy odlíšiť; proxy CONNECT 403 má samostatnú známu vrstvu `network_tunnel`. Pri úspešnom transporte nepredstierame konkrétny HTTP kód, ktorý existujúci fetch adaptér neposkytuje.

## AI a obsah

Najviac dve logické Groq volania: zoradenie ID významných podkladov a výber existujúcich technických dôvodov. Transport má maximálne dve požiadavky na volanie pri retry a rešpektuje krátky Retry-After; dlhé čakanie vedie na fallback. Žiadny web search ani generovanie faktov, dátumov, cien či citácií. Pre známe modely GPT-OSS sa skutočne posiela `reasoning_effort=low`; predtým sa nízka úroveň iba odovzdala vnútornému wrapperu, ktorý ju ignoroval. Ostatné modely tento parameter nedostávajú.

AI diagnostika uvádza samostatne dostupnosť zoradenia fundamentov a technického výberu. HTTP chyby vrátane 400/429 obsahujú iba bezpečný kód/type/param poskytovateľa, nie celé chybové telo alebo nevalidovanú generáciu. Ak nie sú významné vstupné podklady, AI sa na ne nevolá. Jednorazový test nemeria dlhodobú kvalitu alebo pravdivosť zdrojov.

`analysis_validation.json` overuje prítomnosť zdrojových URL a významu/dopadu/potrebného potvrdenia v zobrazených položkách. Nie je to nezávislý fact-check článkov. Večerná analýza je náhľad v skutočnom čase zberu, bez vymysleného ranného porovnania.

## Lokálne reprodukovanie

```sh
python scripts/test_offline.py
BOT_DISABLE_TELEGRAM=1 BOT_DATA_MODE=shadow python scripts/fundamental_sources_shadow.py --use-groq
python scripts/stage_shadow_artifacts.py --source shadow-output/fundamental-sources --destination shadow-public-artifacts/fundamental-sources
```

Zdrojové výpadky samy nezastavia zostavenie N/A reportu. Neúplné trhové dáta ukončia test kódom 2, výstupy sa aj tak bezpečne pripravia do artifactu. Zlyhanie privacy kontroly publikuje iba fixný výsledok odmietnutia, nie pôvodné dáta.

## Skutočne vykonané lokálne overenie (nie GitHub runner)

- **296 offline testov OK**, YAML syntax oboch workflow overená.
- Živý zber **26. 10. 2026 21:24:21 Bratislava**, kompletné aktuálne trhové dáta všetkých šiestich mincí.
- 32 endpointových pokusov: 24 `NETWORK_BLOCKED` (proxy CONNECT 403), 4 `OK_CURRENT`, 2 `STALE`, 2 `OK_NO_RECENT_RELEVANT_ITEMS`. Aktuálnosť a chyby sú oddelené od úspešného načítania; lokálne sieťové blokovanie nedokazuje výpadok serverov a musí sa overiť na GitHub runneri.
- Groq: **2 živé volania, obidve HTTP 200**, platné zoradenie existujúcich fundamentálnych ID a výber existujúcich technických dôvodov. Pred opravou prvé volanie vracalo HTTP 400; doplnený výslovný pokyn JSON v prompte a odovzdávanie nízkeho reasoning effort pre GPT-OSS. Tieto opravy nepredstavujú overenie kvality trhovej predikcie ani doklad o účtovaní poskytovateľa.
- Kontrola zdrojových URL a prítomnosti významu/dopadu/potrebného potvrdenia v reportových podkladoch prešla. Privacy gate **PASSED**. Fault injection **PASSED**.
- Produkčný stav sa nenačítal, pozície sa nenačítali, chránené súbory sa nezmenili, Telegram sa nepoužil a obchody sú vypnuté.
- Verejné lokálne dôkazy sú `LOCAL_REPORT.md`, `LOCAL_SOURCES.json`, `LOCAL_AI.json`, `LOCAL_SUMMARY.json`, `EVENING_PREVIEW.txt`. Neoznačujú sa ako výsledok GitHub-hosted runnera.

Nové DeFiLlama adaptéry majú offline overenie správnosti formátu/typu a dostupnosť sa testuje naživo, ale lokálny proxy ich blokuje. **Úspešné načítanie ekonomických metrík z GitHub runnera ešte treba potvrdiť.** Ani úspešný runner neposkytne automaticky chýbajúce aktívne používateľské metriky TAO/FET/RENDER alebo celý unlock kalendár.

Pokus o spustenie z pracovného prostredia cez `gh workflow run run.yml --ref feature/v11-1-review -f task=fundamental-sources -f use_groq=true` bol odmietnutý pri prístupe na GitHub API odpoveďou **Forbidden**. GitHub-hosted beh teda z tohto prostredia nebol spustený a žiadne jeho ID ani Actions Artifact sa nepredstiera. Vývojová vetva bola úspešne pushnutá; manuálne spustenie cez váš GitHub účet zostáva dostupným ďalším krokom podľa postupu vyššie.
