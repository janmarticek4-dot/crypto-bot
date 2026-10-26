# USA and fundamentals integration — 2026-10-26

User authorized completion and deployment of the analytical source integration.
No trading rules, private ledger or actual fills change.

- Existing XNYS holiday/early-close/DST logic is now wired to the production pilot
  for15:00, with PREOPEN/OPENING/AFTER OPEN/CLOSED based on actual NY session.
- Nasdaq Composite/S&P500 cash indices are separate from NQ/ES futures. Yahoo
  chart IDs, instrument type, currency and quote timestamp must match. PREOPEN
  cash values are explicitly previous-session closes, not today's futures.
- query1 then query2 endpoint fallback; same publisher, NOT two independent sources.
  Public read-only adapter blocks brokerage/Telegram/non-HTTPS/redirect requests.
- The separate US BLS parser now handles official US-Eastern and quoted TZID.
  Macro HTML errors cannot become successful empty feeds.
- Monthly Treasury XML and St Louis Fed FRED DGS2/DGS10 CSV fallback. Both yields
  must exist on the SAME observation date, finite/plausible and at most5 days old.
  A daily observation is never called a live yield or DXY quote. FRED CSV endpoint
  confirmed from upstream pandas-datareader fred.py; runtime availability still
  requires runner evidence.
- Public fundamentals remain attributed; GDP category added, candidate ONDO TVL
  request is N/A if unavailable. Circulating supply is not a confirmed unlock.
  No fabricated adoption/revenue/consensus, no automatic trading recommendation.
- Data coverage still incomplete: primary ONDO news, token unlocks, precise Fed
  decision times, DXY, verified consensus/ETF flows and comprehensive project
  metrics are NOT declared complete just because feeds load.
- scripts/check_us_live_sources.py performs real GET diagnostics without Telegram,
  private credentials or production state. Exports public report and safe annotation.
- USA rollout starts2026-10-27 to avoid duplicating a legacy15:00 report on the
  deployment day.07/20 use upgraded source code; existing monitoring unchanged.
-242 offline tests passed including US/EU DST, holidays, quote fallback, invalid
  instrument data, BLS alias, finite/current FRED observations and N/A outages.
- Local actual probe: US quotes0/4, yields unavailable, feeds8/16 because network
  proxy blocks these hosts. This is NOT evidence of GitHub-hosted availability.
