import os
import json
import time
import math
import re
import urllib.request
import urllib.parse
import urllib.error
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo


# ============================================================
# CONFIG
# ============================================================

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
COINGECKO_API_KEY = os.getenv("COINGECKO_API_KEY", "")

GEMINI_MODEL = "gemini-3.8-flash"

STATE_FILE = "bot_state.json"

BRATISLAVA_TZ = ZoneInfo("Europe/Bratislava")
NEW_YORK_TZ = ZoneInfo("America/New_York")

# Coins already held by user.
PORTFOLIO = {
    "AAVE": "aave",
    "TAO": "bittensor",
    "FET": "artificial-superintelligence-alliance",
    "SOL": "solana",
    "ONDO": "ondo-finance",
    "RENDER": "render-token",
}

BTC_ID = "bitcoin"
ETH_ID = "ethereum"

# Candidate universe for NEW COIN discovery.
# Gemini is allowed to reject all of them and return NO TRADE.
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

RSS_URLS = [
    "https://cointelegraph.com/rss",
]

REQUEST_TIMEOUT = 25


# ============================================================
# GENERIC HTTP
# ============================================================

def http_get(url, headers=None, retries=3):
    headers = headers or {}

    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as response:
                return response.read()

        except Exception as e:
            if attempt == retries - 1:
                raise

            time.sleep(2 * (attempt + 1))

    return None


def http_json(url, headers=None):
    data = http_get(url, headers=headers)
    return json.loads(data.decode("utf-8"))


# ============================================================
# COINGECKO
# ============================================================

def cg_headers():
    headers = {
        "accept": "application/json",
    }

    if COINGECKO_API_KEY:
        headers["x-cg-demo-api-key"] = COINGECKO_API_KEY

    return headers


def coingecko_simple_prices(ids):
    joined = ",".join(ids)

    url = (
        "https://api.coingecko.com/api/v3/simple/price?"
        + urllib.parse.urlencode({
            "ids": joined,
            "vs_currencies": "usd",
            "include_market_cap": "true",
            "include_24hr_vol": "true",
            "include_24hr_change": "true",
        })
    )

    return http_json(url, cg_headers())


def coingecko_global():
    url = "https://api.coingecko.com/api/v3/global"
    return http_json(url, cg_headers())


def coingecko_market_chart(coin_id, days):
    params = {
        "vs_currency": "usd",
        "days": str(days),
        "precision": "full",
    }

    url = (
        f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart?"
        + urllib.parse.urlencode(params)
    )

    return http_json(url, cg_headers())


# ============================================================
# ALTERNATIVE.ME
# ============================================================

def get_fear_greed():
    try:
        data = http_json("https://api.alternative.me/fng/?limit=1")

        item = data["data"][0]

        return {
            "value": int(item["value"]),
            "classification": item["value_classification"],
        }

    except Exception:
        return {
            "value": None,
            "classification": "UNKNOWN",
        }


# ============================================================
# COINTELEGRAPH RSS
# ============================================================

def get_news():
    articles = []

    for rss_url in RSS_URLS:
        try:
            raw = http_get(rss_url)
            root = ET.fromstring(raw)

            for item in root.findall(".//item")[:12]:
                title = item.findtext("title") or ""
                link = item.findtext("link") or ""
                pub_date = item.findtext("pubDate") or ""

                if title:
                    articles.append({
                        "title": title.strip(),
                        "url": link.strip(),
                        "date": pub_date.strip(),
                    })

        except Exception as e:
            print("RSS error:", e)

    return articles[:20]


# ============================================================
# INDICATORS
# ============================================================

def ema(values, period):
    if len(values) < period:
        return None

    multiplier = 2 / (period + 1)

    result = sum(values[:period]) / period

    for price in values[period:]:
        result = (price - result) * multiplier + result

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
    result = 100 - (100 / (1 + rs))

    for i in range(period, len(gains)):
        avg_gain = ((avg_gain * (period - 1)) + gains[i]) / period
        avg_loss = ((avg_loss * (period - 1)) + losses[i]) / period

        if avg_loss == 0:
            result = 100.0
        else:
            rs = avg_gain / avg_loss
            result = 100 - (100 / (1 + rs))

    return result


def macd(values, fast=12, slow=26, signal=9):
    if len(values) < slow + signal:
        return None, None, None

    fast_values = []
    slow_values = []

    for i in range(len(values)):
        fast_values.append(ema(values[:i + 1], fast))
        slow_values.append(ema(values[:i + 1], slow))

    macd_line = []

    for f, s in zip(fast_values, slow_values):
        if f is not None and s is not None:
            macd_line.append(f - s)

    if len(macd_line) < signal:
        return None, None, None

    signal_line = ema(macd_line, signal)

    if signal_line is None:
        return None, None, None

    histogram = macd_line[-1] - signal_line

    return macd_line[-1], signal_line, histogram


def pct_change(old, new):
    if old is None or old == 0:
        return None

    return ((new / old) - 1) * 100


# ============================================================
# TIME SERIES
# ============================================================

def parse_series(chart):
    prices = [
        (int(x[0]), float(x[1]))
        for x in chart.get("prices", [])
    ]

    volumes = [
        (int(x[0]), float(x[1]))
        for x in chart.get("total_volumes", [])
    ]

    return prices, volumes


def aggregate_4h(prices, volumes):
    """
    Convert CoinGecko intraday observations into real 4H candles.

    OHLC:
      O = first price
      H = highest
      L = lowest
      C = last

    Volume is summed inside the 4H bucket.
    """

    buckets = {}

    volume_map = {}

    for ts, vol in volumes:
        bucket = (ts // (4 * 60 * 60 * 1000)) * (4 * 60 * 60 * 1000)
        volume_map.setdefault(bucket, 0)
        volume_map[bucket] += vol

    for ts, price in prices:
        bucket = (ts // (4 * 60 * 60 * 1000)) * (4 * 60 * 60 * 1000)

        if bucket not in buckets:
            buckets[bucket] = {
                "open": price,
                "high": price,
                "low": price,
                "close": price,
            }
        else:
            buckets[bucket]["high"] = max(
                buckets[bucket]["high"], price
            )

            buckets[bucket]["low"] = min(
                buckets[bucket]["low"], price
            )

            buckets[bucket]["close"] = price

    candles = []

    for ts in sorted(buckets.keys()):
        candle = buckets[ts]

        candle["timestamp"] = ts
        candle["volume"] = volume_map.get(ts, 0)

        candles.append(candle)

    return candles


def daily_series(prices, volumes):
    """
    Build daily candles from timestamped observations.
    """

    buckets = {}

    volume_map = {}

    for ts, vol in volumes:
        dt = datetime.fromtimestamp(
            ts / 1000,
            tz=timezone.utc
        )

        day = dt.strftime("%Y-%m-%d")

        volume_map.setdefault(day, 0)
        volume_map[day] += vol

    for ts, price in prices:
        dt = datetime.fromtimestamp(
            ts / 1000,
            tz=timezone.utc
        )

        day = dt.strftime("%Y-%m-%d")

        if day not in buckets:
            buckets[day] = {
                "open": price,
                "high": price,
                "low": price,
                "close": price,
            }
        else:
            buckets[day]["high"] = max(
                buckets[day]["high"], price
            )

            buckets[day]["low"] = min(
                buckets[day]["low"], price
            )

            buckets[day]["close"] = price

    candles = []

    for day in sorted(buckets.keys()):
        candle = buckets[day]
        candle["date"] = day
        candle["volume"] = volume_map.get(day, 0)

        candles.append(candle)

    return candles


def timestamp_change(prices, hours):
    """
    Calculate true percentage change using timestamps,
    instead of assuming array positions equal time.
    """

    if not prices:
        return None

    latest_ts, latest_price = prices[-1]

    target_ts = latest_ts - hours * 60 * 60 * 1000

    previous = None

    for ts, price in prices:
        if ts <= target_ts:
            previous = price
        else:
            break

    if previous is None:
        return None

    return pct_change(previous, latest_price)


# ============================================================
# COIN TECHNICAL ANALYSIS
# ============================================================

def technical_analysis(chart_4h, chart_1d):
    prices4, volumes4 = parse_series(chart_4h)
    prices1, volumes1 = parse_series(chart_1d)

    candles4 = aggregate_4h(prices4, volumes4)
    candles1 = daily_series(prices1, volumes1)

    closes4 = [x["close"] for x in candles4]
    closes1 = [x["close"] for x in candles1]

    if len(closes4) < 60:
        raise ValueError("Not enough 4H data")

    if len(closes1) < 50:
        raise ValueError("Not enough 1D data")

    macd4, signal4, hist4 = macd(closes4)
    macd1, signal1, hist1 = macd(closes1)

    volume4 = [x["volume"] for x in candles4]

    recent_volume = (
        sum(volume4[-6:]) / 6
        if len(volume4) >= 6
        else None
    )

    previous_volume = (
        sum(volume4[-18:-6]) / 12
        if len(volume4) >= 18
        else None
    )

    volume_ratio = None

    if recent_volume and previous_volume:
        volume_ratio = recent_volume / previous_volume

    result = {
        "4h": {
            "rsi": rsi(closes4, 14),
            "ema20": ema(closes4, 20),
            "ema50": ema(closes4, 50),
            "ema100": ema(closes4, 100),
            "ema200": ema(closes4, 200),
            "macd": macd4,
            "macd_signal": signal4,
            "macd_histogram": hist4,
            "volume_ratio": volume_ratio,
            "last_close": closes4[-1],
            "recent_high": max(closes4[-18:]),
            "recent_low": min(closes4[-18:]),
        },

        "1d": {
            "rsi": rsi(closes1, 14),
            "ema20": ema(closes1, 20),
            "ema50": ema(closes1, 50),
            "ema100": ema(closes1, 100),
            "ema200": ema(closes1, 200),
            "macd": macd1,
            "macd_signal": signal1,
            "macd_histogram": hist1,
            "last_close": closes1[-1],
            "recent_high": max(closes1[-30:]),
            "recent_low": min(closes1[-30:]),
        },

        "data_points": {
            "4h": len(closes4),
            "1d": len(closes1),
        },
    }

    return result


# ============================================================
# MARKET SAFETY
# ============================================================

def market_safety(global_data, btc_technical, btc_price_data, fear_greed):
    market_cap_change = (
        global_data
        .get("data", {})
        .get("market_cap_change_percentage_24h_usd")
    )

    btc_change = btc_price_data.get("bitcoin", {}).get(
        "usd_24h_change"
    )

    btc_rsi = btc_technical["4h"]["rsi"]

    warnings = 0
    reasons = []

    if btc_change is not None and btc_change <= -4:
        warnings += 2
        reasons.append("BTC -4% alebo menej za 24H")

    elif btc_change is not None and btc_change <= -2.5:
        warnings += 1
        reasons.append("BTC výrazne klesá")

    if (
        market_cap_change is not None
        and market_cap_change <= -4
    ):
        warnings += 2
        reasons.append("celková kapitalizácia prudko klesá")

    elif (
        market_cap_change is not None
        and market_cap_change <= -2
    ):
        warnings += 1
        reasons.append("celkový kryptotrh oslabuje")

    if btc_rsi is not None and btc_rsi < 25:
        warnings += 1
        reasons.append("BTC 4H RSI je extrémne prepredané")

    fg = fear_greed.get("value")

    if fg is not None and fg <= 20:
        warnings += 1
        reasons.append("Fear & Greed je v extrémnom strachu")

    if warnings >= 4:
        state = "CRITICAL"

    elif warnings >= 2:
        state = "WARNING"

    else:
        state = "NORMAL"

    return {
        "state": state,
        "score": warnings,
        "reasons": reasons,
    }


# ============================================================
# GEMINI SCHEMA
# ============================================================

def gemini_schema():
    return {
        "type": "object",
        "properties": {
            "market_summary": {
                "type": "string"
            },
            "portfolio_action": {
                "type": "string"
            },
            "market_regime": {
                "type": "string"
            },
            "coins": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "symbol": {"type": "string"},
                        "action": {"type": "string"},
                        "what_to_do_now": {"type": "string"},
                        "price": {"type": "number"},
                        "buy_zone_low": {"type": "number"},
                        "buy_zone_high": {"type": "number"},
                        "strong_buy_low": {"type": "number"},
                        "strong_buy_high": {"type": "number"},
                        "invalidation": {"type": "number"},
                        "tp1": {"type": "number"},
                        "tp2": {"type": "number"},
                        "rr": {"type": "number"},
                        "opportunity_score": {"type": "integer"},
                        "entry_score": {"type": "integer"},
                        "confidence": {"type": "integer"},
                        "risk": {"type": "string"},
                        "reversal_24_72h": {"type": "integer"},
                        "continuation_24_72h": {"type": "integer"},
                        "reversal_7_14d": {"type": "integer"},
                        "continuation_7_14d": {"type": "integer"},
                        "expected_scenario": {"type": "string"},
                        "reversal_conditions": {"type": "string"},
                        "cancel_conditions": {"type": "string"},
                        "technical": {"type": "string"},
                        "fundamental": {"type": "string"},
                        "reason": {"type": "string"},
                        "sources": {
                            "type": "array",
                            "items": {
                                "type": "string"
                            }
                        }
                    },
                    "required": [
                        "symbol",
                        "action",
                        "what_to_do_now",
                        "price",
                        "buy_zone_low",
                        "buy_zone_high",
                        "strong_buy_low",
                        "strong_buy_high",
                        "invalidation",
                        "tp1",
                        "tp2",
                        "rr",
                        "opportunity_score",
                        "entry_score",
                        "confidence",
                        "risk",
                        "reversal_24_72h",
                        "continuation_24_72h",
                        "reversal_7_14d",
                        "continuation_7_14d",
                        "expected_scenario",
                        "reversal_conditions",
                        "cancel_conditions",
                        "technical",
                        "fundamental",
                        "reason",
                        "sources"
                    ]
                }
            },
            "new_coin": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string"},
                    "action": {"type": "string"},
                    "what_to_do_now": {"type": "string"},
                    "price": {"type": "number"},
                    "buy_zone_low": {"type": "number"},
                    "buy_zone_high": {"type": "number"},
                    "strong_buy_low": {"type": "number"},
                    "strong_buy_high": {"type": "number"},
                    "invalidation": {"type": "number"},
                    "tp1": {"type": "number"},
                    "tp2": {"type": "number"},
                    "rr": {"type": "number"},
                    "opportunity_score": {"type": "integer"},
                    "entry_score": {"type": "integer"},
                    "confidence": {"type": "integer"},
                    "risk": {"type": "string"},
                    "reversal_24_72h": {"type": "integer"},
                    "continuation_24_72h": {"type": "integer"},
                    "reversal_7_14d": {"type": "integer"},
                    "continuation_7_14d": {"type": "integer"},
                    "expected_scenario": {"type": "string"},
                    "reversal_conditions": {"type": "string"},
                    "cancel_conditions": {"type": "string"},
                    "technical": {"type": "string"},
                    "fundamental": {"type": "string"},
                    "reason": {"type": "string"},
                    "sources": {
                        "type": "array",
                        "items": {
                            "type": "string"
                        }
                    }
                },
                "required": [
                    "symbol",
                    "action",
                    "what_to_do_now",
                    "price",
                    "buy_zone_low",
                    "buy_zone_high",
                    "strong_buy_low",
                    "strong_buy_high",
                    "invalidation",
                    "tp1",
                    "tp2",
                    "rr",
                    "opportunity_score",
                    "entry_score",
                    "confidence",
                    "risk",
                    "reversal_24_72h",
                    "continuation_24_72h",
                    "reversal_7_14d",
                    "continuation_7_14d",
                    "expected_scenario",
                    "reversal_conditions",
                    "cancel_conditions",
                    "technical",
                    "fundamental",
                    "reason",
                    "sources"
                ]
            }
        },
        "required": [
            "market_summary",
            "portfolio_action",
            "market_regime",
            "coins",
            "new_coin"
        ]
    }


# ============================================================
# GEMINI
# ============================================================

def gemini_analyze(prompt):
    """
    Gemini 3.8 Flash via Interactions API.

    IMPORTANT:
    - thinking_level only
    - NO temperature
    - NO top_p
    - NO top_k
    - NO thinking_budget
    """

    url = "https://generativelanguage.googleapis.com/v1beta/interactions"

    payload = {
        "model": GEMINI_MODEL,

        "input": prompt,

        "tools": [
            {
                "type": "google_search"
            }
        ],

        "generation_config": {
            "thinking_level": "high"
        },

        "response_format": {
            "type": "text",
            "mime_type": "application/json",
            "schema": gemini_schema()
        }
    }

    body = json.dumps(payload).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": GEMINI_API_KEY,
        },
        method="POST",
    )

    raw = http_get_request(req)

    response = json.loads(raw.decode("utf-8"))

    output = response.get("output_text")

    if not output:
        raise RuntimeError(
            "Gemini returned no output: "
            + json.dumps(response)[:3000]
        )

    try:
        return json.loads(output)

    except json.JSONDecodeError:
        match = re.search(
            r"\{.*\}",
            output,
            flags=re.DOTALL
        )

        if match:
            return json.loads(match.group(0))

        raise RuntimeError(
            "Gemini output is not valid JSON:\n"
            + output[:3000]
        )


def http_get_request(req, retries=3):
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(
                req,
                timeout=REQUEST_TIMEOUT
            ) as response:
                return response.read()

        except Exception as e:
            if attempt == retries - 1:
                raise

            time.sleep(3 * (attempt + 1))


# ============================================================
# VALIDATION / SAFETY
# ============================================================

VALID_ACTIONS = {
    "BUY NOW",
    "BUY LIMIT",
    "ADD",
    "HOLD",
    "WAIT",
    "REDUCE NOW",
    "TAKE PROFIT NOW",
    "EXIT NOW",
    "NO TRADE",
}


def validate_coin(item, safety_state):
    action = str(item.get("action", "WAIT")).upper().strip()

    if action not in VALID_ACTIONS:
        action = "WAIT"

    item["action"] = action

    price = float(item.get("price", 0) or 0)
    buy_low = float(item.get("buy_zone_low", 0) or 0)
    buy_high = float(item.get("buy_zone_high", 0) or 0)
    strong_low = float(item.get("strong_buy_low", 0) or 0)
    strong_high = float(item.get("strong_buy_high", 0) or 0)
    invalidation = float(item.get("invalidation", 0) or 0)
    tp1 = float(item.get("tp1", 0) or 0)
    tp2 = float(item.get("tp2", 0) or 0)

    # Safety rule:
    # During CRITICAL market conditions, new purchases are blocked.
    if safety_state == "CRITICAL":
        if action in {"BUY NOW", "BUY LIMIT", "ADD"}:
            item["action"] = "WAIT"
            item["what_to_do_now"] = (
                "Nekupovať teraz. Trh je v CRITICAL režime; "
                "čakať na stabilizáciu BTC a trhu."
            )

        if item.get("risk", "").upper() == "NÍZKE":
            item["risk"] = "VYSOKÉ"

    elif safety_state == "WARNING":
        if item.get("risk", "").upper() == "NÍZKE":
            item["risk"] = "STREDNÉ"

        if action == "BUY NOW":
            item["action"] = "BUY LIMIT"
            item["what_to_do_now"] = (
                "Nenaháňať cenu. Preferovať nákup iba v uvedenej BUY ZÓNE."
            )

    # Basic price sanity.
    if price <= 0:
        item["action"] = "WAIT"

    # Buy zone should be ordered.
    if buy_low > buy_high:
        item["buy_zone_low"], item["buy_zone_high"] = (
            buy_high,
            buy_low,
        )

    if strong_low > strong_high:
        item["strong_buy_low"], item["strong_buy_high"] = (
            strong_high,
            strong_low,
        )

    # Stop/invalidation should normally be below entry zones.
    # If Gemini produces contradictory levels, don't let the bot
    # produce a misleading executable recommendation.
    if (
        invalidation > 0
        and buy_low > 0
        and invalidation >= buy_low
    ):
        item["action"] = "WAIT"
        item["what_to_do_now"] = (
            "WAIT — cenové úrovne sú momentálne nejednoznačné. "
            "Nevstupovať, kým sa nepotvrdí support."
        )

    # TP order.
    if tp1 > 0 and tp2 > 0 and tp2 < tp1:
        item["tp1"], item["tp2"] = tp2, tp1

    # Probabilities must add up to 100.
    r1 = int(item.get("reversal_24_72h", 50))
    c1 = int(item.get("continuation_24_72h", 50))

    total1 = r1 + c1

    if total1 != 100:
        if total1 <= 0:
            r1 = c1 = 50
        else:
            r1 = round(r1 / total1 * 100)
            c1 = 100 - r1

    item["reversal_24_72h"] = r1
    item["continuation_24_72h"] = c1

    r2 = int(item.get("reversal_7_14d", 50))
    c2 = int(item.get("continuation_7_14d", 50))

    total2 = r2 + c2

    if total2 != 100:
        if total2 <= 0:
            r2 = c2 = 50
        else:
            r2 = round(r2 / total2 * 100)
            c2 = 100 - r2

    item["reversal_7_14d"] = r2
    item["continuation_7_14d"] = c2

    # Force probability language to match scenario.
    if c1 > r1:
        item["expected_scenario"] = (
            "Hlavný scenár: krátkodobo skôr pokračovanie poklesu; "
            "obrat až po potvrdení supportu."
        )

    return item


# ============================================================
# PROMPT
# ============================================================

def build_prompt(market_data):
    return f"""
Si hlavný analytik kryptomenového investičného bota.

Dátum a čas:
{market_data["now"]}

Tvojou úlohou NIE JE nútiť ma obchodovať.
Tvojou úlohou je povedať mi, čo má zmysel urobiť TERAZ.

PORTFÓLIO:
AAVE, TAO, FET, SOL, ONDO, RENDER

BTC a ETH sú iba benchmark / trhový kontext.

==================================================
HLAVNÉ PRAVIDLÁ
==================================================

1. PRIORITA JE OCHRANA KAPITÁLU.
2. Nenaháňaj cenu.
3. RSI < 30 NIE JE automatický BUY signál.
4. BUY NOW používaj iba vtedy, keď je technický vstup potvrdený.
5. Ak trh prudko padá, preferuj WAIT alebo BUY LIMIT.
6. Ak nie je dostatočná výhoda, použi NO TRADE.
7. Nikdy nevymýšľaj čísla, likvidácie, partnerstvá, regulácie ani
   inštitucionálny záujem.
8. Ak niečo nevieš overiť, napíš to.
9. Pri fundamentálnych tvrdeniach používaj Google Search.
10. Pri aktuálnych udalostiach preferuj posledné dni/týždne.
11. Staré správy nepoužívaj ako dôkaz aktuálnej situácie.
12. Modelové pravdepodobnosti sú ODHAD, nie štatistická istota.
13. Pri širokom market selloffe nesmieš označiť altcoin ako
    NÍZKE RIZIKO iba preto, že má dobrý fundament.
14. Ak je Market Safety CRITICAL, nové BUY odporúčania sú zakázané.
15. Ak je Market Safety WARNING, BUY NOW používaj veľmi výnimočne.
16. Používateľ preferuje BUY LIMIT a pullback, nie market order.

==================================================
ROZHODOVACÍ SYSTÉM
==================================================

Používaj iba tieto akcie:

BUY NOW
BUY LIMIT
ADD
HOLD
WAIT
REDUCE NOW
TAKE PROFIT NOW
EXIT NOW
NO TRADE

Každá minca musí začínať jasnou vetou:

"ČO MÁM TERAZ UROBIŤ"

Príklad:
"Nekupovať teraz. Čakať na $110–115."

==================================================
CENOVÉ ÚROVNE
==================================================

BUY ZONE:
normálna vstupná zóna.

STRONG BUY:
hlbší pullback s lepším R:R, ale iba ak sa support
a širší trh stabilizujú.

INVALIDATION:
cena / technická podmienka, pri ktorej prestáva platiť
bullish vstupný scenár.

TP1:
prvý realistický cieľ.

TP2:
druhý cieľ.

R:R:
musí matematicky dávať zmysel.

Nevytváraj nezmyselnú kombináciu:
BUY ZONE nad INVALIDATION tak, že stop je nad vstupom.

==================================================
VSTUPNÁ STRATÉGIA
==================================================

Ak je BUY LIMIT alebo WAIT, vysvetli:

- čo musí cena urobiť
- kde sa má čakať
- čo musí potvrdiť BTC
- čo zruší vstup

Preferuj postupné vstupy.

Napríklad:
25 % prvý vstup
35 % druhý vstup
40 % silný pullback

ALE toto rozdelenie nepoužív automaticky.
Použi ho iba ak dáva zmysel vzhľadom na riziko.

==================================================
4H VS 1D
==================================================

4H používaj na timing.

1D používaj na hlavný trend.

Ak je:
4H bearish + 1D bullish
=> často WAIT / BUY LIMIT.

Ak je:
4H oversold + 1D bearish
=> NEKUPUJ iba preto, že RSI je nízke.

Ak je:
4H bullish + 1D bullish
=> BUY NOW môže byť možné, ak nie je trh WARNING/CRITICAL
a vstup nie je príliš ďaleko od supportu.

==================================================
MARKET SAFETY
==================================================

Aktuálny stav:
{market_data["market_safety"]}

Dôvody:
{json.dumps(market_data["market_safety_reasons"], ensure_ascii=False)}

==================================================
TRH
==================================================

{json.dumps(market_data["global"], ensure_ascii=False)}

Fear & Greed:
{json.dumps(market_data["fear_greed"], ensure_ascii=False)}

BTC:
{json.dumps(market_data["btc"], ensure_ascii=False)}

==================================================
COINY
==================================================

{json.dumps(market_data["coins"], ensure_ascii=False)}

==================================================
NEWS
==================================================

{json.dumps(market_data["news"], ensure_ascii=False)}

==================================================
NOVÝ COIN
==================================================

Vyber maximálne JEDEN nový coin mimo portfólia.

Ak nie je lepší než existujúce pozície:
NEW COIN = NO TRADE

Neodporúčaj nový coin iba preto, aby bol report zaujímavejší.

==================================================
DÔLEŽITÉ
==================================================

Pri každom coine uveď:

- action
- čo mám teraz urobiť
- cena
- BUY ZONE
- STRONG BUY
- INVALIDATION
- TP1
- TP2
- R:R
- Opportunity score 0–100
- Entry score 0–100
- Confidence 0–100
- Risk
- 24–72h reversal %
- 24–72h continuation %
- 7–14d reversal %
- 7–14d continuation %
- hlavný scenár
- podmienky obratu
- podmienky zrušenia scenára
- technika
- fundament
- dôvod rozhodnutia
- zdroje

ZDROJE:
Pri každom aktuálnom fundamentálnom alebo news tvrdení uveď
URL zdroja.

Ak nemáš spoľahlivý zdroj, tvrdenie vynechaj.

Nevymýšľaj zdroje.

Výstup musí byť iba JSON podľa poskytnutej schémy.
"""


# ============================================================
# TELEGRAM
# ============================================================

def telegram_send(text):
    url = (
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    )

    # Telegram limit is around 4096 chars.
    chunks = []

    while len(text) > 3900:
        cut = text.rfind("\n", 0, 3900)

        if cut < 1000:
            cut = 3900

        chunks.append(text[:cut])
        text = text[cut:]

    chunks.append(text)

    for chunk in chunks:
        data = urllib.parse.urlencode({
            "chat_id": TELEGRAM_CHAT_ID,
            "text": chunk,
        }).encode("utf-8")

        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "Content-Type": "application/x-www-form-urlencoded"
            },
            method="POST",
        )

        http_get_request(req)


# ============================================================
# STATE
# ============================================================

def load_state():
    if not os.path.exists(STATE_FILE):
        return {
            "last_main_analysis": None,
            "last_safety_state": None,
        }

    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)

    except Exception:
        return {
            "last_main_analysis": None,
            "last_safety_state": None,
        }


def save_state(state):
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


# ============================================================
# FORMAT
# ============================================================

def fmt_price(price):
    if price is None:
        return "N/A"

    if price >= 100:
        return f"${price:,.2f}"

    if price >= 1:
        return f"${price:.3f}"

    if price >= 0.1:
        return f"${price:.4f}"

    if price >= 0.01:
        return f"${price:.5f}"

    return f"${price:.8f}"


def format_coin(item, title=None):
    symbol = item["symbol"]

    lines = []

    if title:
        lines.append(title)

    lines.append(
        f"🪙 {symbol} — {item['action']}"
    )

    lines.append(
        f"👉 ČO MÁM TERAZ UROBIŤ: "
        f"{item['what_to_do_now']}"
    )

    lines.append(
        f"💰 Cena: {fmt_price(item['price'])}"
    )

    lines.append(
        f"🟢 BUY ZÓNA: "
        f"{fmt_price(item['buy_zone_low'])} – "
        f"{fmt_price(item['buy_zone_high'])}"
    )

    lines.append(
        f"🔥 STRONG BUY: "
        f"{fmt_price(item['strong_buy_low'])} – "
        f"{fmt_price(item['strong_buy_high'])}"
    )

    lines.append(
        f"🛑 INVALIDÁCIA: "
        f"{fmt_price(item['invalidation'])}"
    )

    lines.append(
        f"🎯 TP1: {fmt_price(item['tp1'])} | "
        f"TP2: {fmt_price(item['tp2'])} | "
        f"R:R {item['rr']:.1f}:1"
    )

    lines.append(
        f"📊 Potenciál {item['opportunity_score']}/100 | "
        f"Vstup {item['entry_score']}/100 | "
        f"Istota {item['confidence']}/100"
    )

    lines.append(
        f"🔄 24–72h: "
        f"OBRAT {item['reversal_24_72h']}% | "
        f"POKRAČOVANIE {item['continuation_24_72h']}%"
    )

    lines.append(
        f"🔄 7–14d: "
        f"OBRAT {item['reversal_7_14d']}% | "
        f"POKRAČOVANIE {item['continuation_7_14d']}%"
    )

    lines.append(
        f"⚠️ Riziko: {item['risk']}"
    )

    lines.append(
        f"📌 Scenár: {item['expected_scenario']}"
    )

    lines.append(
        f"🔄 Obrat nastane ak: "
        f"{item['reversal_conditions']}"
    )

    lines.append(
        f"❌ Scenár ruším ak: "
        f"{item['cancel_conditions']}"
    )

    lines.append(
        f"📈 Technika: {item['technical']}"
    )

    lines.append(
        f"🧠 Fundament: {item['fundamental']}"
    )

    lines.append(
        f"💡 Dôvod: {item['reason']}"
    )

    if item.get("sources"):
        lines.append(
            "🔎 Zdroje:\n" +
            "\n".join(item["sources"][:4])
        )

    return "\n".join(lines)


# ============================================================
# MAIN DATA COLLECTION
# ============================================================

def collect_coin(coin_id, symbol, simple_prices):
    print("Collecting:", symbol)

    current = simple_prices.get(coin_id, {})

    # 90 days for intraday / 4H.
    chart_4h = coingecko_market_chart(
        coin_id,
        90
    )

    # 365 days for daily trend / EMA200.
    chart_1d = coingecko_market_chart(
        coin_id,
        365
    )

    technical = technical_analysis(
        chart_4h,
        chart_1d
    )

    prices4, _ = parse_series(chart_4h)

    result = {
        "symbol": symbol,
        "coin_id": coin_id,
        "price": current.get("usd"),
        "market_cap": current.get("usd_market_cap"),
        "volume_24h": current.get("usd_24h_vol"),
        "change_24h": current.get("usd_24h_change"),

        "change_24h_timestamp_based": timestamp_change(
            prices4,
            24
        ),

        "change_7d_timestamp_based": timestamp_change(
            prices4,
            24 * 7
        ),

        "technical": technical,
    }

    return result


# ============================================================
# RUN
# ============================================================

def main():

    if not GEMINI_API_KEY:
        raise RuntimeError("Missing GEMINI_API_KEY")

    if not TELEGRAM_TOKEN:
        raise RuntimeError("Missing TELEGRAM_TOKEN")

    if not TELEGRAM_CHAT_ID:
        raise RuntimeError("Missing TELEGRAM_CHAT_ID")

    now = datetime.now(timezone.utc)

    now_bratislava = now.astimezone(
        BRATISLAVA_TZ
    )

    print(
        "Crypto bot V5.1:",
        now_bratislava.isoformat()
    )

    # --------------------------------------------------------
    # Current prices
    # --------------------------------------------------------

    all_ids = list(PORTFOLIO.values())

    all_ids += [
        BTC_ID,
        ETH_ID,
    ]

    for candidate in CANDIDATES:
        if candidate not in all_ids:
            all_ids.append(candidate)

    simple_prices = coingecko_simple_prices(
        all_ids
    )

    # --------------------------------------------------------
    # Global
    # --------------------------------------------------------

    global_data = coingecko_global()

    fear_greed = get_fear_greed()

    news = get_news()

    # --------------------------------------------------------
    # BTC technical
    # --------------------------------------------------------

    btc_chart_4h = coingecko_market_chart(
        BTC_ID,
        90
    )

    btc_chart_1d = coingecko_market_chart(
        BTC_ID,
        365
    )

    btc_technical = technical_analysis(
        btc_chart_4h,
        btc_chart_1d
    )

    btc_price_data = simple_prices

    # --------------------------------------------------------
    # Market safety
    # --------------------------------------------------------

    safety = market_safety(
        global_data,
        btc_technical,
        btc_price_data,
        fear_greed
    )

    print("MARKET SAFETY:", safety)

    # --------------------------------------------------------
    # Portfolio coins
    # --------------------------------------------------------

    coins = []

    for symbol, coin_id in PORTFOLIO.items():

        try:
            coin = collect_coin(
                coin_id,
                symbol,
                simple_prices
            )

            coins.append(coin)

        except Exception as e:
            print(
                f"ERROR collecting {symbol}:",
                e
            )

    # --------------------------------------------------------
    # Candidate data
    # --------------------------------------------------------

    candidate_data = []

    for coin_id in CANDIDATES:

        try:
            # Determine symbol from CoinGecko result where possible.
            # Gemini will verify exact ticker through search.
            coin = collect_coin(
                coin_id,
                coin_id.upper(),
                simple_prices
            )

            candidate_data.append(coin)

        except Exception as e:
            print(
                f"Candidate error {coin_id}:",
                e
            )

    # --------------------------------------------------------
    # Prepare Gemini input
    # --------------------------------------------------------

    btc_snapshot = {
        "price": simple_prices.get(
            BTC_ID,
            {}
        ).get("usd"),

        "change_24h": simple_prices.get(
            BTC_ID,
            {}
        ).get("usd_24h_change"),

        "technical": btc_technical,
    }

    market_data = {
        "now": now_bratislava.isoformat(),

        "market_safety": safety["state"],

        "market_safety_reasons":
            safety["reasons"],

        "global":
            global_data.get("data", {}),

        "fear_greed":
            fear_greed,

        "btc":
            btc_snapshot,

        "coins":
            coins,

        "candidate_coins":
            candidate_data,

        "news":
            news,
    }

    # Candidate coins are supplied separately so Gemini can
    # compare them with the portfolio.
    market_data["coins"] = {
        "portfolio": coins,
        "candidates": candidate_data,
    }

    prompt = build_prompt(
        market_data
    )

    # --------------------------------------------------------
    # Gemini
    # --------------------------------------------------------

    analysis = gemini_analyze(
        prompt
    )

    # --------------------------------------------------------
    # Validate
    # --------------------------------------------------------

    validated_coins = []

    for item in analysis.get("coins", []):

        validated = validate_coin(
            item,
            safety["state"]
        )

        validated_coins.append(
            validated
        )

    analysis["coins"] = validated_coins

    if analysis.get("new_coin"):
        analysis["new_coin"] = validate_coin(
            analysis["new_coin"],
            safety["state"]
        )

    # --------------------------------------------------------
    # Telegram
    # --------------------------------------------------------

    telegram = []

    telegram.append(
        "🤖 CRYPTO AI BOT V5.1"
    )

    telegram.append(
        f"🕐 {now_bratislava.strftime('%d.%m.%Y %H:%M')}"
    )

    telegram.append(
        f"🛡️ MARKET SAFETY: {safety['state']}"
    )

    if safety["reasons"]:
        telegram.append(
            "⚠️ " +
            "; ".join(safety["reasons"])
        )

    telegram.append("")

    telegram.append(
        f"🌍 {analysis.get('market_regime', 'N/A')}"
    )

    telegram.append(
        f"🎯 PORTFÓLIO: "
        f"{analysis.get('portfolio_action', 'N/A')}"
    )

    telegram.append("")

    telegram.append(
        "📌 " +
        analysis.get(
            "market_summary",
            ""
        )
    )

    telegram.append("")

    for item in analysis["coins"]:
        telegram.append(
            format_coin(item)
        )

        telegram.append(
            "\n" + ("─" * 35) + "\n"
        )

    # New coin
    new_coin = analysis.get(
        "new_coin"
    )

    if new_coin:
        telegram.append(
            format_coin(
                new_coin,
                title="🆕 NOVÝ COIN"
            )
        )

    message = "\n".join(
        telegram
    )

    telegram_send(
        message
    )

    # --------------------------------------------------------
    # Save state
    # --------------------------------------------------------

    state = load_state()

    state["last_main_analysis"] = (
        now_bratislava.isoformat()
    )

    state["last_safety_state"] = (
        safety["state"]
    )

    state["last_analysis"] = analysis

    save_state(state)

    print("DONE")


if __name__ == "__main__":
    main()
