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

## USA/fundamentals rollout2026-10-26

New immutable source:0209de98779a9d3e10a177dc70c66cc38ddab371.
USA15:00 switches to the integrated session/index/futures report from2026-10-27
Bratislava, preventing a duplicate after today's legacy15:00 delivery.
07/20 use the upgraded fundamentals/yield adapters from the next run.

Actual GitHub-hosted validation40336881117 succeeded on2026-10-26:
US_QUOTES_AVAILABLE=4/4; YIELDS_AVAILABLE=True; FUND_FEEDS_AVAILABLE=16/16;
PHASE=AFTER OPEN. This is live runner evidence, not a local fixture result.
No Telegram or production state ran in the push-triggered validation job.
Artifact us-source-validation-40336881117 contains the public diagnostic report.
Feed reachability is not complete coverage or proof of an economic effect.

Cash indices vs futures, NY calendar/DST, quote timestamps, stale-data refusal,
crypto divergence and primary-source macro dates are integrated. Monthly Treasury
and FRED fallback give daily observations, not live quotes or DXY. Ongoing gaps:
verified consensus/FedWatch, ETF flows, comprehensive unlock/emissions/adoption/
revenues, and ONDO primary news remain N/A where not evidenced. No fabricated
substitution. Existing15-minute risk monitoring and actual trading rules unchanged.

242 offline tests +5 production routing/cutover tests passed. Rollback variable
V111_TRIAL_ENABLED=false restores legacy07/15/20 on subsequent runs. Before
replaying any slot, inspect Telegram and public delivery journal.

## Manual advisory completion2026-10-26

Pinned code929bd6389216be1b4eefcd1be61be89d944abf33.252 offline tests passed.
Public scenario journal now evaluates only confirmed-delivered scenarios after
72h/14d using historical closed bars. Counts include failed ranges; generated
scenarios are not trades or calibrated probabilities. Confirmed pending long
horizons are retained. Unscored records are counted explicitly, not successes.
Latest revised FRED CPI/PCE/UNRATE/PAYEMS levels include observation periods and
source; they are NOT release timestamps, consensus or first-release vintages.
GitHub-only delivery health checks report missing/uncertain slots without Telegram
noise or automatic replay. Real forward performance still requires future data.

Optional private advisory uses NEW production-advisory Environment. Until its
PROD_STATE_REPOSITORY/PROD_STATE_TOKEN/PROD_STATE_ENCRYPTION_KEY are configured,
no real inventory is loaded. New PRIVATE repo crypto-bot-state-production and
marker are required; the synthetic integration repo is refused.
User inventory import is a separate explicit manual advisory_import workflow
input reading INITIAL_ADVISORY_PORTFOLIO Secret. It refuses existing state, has
no public artifact and never invents cash/transactions. Existing bot_state.json
is not migrated, modified by the import or deleted. No actual import executed.

Owner-only Telegram POZICIA/UZAVRETA/POZICIE commands record statements about
already executed manual activity/current inventory, never execute orders. Updates
are encrypted and checkpointed with offset before acknowledgement; old messages
before import are ignored. No routine updates reply. Private inventory and advice
never enter the public journal/source diagnostics. Private advice is appended
only to Telegram after public checkpoint; storage failure gives N/A, not no holdings.
Setup: see reviewed source docs/v11.1/completion/PRIVATE_ADVISORY_SETUP.md.

No AdaptiveHold/research strategy activation. Existing market monitor unchanged.
Data coverage still incomplete for unlocks, comprehensive adoption/revenue,
consensus and ETF/DXY. Code completion is not evidence of investment advantage.
