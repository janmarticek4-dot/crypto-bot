# Historické výsledky V11

Freqtrade 2026.9, spot, bez páky. Obdobie 2024 je vývojové; 2025 je oddelená validácia. Parametre sa po výsledkoch netunili.
Poplatok 1,2 % na každej strane modeluje 1 % eToro + 0,2 % spread/sklz. Je to predpoklad, nie nameraný spread. Skutočné náklady môžu byť vyššie.
4H signály, 1H detail exekúcie, uzavreté 1D informative sviečky. Stoploss -20 % je iba simulovaný stop, nie garancia skutočnej straty.
Hold baseline: rovnaký účet $8 500, $1 000 all-in na dostupný pár, zvyšok cash, vstup na začiatku dostupného obdobia a likvidácia na konci. Nové listingy majú kratšiu históriu; nekryté roky sa nevymýšľajú.

| Obdobie | Stratégia | Výnos | Max DD | Obchody | Win rate | PF | Sharpe | Hold výnos | Hold DD |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 20240101-20250101 | CombinedStrategy | 0.00% | 0.00% | 0 | 0.0% | 0.00 | 0.00 | 39.52% | 45.38% |
| 20240101-20250101 | PullbackComponent | 3.54% | 14.38% | 13 | 38.5% | 1.20 | 0.04 | 39.52% | 45.38% |
| 20240101-20250101 | TrendComponent | 15.12% | 21.36% | 35 | 31.4% | 1.29 | 0.14 | 39.52% | 45.38% |
| 20250101-20260101 | CombinedStrategy | 0.00% | 0.00% | 0 | 0.0% | 0.00 | 0.00 | -42.07% | 48.62% |
| 20250101-20260101 | PullbackComponent | -10.50% | 10.90% | 10 | 30.0% | 0.24 | -0.32 | -42.07% | 48.62% |
| 20250101-20260101 | TrendComponent | -43.44% | 43.44% | 44 | 20.5% | 0.37 | -0.99 | -42.07% | 48.62% |

Detaily vrátane Sortino, baseline Sharpe a názvov zdrojových archívov sú v BACKTEST_RESULTS.json.
Výsledky týchto výskumných stratégií nie sú validáciou celej produkčnej logiky: portfóliové prahy, overovanie eToro a správy sa nesimulujú. V11_RULES_VALIDATED preto zostáva predvolene false.
HYPE: Binance listing 24.09.2026; pre obdobia 2024/2025 neexistujú sviečky. Nie je zahrnuté do výnosov.
Lookahead-analysis TrendComponent 2024: 10 signálov, no bias detected. Nie je to dôkaz ziskovosti.
Lookahead-analysis CombinedStrategy sa skončila ako FAILED/too few trades (menej než 10); nejde o úspešnú kontrolu úniku budúcnosti. Pravidlá preto neaktivovať.
Zero-trade beh nie je dôkaz predikčnej schopnosti. Backtest nepoužíva AI ani percentuálne pravdepodobnosti.
