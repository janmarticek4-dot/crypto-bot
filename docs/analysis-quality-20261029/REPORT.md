# Main analysis quality repair — 29 October 2026

## Proven production failure

Read-only audit 40880365441 inspected the original morning run 40827329123.
The actual analytical checkout was 59c5a774fc27c51a7ec374df09593697c225c624.
This was not an unactivated source pin or missing candles: all BTC and six asset
series had 299 valid aligned 4h bars and successful preparation.

The observation clock was 2026-10-29T06:08:43.651541Z; the snapshot clock was
1793254123.6515152 seconds. Converting only the first to integer milliseconds
produced a difference of -0.51513671875 ms. The old guard raised ValueError
("Snapshot stale/future"), discarding the entire forecast set. Diagnostics used
to retain only the exception class, hiding the cause.

Both timestamps now use integer millisecond precision. True future timestamps,
15-minute stale snapshots, stale/forward model packages, gaps, unaligned BTC data,
missing states and nonfinite features still fail closed. Rejection reasons are
attributed per coin where possible; missing outputs never become invented bands.
The report origin is refreshed after fundamental collection. Model selection,
coefficients, horizon logic and trading rules were not changed.

The old dry run missed this defect because it created its clock after file I/O,
whereas production captured datetime immediately after data collection. Tests now
reproduce the exact production timestamps. A read-only replay uses the archived
production snapshot and the original pre-event package, never a future fitted
package; it does not write to the prospective paper journal and is not independent
performance validation.

## Report behavior

- Investment verdict first: market state, action for new purchases, action for
  safely loaded existing positions, technical 24–72h / 7–14d baseline, reasons
  and invalidation conditions. Missing private inventory does not imply HOLD.
- Personal action lines are copied from the unchanged approved renderer. A
  technical SELL diagnostic is not promoted into a personal instruction.
- Falling capitalization, rising rolling 24h volume and altcoin relative weakness
  are interpreted as indications of selling pressure, not measured net flow or
  guaranteed further losses. Missing volume cannot confirm selling pressure.
- V2 has compact, individually calculated ranges and remains experimental. A
  missing forecast is separately labeled as a fallback technical scenario only
  when current technical inputs support it; no invented probabilities or bands.
- Short Slovak Fed summary, actual rates/vote when verified, conditional impact
  and observed BTC reaction. Original English statement and URLs remain only in
  diagnostics. Missing pre-event consensus stays N/A, never reconstructed from
  a forecast first observed after release. Past events are not upcoming events.
- Repeated indicator dumps and low-materiality metric details stay in artifacts;
  support/resistance, informational entry invalidation and action reasons remain.

## Actual delivery verification

Production Prediction Diagnostics now also runs read-only after the existing
Crypto AI Bot V11.2 workflow completes. Monitoring-only and USA runs without a
full analytical artifact are skipped by a lightweight selector. Full reports are
checked using artifact diagnostics, actual checkout logs and a minimal canonical
sent receipt. The receipt adds only public run/source/format booleans and V2 count,
never personal text, positions, amounts or prices paid.

The sender and CAS-before-send owner remain the same. attempting/uncertain states
still prevent automatic resends; metadata is persisted by the existing result
write, without adding another Telegram sender. Verification cannot cause a second
message or a trade. An audit failure is an operational diagnosis, not a market
safety alert.

271 existing plus 14 targeted regressions passed locally (285 total), including
unaltered native file identity, causality, slots, manual deduplication, private
boundaries, missing inputs, the exact clock defect, Slovak Fed and report fallback.
Candidate must pass GitHub replay/live preview before its fixed pin is activated.
No test Telegram or real-state mutation is authorized by this verification.

## Timing limits

A read-only active-source check can prove deployment now. A future 20:00 or 07:00
Telegram delivery cannot honestly be declared verified before it happens. The
post-delivery job records that actual result automatically, requiring no manual
rerun or private-data upload. GitHub can delay scheduled starts.

Rollback: revert only the activation workflow-pin commit with normal git revert
and push, returning to the preceding 59c5a77 source. Do not reset main or overwrite
bot_state.json, delivery journal, public paper journal, private state or Secrets.

## Final verification / activation

Candidate immutable source: 92365801208bf4b1aa39aa3a1c1947193c79cad0.
285 offline tests passed locally and in GitHub Analytical Release Review
40885112617. Live readiness 40885112787 produced all 18 forecasts, verdict-first
morning/evening reports, no URLs and two logical Telegram parts each, with no
delivery. Original morning replay 40885112804 produced 18 outputs from the same
archived input and original package after the clock fix; never saved as paper
observations or claimed independent validation.

The existing run.yml and daily research pins are switched to that tested source.
Production Prediction Diagnostics is enabled read-only after actual full reports,
using the same expected source. No user Secrets/Variables need changing.
A source-validation push run proves the active checkout without a Telegram test.
The next scheduled full delivery remains pending until its actual execution; the
automatic post-delivery audit will prove or reject its contract then.
