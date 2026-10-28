# Integration verification

- Backup: `backup/main-before-prediction-shadow-20261028-e770f4c`.
- Base: main `e770f4c`; normal fast-forward integration, no PR/force/reset.
- Offline suite: 183 tests, blocked unmocked network, including missing data,
  chronological causality, fee sensitivity, unique price scaling, journal limits,
  deduplication, exact endpoint matching and immutable evaluated outcomes.
- Live public GET collection: 28 Oct 2026 06:37 UTC (07:37 Bratislava).
  Six primary coins had available current market data and closed candle history.
  Forecast-origin prices are closed 4h prices, not the later ticker quotes.
- Fundamental source diagnostics: 33 attempts, 4 current in this execution
  environment. See source-check.json for explicit per-endpoint outcomes.
  This is not a new GitHub-hosted runner execution, nor complete macro coverage.
- Live preview and historical tests executed locally, not sent to Telegram.
  Histories are the last 1000 closed 4h bars per coin, not full multi-year tests.
- Historical performance insufficient: all 18 coin/horizon point-MAE comparisons
  lose to unchanged-price baseline. Recommendation: reject production promotion;
  no probability calibration or medium/high confidence justified.
- Manual GitHub workflow prepared but not dispatched here. Its runner results
  and future time-separated paper observations remain unverified.
- No new executable production hook, source-pin update or activation flag.
  No private inventory accessed, Secrets changed or production state written.
- Byte comparison with base confirmed unchanged main.py, bot_state.json,
  trial-public/v111-delivery.json, run.yml, strategy.py, analyst.py and delivery
  scripts. Existing manual/07:00/15:00/20:00 reports and monitoring are untouched.

Remaining scope deliberately not claimed as complete: calibrated macro-event
forecasting, full order-flow/liquidity coverage, verified multi-timeframe predictive
advantage, risk-adjusted ranking validation and independent future confirmation.
No automatic adaptive learning or new trading strategy was introduced.
