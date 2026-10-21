## Problem and behavior

Morning/evening V11 reports lacked reliable incomplete-data persistence,
forecast provenance and safe delivery retries. This draft extends the existing
V11 work with same-day morning/evening comparisons, independent per-asset
conditional scenarios, source-labelled fundamentals/calendar gaps, Treasury
observations, private delivery-attempt checkpoints and explicit preview guards.
Telegram reports are numbered Unicode-safe parts; ambiguous delivery requires
operator review rather than replaying possibly delivered messages.

V11 trade decisions, manual fill logic and actual tracked state are unchanged.
No strategy is promoted, no automatic trading added and nothing is deployed.
This branch includes previously unmerged V11 phase-2/phase-3 research and the
USA-calendar/report hotfix, so review runtime/workflow migration separately.

## Validation

126 offline bot tests, 22 phase-3 tests and 11 phase-2 tests passed. 33 real
single-asset Freqtrade runs completed; 3 ONDO-2024 targets are NO_DATA. All
asset-period strategies are insufficiently evidenced; combined has zero trades.
See docs/v11.1/SINGLE_COIN.md, VALIDATION.md and BACKTEST_MANIFEST.json.

## Review limits

Full project economics and macro consensus/release-result extraction remain
incomplete and show N/A. Official calendar date-only entries do not invent
hours. Source live-access checks on an isolated GitHub runner and shadow report
review are required before any deployment. Approval of this PR does not
approve an experimental trading strategy. Synthetic previews never load a real
portfolio or send to production Telegram.
