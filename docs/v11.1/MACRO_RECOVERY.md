# Macro source recovery — 2026-10-22

Baseline: user-supplied artifacts from GitHub run 39781109806, commit f6c40dd,
14:46 Europe/Bratislava. Preserved in macro-run-39781109806/.
6/9 endpoints succeeded. BEA returned 406; SEC 404; Treasury timed out at 12s.
These are endpoint-specific failures, unlike local proxy CONNECT403.

Changes (research branch only):
- Keep original failing endpoints as explicit evidence; additionally probe official
  www.bea.gov RSS and SEC legacy RSS candidates. Candidates are NOT verified fixes.
- BEA candidate is available as a V11 source fallback; provenance remains explicit.
- Reject HTML/error XML in the fundamental feed parser, rather than calling an empty
  parse successful. No effect on trade rules or real positions.
- Diagnostics retry a timeout/selected HTTP5xx only once, with 25s timeout.
  No retry of 4xx/proxy blocks, no bypass of TLS or fair-access policies.
  Attempt history remains in results.json; no automatic quota-intensive retries.
- Manual diagnostics additionally create CALENDAR.md and calendar-results.json.
  Fed/BLS events are parsed into nested 24h/7d/14d windows; timestamps are converted
  to Bratislava. Date-only events are explicitly candidates, not exact-time events.
  Consensus, actual result and confirmed direction remain null/N/A.
  Coverage excludes BEA/ECB calendars and unscheduled risks; no entries does not mean
  no events. Meeting dates do not establish a Fed decision hour.

Validation: 187 offline tests passed, including retry limits, preserved failures,
HTTP404/406/429/proxy no-retry, HTML challenge rejection and US/EU DST mismatch.
Local live probes: all 11 endpoints blocked at proxy CONNECT403; cannot establish
GitHub reachability for candidates. Re-run registered run.yml manually with branch
feature/v11-1-review. Download macro-sources-diagnostics-<run>-<attempt> artifact.

No production main.py/state/portfolio/Telegram/signal rule changes. No trading.
The true 07:00→20:00 shadow pair still requires future separate observations;
this source diagnostic is not a completed morning/evening shadow test.
