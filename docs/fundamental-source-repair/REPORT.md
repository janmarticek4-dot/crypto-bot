# Fundamental source repair — 28 October 2026

## Verified causes, not assumptions

Read-only GitHub-hosted audits: 40773603881 before and 40774035447 after.
The compact public verdicts are retained beside this report; full HTTP/parser
records and publication dates are in their Actions artifacts. No test Telegram,
private inventory, production state mutation, or exchange access was involved.

| Source | Observed problem | Repair / correct interpretation |
|---|---|---|
| ONDO official RSS and alternate URLs | HTTP 404 | Keep failure visible. Retain CoinDesk backup and add verified The Block/Decrypt project-filtered secondary backups; never label these official. No new story still means no new verified news. |
| SEC legacy RSS | Old publication outside 72h window | Keep official feed, try current secondary regulatory coverage when it has no current item. Alternative official RSS path was 404, so removed from production fallback list. A secondary story is not an official ruling. |
| BEA RSS and www mirror | Last observed publication 2026-10-06 | RSS was retrieved successfully, not a connectivity failure. Add the independently verified official BEA ICS calendar for PCE/GDP. Revised monthly FRED levels remain separate from news, consensus and original release vintages. |
| BLS | Feed retrieved; no currently relevant accepted item | Not an outage. Keep working official feed/calendar. Remove nonexistent current_year.ics fallback (404). |
| AAVE aggregate TVL | Response larger than old 8 MB safety cap | Allow at most 32 MB only for exact api.llama.fi/protocol/aave. Runner now parsed a current timestamped series. Other protocol responses remain 8 MB and feeds 2 MB. Numeric undated TVL fallback remains explicitly unknown-as-of. |
| FET Fetch blog candidate | HTML instead of RSS | Rejected, not accepted as a valid feed. Existing old software release is not fresh economic evidence. Add secondary project news backup. |
| SOL news candidate | HTTP 429 | Not activated as a stable source. Existing official release feed remains; secondary reporting supplements it without calling a code release proof of adoption. |
| TAO blog / EU Council candidates | HTTP 403 | Origin-or-gateway HTTP error; cannot prove bot protection is the cause. Not activated. |
| RENDER RSS candidate | HTTP 404 | Not activated. Existing repository change notices remain low-significance; project-filtered secondary reporting is available. |
| Decrypt / The Block | RSS parsed with current relevant items | Added as secondary news providers; retain dates, provenance, deduplication and explicit confirmation requirements. |

## Confirmed implementation defect

A successful fetch with an empty or old feed used to return immediately, preventing
fallback lookup. Selection now tries backups for those cases. If every backup
fails, the valid quiet primary stays available and its backup failures remain in
the attempt trail. A secondary source never inherits official trust. Shared URLs
are fetched once per collection, including shared failures, rather than once per
asset, reducing unnecessary traffic and rate-limit exposure.

No news freshness thresholds were relaxed to make stale stories look current.
A successful feed without new items does not prove no important event happened.

## Validation and activation

240 offline tests passed locally. GitHub 40774141314 (full live preview) and
40774141281 (analytical regression/source checks) succeeded for the selected
immutable source fb5daf326321ee38a994a4636708a76810801b95.

The inherited payload-budget test initially expected the old 8 MB cap. It was
updated to the explicitly revised Aave-only bound; additional tests verify that
responses above the new cap are rejected and unrelated hosts retain their smaller
caps. The earlier intermediate failing candidate was never activated.

Production activation changes only the existing fixed source pins in run.yml and
prediction-shadow.yml. Future main changes are not automatically deployed. No
trading rule, private portfolio, bot_state.json, delivery journal, Secrets,
notification cadence, or monitoring policy was modified. Roll back the activation
commit with normal git revert/push to restore the preceding d79926d source; never
reset state to an old snapshot.

## Actual coverage and remaining gaps

| Area | What is available | What remains incomplete |
|---|---|---|
| Fed / ECB / US macro | Official feeds, Fed result verification, FOMC/BLS/BEA calendars, revised FRED levels, daily Treasury yields | Verified consensus, all first-release vintages, complete speaker coverage, intraday event-aligned reaction of stocks/DXY/yields |
| Regulation / geopolitics | Current CFTC and crypto-news sources; dated secondary SEC reporting | Complete official SEC decision stream and broad primary geopolitical coverage |
| SOL | Official software notices, relevant secondary news, TVL and protocol-activity observations when available | Software release is not adoption; complete active-user/validator/incident coverage not established |
| AAVE | Governance notices plus current dated TVL, fees/revenue when provider observations pass validation | Governance is not execution; cashflow to token holders is not protocol revenue |
| ONDO | Secondary project news backup and available provider metrics | Official blog feed broken; not all economic observations have current valid periods |
| TAO / FET / RENDER | Official repository notices plus project-filtered secondary reporting | Comprehensive usage, emissions/unlocks and economically meaningful revenue measurements |
| ETF flows / exchange flows / liquidity | Relevant news can be surfaced | News is not a verified flow dataset. Comprehensive issuer/exchange flow observations and stablecoin/liquidity measures are not implemented here |

Counts of accessible endpoints are NOT a percentage of economically important
information covered. No claim of full coverage, independently verified article
facts, calibrated predictions, or automatic trading is made. Candidate endpoints
that failed remain diagnostic-only; adding broken URLs would not improve coverage.
