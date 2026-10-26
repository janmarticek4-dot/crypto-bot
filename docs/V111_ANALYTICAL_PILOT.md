# Approved V11.1 analytical pilot

Enabled by user instruction on2026-10-26. Source pinned to90464629be7b1e61a263de23d52455029dcba1f9.
Only scheduled07:00/20:00 Bratislava reports are replaced.15:00 USA outlook,
manual V10.6 analyses, existing safety monitoring and trading rules stay unchanged.
GitHub Actions15-minute scheduling is best effort; actual collection time is displayed.
Pilot is accepted07:00–08:30 and20:00–21:30. Actual delivery is not yet verified.

No real holdings, account balances, fill ledger, private-state secrets, Groq or
experimental strategy activation. Every new-entry status is WAIT, not a production
BUY. Holdings/protective sells and actionable entry/stop/TP/R:R are N/A.
The report contains public technical/fundamental scenarios, explicitly uncertain.

Public journal trial-public/v111-delivery.json stores only public quotes and
slot delivery states, never private portfolio or chat/token values. CAS checkpoint
before Telegram prevents replay; uncertain/partial sends need operator review,
not automatic retry. The journal contains morning source observations for the
evening same-day comparison; it does not prove forecast performance.

## Rollback
Set repository Actions variable V111_TRIAL_ENABLED to literal false. This skips
the pilot and restores scheduled V10.6 full reports on subsequent runs. Do not
replay a sent/uncertain slot without checking Telegram. Switching within a slot
may produce a legacy analysis too. Preserve journal and bot_state.json.
Alternatively revert only the pilot deployment commit; do not merge/revert the
whole research branch. No production portfolio migration is involved.

## Validation
235 offline tests passed on pinned source, including DST, duplicate-attempt
refusal, CAS-before-send and independent morning reference changes. Production
routing is tested separately using mocked calls. No Telegram smoke message was
sent during preparation; actual07/20 delivery remains to be observed.
