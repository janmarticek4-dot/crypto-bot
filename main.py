import os
import json
import time
import re
import math
import urllib.request
import urllib.parse
import urllib.error
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from zoneinfo import ZoneInfo


# ============================================================
# CRYPTO AI BOT V5.2
# ============================================================
# - CoinGecko market + technical data
# - Alternative.me Fear & Greed
# - RSS news with fallback
# - Gemini 3.8 Flash Interactions API
# - Gemini background execution + polling
# - Google Search grounding
# - thinking_level = high
# - NO temperature / top_p / top_k / thinking_budget
# - Telegram
# - bot_state.json
# - FET corrected to fetch-ai
# ============================================================


# =========================
# CONFIG
# =========================

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()
COINGECKO_API_KEY = os.getenv("COINGECKO_API_KEY", "").strip()

GEMINI_MODEL = "gemini-3.8-flash"

REQUEST_TIMEOUT = 120
GEMINI_MAX_WAIT = 600
POLL_INTERVAL = 5

STATE_FILE = "bot_state.json"

MANUAL_ANALYSIS = os.getenv("MANUAL_ANALYSIS", "false").lower() == "true"

TZ = ZoneInfo("Europe/Bratislava")


# =========================
# PORTFOLIO
# =========================

PORTFOLIO = {
    "AAVE": "aave",
    "TAO": "bittensor",
    "FET": "fetch-ai",
    "SOL": "solana",
    "ONDO": "ondo-finance",
    "RENDER": "render-token",
}


# =========================
# CANDIDATES
# =========================

CANDIDATES = [
    "sui",
    "chainlink",
    "compound-governance-token",
    "avalanche-2",
    "hyperliquid",
    "near",
    "injective-protocol",
    "uniswap",
    "arbitrum",
    "optimism",
    "maker",
    "mantle",
]


# =========================
# RSS SOURCES
# =========================

RSS_FEEDS = [
    ("CoinTelegraph", "https://cointelegraph.com/rss"),
    ("CoinDesk", "https://www.coindesk.com/arc/outboundfeeds/rss/"),
]


# =========================
# HELPERS
# =========================

def now_local():
    return datetime.now(TZ)


def iso_now():
    return now_local().isoformat()


def safe_float(value, default=None):
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def clamp(value, low, high):
    return max(low, min(high, value))


def pct_change(old, new):
    if old in (None, 0) or new is None:
        return None
    return ((new - old) / old) * 100.0


# =========================
# HTTP
# =========================

def http_get_request(req, timeout=REQUEST_TIMEOUT, retries=4):
    last_error = None

    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                return response.read()

        except urllib.error.HTTPError as e:
            last_error = e

            print(
                f"HTTP {e.code} "
                f"(pokus {attempt + 1}/{retries}): {e.reason}"
            )

            # 404 / 403 etc. nema zmysel donekonecna retryovat.
            if e.code in {400, 401, 403, 404}:
                raise

            if attempt < retries - 1:
                wait = 2 ** attempt
                print(f"Retry o {wait} sekúnd...")
                time.sleep(wait)

        except (
            urllib.error.URLError,
            TimeoutError,
            ConnectionError,
            OSError
        ) as e:
            last_error = e

            print(
                f"HTTP chyba "
                f"(pokus {attempt + 1}/{retries}): {e}"
            )

            if attempt < retries - 1:
                wait = 2 ** attempt
                print(f"Retry o {wait} sekúnd...")
                time.sleep(wait)

    if last_error:
        raise last_error

    raise RuntimeError("HTTP request zlyhal.")


def http_json(
    url,
    headers=None,
    timeout=REQUEST_TIMEOUT,
    retries=4
):
    if headers is None:
        headers = {}

    req = urllib.request.Request(
        url,
        headers=headers,
        method="GET"
    )

    raw = http_get_request(
        req,
        timeout=timeout,
        retries=retries
    )

    return json.loads(raw.decode("utf-8"))


# =========================
# COINGECKO
# =========================

def coingecko_headers():
    headers = {
        "Accept": "application/json",
        "User-Agent": "CryptoAIBot/5.2"
    }

    if COINGECKO_API_KEY:
        headers["x-cg-demo-api-key"] = COINGECKO_API_KEY

    return headers


def coingecko_get(endpoint, params=None):
    base = "https://api.coingecko.com/api/v3"

    if params:
        query = urllib.parse.urlencode(params)
        url = f"{base}/{endpoint}?{query}"
    else:
        url = f"{base}/{endpoint}"

    return http_json(
        url,
        headers=coingecko_headers()
    )


def coingecko_simple_price(ids):
    if not ids:
        return {}

    data = coingecko_get(
        "simple/price",
        {
            "ids": ",".join(ids),
            "vs_currencies": "usd",
            "include_market_cap": "true",
            "include_24hr_vol": "true",
            "include_24hr_change": "true",
            "include_last_updated_at": "true",
        }
    )

    return data


def coingecko_markets(ids):
    if not ids:
        return []

    data = coingecko_get(
        "coins/markets",
        {
            "vs_currency": "usd",
            "ids": ",".join(ids),
            "order": "market_cap_desc",
            "per_page": len(ids),
            "page": 1,
            "sparkline": "false",
            "price_change_percentage": "24h,7d",
        }
    )

    return data


def coingecko_chart(coin_id, days=90, interval="hourly"):
    params = {
        "vs_currency": "usd",
        "days": days,
    }

    # CoinGecko automaticky určuje interval pri dlhších obdobiach.
    if interval:
        params["interval"] = interval

    return coingecko_get(
        f"coins/{coin_id}/market_chart",
        params
    )


# =========================
# TECHNICAL ANALYSIS
# =========================

def closes_from_chart(chart):
    prices = chart.get("prices", [])

    return [
        {
            "timestamp": p[0],
            "price": safe_float(p[1])
        }
        for p in prices
        if len(p) >= 2 and safe_float(p[1]) is not None
    ]


def aggregate_candles(prices, hours=4):
    if not prices:
        return []

    buckets = {}

    bucket_ms = hours * 60 * 60 * 1000

    for p in prices:
        ts = int(p["timestamp"])
        price = p["price"]

        bucket = (ts // bucket_ms) * bucket_ms

        if bucket not in buckets:
            buckets[bucket] = {
                "timestamp": bucket,
                "open": price,
                "high": price,
                "low": price,
                "close": price,
            }
        else:
            buckets[bucket]["high"] = max(
                buckets[bucket]["high"],
                price
            )
            buckets[bucket]["low"] = min(
                buckets[bucket]["low"],
                price
            )
            buckets[bucket]["close"] = price

    return [
        buckets[k]
        for k in sorted(buckets.keys())
    ]


def ema(values, period):
    if not values:
        return []

    if len(values) < period:
        return [None] * len(values)

    result = [None] * len(values)

    sma = sum(values[:period]) / period
    result[period - 1] = sma

    multiplier = 2 / (period + 1)

    previous = sma

    for i in range(period, len(values)):
        current = (
            (values[i] - previous) * multiplier
            + previous
        )

        result[i] = current
        previous = current

    return result


def rsi(values, period=14):
    if len(values) < period + 1:
        return None

    gains = []
    losses = []

    for i in range(1, len(values)):
        change = values[i] - values[i - 1]

        gains.append(max(change, 0))
        losses.append(max(-change, 0))

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    if avg_loss == 0:
        return 100.0

    rs = avg_gain / avg_loss
    current_rsi = 100 - (100 / (1 + rs))

    for i in range(period, len(gains)):
        avg_gain = (
            (avg_gain * (period - 1))
            + gains[i]
        ) / period

        avg_loss = (
            (avg_loss * (period - 1))
            + losses[i]
        ) / period

        if avg_loss == 0:
            current_rsi = 100.0
        else:
            rs = avg_gain / avg_loss
            current_rsi = 100 - (100 / (1 + rs))

    return current_rsi


def macd(values):
    if len(values) < 35:
        return {
            "macd": None,
            "signal": None,
            "histogram": None
        }

    ema12 = ema(values, 12)
    ema26 = ema(values, 26)

    macd_values = []

    for a, b in zip(ema12, ema26):
        if a is None or b is None:
            macd_values.append(None)
        else:
            macd_values.append(a - b)

    valid = [
        x for x in macd_values
        if x is not None
    ]

    signal_values = ema(valid, 9)

    if not signal_values:
        return {
            "macd": None,
            "signal": None,
            "histogram": None
        }

    current_macd = valid[-1]
    current_signal = signal_values[-1]

    if current_signal is None:
        histogram = None
    else:
        histogram = current_macd - current_signal

    return {
        "macd": current_macd,
        "signal": current_signal,
        "histogram": histogram
    }


def technical_summary(candles):
    if not candles:
        return {}

    closes = [
        c["close"]
        for c in candles
        if c.get("close") is not None
    ]

    if len(closes) < 20:
        return {
            "price": closes[-1] if closes else None
        }

    ema20 = ema(closes, 20)
    ema50 = ema(closes, 50)
    ema100 = ema(closes, 100)
    ema200 = ema(closes, 200)

    current = closes[-1]

    rsi14 = rsi(closes, 14)
    macd_data = macd(closes)

    def last_valid(arr):
        for x in reversed(arr):
            if x is not None:
                return x
        return None

    e20 = last_valid(ema20)
    e50 = last_valid(ema50)
    e100 = last_valid(ema100)
    e200 = last_valid(ema200)

    return {
        "price": current,
        "ema20": e20,
        "ema50": e50,
        "ema100": e100,
        "ema200": e200,
        "rsi14": rsi14,
        "macd": macd_data,
        "above_ema20": (
            current > e20
            if e20 is not None
            else None
        ),
        "above_ema50": (
            current > e50
            if e50 is not None
            else None
        ),
        "above_ema200": (
            current > e200
            if e200 is not None
            else None
        ),
    }


def recent_returns(closes):
    if not closes:
        return {}

    current = closes[-1]

    result = {}

    periods = {
        "24h": 6,
        "7d": 42,
        "30d": 180,
    }

    for name, bars in periods.items():
        if len(closes) > bars:
            old = closes[-bars - 1]
            result[name] = pct_change(old, current)

    return result


# =========================
# COIN DATA
# =========================

def collect_coin_data(symbol, coin_id):
    print(f"Collecting: {symbol}")

    simple = coingecko_simple_price([coin_id])
    current = simple.get(coin_id, {})

    # 90 dní pre 4H techniku
    chart_90 = coingecko_chart(
        coin_id,
        days=90,
        interval="hourly"
    )

    prices_90 = closes_from_chart(chart_90)

    candles_4h = aggregate_candles(
        prices_90,
        hours=4
    )

    technical_4h = technical_summary(
        candles_4h
    )

    closes_4h = [
        x["close"]
        for x in candles_4h
    ]

    returns = recent_returns(closes_4h)

    return {
        "symbol": symbol,
        "coin_id": coin_id,
        "price_usd": current.get("usd"),
        "market_cap": current.get("usd_market_cap"),
        "volume_24h": current.get("usd_24h_vol"),
        "change_24h": current.get("usd_24h_change"),
        "last_updated": current.get("last_updated_at"),
        "technical_4h": technical_4h,
        "returns": returns,
    }


# =========================
# CANDIDATE SHORTLIST
# =========================

def shortlist_candidates():
    print("Shortlisting candidate coins...")

    market_data = coingecko_markets(
        CANDIDATES
    )

    if not market_data:
        return CANDIDATES[:3]

    portfolio_ids = set(PORTFOLIO.values())

    filtered = [
        x for x in market_data
        if x.get("id") not in portfolio_ids
    ]

    # Kombinácia likvidity + market cap.
    # Neberieme úplne malé illiquid tokeny.
    filtered = [
        x for x in filtered
        if safe_float(x.get("market_cap"), 0) > 100_000_000
    ]

    filtered.sort(
        key=lambda x: (
            safe_float(x.get("total_volume"), 0),
            safe_float(x.get("market_cap"), 0)
        ),
        reverse=True
    )

    selected = filtered[:3]

    print(
        "Candidate shortlist:",
        [
            x.get("id")
            for x in selected
        ]
    )

    return [
        x["id"]
        for x in selected
    ]


# =========================
# MARKET DATA
# =========================

def get_market_global():
    return coingecko_get("global")


def get_fear_greed():
    try:
        data = http_json(
            "https://api.alternative.me/fng/?limit=1",
            headers={
                "User-Agent": "CryptoAIBot/5.2"
            }
        )

        item = data["data"][0]

        return {
            "value": int(item["value"]),
            "classification": item["value_classification"],
            "timestamp": item.get("timestamp"),
        }

    except Exception as e:
        print(f"Fear & Greed error: {e}")

        return {
            "value": None,
            "classification": "UNKNOWN",
            "timestamp": None,
        }


# =========================
# NEWS / RSS
# =========================

def get_rss_news():
    headers = {
        "User-Agent": (
            "Mozilla/5.0 "
            "(compatible; CryptoAIBot/5.2; +https://github.com/)"
        ),
        "Accept": (
            "application/rss+xml, "
            "application/xml, "
            "text/xml, "
            "*/*"
        ),
    }

    all_items = []

    for source_name, url in RSS_FEEDS:
        try:
            print(f"RSS: {source_name}")

            req = urllib.request.Request(
                url,
                headers=headers,
                method="GET"
            )

            raw = http_get_request(
                req,
                timeout=30,
                retries=2
            )

            root = ET.fromstring(raw)

            count = 0

            for item in root.iter():
                if item.tag.lower().endswith("item"):
                    title = ""
                    link = ""
                    pub_date = ""

                    for child in item:
                        tag = child.tag.lower()

                        if tag.endswith("title"):
                            title = (
                                child.text or ""
                            ).strip()

                        elif tag.endswith("link"):
                            link = (
                                child.text or ""
                            ).strip()

                        elif tag.endswith("pubdate"):
                            pub_date = (
                                child.text or ""
                            ).strip()

                    if title:
                        all_items.append({
                            "source": source_name,
                            "title": title,
                            "link": link,
                            "pub_date": pub_date,
                        })

                        count += 1

                    if count >= 10:
                        break

            if count:
                print(
                    f"RSS {source_name}: "
                    f"{count} článkov"
                )

        except Exception as e:
            print(
                f"RSS error {source_name}: {e}"
            )

    return all_items[:20]


# =========================
# MARKET SAFETY
# =========================

def market_safety(global_data, simple_prices):
    score = 0
    reasons = []

    try:
        total_market_cap_change = (
            global_data["data"]
            .get("market_cap_change_percentage_24h_usd")
        )

        if total_market_cap_change is not None:
            if total_market_cap_change < -5:
                score += 2
                reasons.append(
                    "celková kapitalizácia prudko klesá"
                )
            elif total_market_cap_change < -2:
                score += 1
                reasons.append(
                    "celková kapitalizácia klesá"
                )

    except Exception:
        pass

    try:
        btc = simple_prices.get("bitcoin", {})
        btc_change = btc.get("usd_24h_change")

        if btc_change is not None:
            if btc_change < -7:
                score += 3
                reasons.append(
                    "BTC výrazne klesá"
                )
            elif btc_change < -3:
                score += 2
                reasons.append(
                    "BTC prudko klesá"
                )
            elif btc_change < -1.5:
                score += 1
                reasons.append(
                    "BTC klesá"
                )

    except Exception:
        pass

    if score >= 5:
        state = "CRITICAL"
    elif score >= 2:
        state = "WARNING"
    else:
        state = "NORMAL"

    return {
        "state": state,
        "score": score,
        "reasons": reasons,
    }


# =========================
# GEMINI SCHEMA
# =========================

def gemini_schema():
    return {
        "type": "object",
        "properties": {
            "market_regime": {
                "type": "string"
            },
            "market_summary": {
                "type": "string"
            },
            "action": {
                "type": "string"
            },
            "new_coin": {
                "type": "string"
            },
            "new_coin_action": {
                "type": "string"
            },
            "new_coin_reason": {
                "type": "string"
            },
            "coins": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "symbol": {
                            "type": "string"
                        },
                        "action": {
                            "type": "string"
                        },
                        "current_price": {
                            "type": "number"
                        },
                        "buy_zone_1": {
                            "type": "string"
                        },
                        "buy_zone_2": {
                            "type": "string"
                        },
                        "invalidation": {
                            "type": "string"
                        },
                        "tp1": {
                            "type": "string"
                        },
                        "tp2": {
                            "type": "string"
                        },
                        "risk_reward": {
                            "type": "string"
                        },
                        "bull_probability": {
                            "type": "number"
                        },
                        "bear_probability": {
                            "type": "number"
                        },
                        "technical_score": {
                            "type": "number"
                        },
                        "fundamental_score": {
                            "type": "number"
                        },
                        "reason": {
                            "type": "string"
                        }
                    },
                    "required": [
                        "symbol",
                        "action",
                        "current_price",
                        "buy_zone_1",
                        "buy_zone_2",
                        "invalidation",
                        "tp1",
                        "tp2",
                        "risk_reward",
                        "bull_probability",
                        "bear_probability",
                        "technical_score",
                        "fundamental_score",
                        "reason"
                    ]
                }
            },
            "best_opportunity": {
                "type": "string"
            },
            "avoid": {
                "type": "string"
            },
            "conditions_to_watch": {
                "type": "array",
                "items": {
                    "type": "string"
                }
            }
        },
        "required": [
            "market_regime",
            "market_summary",
            "action",
            "new_coin",
            "new_coin_action",
            "new_coin_reason",
            "coins",
            "best_opportunity",
            "avoid",
            "conditions_to_watch"
        ]
    }


# =========================
# GEMINI OUTPUT PARSER
# =========================

def extract_output_text(response):
    output_text = response.get("output_text")

    if output_text:
        return output_text

    # Fallback pre prípad, že REST odpoveď vráti output bloky.
    output = response.get("output")

    if isinstance(output, str):
        return output

    if isinstance(output, list):
        texts = []

        for block in output:
            if isinstance(block, str):
                texts.append(block)

            elif isinstance(block, dict):
                text = block.get("text")

                if text:
                    texts.append(str(text))

        if texts:
            return "\n".join(texts)

    # Ďalší fallback cez steps.
    steps = response.get("steps", [])

    texts = []

    if isinstance(steps, list):
        for step in steps:
            if not isinstance(step, dict):
                continue

            step_output = step.get("output")

            if isinstance(step_output, list):
                for block in step_output:
                    if isinstance(block, dict):
                        text = block.get("text")

                        if text:
                            texts.append(str(text))

    if texts:
        return "\n".join(texts)

    return None


def parse_json_output(text):
    if not text:
        raise RuntimeError(
            "Gemini neposlal žiadny textový výstup."
        )

    text = text.strip()

    # Odstránenie markdown JSON fences.
    text = re.sub(
        r"^```json\s*",
        "",
        text,
        flags=re.IGNORECASE
    )

    text = re.sub(
        r"\s*```$",
        "",
        text
    )

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Fallback: nájdenie prvého JSON objektu.
    start = text.find("{")
    end = text.rfind("}")

    if start >= 0 and end > start:
        candidate = text[start:end + 1]

        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass

    raise RuntimeError(
        "Gemini output nie je validný JSON:\n"
        + text[:5000]
    )


# =========================
# GEMINI BACKGROUND API
# =========================

def gemini_analyze(prompt):

    if not GEMINI_API_KEY:
        raise RuntimeError(
            "GEMINI_API_KEY nie je nastavený."
        )

    create_url = (
        "https://generativelanguage.googleapis.com"
        "/v1beta/interactions"
    )

    payload = {
        "model": GEMINI_MODEL,
        "input": prompt,
        "tools": [
            {
                "type": "google_search"
            }
        ],
        "background": True,
        "generation_config": {
            "thinking_level": "high"
        },
        "response_format": {
            "type": "text",
            "mime_type": "application/json",
            "schema": gemini_schema()
        }
    }

    body = json.dumps(
        payload,
        ensure_ascii=False
    ).encode("utf-8")

    req = urllib.request.Request(
        create_url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": GEMINI_API_KEY,
            "Api-Revision": "2026-05-20",
        },
        method="POST"
    )

    print(
        "Spúšťam Gemini background analysis..."
    )

    raw = http_get_request(
        req,
        timeout=REQUEST_TIMEOUT,
        retries=4
    )

    response = json.loads(
        raw.decode("utf-8")
    )

    interaction_id = response.get("id")

    if not interaction_id:
        raise RuntimeError(
            "Gemini nevytvoril interaction:\n"
            + json.dumps(
                response,
                ensure_ascii=False
            )[:5000]
        )

    print(
        f"Gemini interaction ID: "
        f"{interaction_id}"
    )

    status_url = (
        "https://generativelanguage.googleapis.com"
        f"/v1beta/interactions/{interaction_id}"
    )

    started = time.time()

    while True:

        elapsed = time.time() - started

        if elapsed > GEMINI_MAX_WAIT:
            raise TimeoutError(
                "Gemini background analysis "
                "trvá dlhšie ako 10 minút."
            )

        status_req = urllib.request.Request(
            status_url,
            headers={
                "x-goog-api-key": GEMINI_API_KEY,
                "Api-Revision": "2026-05-20",
            },
            method="GET"
        )

        raw_status = http_get_request(
            status_req,
            timeout=60,
            retries=4
        )

        result = json.loads(
            raw_status.decode("utf-8")
        )

        status = result.get(
            "status",
            "unknown"
        )

        print(
            f"Gemini status: {status} "
            f"({int(elapsed)}s)"
        )

        if status == "completed":

            output_text = extract_output_text(
                result
            )

            return parse_json_output(
                output_text
            )

        if status in {
            "failed",
            "cancelled",
            "incomplete",
            "budget_exceeded"
        }:

            raise RuntimeError(
                "Gemini interaction skončila "
                f"stavom {status}:\n"
                + json.dumps(
                    result,
                    ensure_ascii=False
                )[:6000]
            )

        if status == "requires_action":
            raise RuntimeError(
                "Gemini interaction vyžaduje "
                "ďalšiu akciu, ktorú tento bot "
                "nevie automaticky vykonať."
            )

        time.sleep(POLL_INTERVAL)


# =========================
# PROMPT
# =========================

def build_prompt(
    market_global,
    fear_greed,
    safety,
    news,
    portfolio_data,
    candidate_data
):

    prompt = f"""
You are the main investment intelligence engine of a crypto trading bot.

CURRENT TIME:
{iso_now()}

IMPORTANT:
You MUST use current information from Google Search where relevant.
Do not rely on old knowledge when judging current events, regulation,
ETF/news, partnerships, token unlocks, ecosystem developments,
institutional activity or other fundamental factors.

The user wants practical investment decisions, not generic education.

INVESTMENT HORIZON:
- Main horizon: now through approximately April 2027.
- Short-term technical horizon: hours to several weeks.
- The user prefers buying pullbacks rather than chasing pumps.
- The user is willing to hold high-risk altcoins if the upside justifies it.
- The user does NOT want additional APT exposure.
- The user already owns the portfolio coins listed below.

VERY IMPORTANT:
If there is no attractive new coin setup, say NO TRADE.
Do NOT invent a buy opportunity simply because the bot is expected to
recommend something.

MARKET DATA
===========
Global CoinGecko data:
{json.dumps(market_global, ensure_ascii=False, indent=2)}

Fear & Greed:
{json.dumps(fear_greed, ensure_ascii=False, indent=2)}

Market safety:
{json.dumps(safety, ensure_ascii=False, indent=2)}

RECENT NEWS
==========
{json.dumps(news, ensure_ascii=False, indent=2)}

CURRENT PORTFOLIO
=================
{json.dumps(portfolio_data, ensure_ascii=False, indent=2)}

POTENTIAL NEW COINS
===================
These are candidates preselected for liquidity/market-cap reasons.
You must still independently judge whether any of them is actually
worth buying.

{json.dumps(candidate_data, ensure_ascii=False, indent=2)}

TASK
====

Perform a fresh market analysis.

1. Determine the current crypto market regime:
   - bullish
   - neutral
   - corrective
   - bearish
   - capitulation

2. Analyze BTC and total market conditions.

3. Analyze each portfolio coin:
   AAVE
   TAO
   FET
   SOL
   ONDO
   RENDER

4. For each portfolio coin decide:
   - BUY NOW
   - BUY PULLBACK
   - HOLD
   - REDUCE
   - SELL
   - NO TRADE

5. Give realistic buy zones based on current price and technical
   structure. Do NOT choose arbitrary round numbers.

6. Give invalidation levels.

7. Give TP1 and TP2.

8. Estimate bull and bear probabilities.
   They should reflect the current setup, not simply be 50/50.

9. Give technical score from 0 to 10.

10. Give fundamental score from 0 to 10.

11. For fundamentals consider:
   - adoption
   - revenue/fees where relevant
   - TVL where relevant
   - developer activity
   - institutional adoption
   - token utility
   - token unlocks
   - inflation
   - competition
   - ecosystem growth
   - regulatory/news catalysts
   - valuation

12. Analyze the potential NEW COINS.

13. Choose at most ONE best new coin.

14. The new coin must have a compelling asymmetric setup.
   High upside alone is NOT enough.

15. Compare the new coin against the user's existing portfolio.
   If putting more money into an existing position is better,
   say so and set new_coin_action to NO TRADE.

16. Do NOT recommend APT.

17. Be especially careful if the market safety state is WARNING or CRITICAL.
   In those conditions prefer pullbacks and smaller risk.

18. If a coin has already pumped heavily, do not recommend chasing it.
   Instead give a pullback zone or NO TRADE.

19. Search current information for important fundamental claims.
   Prefer primary sources and reliable financial/crypto sources.

20. Ignore unsupported hype.

21. The output MUST follow the supplied JSON schema exactly.

ACTION DEFINITIONS
==================
BUY NOW:
Current price is attractive enough to enter.

BUY PULLBACK:
Do not buy current price. Wait for the specified zone.

HOLD:
Keep the existing position; no aggressive action.

REDUCE:
Take partial profit / reduce risk.

SELL:
Exit the position because risk/reward has deteriorated.

NO TRADE:
No attractive setup.

RISK/REWARD:
Use practical approximate R:R based on buy zone, invalidation and TP1.

IMPORTANT:
The user values capital preservation during corrections.
A missed trade is better than a bad trade.
"""


    return prompt


# =========================
# TELEGRAM
# =========================

def telegram_send(text):

    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print(
            "Telegram credentials nie sú nastavené."
        )
        return

    url = (
        "https://api.telegram.org"
        f"/bot{TELEGRAM_TOKEN}/sendMessage"
    )

    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }

    body = json.dumps(
        payload,
        ensure_ascii=False
    ).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json"
        },
        method="POST"
    )

    try:
        http_get_request(
            req,
            timeout=30,
            retries=3
        )

    except Exception as e:
        print(
            f"Telegram error: {e}"
        )


def clean_html(text):
    if text is None:
        return ""

    text = str(text)

    text = (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )

    return text


def format_price(value):
    value = safe_float(value)

    if value is None:
        return "N/A"

    if value >= 1000:
        return f"${value:,.0f}"

    if value >= 100:
        return f"${value:,.2f}"

    if value >= 1:
        return f"${value:,.3f}"

    if value >= 0.01:
        return f"${value:,.4f}"

    return f"${value:.8f}"


def format_bot_message(
    analysis,
    safety,
    fear_greed
):

    lines = []

    lines.append(
        "<b>📊 CRYPTO AI BOT — 4H ANALÝZA</b>"
    )

    lines.append(
        f"🕒 {clean_html(iso_now())}"
    )

    lines.append("")

    lines.append(
        f"<b>🌐 Trh:</b> "
        f"{clean_html(analysis.get('market_regime', 'N/A'))}"
    )

    lines.append(
        f"<b>🛡 Safety:</b> "
        f"{clean_html(safety.get('state', 'N/A'))} "
        f"({safety.get('score', 0)})"
    )

    if safety.get("reasons"):
        lines.append(
            " • " +
            " • ".join(
                clean_html(x)
                for x in safety["reasons"]
            )
        )

    fg_value = fear_greed.get("value")

    if fg_value is not None:
        lines.append(
            f"<b>😱 Fear & Greed:</b> "
            f"{fg_value}/100 "
            f"({clean_html(fear_greed.get('classification', ''))})"
        )

    lines.append("")

    lines.append(
        "<b>🧠 Makro:</b>"
    )

    lines.append(
        clean_html(
            analysis.get(
                "market_summary",
                ""
            )
        )
    )

    lines.append("")

    coins = analysis.get(
        "coins",
        []
    )

    for coin in coins:

        symbol = coin.get(
            "symbol",
            "?"
        )

        action = coin.get(
            "action",
            "N/A"
        )

        lines.append(
            f"<b>━━ {clean_html(symbol)} ━━</b>"
        )

        lines.append(
            f"<b>Akcia:</b> "
            f"{clean_html(action)}"
        )

        lines.append(
            f"<b>Cena:</b> "
            f"{format_price(coin.get('current_price'))}"
        )

        lines.append(
            f"<b>BUY 1:</b> "
            f"{clean_html(coin.get('buy_zone_1', 'N/A'))}"
        )

        lines.append(
            f"<b>BUY 2:</b> "
            f"{clean_html(coin.get('buy_zone_2', 'N/A'))}"
        )

        lines.append(
            f"<b>Invalidácia:</b> "
            f"{clean_html(coin.get('invalidation', 'N/A'))}"
        )

        lines.append(
            f"<b>TP1:</b> "
            f"{clean_html(coin.get('tp1', 'N/A'))}"
        )

        lines.append(
            f"<b>TP2:</b> "
            f"{clean_html(coin.get('tp2', 'N/A'))}"
        )

        lines.append(
            f"<b>R:R:</b> "
            f"{clean_html(coin.get('risk_reward', 'N/A'))}"
        )

        bull = safe_float(
            coin.get("bull_probability")
        )

        bear = safe_float(
            coin.get("bear_probability")
        )

        if bull is not None and bear is not None:
            lines.append(
                f"<b>🐂 Bull:</b> {bull:.0f}% "
                f"| <b>🐻 Bear:</b> {bear:.0f}%"
            )

        lines.append(
            f"<b>Technika:</b> "
            f"{coin.get('technical_score', 'N/A')}/10"
        )

        lines.append(
            f"<b>Fundament:</b> "
            f"{coin.get('fundamental_score', 'N/A')}/10"
        )

        lines.append(
            f"<i>{clean_html(coin.get('reason', ''))}</i>"
        )

        lines.append("")

    lines.append(
        "<b>🚀 Najlepšia príležitosť:</b>"
    )

    lines.append(
        clean_html(
            analysis.get(
                "best_opportunity",
                "N/A"
            )
        )
    )

    lines.append("")

    lines.append(
        "<b>🆕 Nová kryptomena:</b> "
        + clean_html(
            analysis.get(
                "new_coin",
                "NO TRADE"
            )
        )
    )

    lines.append(
        "<b>Akcia:</b> "
        + clean_html(
            analysis.get(
                "new_coin_action",
                "NO TRADE"
            )
        )
    )

    lines.append(
        "<b>Dôvod:</b> "
        + clean_html(
            analysis.get(
                "new_coin_reason",
                ""
            )
        )
    )

    lines.append("")

    lines.append(
        "<b>⚠️ Vyhnúť sa:</b> "
        + clean_html(
            analysis.get(
                "avoid",
                ""
            )
        )
    )

    conditions = analysis.get(
        "conditions_to_watch",
        []
    )

    if conditions:
        lines.append("")
        lines.append(
            "<b>👀 Sledovať:</b>"
        )

        for condition in conditions[:6]:
            lines.append(
                "• " + clean_html(condition)
            )

    lines.append("")

    lines.append(
        "<i>Nie je to finančné poradenstvo. "
        "Bot pracuje s aktuálnymi dátami a pravdepodobnostnými scenármi.</i>"
    )

    message = "\n".join(lines)

    # Telegram má limit približne 4096 znakov.
    if len(message) <= 4000:
        return [message]

    chunks = []

    current = ""

    for line in lines:
        if len(current) + len(line) + 1 > 3900:
            chunks.append(current)
            current = line
        else:
            current += (
                "\n"
                if current
                else ""
            ) + line

    if current:
        chunks.append(current)

    return chunks


# =========================
# STATE
# =========================

def load_state():

    if not os.path.exists(STATE_FILE):
        return {}

    try:
        with open(
            STATE_FILE,
            "r",
            encoding="utf-8"
        ) as f:
            return json.load(f)

    except Exception as e:
        print(
            f"State load error: {e}"
        )
        return {}


def save_state(state):

    try:
        with open(
            STATE_FILE,
            "w",
            encoding="utf-8"
        ) as f:
            json.dump(
                state,
                f,
                ensure_ascii=False,
                indent=2
            )

    except Exception as e:
        print(
            f"State save error: {e}"
        )


# =========================
# MAIN
# =========================

def main():

    print(
        "Crypto bot V5.2:",
        iso_now()
    )

    if not GEMINI_API_KEY:
        raise RuntimeError(
            "Chýba GEMINI_API_KEY."
        )

    # --------------------------------
    # 1. Global market
    # --------------------------------

    print("Collecting global market...")

    market_global = get_market_global()

    # --------------------------------
    # 2. Fear & Greed
    # --------------------------------

    print("Collecting Fear & Greed...")

    fear_greed = get_fear_greed()

    # --------------------------------
    # 3. Simple prices for safety
    # --------------------------------

    all_ids = list(
        dict.fromkeys(
            list(PORTFOLIO.values())
            + CANDIDATES
            + ["bitcoin"]
        )
    )

    simple_prices = coingecko_simple_price(
        all_ids
    )

    # --------------------------------
    # 4. Market safety
    # --------------------------------

    safety = market_safety(
        market_global,
        simple_prices
    )

    print(
        "MARKET SAFETY:",
        safety
    )

    # --------------------------------
    # 5. News
    # --------------------------------

    news = get_rss_news()

    # --------------------------------
    # 6. Portfolio technical data
    # --------------------------------

    portfolio_data = {}

    for symbol, coin_id in PORTFOLIO.items():

        try:
            portfolio_data[symbol] = (
                collect_coin_data(
                    symbol,
                    coin_id
                )
            )

        except Exception as e:

            print(
                f"ERROR collecting "
                f"{symbol}: {e}"
            )

            portfolio_data[symbol] = {
                "symbol": symbol,
                "coin_id": coin_id,
                "error": str(e),
            }

    # --------------------------------
    # 7. Candidate shortlist
    # --------------------------------

    shortlist = shortlist_candidates()

    # --------------------------------
    # 8. Deep technical data ONLY
    #    for top candidates
    # --------------------------------

    candidate_data = {}

    for coin_id in shortlist:

        symbol = coin_id.upper()

        try:
            candidate_data[symbol] = (
                collect_coin_data(
                    symbol,
                    coin_id
                )
            )

        except Exception as e:

            print(
                f"ERROR collecting "
                f"candidate {coin_id}: {e}"
            )

            candidate_data[symbol] = {
                "coin_id": coin_id,
                "error": str(e),
            }

    # --------------------------------
    # 9. Build Gemini prompt
    # --------------------------------

    prompt = build_prompt(
        market_global=market_global,
        fear_greed=fear_greed,
        safety=safety,
        news=news,
        portfolio_data=portfolio_data,
        candidate_data=candidate_data,
    )

    # --------------------------------
    # 10. Gemini analysis
    # --------------------------------

    print("Sending data to Gemini...")

    analysis = gemini_analyze(
        prompt
    )

    print(
        "Gemini analysis completed."
    )

    # --------------------------------
    # 11. Save state
    # --------------------------------

    state = load_state()

    state["last_run"] = iso_now()
    state["market_safety"] = safety
    state["fear_greed"] = fear_greed
    state["last_analysis"] = analysis

    save_state(state)

    # --------------------------------
    # 12. Telegram
    # --------------------------------

    messages = format_bot_message(
        analysis,
        safety,
        fear_greed
    )

    for message in messages:
        telegram_send(message)

        # malé oneskorenie kvôli Telegram API
        time.sleep(1)

    print(
        "Crypto bot V5.2 finished successfully."
    )


# =========================
# RUN
# =========================

if __name__ == "__main__":
    main()
