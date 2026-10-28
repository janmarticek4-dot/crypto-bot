# Extended fundamentals — 28 October 2026

## What changed

The existing analytical bot now has a deterministic public-data extension. It does
not change trading rules, predictive model weights, broker costs, holdings,
monitoring, Telegram deduplication, or slot schedules. It uses no paid API keys.
No test Telegram was sent. Secrets and private state were not read by tests.

- BTC/ETH US spot ETF net flows: Farside public tables. Validate asset identity,
  USD-million units, ticker/header width, numeric syntax, constituent sum, date,
  freshness and completeness. Dashes are missing, never zero. Report the latest
  complete provider row, preserving its actual date and previous complete row.
  A current partially populated row does not replace it. This is an attributed
  aggregator observation, not an independent audit or a cause of market movement.
- Economic forecasts: public Forex Factory/Fair Economy current-week JSON.
  Capture only future USD events with explicit timezone and numeric forecasts.
  Keep previous value, retrieval timestamp and provider attribution. Match known
  official schedules; suppress conflicting times. Unmatched dates remain explicitly
  third-party schedules. No post-event hindsight, actual releases, historical
  consensus, market probabilities or CME FedWatch data are inferred from this feed.
- Token unlocks: asset-specific next-date FAQ statements on public Tokenomist
  pages for ONDO/FET. Store date only, unknown quantity/timezone as null, provider
  status unconfirmed by project/on-chain data. Dates enter the main risk calendar
  only within 14 days. This is not a complete vesting calendar or an instruction
  to sell. AAVE's undated 'fully unlocked' statement is not accepted as proof that
  there is no future issuance. No gated endpoint/paywall was bypassed.
- SOL: daily closed-period DEX USD volume, USD-valued stablecoin supply stock,
  finalized RPC circulating supply, reported native annualized inflation.
- TAO: dTAO subnet AMM TAO-reserve liquidity, explicitly not all staking, total
  project TVL, active users, revenue, or evidence of net cash inflow.
- RENDER: provider-estimated BME job spend from burns, retaining its methodology.
  The provider describes a modeled off-chain fee component; not audited company
  revenue or token-holder cashflow.
- FET: Fetchhub native inflation parameter, not global FET/ASI net issuance or a
  dated token unlock.
- Supply metadata: preserve fresh total/max supply alongside existing circulating
  supply. Report circulation/total only with valid same-source fresh metadata;
  the remaining percentage is not labeled locked or scheduled for sale.
- Existing AAVE fee/revenue/TVL and available ONDO news/market metadata remain.

All new source URLs and timestamps stay in public diagnostics. Main Telegram
presentation remains URL-free. Quiet sources and inaccessible sources are
separate. Failed extensions degrade to N/A; the primary analysis still works.
Safe read-only Solana RPC methods are explicitly allowlisted; sendTransaction
and any RPC endpoint other than the configured public Solana node are refused.

## Actual runner observations

Public endpoint discovery: Actions 40779916323, 40780260506, 40780979100.
Full integrated preview: 40782154638. It verified:

- Latest complete BTC ETF row: 27 October, +176.0 million USD; previous +110.3m.
- Latest complete ETH ETF row: 27 October, -60.2 million USD; previous -88.6m.
- 28 October rows were incomplete and were NOT reported as final zero/inflows.
- GDP / Core PCE forecasts for 29 October 13:30 Bratislava matched the official
  schedule. Provider forecasts were 3.2% and 0.3%, respectively; these are calendar
  forecasts, not independently verified survey medians or actual results.
- Public next-date FAQ statements: FET 28 November 2026, ONDO 18 January 2027.
  Amounts and exact time were unavailable; both outside the 14-day report window.
- Seven scoped extra metric observations were parsed. Full public values, dates
  and units are in verified-live-sample.json. Supply/rate RPC queries have a known
  collection time, not an invented historical measurement/publication time.

The sample is one real collection, not a fabricated morning/evening comparison.

## Tests, immutable deployment and rollback

271 offline tests passed locally, including malformed/partial ETF tables, bad
units, reconciliation, stale/future dates, pre-event forecasts, DST, official
calendar conflicts, asset-specific unlock identity, unknown event time/amount,
stale metrics, supply reconciliation, safe RPC methods, full outages, private
export boundaries and unchanged action lines with synthetic private inventory.
Final immutable candidate: 59c5a774fc27c51a7ec374df09593697c225c624.
Final candidate GitHub live preview 40782668161 and regression/source checks 40782668184 both succeeded.
Backup ref: backup/before-extended-fundamentals-20261028-59c5a77.
Activation uses the existing run.yml and daily paper workflow with that fixed source; future main commits do not auto-deploy.
Reverting only the activation commit restores the prior fixed source
fb5daf326321ee38a994a4636708a76810801b95. Never reset production state.

## Honest remaining limits

The DefiLlama emissions API returned HTTP 402 for all six candidate unlock
endpoints. No paid account or API key was created. Public FAQ dates are a limited
substitute; complete schedules/amounts and primary-project confirmations remain
unavailable. Native-chain inflation is a different observation, not a substitute
for missing cliff events. No fabricated dates are filled in for SOL/TAO/RENDER.

CME FedWatch probabilities, consensus survey methodology and independent
historical forecast vintages remain unavailable. The current-week calendar does
not guarantee complete 7/14-day forecast coverage. Actual releases continue to
come from official sources. Missing past expectations stay N/A.

Ondo Yield Assets / Global Markets provider TVL arrays were empty; they were not
converted to zero or passed off as current economic activity. Complete project
user counts and audited revenue for all six assets are not established. Access to
more endpoints is not a measure of complete information or predictive advantage.
