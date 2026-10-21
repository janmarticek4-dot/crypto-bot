# V11.1 verification

## Automated checks

- 127 bot unit/integration tests passed via `python scripts/test_offline.py`.
  Unmocked socket connections are blocked and Telegram disabled. Includes
  source failure, stale/invalid fallback provenance, fees/R:R, Groq cache/failure
  and Retry-After, silent monitoring/cooldowns, DST/holidays, synthetic isolation,
  forecast maturity/legacy migration and uncertain-send non-replay.
- 22 phase-3 research tests passed.
- 11 phase-2 engine tests passed.
- Workflow YAML parsed, backtesting shell syntax and `git diff --check` passed.
- Offline synthetic examples regenerated with independent asset fixtures.
  Morning/evening currently fit four numbered Telegram parts each; USA one.
- `v11/strategy.py`, `v11/portfolio.py` and tracked `bot_state.json` are unchanged
  from research/v11-phase3. No actual fill/holding was edited.

## Real Freqtrade execution

36 asset/strategy/period targets: 33 executed backtests, 3 NO_DATA targets (ONDO
2024 absent in this stored dataset). See SINGLE_COIN.md and JSON for all metrics.
All executed targets have fewer than 10 trades individually and are labelled
INSUFFICIENT. Trend totals 48 trades across targets, pullback 22, combined zero.
These totals do not turn an insufficient asset-period test into a validated
strategy. Cash sometimes outperforms declining buy-and-hold; that is not proof
of predictive skill. No strategy is approved.

Config, strategy and OHLCV data checksums and package versions are recorded in
BACKTEST_MANIFEST.json. Per-run archive hashes are in single_coin_results.json;
raw archives/logs stay under ignored backtesting/user_data/v111-single.
The research workflow uploads these research files only, without private state.

The initial single-asset run stopped on ONDO's missing 2024 history. The runner
was corrected to label missing periods NO_DATA, then the whole matrix reran.
No missing price history was generated or silently substituted.

## Not performed / not claimed

No production Telegram send, brokerage order, deployment, paid-data purchase,
new live macro-source verification or fresh full walk-forward optimization.
The existing combined-strategy lookahead test remains inconclusive due to too
few trades; no new successful lookahead certification is claimed. Component
backtests are not validation of the complete production recommendation system.

Live source accessibility/schema verification, macro numeric results/consensus,
full per-project economics coverage, manual execution-delay simulation and
independent-origin verification of crisis reports remain deployment blockers
for claiming complete coverage. Review AUDIT.md before approving rollout.
