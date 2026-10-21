# Overenie a rozsah V11.0

- Unit/integration suite (37 testov, všetky prešli): `python3 -m unittest discover -s tests -v`.
- Živá analýza na verejných API: ceny pre všetkých 10 sledovaných mincí aj BTC/ETH;
  všetky štyri rámce pre primárne mince. HYPE má krátku históriu, 1D/1W chýbajú.
- Celý report vznikol s kópiou V10 stavu, nulovými reálnymi pozíciami a 36
  volatilnými scenármi. Telegram send bol nahradený zápisom do súboru.
- Groq výber existujúcich dôvodov prešiel v reálnom reportovom behu; unit test
  preukazuje odmietnutie neexistujúcich indexov/voľných správ a reuse cache.
- Živý tichý V11 monitor: core ceny aj 4H dáta dostupné, výsledok quiet, nula Telegram odoslaní.
- Šesť Freqtrade behov (3 stratégie × 2 obdobia), 1H detail/4H signály/1D trend.
  Výsledky sú v BACKTEST_RESULTS.md/json; surové archívy v ignored
  backtesting/user_data/backtest_results. Príkazy v backtesting/run.sh.
- Lookahead-analysis TrendComponent v 2024 na 10 signáloch: no bias detected; toto nie je dôkaz budúcej ziskovosti.
- CombinedStrategy má nula obchodov v oboch celoročných behoch. Lookahead test
  sa ukončil pre nedostatok obchodov; NEPREŠIEL. Obmedzenie je v reportoch.
- HYPE: nový listing na použitom Binance zdroji 24.09.2026; historické obdobia
  2024/2025 nemožno na tomto zdroji testovať. Nepoužili sme vymyslené dáta.
- Bybit nie je potrebný. Presná príčina starého Bybit pokusu nie je známa bez
  jeho logov. Aktuálny CCXT problém bol potvrdený ako certificate chain failure;
  oprava je include_OS_certificates + aiohttp_trust_env, bez vypnutia overovania.

## Neuzavreté požiadavky a nasadenie

Celý ambiciózny rozsah zadania NIE JE validovaná investičná stratégia.
Aktívne BUY pravidlá zostávajú deaktivované. Produkcia nepoužíva backtest
výsledky ako pravdepodobnosti a nesľubuje výnos ani maximálnu stratu.

Chýba overený zdroj plného makro kalendára, ETF tokov, unlockov a derivátových
metrík; tieto polia sú N/A. Cenová stratégia nepredstavuje plnú fundamentálnu
vrstvu. Dostupnosť eToro a skutočný spread závisia od používateľovho účtu/krajiny;
bez ich nastavenia sa nový nákup neodporúča.

Príkazy a zostatky sa zatiaľ ukladajú do rovnakého súboru ako starý stav.
Vo verejnom repozitári budú verejné; pre skutočnú evidenciu treba súkromné úložisko.
Žiadna reálna pozícia sa pri vývoji nepridala a tracked bot_state.json je nezmenený.

Zmeny sú lokálne na kontrolu, neboli pushnuté do main ani nasadené cez GitHub
Actions. Nový workflow nebol spustený na GitHub runneri. Žiadna nová V11 správa
nebola počas vývoja odoslaná používateľovi.
