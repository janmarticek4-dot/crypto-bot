# V11.1 integration into the existing Crypto AI Bot — review only

## Baseline and scope

Integration branch: `integration/v11-1-main-review`, based on production `main` at **3f21337**. Reviewed source: **b248252** from `feature/v11-1-review`.

There is one repository and one production bot. No new bot, repository, portfolio migration or Secret is created. No merge, deployment, scheduled production run or test Telegram message is performed.

Production is already hybrid: `main.py` remains V10.6, while the existing workflow routes scheduled morning/evening and USA reports to a previously approved V11.1 pilot pinned at `929bd6389216be1b4eefcd1be61be89d944abf33`. Monitoring and manual legacy analysis stay in V10.6. A wholesale merge of the research branch would replace legacy entrypoint/state semantics and is deliberately avoided.

## Prepared changes

| Area | Existing production | Integration candidate |
|---|---|---|
| BUY/SELL/risk logic | Native V10.6 and previously deployed pilot | Calls unchanged `main.evaluate_all`, `technical_summary`, `calculate_technical_score`, `compute_structure`; new events do not modify scores or signals |
| New fundamentals | Older pilot source | Evidence-bounded market/project explanations, dates/URLs, deduplication, source freshness/coverage, bp changes, TVL/fees/revenue history |
| Source credibility | Mixed availability | Transport/schema/current relevant content distinguished; missing observations stay N/A; headlines are not verified outcomes |
| Forecasts/strategies | Existing production behavior | No AdaptiveHold, Freqtrade, new V11 entry/exit rules or probabilistic model activation; only prior delivered forecasts are audited, no new V11 forecast is created |
| Morning/evening | Existing delivery journal | Public native-rule observations plus strict independent morning reference; missing/invalid reference N/A |
| Telegram/dedup | Existing pilot sender/CAS | Same canonical journal and sender; no second delivery process. Missing established journal fails closed |
| 15:00 USA | Existing pilot session/calendar implementation | Delegated to the same USA path; no legacy holiday logic re-enabled |
| 15-minute monitoring | Existing `main.py` | Byte-identical; no new scheduled job |
| Portfolio | Existing private advisory storage | No migration/read in shadow; existing private module unchanged from deployed source |

`v11/integration.py` adds the public report. `scripts/v111_integrated_delivery.py` is an explicit feature-gated adapter, not wired into production. `scripts/state_public_guard.py` validates state read-only; its optional ephemeral schema file contains only root key names. `main.py`, `bot_state.json`, and `.github/workflows/run.yml` remain byte-identical to the production baseline; `BASELINE.json` and tests verify this.

The data bridge recalculates native V10.6 indicators from the fetched closed 4h candles. Algorithm parity is verified for identical inputs; it is **not** a claim that independent provider fetches always equal a simultaneous legacy run. Binance fallback coverage and missing data must be checked in the manual shadow report. Rule inputs from the old V10.6 fundamental cache are preserved for native evaluation, but their truth is not re-certified. New verified-source explanations are kept separate and do not add risk points.

## Security audit

- Current baseline public `bot_state.json` and public delivery journal parse successfully and pass known private-field/credential-pattern checks. This is not a complete historical/semantic leak audit. No private values are displayed.
- Local preview reads a whitelisted copy of the public checkout cache; GitHub shadow reads the latest public main cache using the built-in read-only token; never loads actual private positions, does not export the raw cache, and never calls `save_state`.
- Missing/corrupt/empty state is refused; no replacement with `{}` at I/O boundaries. Native evaluation uses copies because the legacy peak calculation mutates its argument.
- The future delivery adapter reads the latest main rule cache via read-only Contents API, refuses private contamination and uses the already-existing scoped GitHub token. It never writes `bot_state.json`.
- Existing private advisory code and its strategy helper are unchanged from deployed source `929bd638…`. No private Secrets are passed into shadow; no artifacts contain portfolio data. Canary/privacy tests verify rejection.
- Scheduled report deduplication keeps the existing slot keys and CAS-before-send. An attempted/uncertain slot is never automatically replayed. Telegram cannot provide a general exactly-once guarantee; partial delivery requires manual inspection.
- **Existing production risks:** V10.6 `load_state` can return `{}` after corruption; the workflow ignores failed rebase using `|| true`; legacy Telegram transport retries POST. These are existing risks, not fixed in active production. The proposed workflow patch adds pre/post state validation (including refusal to drop existing root sections) and stops ignoring a failed rebase. Legacy monitor transport retries remain unchanged and are a residual risk requiring a separate reviewed transport fix; no claim of universal alert exactly-once delivery is made.
- Existing `contents: write` for the legacy state writer is retained, not expanded. No Secret name/value or GitHub environment setting is modified by this work.

## Tests and actual observations

- **81 main-based offline tests PASS**: all applicable integration-branch tests, native evaluation parity, immutable inputs, valid negative news not changing signals, secret canary refusal, malformed/empty state, existing sender ownership, USA delegation, missing journal no reset, public artifact gate and source analysis.
- The review branch's **314-test** suite was run separately against its own V11 entrypoint. Review-only tests that require replacing `main.py` with the V11 entrypoint are not represented as tests of the production-main candidate. Production candidate keeps the selected source/renderer/transport/privacy tests plus native-rule tests; fixture-only helpers are named `fixtures_*` to prevent unrelated entrypoint suites being counted.
- Actual isolated integration preview fetched current data for all six coins, exercised native V10.6 evaluation and produced the enriched evening preview. `legacy_rule_audit.json` confirms equality of native evaluations before/after enrichment. Protected file hashes remained unchanged; privacy staging PASSED.
- This is **one preview**, not two real independent observations. Real morning/evening comparison is N/A. Missing market/fundamental inputs remain N/A; local macro-provider proxy restrictions are not proof the original servers are down.

## Manual test in the existing GitHub repository

Workflow **V11.1 Integration Shadow**, `.github/workflows/v111-integration-shadow.yml`, has **no schedule**, read-only permissions, no production Secrets and explicit Telegram disablement.

Use the already registered `run.yml` **on feature/v11-1-review**, task **integration-shadow** (review-branch entrypoint added after candidate code is pinned). It calls the candidate from an immutable commit in the same repository. Do not select main or advisory import.

1. `phase=preview`: one current evening-format preview at the actual collection time. No independent pair is claimed.
2. `phase=morning`: only at 07:00–08:30 Europe/Bratislava; save the run ID after success.
3. `phase=evening`: only at 20:00–21:30 Europe/Bratislava; enter that morning run ID. Without a reference the evening snapshot is retained with comparison N/A.
4. Download **`v111-integration-<run_id>-<attempt>`**. Inspect `evening.txt`/`morning.txt`, `legacy_rule_audit.json`, `comparison.json`, `comparison.txt`, `source_diagnostics.json`, `fundamental_evidence.json`, `summary.json`, `artifact_privacy.json`.

Checks reject another date/commit/branch, damaged checksums, repeated source fingerprints or insufficient time separation. DST uses `Europe/Bratislava`. GitHub may delay starts; timestamps are actual. Keep the same source pin for both observations. No new repository is necessary. GitHub cannot automatically schedule a development branch; this proposal uses manual tests and leaves the existing production scheduler untouched.

If the web form does not expose the development inputs:

```sh
gh workflow run run.yml --repo janmarticek4-dot/crypto-bot --ref feature/v11-1-review -f task=integration-shadow -f phase=preview
```

For the real pair use `-f phase=morning`, then `-f phase=evening -f morning_run_id=<ID>`.

## Proposed deployment, only after approval

1. Review this branch and complete a genuine independent morning/evening pair. Confirm source coverage and native-rule results; do not infer strategy performance from a single day.
2. Before merge, rebase/review against the then-current main code; preserve the live bot_state/journal as generated on main. Never checkout historical state from this branch over production state. The source pin is immutable, but production state is not.
3. Merge only the reviewed additive implementation after explicit approval. This alone leaves the production workflow/entrypoint unchanged and feature disabled.
4. Review/apply `PRODUCTION_CANDIDATE.patch` separately. It changes only the existing pilot job source/test/entrypoint and adds state validation/fail-closed rebase to the existing legacy job. It does not add a scheduled sender, private environment, Secret or new bot. The existing 07/15/20 routing and monitoring remain.
5. After approval set repository **variable** `V111_INTEGRATION_ENABLED=true`; no Secrets change. Run a non-delivery shadow first, then observe the next scheduled slot. Never replay a slot already attempted or uncertain.
6. Check source errors, delivery health, state continuity and private/public separation. If essential data is missing, keep N/A and do not promote another strategy to fill the gap.

## Rollback

Preferred rollback restores the existing pilot source pin `929bd6389216be1b4eefcd1be61be89d944abf33`, its old test command and `scripts/v111_trial.py`, or first disables the integration variable. Preserve the current bot_state, private repo and delivery journal. The journal prevents re-sending an already attempted slot.

For a full V10.6 fallback the pre-existing `V111_TRIAL_ENABLED=false` switch restores legacy scheduled reports. Do this **outside** 07:00–08:30, 15:00–16:30 and 20:00–21:30 Bratislava, after checking Telegram: the legacy state and pilot journal are different dedup stores. Switching within an already sent slot can duplicate a report. Do not reset either ledger or copy the baseline bot_state over the current one. Corrupt private-state recovery, if ever necessary, remains a separately approved procedure.

## Remaining gates

No merge/deployment performed. No real two-time pair yet. Provider coverage is still incomplete (consensus/first release/ETF flows/unlocks and full project usage); no invented substitute. Algorithm parity does not equal provider parity or investment performance. Original monitor POST retry risk remains. Approval of the concrete patch and observing the first real scheduled delivery are still required.

## Frozen source pin

Candidate implementation: `718f7504ac641007cbb814361bd7aa48600d8d9c`. `PRODUCTION_CANDIDATE.patch` pins that exact implementation; later documentation-only commits need not change it. The patch is present for review only and was not applied to the production workflow.
