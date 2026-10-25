# V11.1 isolated shadow validation

Branch: feature/v11-1-review only. Production main, state, portfolio, signals and
Telegram are untouched. No trading API or delivery API. Groq disabled in the
registered entrypoint, deterministic calculations remain independent of AI.

## How to run without changing default branch

Open https://github.com/janmarticek4-dot/crypto-bot/actions/workflows/run.yml
(the list can still show the default-main production name). Run workflow, choose
feature/v11-1-review and task=shadow. The development workflow calls the local
reusable shadow workflow at the same commit, never the production main job.

- phase=preview: immediately create live market report templates. The two templates
  share one snapshot; they are NOT an actual morning/evening comparison.
- phase=morning: run at 07:00 Europe/Bratislava; accepted observation window
  07:00–08:30. Creates a public immutable checkpoint and dedicated morning artifact.
- phase=evening: run at 20:00 the SAME Bratislava day; accepted window20:00–21:30.
  Leave morning_run_id empty to discover a successful morning artifact on the
  SAME branch/commit; or provide the morning run ID explicitly.

Do not push another commit between morning and evening. A changed SHA is refused.
Evening checks SHA, branch, workflow provenance, success, checksum, observation
windows, same day, 8–16h gap, market freshness and changed source fingerprint.
Missing/invalid reference or reused data fails closed, not a fabricated comparison.
No actual positions are loaded; holdings cannot be validated by this shadow test.

Download v11-1-shadow-<run>-<attempt>: summary.json, morning.txt OR evening.txt,
market_snapshot.json, fundamentals.json, calendar.txt, source_availability.json,
calendar_coverage.json, entry_diagnostics.json, risk_evidence.json, outage_checks.json.
Evening also produces comparison.json/txt and morning_reference.txt. Morning also
has v111-morning-<run>-<attempt> for automatic discovery. Artifact retention7 days
is sufficient for this public same-day test, NOT permanent portfolio storage.

## Schedule limitation

No automatic morning/evening run has been scheduled. GitHub schedule and
workflow_run triggers require the workflow on the default branch. This task
forbids modifying main. GitHub API dispatch from this environment is Forbidden.
Therefore two manual runs at the above times are currently necessary; no claim
of unattended scheduling or completed temporal validation is made.
Next local slots after the preview below: 2026-10-26 07:00 and20:00 Bratislava
(06:00UTC and19:00UTC). Actions can start late; actual collected times are recorded.

## Actual local preview 2026-10-25

Collection20:43:19UTC /21:43:19 Bratislava. All six live altcoins had usable current
market data and technical frames. 8/16 fundamental sources fetched successfully;
Fed/BLS/BEA/ECB/CFTC/SEC blocked by local CONNECT proxy403, not application HTTP403.
Public GitHub artifacts previously confirmed Fed/BLS/ECB/SEC/CFTC accessibility
from GitHub-hosted runners; this local preview does not replace that observation.
Treasury remained N/A. Groq unused; outage injection passed; protected hashes
unchanged; no portfolio/state loaded or written, Telegram and orders disabled.
Saved actual reports are in observations-20261025/. Both are explicitly labeled
same-snapshot PREVIEW and must not be scored as independent predictions.
193 offline tests passed including BLS→report integration and workflow safety.

## CI failure 40233027569 and fix

The offline test subprocess inherited BOT_DATA_MODE=shadow from the job.
This correctly triggered require_live_snapshot/production-entrypoint protections
in tests designed to invoke those entrypoints with mocked data and mocked I/O.
Reproduced locally under the same environment: 193 tests, 11 errors.
The harness now explicitly sets BOT_DATA_MODE=live for that subprocess only,
keeps BOT_DISABLE_TELEGRAM=1, clears Telegram/Groq credentials and blocks every
unmocked socket connection. Tests for synthetic/shadow rejection continue to set
those modes explicitly. No production snapshot guard was changed or disabled.
The next independent Actions step still inherits BOT_DATA_MODE=shadow from the
job and the live shadow runner explicitly sets it again.
Regression: 194 tests passed under inherited BOT_DATA_MODE=shadow.
The failed run created no live reports, so it is not evidence of data-provider
failure or a completed shadow test. Start a NEW workflow run on the latest branch
commit; re-running old jobs reuses the old failing commit.

## Second CI failure 40233303240

Public annotations identify Offline regression as the failed step; authenticated
full logs were not accessible here. Inspection found the added integration test
imported PyYAML, absent from declared requirements but installed locally.
Reproduced with inherited shadow mode and yaml import deliberately unavailable:
193 tests, one discovery error (ModuleNotFoundError: yaml). After removing this
unnecessary test-only dependency, the SAME constrained run passes194 tests.
This is a confirmed reproducible defect; exact runner traceback still requires
its full log. No production dependencies or production code changed.
The workflow now captures offline-tests.log under shadow-output before running
any tests, publishes it even on failure, and preserves the actual test exit code.
Future runs therefore provide failure evidence even if no live snapshot exists.
