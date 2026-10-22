# Macro Sources Diagnostics

Samostatný **manuálny** workflow: `.github/workflows/macro-sources-diagnostics.yml`.
Skript: `scripts/macro_source_diagnostics.py`. Používa iba štandardnú knižnicu Pythonu; neimportuje main,v11,portfólio,Telegram,Groq ani exchange klienta. Žiadne secrets, platené API, obchodné signály alebo obchodné príkazy. Žiadna inštalácia závislostí bota.

## Čo testuje z GitHub-hosted runnera

Job má `runs-on: ubuntu-latest` a9 verejných HTTPS endpointov siedmich poskytovateľov:

| Poskytovateľ | Dáta/formát |
|---|---|
| Fed | tlačové správy RSS + FOMC kalendár HTML |
| BLS | tlačové správy RSS + kalendár ICS |
| BEA | oficiálny RSS, vrátane povoleného publisher redirectu apps.bea.gov→bea.gov |
| ECB | oficiálny RSS |
| SEC | oficiálny press-release RSS |
| CFTC | oficiálny press-release RSS |
| Treasury | XML denných2Y/10Y výnosov aktuálneho roka |

Skript robí jeden sekvenčný GET na endpoint, timeout12s, limit2MB, overuje TLS certifikáty, rešpektuje existujúci proxy a neobchádza sieťovú politiku. Pred presmerovaním povoľuje iba HTTPS v pôvodnom publisher doméne; presmerovanie na Telegram či nesúvisiaci web odmietne pred kontaktovaním cieľa.

## Význam výsledkov

| Stav | Význam |
|---|---|
| `SUCCESS` | HTTPS úspech a rozpoznaný RSS/Atom,ICS,FOMC HTML alebo Treasury XML. Nie je to certifikácia aktuálnosti či úplnosti udalostí. |
| `NETWORK_BLOCKED` | Konkrétne odmietnutie proxy/CONNECT403/407 alebo explicitná HTTP proxy blokácia. `origin_http_status=null`; nie je to dokázaná chyba pôvodného webu. |
| `NETWORK_ERROR` | DNS,timeout alebo prenos/spojenie bez použiteľnej HTTP odpovede. |
| `TLS_ERROR` | Chyba TLS/certifikátu, nikdy sa nevypína overovanie certifikátu. |
| `HTTP_ERROR` | HTTP403/404/429/5xx z HTTPS endpointu alebo CDN/gateway. Zaznamená status a Retry-After. Konkrétny aplikačný origin nemožno vždy dokázať iba z klienta; nepripisujeme mu automaticky chybu gateway. |
| `INVALID_FORMAT` | Napr.HTTP200 s HTML challenge namiesto RSS/ICS, poškodené XML alebo chýbajúce Treasury polia. |
| `REDIRECT_BLOCKED` | Presmerovanie porušuje publisher/HTTPS politiku. |
| `DIAGNOSTIC_ERROR` | Neočakávaná chyba samotnej diagnostiky; job zlyhá, bez exportu potenciálne citlivého textu výnimky. |

Neúspech zdroja je užitočný výsledok diagnostiky, preto sám o sebe nezlyhá job. Zelený beh **neznamená**, že všetky zdroje fungujú. Pozri tabuľku a `counts`. Atom/RSS dátum vydania nie je dátum ekonomickej udalosti; dátumy FOMC neznamenajú overený čas rozhodnutia. Denné Treasury pozorovanie nie je živá kotácia. Žiadne nedostupné hodnoty sa nevymýšľajú.

Do výstupov sa nezapisujú raw response bodies,cookies,autentifikačné hlavičky,proxy URL ani environment dump. Iba boolean prítomnosti proxy,štandardný GitHub branch/SHA,verejné URL,vybrané diagnostické hlavičky,statusy,formát,timing a SHA256 odpovede. Výstup je obmedzený na ignorovaný `macro-diagnostics-output/`.

## Manuálne spustenie v pôvodnom repozitári

1. Otvor `https://github.com/janmarticek4-dot/crypto-bot/actions`.
2. Vľavo vyber **Macro Sources Diagnostics**.
3. **Run workflow → Use workflow from: feature/v11-1-review → Run workflow**. Žiadne vstupy ani API kľúče netreba.
4. Otvor konkrétny beh. Tabuľka je v **Summary**; ZIP stiahni dole cez **Artifacts → macro-sources-diagnostics-RUN_ID-ATTEMPT**.
5. ZIP obsahuje `REPORT.md`, `results.json`, `README.txt`. Retencia7dní. Toto sú diagnostické výstupy, nie trvalé úložisko portfólia.

CLI (ak workflow GitHub pozná a klient má oprávnenie Actions):

```bash
gh workflow run macro-sources-diagnostics.yml --repo janmarticek4-dot/crypto-bot --ref feature/v11-1-review
gh run list --repo janmarticek4-dot/crypto-bot --workflow macro-sources-diagnostics.yml
gh run download RUN_ID --repo janmarticek4-dot/crypto-bot --dir macro-download
```

V pôvodnom repozitári je job guard obmedzený na vývojovú vetvu. Existujúce produkčné workflow,main,state ani strategické súbory sa nemenia. Žiadny schedule,push trigger,deploy či writeback.

## Ak workflow na vývojovej vetve nie je viditeľný/spustiteľný

GitHub vyžaduje registráciu nového `workflow_dispatch` súboru na predvolenej vetve. Samotné `--ref feature/v11-1-review` túto podmienku neobíde. **Nemeníme preto produkčný main ani nespúšťame produkčný workflow.**

Bezpečná alternatíva je nový **prázdny diagnostický repozitár**, napr.`crypto-bot-macro-diagnostics`, s iba týmito dvoma súbormi na jeho vlastnej predvolenej vetve:

1. `scripts/macro_source_diagnostics.py`
2. `.github/workflows/macro-sources-diagnostics.yml`

Najskôr pridaj skript, potom workflow. Nie je potrebné kopírovať bota,produkčný workflow,stav,portfólio ani akékoľvek secrets. Podmienka jobu výslovne umožňuje samostatný diagnostický repozitár. Tam otvor **Actions → Macro Sources Diagnostics → Run workflow**, nechaj jeho predvolenú vetvu, a stiahni rovnaký Artifact. Ide výhradne o verejné HTTP/schema testy, nie nasadenie V11.1. Prázdny repozitár je vhodnejší než fork celého bota s potenciálnymi naplánovanými workflow.

Tento alternatívny repozitár sa automaticky nevytvára a nemenia sa nastavenia originálneho main. Pôvodný workflow zostáva pripravený na vývojovej vetve.

## Lokálne overenie a hranice tvrdení

```bash
python -m unittest tests.test_macro_source_diagnostics -v
python scripts/macro_source_diagnostics.py
```

Samostatný skript nemá externé závislosti. Kompletná offline sada projektu sa overuje samostatne cez `python scripts/test_offline.py`.

Lokálny živý test22.10.2026: všetkých9 endpointov vrátilo `NETWORK_BLOCKED / proxy_connect /403`, pričom pôvodný HTTP status ostal neznámy. To sú výsledky cloudového pracovného prostredia, **nie GitHub-hosted runnera**. Presný JSON je `MACRO_DIAGNOSTICS_VALIDATION.json`. Skutočné GitHub-hosted výsledky vzniknú až pri behu workflow a budú označené `runner_environment=github-hosted`; bez run URL ich nepredstierame.
