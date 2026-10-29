# Prediction Research V2 — main delivery integration, 29 October 2026

## Root cause and current production

The actual 29 October morning run 40827329123 checked out source 59c5a774. Its 18 missing forecasts were caused by inconsistent millisecond truncation: observation `2026-10-29T06:08:43.651541Z`, snapshot `1793254123.6515152` seconds, computed age `-0.51513671875 ms`. All seven histories had 299 aligned closed candles; the old future-snapshot guard rejected them all. The original archived inputs and original pre-event package replay to 18 forecasts with the fixed clock. Evidence is retained in `docs/analysis-quality-20261029` and audit 40885112804. This replay is a regression, not independent prediction-performance validation.

At the start of this task, main was e7938cb and the actual approved delivery source was a4a1e9c, confirmed by successful production source run 40899232073. That source already contained the clock fix. Therefore the morning failure is historical, not proof that the current production still returns N/A. The next 20:00 delivery has not happened at the time of this work. No test Telegram is authorized or sent.

## Finishing the delivery boundary

- Runtime output now carries generation time, model observation time and a display validity deadline. Current presentation lasts at most 15 minutes, additionally bounded by snapshot age, last closed 4h bar and the existing 48-hour model/package limits. The deadline is not the 24/72/336-hour forecast target. Historical paper predictions retain their original dates.
- The final main renderer filters expired, future, unclocked, nonfinite or invalid-range outputs. Missing forecasts use only explicitly labeled technical fallback; stale inputs do not create invented bands. Private personalization checks the current wall clock after private-store requests, without changing any action rules.
- Diagnostics give package/snapshot age, HTTP status on public-store failure, per-coin availability and specific missing-horizon/input reasons. Genuine future/stale packages and gapped histories remain rejected. A missing horizon does not discard the other 17 outputs; a single coin's data gap does not discard the other 15.
- Actual receipt metadata counts predictions in final rendered text rather than the raw in-memory model. Only public counts/source/format fields are persisted. Existing attempting/uncertain dedup and private-state boundaries remain in force.
- The existing production readiness workflow creates full morning/evening previews with current data, proves 18 outputs and emits a minimal freshness contract. No new research workflow, new strategy, online fitting, trading permission, AI probability or broker call was introduced.

The live local preview produced SOL/TAO/FET/AAVE/ONDO/RENDER = 3 forecasts each. Snapshot age 2974 ms, package age 15192192 ms (~4.22 hours), no missing outputs. Local network restrictions prevented some official sources; the GitHub-runner preview is required before activation. Preview time is the actual collection time on 29 October, not a reconstruction of 07:00. Morning/evening previews are two format checks of the same new collection, not two independent observations.

308 offline tests pass, including exact-clock regression, both main report formats, the actual scheduled delivery entrypoint with a synthetic SOL/TAO inventory, unchanged personal actions, all 18 outputs, real future/stale inputs, missing horizons, isolated coin gaps, safe dated fallback on HTTP 429, no fitting in delivery, privacy and repeat-run dedup. Synthetic fixtures are never sent to Telegram or persisted in real state.

## Deployment and limits

Backup tag: `backup/before-v2-completion-20261029` -> e7938cb. Activate only the immutable candidate after clean CI and a live GitHub-hosted preview. Preserve the USA implementation byte-for-byte; preserve main.py, bot_state.json, private portfolio, public delivery/paper journals, Secrets, fees, schedules and existing trading rules. Rollback reverts only the activation pin commit, never resets or rewrites state.

This verifies operational availability, not predictive advantage or calibrated probabilities. Future market/API/model outages can still legitimately produce an explicit fallback. Actual scheduled Telegram delivery can be verified only after it occurs, using the existing read-only production audit. It must not be simulated by sending a test message.
