# V11 morning/evening analytical reports — review only

Branch: `feature/v11-analysis-events`, based on research/v11-phase3.
No push, merge, deployment, brokerage connection or strategy promotion.

## Implemented

- Distinct morning plan and evening comparison, same-day Bratislava baseline,
  price/market-cap/volume changes and explicit unexecuted-trade distinction.
- Main six assets separate from supplemental watchlist; actual ledger ownership.
- BTC and per-asset conditional 24–72-hour and 7–14-day paths using closed
  support/resistance and ATR. These are technical scenarios, not calibrated
  statistical forecasts or probabilities. Missing valid boundaries => N/A.
- Forecast registry, immutable slot identities, evaluation only after 72h/14d,
  exact past closed hourly candle, negative outcomes retained. Missing historic
  due-time prices stay pending; never substitute a delayed current quote.
  1h retrieval increased to 1000 bars to cover 14 days.
- Fresh global capitalization, volume and BTC dominance; stale metadata excluded.
- Project-source notices per asset and explicit coverage gaps; TVL observations
  for Aave protocol and Solana chain via DeFiLlama (not token revenue or flows).
- BLS timed calendar, FOMC official meeting date parser without invented decision
  time, ECB/CFTC source adapters, upcoming nonduplicated 24h/7d/14d sections.
- Events retain expectations/results as N/A absent evidence. Due events are
  rechecked in reports; separate timestamped post-event price observations do
  not claim exact event returns or causality. Source refresh is 15 minutes.
- Removal of fictitious re-entry reference to an unexecuted sale recommendation.
- Existing US-calendar/index/futures hotfix integrated into V11 entrypoints;
  short report retains N/A, dates, divergence and execution-delay diagnostics.
- Main-slot cron candidates added for CET/CEST; monitor still every 15 minutes,
  offset from the hour. GitHub Actions has no exact-time guarantee.
- Research-only manually dispatched Freqtrade workflow, no production state or
  Telegram secrets. Portable script, reports before lookahead failures, data
  hashes, dependency versions and result archives captured. No trading command.

## Trade-policy boundaries

`v11/strategy.py` is unchanged. Production V10.6 decision functions are unchanged.
No experimental strategy is promoted. V11 protective suggestions are explicitly
labelled experimental as well; they are not presented as production approval.
The existing V11 code can calculate REDUCE/SELL without its BUY validation flag;
this change does not silently rewrite that policy. New BUY remains blocked by
its existing default validation gate. Action summaries disclose that this layer
supplies no newly confirmed production BUY.

Monitoring and manual fill commands remain unchanged. Planned calendar events
never feed strategy decisions or generate extraordinary monitoring alerts.
Private state continues through the encrypted private-repository backend; no
real portfolio is copied to public docs or workflow artifacts.

## Source availability / remaining limitations

CoinGecko and Binance answered HTTP 200 in the audit. Fed/BLS/BEA/ECB/CFTC/SEC,
DeFiLlama, FRED/CME and Solana RPC were not reachable from this environment.
Live source payload compatibility and GitHub-runner access need shadow checking;
fixture tests are not evidence of live availability.

This is not complete fundamental data coverage. Network activity, protocol
revenues, emissions/unlocks and project economic impact remain N/A unless
provided by an implemented verified source. Release notices and governance
proposals never imply deployment, partnership adoption or positive token value.
FOMC date-only entries explicitly show time N/A. Comprehensive ECB/DOL/Census/
ISM calendars, consensus/FedWatch, DXY/yields, ETF flows, liquidations and
geopolitical feeds are not yet implemented. No invented schedule fills gaps.
Published numeric macro results and consensus are not automatically extracted;
event ledger keeps these N/A while displaying follow-up observation status.

No new full Freqtrade backtest was run for this reporting change. Existing
backtest outcomes do not validate production policy. Re-downloading data may
change results; recorded checksums detect differences but do not create a fixed
historical dataset. Failed or too-small lookahead analysis is not a pass.

## Validation and rollout

Run unit suites offline with mocked network/Telegram; run research tests in the
Freqtrade virtual environment. Review generated synthetic morning/evening and
USA examples in EXAMPLES.md. No messages sent to the user's Telegram.

Before deployment: verify source access and parser compatibility on an isolated
runner; shadow-run reports without production sends or state; review report
length and N/A coverage; verify timezone boundary days and delivery timing.
User approval is required before any push/merge/deployment. Any trade policy
change requires separate independent validation and approval.

## Verification completed

108 bot unit tests passed, including 35 US-context tests and 13 report/event
regressions. 22 phase-3 research tests passed. Workflow YAML parsing and shell
syntax validation passed; git diff whitespace check passed. AST comparison of
legacy main.py shows changes only in timezone normalization and the US outlook
entrypoint. v11/strategy.py is unchanged. No live Telegram send or new full
backtest was performed.

## Source/cost register

| Source | Implemented use | Cost/access boundary |
|---|---|---|
| Binance public data | Closed candles and tickers | Public rate limits; no trading credentials |
| CoinGecko | Coin metadata and global market | Public/demo limits; paid tiers optional |
| Fed | Official notices and meeting dates | Public pages; exact future decision time N/A if absent |
| BLS | Notices and ICS calendar | Public, availability must be checked |
| BEA | Publication notices | Public; full future schedule not yet parsed |
| ECB / CFTC / SEC | Publication feeds | Public candidate endpoints, live compatibility unverified |
| Official project feeds | GitHub releases, governance, project blog | Public; notice is not economic outcome |
| DeFiLlama | Aave protocol / Solana chain TVL | Public candidate endpoints; coverage and terms must be checked |
| Yahoo Finance | Index and futures context | Endpoint accessibility/licensing/latency not guaranteed |
| CME FedWatch / licensed macro consensus | Not connected | N/A; public website is not permission for a stable free API |
| DOL / Census / ISM / Treasury / FRED | Not connected | Public or licensed depending dataset; no invented values |
| Unlock / ETF / liquidation aggregators | Not connected | Coverage, permission and paid-plan requirements unresolved |

No exact current commercial price is claimed. All unavailable fields are N/A,
not estimated consensus or invented events.
