# V11.1 Shadow Test

Manual-only workflow: `.github/workflows/v11-1-shadow-test.yml`. Intended branch: **feature/v11-1-review**, job guard refuses any other branch. Production `main`, existing workflows, analytical decision rules and tracked positions are unchanged.

## What runs

1. Install existing requirements and run the full network-disabled offline suite.
2. Read current public Binance/CoinGecko prices and closed 1h/4h/1d/1w candles for AAVE, TAO, FET, SOL, ONDO, RENDER plus BTC/ETH context. Check freshness using existing V11 data logic. No synthetic fallback.
3. Probe the existing16 fundamental feeds/calendars, DeFiLlama metrics and Treasury source. Record fetch and parser results separately. HTTP200 with0 recent relevant items means reachable, not comprehensive fundamental coverage. Unavailable sources/metrics remain N/A.
4. Render morning and evening templates using the same current snapshot. These are previews, **not historical07:00/20:00 analyses**, and do not invent a morning-to-evening comparison. Actual positions are unknown; all assets have an explicitly empty SHADOW context, no assumed account balance.
5. Optional Groq only selects existing deterministic reasons. Missing key, invalid selection, HTTP429 or provider failure uses deterministic explanations; no invented facts. `use_groq=false` by default. A long Retry-After stops retries rather than retrying too early.
6. Independently inject Groq and fundamental-source outages, compare deterministic decisions and save clearly labelled fault reports. Fault outputs never replace the live source report.
7. Upload isolated public-market artifacts even if the live market quality check fails. All six assets need a current price and usable4h EMA200 for a successful live check; missing data makes the step fail(exit2), with diagnostic files preserved.

## Safety boundaries

- The runner never imports `main.py`, loads a state backend, parses `bot_state.json`, reads Telegram updates, loads real positions, calls portfolio commands or invokes production analysis/delivery entrypoints. It only hashes protected files before/after as an invariant.
- No Telegram/state/broker secrets are passed to the job. Only optional `GROQ_API_KEY` is available to the live step. Checkout credentials are not persisted; token permission is `contents: read`.
- A restricted API facade permits only public market GET endpoints and optional Groq POST. Telegram, broker/order endpoints, HTTP and arbitrary redirect destinations are refused. No exchange client or order method exists. Fundamental reads use the existing bounded public-feed fetcher.
- `BOT_DISABLE_TELEGRAM=1`, `BOT_DATA_MODE=shadow`, `V11_RULES_VALIDATED=false`; no active production signal is enabled. Runtime guard enforces shadow flags even when called outside Actions.
- Output is restricted to `shadow-output/`, ignored by Git. Artifacts contain public prices/events and test diagnostics, not production state, environment dumps, credentials or real balances. Retention7days. Artifacts are test output, not a portfolio storage system.
- No schedule, push trigger, deployment, writeback or concurrency with the production group. No existing workflow changed.

## Manual launch after the development branch is pushed

In GitHub: repository **Actions → V11.1 Shadow Test → Run workflow**, select **feature/v11-1-review**, leave `use_groq` off for the free deterministic baseline, then run. To check Groq, repeat with `use_groq=true` after the repository secret `GROQ_API_KEY` is configured. Do not enter credentials as workflow inputs. Never run the production bot workflow for this test.

CLI alternative (requires repository Actions permissions):

```bash
gh workflow run v11-1-shadow-test.yml --repo janmarticek4-dot/crypto-bot --ref feature/v11-1-review -f use_groq=false
gh run list --repo janmarticek4-dot/crypto-bot --workflow v11-1-shadow-test.yml --branch feature/v11-1-review
gh run download RUN_ID --repo janmarticek4-dot/crypto-bot --dir shadow-download
```

**GitHub discovery limitation:** a brand-new `workflow_dispatch` workflow may not appear/be dispatchable until its file is registered on the repository's default branch. Selecting `--ref` selects the executing version; it does not bypass GitHub's discovery/authorization requirement. If GitHub returns404/does not list it, do not modify or dispatch the production workflow as a workaround. This change intentionally does not add anything to main. Without touching the original main, a separate research fork with `feature/v11-1-review` as its default branch can run the workflow (guard still matches the branch name). Alternatively run the identical script locally. Main/default-branch registration requires a separately approved repository change and was not performed.

## Downloaded results

Open the run → **Summary → Artifacts → `v11-1-shadow-RUN_ID-ATTEMPT`** and download the ZIP.

- `morning.txt`, `evening.txt`: current-data previews of both templates.
- `morning_parts.json`, `evening_parts.json`: the logical Telegram-sized parts, saved only; never sent.
- `market_snapshot.json`: public prices, closed candles, indicator values and source errors.
- `fundamentals.json`, `source_availability.json`: attributed events, actual source reachability/parser status and missing metrics.
- `summary.json`: six-coin freshness, actual AI availability and protected-state invariants.
- `outage_checks.json`, `*_injected_outage.txt`: deliberate failure cases, separate from actual source results.

## Local verification on22.10.2026

Live collection completed at12:07:31 Europe/Bratislava. All six prices/4h trend data were current, BTC/ETH context complete. Six of16 feed parsers were accessible: SOL/TAO/FET/RENDER GitHub feeds plus CoinDesk/Cointelegraph; only some had recent items. Ten feeds/calendars returned403 from this environment; TVL metrics and Treasury data were N/A. These results describe this environment, not guaranteed accessibility from a GitHub-hosted runner. Groq was not called in the live baseline; missing-key and injected-failure fallbacks were tested. Both report templates were generated, protected files unchanged. See `SHADOW_VALIDATION.json`.

Local reproduction:

```bash
python -m pip install -r requirements.txt
python scripts/test_offline.py
python scripts/v111_shadow.py
# Optional, using GROQ_API_KEY from environment without printing it:
python scripts/v111_shadow.py --use-groq
```

No GitHub Actions run or remote artifact is claimed unless an actual run URL is available. Repository Actions API access returned Forbidden from this environment during setup; local files/tests remain independently reviewable.
