# CRYPTO AI BOT V11.0 — ACTIVE BULLRUN STRATEGY

Slovenský analytický bot, ručné obchody na eToro, bez obchodných API kľúčov.

**Fáza 2 je pripravená na samostatnej vetve, zatiaľ nenasadená.**
[Diagnostika a porovnanie stratégií](docs/phase2/REPORT.md),
[súkromný stav](docs/phase2/PRIVATE_STORAGE.md),
[fundamentálna vrstva a jej limity](docs/phase2/FUNDAMENTALS.md).
Nový workflow vyžaduje súkromný šifrovaný backend; pred jeho konfiguráciou sa
produkčný beh odmietne. Starý verejný bot_state.json nesmie obsahovať reálne portfólio.
Cieľ +100 % je ambícia používateľa, nie predikcia. Nová aktívna stratégia je
**experimentálna a zatiaľ nezvalidovaná**. Predvolene negeneruje nové BUY signály;
reporty, sledovanie trhu, ochranné upozornenia a evidencia ručných obchodov fungujú.

Audit je v [docs/AUDIT.md](docs/AUDIT.md), skutočné výsledky v
[docs/BACKTEST_RESULTS.md](docs/BACKTEST_RESULTS.md). Samotná inštalácia ani
zero-trade backtest neznamenajú, že stratégia zarába.

## Spustenie

Python 3.12; `python -m pip install -r requirements.txt`;
`python -m unittest discover -s tests -v`.

Návrh GitHub Actions spúšťa `python main.py` každých 15 minút, až po konfigurácii súkromného stavu. Nepotrebuje lokálny
počítač, server ani druhý scheduler. Secrets na GitHub Actions:
`TELEGRAM_TOKEN`, `TELEGRAM_CHAT_ID`, voliteľne `GROQ_API_KEY` a
`COINGECKO_API_KEY`. Groq nie je nutný pre výpočty. Cloudové secrets a GitHub
Actions secrets sa nastavujú oddelene.

Actions Variables:

| Názov | Význam |
|---|---|
| GROQ_MODEL | predvolene openai/gpt-oss-120b; podporu nástrojov nepredpokladáme |
| SPREAD_ESTIMATE | odhad spreadu/sklzu na jednu stranu ako zlomok, napr. 0.002; prázdne = neznámy, nový nákup blokovaný |
| ETORO_VERIFIED_SYMBOLS | používateľom overené dostupné spot mince pre jeho krajinu/účet, oddelené čiarkami; bez tohto nevzniká nákupný signál |
| MIN_NET_EDGE | predvolene 0.03, minimálna čistá výhoda po nákladoch |

`BUY_FEE`/`SELL_FEE` sú konfigurovateľné procesné premenné, predvolene .01.
Zmena poplatkov nemení historické transakcie pri oprave. Žiadne odporúčanie
neaktivuje dodatočných $10 000. V11_RULES_VALIDATED musí zostať false do úspešnej
nezávislej validácie; aktuálne backtesty aktiváciu neodôvodňujú.

Ručná analýza: Actions → Run workflow → manual_analysis=true. Lokálny ekvivalent (len s bezpečne nakonfigurovaným stavom):
`GITHUB_EVENT_NAME=workflow_dispatch MANUAL_ANALYSIS=true python main.py`.
Tento príkaz **odosiela Telegram správy**. Na vývoj použite kópiu stavu:
`STATE_FILE=/tmp/crypto-state.json`; prvýkrát do nej skopírujte iba testovací stav bez reálnych údajov; nesmie sa commitnúť.
Nepracujte paralelne s produkčným Telegram getUpdates. Vývojové testy neodosielajú správy.

## Účtovná kniha a Telegram

Príkazy sa načítajú pri najbližšom Actions behu, zvyčajne do 15 minút; GitHub
plánovač môže meškať. Bot nesmie mať webhook ani druhého getUpdates konzumenta.
Príkazy sa spracujú len z TELEGRAM_CHAT_ID; skupinový chat povoľuje jeho členom
zadávať záznamy, preto na osobnú evidenciu použite súkromný chat.

- `KUPIL SOL 105 1500`: cena je skutočná exekučná jednotková cena, $1500 je
  **celkový odpis hotovosti vrátane 1% poplatku**. Množstvo = 1500/1.01/105.
  Spread už obsiahnutý v exekučnej cene sa pri evidencii neúčtuje znova.
- `PREDAL SOL 125 VSETKO` alebo `PREDAL SOL 125 50%`: výnos = množstvo × cena × .99.
- `PORTFOLIO`, `HOTOVOST`, `HISTORIA`.
- `OPRAV ID`: pripraví zrušenie nesprávneho záznamu; `POTVRDIT ID` ho zruší a
  prehrá históriu. Ak by neskorší predaj vznikol bez pozície, oprava sa odmietne.
  Najskôr zrušte závislé záznamy, potom vložte opravené obchody.

Počiatočný stav je $8500 cash, bez pozícií. Staré `last_actions` sú odporúčania,
**nikdy sa automaticky nezmenia na vykonané obchody**. Údaje V10 zostávajú zachované.
Stav sa zapisuje atomicky pod procesným lockom; workflow serializuje behy.
Offset Telegram update a transakcia sa uložia spolu pred potvrdením. Telegram
nemá idempotency key pre sendMessage: pri páde medzi odoslaním a uložením slotu
môže byť správa zopakovaná; žiadny kód nesmie tvrdiť zaručené exactly-once doručenie.
Pri konflikte súkromného checkpointu workflow zlyhá; šifrovaná záloha a commit história zostávajú v private repo. Verejný plaintext recovery artifact sa nevytvára.

**Verejný zápis reálneho portfólia je zablokovaný.** Použite výhradne šifrovaný private backend podľa docs/phase2/PRIVATE_STORAGE.md. Secrets sa do stavu neukladajú.

## Analytika a obmedzenia

SOL/TAO/ONDO/RENDER/AAVE/FET + HYPE/SUI/LINK/APT, BTC/ETH ako kontext.
Binance verejné spot OHLCV 1H/4H/1D/1W; len uzavreté, súvislé, čerstvé sviečky.
CG metadata jedným batch volaním; výpadok metadata nezablokuje burzovú cenu.
Neznáme hodnoty zostávajú N/A. HYPE a nové listingy môžu mať krátku históriu.
RSI/MACD/EMA/ATR/ADX/BB/rolling VWAP/RVOL/support/retest/divergencie,
relatívna sila a korelácia BTC sa počítajú v Pythone. VWAP je rolling 20 sviečok.
Krížové potvrdenie technických signálov nie je štatistická kalibrácia.

Volatilné intervaly ATR√čas sú iba orientačné scenáre, nie confidence intervaly
ani odhady pravdepodobností. Výsledky sa evidujú oproti neskoršej uzavretej 1H
sviečke. Rozsah neurčuje automatický predaj. Malá korekcia sama nespúšťa SELL.
Pre vlastnené pozície sa používajú ochranné prahy drawdownu; 30 % nie je povolený
rozpočet na stratu. Korelácia je historická a môže sa zmeniť.

AI smie vyberať len existujúce dôvody podľa indexov. Neoverené nové udalosti ani
číselné pravdepodobnosti sa do výstupu AI nedostanú. Cache 12h, pri chybe pauza 2h,
obmedzené retry s Retry-After; dlhý reset sa neobchádza kratšou pauzou. Aktuálne
free-tier kvóty sú závislé od účtu/modelu; presnú príčinu historických 429 bez
pôvodných rate-limit hlavičiek nemožno určiť.

Ráno 07:00 a večer 20:00 plný report, 15:00 len USA kontext. Bratislava a New York
používajú ZoneInfo vrátane odlišných dní zmeny DST. Načasovanie nie je SLA.
Slot má 90-minútové grace okno, opakovanie bráni uložený last_main_slot.
Rutinný monitor neposiela správy ani nevolá Groq. Mimoriadny alert vyžaduje
čerstvé kompletné cenové dáta, BTC aj ETH pod -5 %/24h a dva nezávislé aktuálne RSS
zdroje s rovnakým typom incidentu pri významnej burze/stablecoine. Osemhodinový
cooldown sa deduplikuje podľa subjektu a kategórie, nie premenlivého titulku.
Ide o konzervatívny scenár ďalšieho systémového rizika, nie kalibrovanú predpoveď
>10 % ani garanciu detekcie. Zatiaľ nekryje všetky typy geopolitických kríz a
samotné titulky nie sú plnohodnotné nezávislé preverenie obsahu článkov.
Nepodporovaný browser_search sa pri bežnom behu nepoužíva.

**Zatiaľ nepokryté overeným zdrojom:** Fed/CPI/PCE/US zamestnanosť kalendár,
US futures/indexy, ETF toky, unlocky, CVD/OI/funding/likvidácie a burzové toky.
Report ich označuje N/A, nevymýšľa hodnoty ani mechanizmy pre neoverené udalosti.
RSS titulky majú dátum/URL a sú označené ako samostatne nepotvrdené.

## Historické testy

Samostatné prostredie: `python3.12 -m venv /workspace/.venvs/freqtrade`, potom
`/workspace/.venvs/freqtrade/bin/pip install -r backtesting/requirements.txt`.
`bash backtesting/run.sh`, následne
`/workspace/.venvs/freqtrade/bin/python backtesting/report.py`.

Spúšťajte iba download-data, backtesting, lookahead-analysis, recursive-analysis;
nie `freqtrade trade`. Konfigurácia neobsahuje obchodné kľúče. Zdroj je Binance
spot data-api.binance.vision; CCXT rešpektuje systémové certifikáty a cloud proxy.
TLS overovanie sa nevypína. Žiadny prístup k účtu eToro.
