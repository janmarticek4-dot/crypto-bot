# Overenie fázy 2

## Reálne vykonané

Posledná kontrola: **60 testov bota/storage/fundamentov + 11 výskumných testov = 71 testov, všetky prešli, bez preskočenia.**

- Stiahnuté verejné OHLCV Binance spot 1H/4H/1D pre šesť altcoinov a BTC/ETH;
  všetky dáta obsahujú časové pečiatky. Počty, intervaly, SHA256 a tool versions
  sú v manifest.json. Exekučná medzera počas testu sa nevypĺňa vymyslenou cenou.
- 378 samostatných metrík: 6 stratégií × 3 časové obdobia × 3 nákladové varianty ×
  (portfólio + 6 samostatných mincí). Celkovo 2380 uzavretých simulovaných obchodov
  naprieč variantmi; nie je to 2380 nezávislých pozorovaní.
- Pôvodný Freqtrade test rozobraný z uložených archívov, SHA uvedené v JSON.
  Nové explicitné porovnania fee 0 / .002 na 2024/2025, protective-exit ablation
  pre 2024/2025/2026 a pôvodný TrendComponent na holdoute 2026.
- Každá kombinovaná sviečka uložená s čiastkovými podmienkami a blockers v gzip CSV.
- Unit/integration testy bota, súkromného storage a fundamentov; samostatné testy
  výskumného enginu vrátane budúcej mutácie cien, budúcej dennej dostupnosti,
  gap stop fill, nákladov, reentry a cash rozpočtu.
- Test lokálnej súbežnosti: druhý proces/thread nesmie načítať starý vzdialený
  checkpoint cez lokálny súbor práve bežiaceho zapisovača. Lock pred načítaním
  dopĺňa vzdialený SHA compare-and-swap.
- Opravená ochrana pôvodného reportu proti prepísaniu fee-zero alebo ablation
  výsledkom len kvôli novšiemu názvu archívu; regresný test overuje výber.
- Súkromný storage: autentifikované šifrovanie, iné prostredie/kľúč, public repo,
  chýbajúci stav, záloha, konflikt, nejednoznačný úspech PUT, ochrana public checkoutu.
- Živé verejné fundamentálne HTTP požiadavky: oficiálne domény blokované proxy
  403; Cointelegraph pri poslednej kontrole vrátil 4 čerstvé klasifikované položky. GitHub Atom feedy SOL/TAO/FET a RENDER boli dostupné, bez čerstvých položiek v 72h okne. CoinDesk HTTP
  úspech, nula čerstvých relevantných položiek. Health snapshot je uložený.
- Manifest výsledkov má stav complete a SHA256 artefaktov; report odmietne nedokončený, zamenený alebo zmenený beh.
- Syntax GitHub workflow, `bash -n`, Python compile, pip check v oboch venv,
  git diff whitespace kontrola; stratégie v produkčnom v11/strategy.py a pôvodný
  bot_state.json sú oproti fáze 1 nezmenené.

## Opakovanie

Použite samostatný Python 3.12 venv s backtesting/requirements.txt a bot dependencies.
`bash research/phase2/run_all.sh` s cestami FREQTRADE_BIN/RESEARCH_PYTHON podľa
prostredia. Skript nevykoná main.py, Telegram ani žiadne broker operácie.

Rýchle kontroly bez sieťových API:

```
/workspace/.venvs/crypto-bot/bin/python -m unittest discover -s tests -v
/workspace/.venvs/freqtrade/bin/python -m unittest discover -s research/phase2 -p 'test_*.py' -v
```

## Nevyskúšané / blokované / nenasadené

- Žiadny private repo, GitHub PAT ani šifrovací kľúč nie sú nakonfigurované.
  Live persistence, reštart GitHub runnera a obnova zo skutočného private repo
  zatiaľ NEBOLI overené. Neexistujúce hodnoty sa nenahradili vymyslenými.
- Oficiálne RSS/ICS endpointy čakajú na sieťový prístup a následné reálne overenie.
  Token unlock kalendár bez potvrdeného zdroja zostáva N/A.
- Žiadna nová produkčná BUY/SELL logika, merge, push, GitHub Actions run ani
  publikovanie cloudového prostredia. Žiadne nové Telegram odoslanie alebo
  spracovanie reálnych príkazov. Reálne finančné dáta neboli vytvorené ani uložené.
- Holdout sa vyhodnocoval pre fixné pravidlá bez doladenia; kontrola chýbajúcich exekučných dát bola po oprave zopakovaná. Neoptimalizovať na už zobrazených
  výsledkoch a nenazývať prípadné ďalšie doladenie nezávislou validáciou.
