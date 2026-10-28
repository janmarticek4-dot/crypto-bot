# Approved V2 production display — 28 October 2026

## Scope and immutable source

The user explicitly approved experimental prediction display in the existing
production report, without changing trading decisions. The runtime is pinned to
`d79926d3685d2664c26256442a6a47238d08a16d`, never to a moving branch. Both existing
V111_INTEGRATION_ENABLED and V112_ANALYTICS_ENABLED flags must remain true.
No Secrets or Variables were changed. The old V112_APPROVED_SOURCE variable is
retained unchanged for rollback, but this explicitly approved workflow release
selects the new immutable source directly.

The original main.py is byte-identical to its audited baseline. A presentation
wrapper removes URLs from native alerts/reports before the existing sender is
called. The approved analytical sender retains canonical slot/manual-run IDs,
attempting/uncertain handling and no automatic delivery retries. Multipart reports
use existing logical splitting with one attempt per part and pacing. No orders or
exchange credentials exist in this integration.

## Validation

- 233 offline tests passed locally, including native-file identity, causal
  research checks, timezones/holidays, missing data, private export boundaries,
  unchanged recommendations, URL removal, failed-model fallback and public-state
  compare-and-swap handling.
- Live public morning/evening previews: six coins, three horizons each, two
  Telegram-safe parts, no delivery, no private inventory loaded. These are two
  presentation variants of ONE snapshot, not independent morning/evening data.
- Missing/zero aggregate volume is now N/A, never a fictitious -100% change.
- GitHub readiness 40765227415 and 40766094413 succeeded. The latter verified the
  official Fed statement, publication 18:00 UTC / 19:00 Bratislava, target range
  3.75–4.00%, 10–2 vote and actual statement commentary. Consensus remains N/A.
- `official-fed-verification.json` preserves public verification/provenance.
  Market reaction there uses the first readiness run's hourly close window;
  statement text/voting use the second. Neither proves causation.
- Local Fed retrieval is blocked by this environment's network proxy. GitHub
  runner retrieval succeeded; it is not described as a local successful fetch.
- Production V2 performs frozen-package inference only. Package failure/expiry
  degrades to N/A and preserves the primary report. Independent predictive
  superiority and calibrated probabilities have NOT been established.

## Schedules and data

The existing production workflow remains `run.yml` (display name Crypto AI Bot
V11.2). Europe/Bratislava slot selection, 07:00 / 15:00 / 20:00 reports, manual
analysis and the quiet 15-minute monitor remain intact. GitHub may delay runs.
To request an intentional manual report after release: Actions → Crypto AI Bot
V11.2 → Run workflow → main → only “Ručná analýza V11.2”. No test delivery was
requested during deployment.

Daily Prediction Research Shadow is enabled at 10:25 UTC. It uses the same fixed
code source, reads the latest public paper journal separately, then computes and
CAS-publishes its result. Manual paper persistence remains opt-in. No private
state is loaded; no Telegram credentials are passed. Concurrent journal writes
are refused rather than silently overwriting. Reports append public forecasts;
no real positions are recorded in that public journal.

Future scheduled deliveries and future daily paper maturation can only be
confirmed after they actually run. The push-only source-validation job verifies
actual production environment flags and the analytical checkout without sending.

## Rollback

Backup branch: `backup/production-before-v2-integration-20261028-a77a242`.
Do NOT reset main to that branch: current state/journals must be preserved.

Revert only the activation commit using a normal git revert and normal push.
This restores the previous analytical source pin
`feab545852a159c5f61d9b18af16279aebcd77d9`, previous daily-paper activation gate and
native command. Keep bot_state.json, delivery journal, public paper records,
private repository, Secrets and Variables unchanged. The candidate code may stay
on main because the runtime is explicitly pinned. No force-push is required.
