# Two actual observations —22.10.2026

**Completed**, with public live data and preserved original recommendations. See REPORT.md and comparison.json. This is a56.15minute observation test, not a claimed07:00→20:00 test.

- First: existing actual live collection22.10.2026 **12:07:31 Bratislava**, saved before this task and already reviewed. Original report, summary, source timestamps and raw public candles are preserved in first.json.gz.
- Second: NEW actual live collection **13:03:40 Bratislava**, obtained during this task, preserved in second.json.gz. No copied quote data, clock replacement or synthetic price changes.
- All six assets have newer closed1h candles (12:00→13:00 Bratislava), fresh quote evidence and changed source fingerprints. Last completed4h candle is the same for both, explaining unchanged4h trend indicators. WAIT→WAIT is an observed result, not a requirement to create activity.
- Capitalization/rolling24h volume changes use CoinGecko metadata; live prices use Binance USDT. Different provider timestamps and USD/USDT bases can yield different relative movements. Neither capitalization nor volume differences prove net capital flow.
- Original actions are extracted from the actual original text reports. Strategy file SHA256 matches commit993e4f6, so the decision rules were not revised to reinterpret the first observation.
- First checkpoint was atomically written with a checksum before comparison. Checkpoint files cannot be overwritten. Public inputs are now additionally stored in compressed archives in the development branch, surviving replacement of this workspace. No actual positions or credentials are included.
- No new schedule was necessary: the second observation was obtainable immediately. The stricter existing morning/evening workflow, slots and>=8h guard remain unchanged. No schedule or production workflow was edited.

## Reproduction

Requires the existing repository Python environment; no new package or network is needed to replay the archived comparison:

```python
import gzip,json
from pathlib import Path
from scripts.v111_compare_observations import compare,markdown
root=Path('docs/v11.1/observations-20261022')
first=json.loads(gzip.decompress((root/'first.json.gz').read_bytes()))
second=json.loads(gzip.decompress((root/'second.json.gz').read_bytes()))
print(markdown(compare(first,second)))
```

Verify input hashes against VALIDATION.json first. To compare fresh saved shadow-output bundles, use a NEW output directory:

```bash
python scripts/v111_compare_observations.py --first shadow-output --second shadow-output/two-observations-20261022/second --output shadow-output/new-audit-result
```

The loader rejects synthetic input, incomplete market coverage, missing quote freshness, missing original recommendations and nonisolated input paths. Comparison requires at least15minutes and a newer provider timestamp per asset, not just a different collector timestamp. It checks source fingerprints and rejects future closed candles. The original strict07/20 validator was not relaxed or bypassed; this is a separately labelled observation audit.

## Concrete macro-source failure

macro-probes.json contains fresh direct probes of Fed calendar/RSS, BLS RSS/calendar, BEA, ECB, CFTC and SEC. All returned:

```text
urllib.error.URLError
Tunnel connection failed: 403 Forbidden
origin_http_status: null
layer: network_tunnel
```

This is a refused HTTPS CONNECT/tunnel before a publisher response. It is NOT a confirmed HTTP403 from the Fed/BLS/etc server. Changing feed paths or User-Agent on the same blocked host cannot repair this layer. No missing macro release, result or forecast was invented.

Proposed repairs, without changing production or granting any trading access:

1. Allow outbound HTTPS/CONNECT in this cloud environment to the specific public source hosts: `www.federalreserve.gov`, `www.bls.gov`, `apps.bea.gov`, `www.bea.gov`, `www.ecb.europa.eu`, `www.sec.gov`, `www.cftc.gov`, plus `home.treasury.gov` for existing Treasury data. Broader wildcards are unnecessary. This is an environment networking change; it was not silently applied.
2. Run the same isolated source probes from an authorized GitHub-hosted runner to distinguish cloud policy from origin restrictions. The shadow workflow/artifact procedure already exists. Existing Actions API Forbidden/discovery limitations remain; do not dispatch the production workflow as a workaround.
3. Once CONNECT succeeds, inspect actual origin status and parser/schema. If SEC THEN returns origin403, use compliant identification/contact and SEC fair-access limits; do not pretend that this is the presently observed error. Respect429 Retry-After; retry/backoff cannot solve a persistent tunnel deny.
4. Keep publisher-preserving fallbacks with explicit trust labels. AAVE repository and filtered ONDO secondary feeds are reachable, but are not substitutes for verified Fed/BLS event dates or complete fundamentals. Retain N/A for unavailable official calendars, consensus and actual economic impact.
5. Re-run the upcoming24h/7d/14d calendar checks after source access is restored. Parser/unit tests alone do not verify actual upcoming events.

## Remaining unverified

- Full real07:00→20:00 same-day comparison and longer forecast horizons; the existing strict two-run protocol remains prepared, not claimed executed.
- Official macro calendar/release completeness, consensus and actual economic price causation.
- Actual GitHub Actions execution from this environment. This test ran locally with live public network data; no Actions run URL or remote artifact is invented.
- Live Groq success was not requested for this test; deterministic fallback and provider-failure behavior are covered by offline tests.
- Longer-run trading profitability/manual broker execution is outside this observation comparison. No real trades, portfolio load, Telegram messages or main changes occurred.

Validation:164 offline bot/shadow tests plus22phase3 and11phase2 research tests passed. Original main,state,portfolio,strategy,monitor/runtime and production workflow remain unchanged. Both compressed inputs were replayed to reproduce the result exactly.
