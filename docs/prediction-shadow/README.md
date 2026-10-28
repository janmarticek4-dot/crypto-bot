# Disabled prediction research — 28 October 2026

This is a small, separate research module, not another bot or trading strategy.
Production delivery, runtime pins, schedules, private holdings, main.py,
bot_state.json and Telegram journal are unchanged. No activation flag is added.

## Method frozen before evaluation

- Six individual spot pairs, Binance public 4h candles, last 1000 closed bars.
- Horizons are endpoint closes after 24h, 72h and 336h. Labels “48–72h” and
  “7–14 days” describe the scenario horizon; tests measure 72h and 14 days only.
- Directional heuristic: EMA50 and MACD agreement; trailing 20-bar return scaled
  by horizon, clipped at one past log-return standard deviation scaled by sqrt(h).
  No learned coefficients, parameter search, automatic retraining or probabilities.
- Band: empirical 10th–90th percentiles of *already completed* horizon returns.
  These are NOT calibrated confidence intervals, intraperiod extremes or guarantees.
- First 70% development, last 30% chronological research test. Labels crossing
  the split are purged; a test origin may use earlier, already observed test data.
  Fixed origins every six bars. Outcomes overlap; sample counts are not effective
  independent sample sizes. All 2024–2026 history is previously examined, including
  this test. No claim of independent out-of-sample confirmation.
- Compare endpoint MAE and exact up/down/unchanged direction against unchanged
  price and uncapped continuation of the past 20-bar trend. Flat direction is
  literally unchanged (not an invented tolerance). Small drift matters to this metric.
- The module does not trade. Forecast errors are not net trading returns. There
  is no new BUY/SELL rule requiring a strategy-vs-HOLD performance claim. Optional
  watch-zone economics use 1% and 1.2% each side + 0.25% adverse fill each side;
  these are assumptions, not verified eToro spreads. No finding authorizes a trade.

## Individual interpretation and limits

Each coin has its own historical return distribution, structural levels, momentum
change, volume ratio, BTC-relative strength and daily/4h/1h diagnostic frames.
Potential reversal is distinct from volume confirmation; action remains WAIT for
new purchases. This research does not inspect personal holdings or override HOLD.
Risk families group correlated technical evidence; volume is only a candle proxy,
not observed order flow. Liquidity depth, full ETF flows and calibrated event
surprises remain N/A. Source announcements are evidence of publication, not
proof of adoption or causal price movement. Missing fundamentals reduce certainty;
they never become numeric drift. No unvalidated combined macro/technical weights.
Ranking is an explicit heuristic count of three evidence groups, not an expected
return/risk ranking validated on independent data. This limitation prevents promotion.
Current ticker and closed-4h origin can differ and are explicitly distinguished.

## Public journal and paper observation

`public-predictions.json` is separate from production state and delivery journal.
Whitelisted public fields only; bounded to 600 records, atomic local writes,
deterministic IDs and exact-horizon closes. Missing endpoint => unscored; never
substitute today's quote. Matured results are immutable. Scores include actual
return, direction, band hit, point error and flat/continuation baseline errors.
A 600-record cap can discard unscored forecasts under frequent manual runs;
this is bounded diagnostic memory, not a complete longitudinal research database.

Workflow **Prediction Research Shadow** is manual only, no Secrets, no Telegram,
no private repo. Default permission is contents:read. Outputs are validated by
public-data policy before upload. Optional `persist_public_research_journal`
(default false) enables a separate contents:write job for exactly
`public-analytics/prediction-shadow.json` on main, with old-content digest and
GitHub blob-SHA compare-and-swap. Conflicting changes fail instead of overwriting.
Only public research forecasts are stored. No production snapshot is migrated.
Local corrupted journal fails visibly, never silently initializes a replacement.
Artifacts expire in 14 days and are not treated as durable portfolio storage.

## How to run / activation

GitHub → crypto-bot → Actions → **Prediction Research Shadow** → Run workflow →
branch **main** → Run workflow. Leave public-journal checkbox off for a pure preview.
Results: run → Artifacts → `prediction-research-<run_id>` → `preview.txt`,
`diagnostics.json`, `public-predictions.json`, `journal-manifest.json`.
To deliberately build a *public paper-research* history, tick the clearly named
journal checkbox. It does not enable production forecasts or Telegram delivery.

**Do not activate this model in production.** There is no production switch for
it. Existing V11.2 settings are unchanged. A later explicit approval would require
validated forward observations, a reviewed presentation hook and a new immutable
runtime source pin; merely setting an invented environment variable has no effect.
Rollback of this addition is a normal revert of its code commit; existing production
state and operational source pin require no rollback because they were not changed.
