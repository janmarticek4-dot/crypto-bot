# V11.1 shadow follow-up — 22.10.2026

## Scope

Only feature/v11-1-review. No production/main merge, broker, Telegram, private state or actual portfolio changes. `v11/strategy.py`, `v11/portfolio.py`, `v11/runtime.py`, `main.py`, `bot_state.json` and `.github/workflows/run.yml` stay byte-identical to993e4f6. AdaptiveHold V2 is neither imported nor activated. New explanations do not change trade decisions or alert thresholds.

## Confirmed causes and repairs

| Observation | Exact cause | Change / remaining limit |
|---|---|---|
| Fed/BLS/ECB/SEC/AAVE/ONDO unavailable | Original failures are URLError: network tunnel403, before an origin response. Not evidence of publisher outage or a faulty API key. | Each attempt now records `error_layer` and original/selected source. Free endpoint alternatives preserve publisher checks and individual trust; blocked origins remain N/A. |
| AAVE primary forum blocked | Same tunnel restriction. | Reachable `github.com/aave/aip/commits/main.atom` fallback. A proposal/commit is labelled a repository change, not adoption, implementation or positive economics. No current records in the live recheck. |
| ONDO primary blog blocked | Same tunnel restriction. Probed guessed repository paths404; these were NOT added. | Secondary CoinDesk RSS restricted to ONDO and substantive fundamental/regulatory topics. Secondary attribution remains explicit. Reachable feed with0 matching current records is NOT a fundamental conclusion. |
| Calendar empty | Official FOMC/BLS endpoints blocked here. News publication time is not event time. | Verified parser/window tests for24h,7d,14d, exact boundaries, US/EU DST mismatch, date-only/floating times. Unknown time stays N/A; no assumed20:00 Fed announcement. Actual upcoming calendar remains unverified until an official source is accessible. |
| All six WAIT | Actual12:07 snapshot had technical scores only2–3/6. In addition: eToro availability not verified, spread unknown and V11 rules unvalidated. Shadow does not load real holdings. | Separate technical checks/failed conditions from entry blockers. Never rerun decide with `approved=True` to force BUY. Unknown holdings now explicitly labelled DRŽBA N/A(SHADOW); no HOLD/SELL claims for actual positions. |
| NORMAL at market cap−5.12% | Existing WARNING requires BTC and ETH closed4h support breakdown plus>=4altcoin breaks. All8 observed support flags were false; BTC24h−1.613%,ETH−1.704%. Aggregate cap is not that technical predicate. | Keep risk/alert policy intact. Show each evidence flag and price breadth. Label broad price weakness separately, and explicitly say NORMAL does not mean low overall risk. No calibrated crash probability or automatic alert from cap decline. |
| Same12:07 snapshot in two templates | Previous runner intentionally generated previews, not independent temporal samples. | Separate morning/evening phases with durable public checkpoint artifacts, checksums, freshness, source fingerprint, same-date/time separation and Actions provenance validation. Reused data, wrong day, noon-as-morning and stale data fail closed. |

## Original WAIT diagnostics (real22.10,12:07 Bratislava)

| Coin | Score | Failed technical gates |
|---|---:|---|
| AAVE |3/6|4h trend,volume,structure|
| TAO |2/6|4h trend,momentum,structure,ADX strength|
| FET |2/6|4h trend,daily trend,volume,structure|
| SOL |3/6|4h trend,momentum,structure|
| ONDO |3/6|4h trend,volume,structure|
| RENDER |3/6|4h trend,volume,structure|

All also retain unverified eToro/spread/unvalidated-policy blockers. A technical ranking is a hypothesis for review, never permission to buy. New current figures live in `entry_diagnostics.json`; the old scores above are not silently reused as current advice.

## Source fallback policy

`FALLBACKS` in v11/fundamentals.py:
- Fed monetary RSS as an alternate Fed news endpoint; not a substitute verified meeting calendar.
- BLS current-year ICS as an alternate calendar endpoint; remains blocked/unverified here.
- ECB blog as a narrower official commentary fallback, not rate-decision confirmation.
- SEC legacy press feed, same publisher/redirect trust validation.
- AAVE public AIP repository commits, unconfirmed governance-change semantics.
- ONDO filtered secondary news, never relabelled official.

Fall back only after fetch/schema failure, not merely because a valid feed has no fresh items. Keep each attempt and selected source. Official feeds cannot confer official trust on unrelated linked domains. Do not use open proxies, undocumented paid-data APIs or AI guesses to evade unavailable sources. Reachability is not completeness, and marketing is not demonstrated adoption. Macro/protocol revenue/unlocks/consensus gaps remain explicit.

## A real two-run test

Workflow **V11.1 Shadow Test** now has `phase=preview|morning|evening`:

1. On the next testing day (e.g.23.10.2026), run `phase=morning` from07:00 to08:30 **Europe/Bratislava**. Keep Groq off for the deterministic baseline. Choose branch `feature/v11-1-review`.
2. Download/preserve the resulting artifact; note the run ID. It contains `checkpoints/morning.json`, actual morning report, public market source data and evaluations. Existing checkpoint cannot be overwritten. Artifact retention7days is enough for this same-day isolated test; download for a longer audit archive. This is not a store of actual portfolio data.
3. From20:00 to21:30 on the SAME Bratislava date, run `phase=evening`, enter that `morning_run_id`, and use the SAME COMMIT. Do not push code changes between phases. Workflow validates upstream workflow path,event,branch,SHA,success and artifact attempt. Only actions:read is added; no state/broker permission.
4. The evening runner checks schema/checksum, real morning window, quote completeness/freshness, same date,>=8h and<=16h gap, different market-source fingerprint and at least8h difference in actual collector timestamps. Changing only `snapshot.at` cannot make reused data independent.
5. Download evening artifact: `evening.txt`, `morning_reference.txt`, `comparison.json`, `comparison.txt`, `entry_diagnostics.json`, `risk_evidence.json`, `calendar_coverage.json`, source statuses and fault tests. The comparison includes prices,marketcap,rolling24h volumes,EMA/ADX/structure and original→current recommendations. Price endpoint results are not profits;24–72h/7–14d predictions are not prematurely graded.

These are live observation windows, not backdate arguments. The CLI exposes no timestamp override. Manual delay within the window is logged as the actual observed time. Missing/malformed/incomplete checkpoints or wrong-time phases return failure and record `phase_validation.json`; they never silently compare against a different day or a newly fabricated morning.

CLI, from an authorized GitHub client:

```bash
gh workflow run v11-1-shadow-test.yml --repo janmarticek4-dot/crypto-bot --ref feature/v11-1-review -f phase=morning -f use_groq=false
# At the actual evening slot of the same day:
gh workflow run v11-1-shadow-test.yml --repo janmarticek4-dot/crypto-bot --ref feature/v11-1-review -f phase=evening -f morning_run_id=MORNING_RUN_ID -f use_groq=false
```

Existing GitHub default-branch workflow-discovery limitation still applies; do not change or dispatch the production workflow as a workaround. A separate research fork with this branch as its default is an alternative; see SHADOW_TEST.md. No scheduled action or deployment was enabled.

Local equivalent (same directory persisted between actual runs):

```bash
python scripts/v111_shadow.py --phase morning --output shadow-output/day-test
# SAME day, at the actual evening observation window:
python scripts/v111_shadow.py --phase evening --output shadow-output/day-test --checkpoint shadow-output/day-test/checkpoints/morning.json
```

## What has and has not been verified

Automated causal/protocol tests use explicitly synthetic fixtures and never send Telegram. They cover price/cap/volume/trend/action changes, stale/missing fields, wrong day,time windows,DST,checksum corruption,overwrite protection,reused source snapshots,proxy403 vs origin errors,fallback trust,calendar boundaries and technical-vs-operational blockers. Existing offline/runtime/monitor/strategy tests are rerun unchanged.

A new isolated LIVE midday preview was generated on22.10.2026 with current data for all six coins. AAVE/ONDO secondary endpoints improved feed reachability from6/16 to8/16, but had0 matching current events. Official macro sources remain blocked by the tunnel; upcoming calendar completeness and new fundamental facts remain N/A. Groq missing/unavailable fault cases passed; no new live Groq request was made.

**No actual07:00→20:00 pair has yet been observed.** The12:07 original and new midday snapshot are not passed off as a valid pair. A real wrong-time morning attempt was refused; successful pair/change tests are synthetic. See SHADOW_FOLLOWUP_VALIDATION.json for exact live timestamps and results. GitHub Actions/API operation is claimed only with an actual run URL; the previous API Forbidden was not presented as a successful Actions run.
