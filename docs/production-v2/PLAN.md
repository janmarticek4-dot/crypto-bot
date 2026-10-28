# Approved production display integration — 28 October 2026

The user explicitly approved experimental V2 forecasts in the primary report,
without any change to trading decisions. A backup branch points to a77a242.
Candidate code must pass offline tests and V2 Production Readiness before the
production workflow pin changes. The pin stays immutable, never tracks main.

- Prediction packages are fitted/selected by the isolated research workflow.
- Production performs bounded inference only, never backtests or fitting.
- Package failure/expiry/store failure does not block the primary analysis.
- Public forecast records are generated before private holdings are loaded and
  written only to public-analytics/prediction-shadow.json via optimistic CAS.
- Calendar entries are not official results. Fed result uses the official dated
  statement, publication timezone, rate range and voting paragraphs. Unknown
  results/consensus stay N/A; superseded previews are excluded from the report.
- All report/US/alert URLs are removed at presentation/transport boundaries;
  evidence, source URLs and timestamps remain in diagnostics.
- Same native BUY/SELL/HOLD rules, same private loader and same delivery journal
  attempting/uncertain protection. Multipart delivery has one attempt per part
  and a 1.1-second pacing delay, not a retry.
- Daily research/paper execution will be enabled by the reviewed workflow change,
  without editing repository Secrets or Variables.

228 offline tests passed before candidate publication. Full live-data public
morning/evening previews produced two Telegram-safe parts without sending them.
Local Fed verification is blocked by the execution proxy; the GitHub-hosted
readiness job must independently fetch the official result before activation.
