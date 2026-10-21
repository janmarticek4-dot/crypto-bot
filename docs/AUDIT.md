# Audit pred V11.0

Overené 21.10.2026 na pôvodnej V10.6. Celý projekt tvorí main.py,
requirements.txt, dva uložené výstupy/stavy a jeden Actions workflow.

- Zber cien musí najskôr prejsť CoinGecko. Výpadok po niekoľkých volaniach
  znefunkční FET/SOL/ONDO/RENDER napriek dostupným Binance dátam.
- Jedna cena na jedno CG volanie, následne ticker, sviečky a Coinbase pre každú
  mincu zvyšujú záťaž. Snapshoty treba dávkovať a cacheovať v rámci behu.
- 4H indikátory existujú; ADX, BB, VWAP a viacero rámcov chýbajú.
- Chýbajúce kapitalizácie sa menia na nulu. Neúplné pokrytie môže vrátiť NORMAL
  a zmeniť REDUCE na WAIT. Nejde o dôkaz zlepšenia.
- BUY NOW pri stabilizovanom poklese obchádza hlavný prah skóre a ekonomiku R:R.
- HOLD/SELL nerozlišuje skutočné vlastníctvo. Neexistuje účtovná kniha.
- Groq vysvetľuje aj nekryté správy; AI percento istoty nie je kalibrácia.
- HTTP 429 nemá Retry-After ani cache. Staré logy neobsahujú dôkaz presnej
  príčiny minulých 429: môže ísť o RPM/TPM/dennú kvótu; nesmie sa tvrdiť presná
  príčina bez odpovede poskytovateľa. Limity sa líšia podľa účtu/modelu.
- GPT-OSS inference bola overená HTTP 200. Browser search na bežnom GPT-OSS
  nie je predpoklad: výskum musí pri nepodporovanom nástroji bezpečne zlyhať.
- */15 UTC + ZoneInfo Bratislava/New_York rieši DST v aplikácii; Actions má
  oneskorenia a nemá SLA. Potrebná deduplikácia slotov a obmedzené doháňanie.
- Workflow nemá inštaláciu requirements; `git pull ... || true` môže ignorovať
  konflikt. Git stav obsahuje iba odporúčania, nie dôkaz vykonaných obchodov.
- Samotné dva URL vytvorené AI neoverujú nezávislé potvrdenie krízy.
- Žiadny test suite ani Freqtrade modul. Starý pokus s Bybit nie je v checkout;
  jeho presnú príčinu bez logu nemožno rekonštruovať. Nové testy majú používať
  verejné Binance spot dáta a oddelené prostredie, bez obchodných kľúčov.

Úpravy sú vývoj V11, nie onboarding: pôvodný tracked bot_state.json sa nemigruje
pri importe; len pri riadnom behu sa aditívne pridajú nové oddelené sekcie.
Nové strategické filtre sú experimentálne do ukončenia historickej validácie.
