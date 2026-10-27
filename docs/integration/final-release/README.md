# Finálny analytický kandidát, bez E1

Zdrojová integračná vetva zostáva zachovaná vrátane uzavretého výskumu. Pre jediný čistý produkčný PR bola vytvorená vetva z aktuálnej main87a3143: `release/v11-1-analytics-review`. Nejde o nový repozitár ani ďalšieho bota. PR obsahuje iba analytický runtime, potrebné helpery, testy, navrhované prepnutie existujúceho pilota a ochranu stavu; nie E1/research/backtesting/experimentálne reporty.

Všetky kroky a zistenia:
https://github.com/janmarticek4-dot/crypto-bot/blob/release/v11-1-analytics-review/docs/v11.1-release/REVIEW.md

Aktivácia a rollback (zatiaľ nevykonané):
https://github.com/janmarticek4-dot/crypto-bot/blob/release/v11-1-analytics-review/docs/v11.1-release/ACTIVATION.md

139 testov čistého kandidáta prešlo; extra výskumné testy sa do produkčného testovacieho runnera nekopírovali. Overené rovnaké main.py, bot_state.json, delivery journal a pôvodné requirements oproti87a3143, rovnaký cron/concurrency, nezmenené ostatné produkčné joby. Nový analytický zdroj sa vyberie iba výslovným V111_INTEGRATION_ENABLED=true; inak sa zachová presný pôvodný pin929bd63.

GitHub odmietol vytvorenie draft PR cez GraphQL aj REST: Forbidden. Vetva je pushnutá, PR nie je vytvorený. Pripravené otvorenie jedného PR:
https://github.com/janmarticek4-dot/crypto-bot/compare/main...release/v11-1-analytics-review?expand=1

Žiadny merge, deployment, testovací Telegram, zmena Secrets alebo skutočného stavu neboli vykonané. Finálny živý runner/časovo oddelené ráno a večer zostávajú neoverené; zdrojové pokrytie je čiastočné podľa RELEASE REVIEW.
