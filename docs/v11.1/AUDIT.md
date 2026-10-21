# V11.1 audit and review boundaries

Work builds on the existing V11 phase-2/phase-3 research and the prior local
morning/evening/USA report work. It is not a replacement bot.

| Area | Existing | Findings / V11.1 changes |
|---|---|---|
| Scheduling | Bratislava 07/15/20 with grace window | Aware timezone conversion, CET/CEST cron candidates, silent 15-minute monitor, workflow concurrency retained |
| Main report | Per-asset closed-candle TA and costs | Missing `previous` caused incomplete-data path to fail after sending; fixed and regression-tested |
| Data | Binance candles, CG metadata | Invalid Binance price could borrow a fresh ticker timestamp for a stale CG fallback; provenance fixed |
| Indicators | RSI/MACD/EMA20/50/100/200/ADX/ATR, support/structure | Expose calculated values and BTC/alt-median relative strength; never AI price levels |
| Forecasts | Technical scenarios and registry | Preserve text/method/source/bar timestamps; import legacy registry without modifying original records; endpoint tests are not proof of alternate-path accuracy |
| Telegram | Long-message line splitter | Numbered UTF-16-safe chunks; synthetic/test guard; durable attempt journal; uncertain timeout cannot safely be retried automatically |
| AI | Groq chooses existing reason indexes; caching, 2h failure cooldown | Existing bounded 429 Retry-After/backoff retained; selected reasons now used by report, deterministic fallback remains |
| Holdings | Manual ledger and encrypted private state | No real position changes. Legacy recommendation is not a fill. Default initial cash is explicitly unconfirmed without ledger evidence |
| Fundamentals | Official project notices, BLS/Fed/BEA/SEC, candidate ECB/CFTC feeds, TVL | Project notices remain distinct from adoption/revenue; incomplete coverage is explicit |
| Macro | BLS timed events, FOMC meeting dates | Add official Treasury daily yields with freshness bounds; never call them live, DXY or consensus |
| Event review | Separate expected/result/observations | Numeric consensus and macro release extraction remain N/A; no unsupported surprise score |
| Monitor | Two matching incident sources + market stress + cooldown; no routine AI | Safety criteria unchanged. Two domains may share an original report; independent-origin verification remains a limitation |
| Freqtrade | 2026.9 installed, real historical archives, pinned research requirement | Manual research workflow; independent single-asset runs, archive hashes, per-period hold comparisons; no trading command |
| State | Corrupt state fails closed, private repo encryption/CAS/local locking | Keys retained; no public portfolio copy. No real state is used by generated examples |
| Review CI | Existing unit tests | Offline runner rejects unmocked socket connections and disables Telegram; PR workflow receives no secrets |

## Freqtrade and historical errors

The installed executable reports Freqtrade 2026.9, Python 3.12 and CCXT 4.5.89.
The configured exchange is Binance spot public data, not Bybit. The older Bybit
failure cannot be reconstructed without its logs. Prior documented CCXT problem
was certificate-chain validation; config includes OS certificates and proxy
support without disabling TLS verification.

Single-asset runner explicitly rejects configs containing exchange credentials
or dry_run=false and invokes only `backtesting`. Model cost is 1.2% each side:
1% fee plus assumed 0.2% spread/slippage, not an observed eToro spread. Runtime
BUY_FEE and SELL_FEE are configurable separately; research cost is the config fee.
2024/2025 were already inspected, so 2025 is not described as a newly untouched
holdout. Existing walk-forward/robustness work remains in docs/phase3.

The available ONDO dataset has no 2024 candles. This is NO_DATA rather than a
zero-return strategy result or a fabricated history. Shorter listing/warmup
coverage is reported. No strategy is promoted from historical results.

## Delivery semantics

A private-state journal is checkpointed before sending a scheduled report.
Already attempted slots are not replayed; last_main_slot marks completion only
following success. Telegram has no idempotency key: a timeout can mean that a
message arrived. Status `uncertain` therefore requires operator review of the
chat before deleting that slot's journal entry for an explicit retry. Partial
reports may remain partial until review; exactly-once delivery is not claimed.
Telegram sendMessage itself uses one HTTP attempt to avoid timeout retries.
Journal contains hashes/status/timestamps, not public message bodies.

## Remaining source/validation limits

- Comprehensive verified adoption, revenues, unlocks and incident data for all
  six projects are NOT complete; unavailable values remain N/A.
- Full future macro coverage, licensed expectations/FedWatch, actual numeric
  releases, ETF flows, DXY and global geopolitical coverage remain incomplete.
- FOMC calendar provides meeting dates; exact decision time is N/A unless
  explicitly evidenced. A scheduled date is not a confirmed release result.
- Official Treasury parser is fixture-tested; live access/schema compatibility
  on the deployment runner must still be verified. No paid source purchased.
- Forecast outcome currently tests base-range endpoint at 72h/14d. It does not
  reconstruct every intrahorizon branch or provide calibrated probabilities.
- Manual execution latency is acknowledged, not fully simulated by the
  Freqtrade component tests. eToro fills may differ from Binance USDT proxies.
- No new production trade signal is approved. Existing v11/strategy.py and
  portfolio fill/safety decision logic are not modified by this change.

The PR includes earlier unmerged V11 research history because main is still the
V10.6 base. Review workflow/runtime migration separately from research reports.
No deployment, merge, live trade or real ledger update is authorized here.
