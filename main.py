import os
import json
import math
import time
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

# ============================================================
# CRYPTO AI BOT V4
# Gemini 3.8 Flash + Google Search + Structured JSON
#
# RUN_MODE:
#   analysis = 3x daily main analysis
#   safety   = safety monitor / emergency alert
# ============================================================

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
COINGECKO_API_KEY = os.getenv("COINGECKO_API_KEY", "")

GEMINI_MODEL = "gemini-3.8-flash"

RUN_MODE = os.getenv("RUN_MODE", "analysis").lower()

STATE_FILE = "bot_state.json"

LOCAL_TZ = ZoneInfo("Europe/Bratislava")

# ------------------------------------------------------------
# PORTFOLIO
# ------------------------------------------------------------

HELD_COINS = {
    "aave": {
        "symbol": "AAVE",
        "name": "Aave",
    },
    "bittensor": {
        "symbol": "TAO",
        "name": "Bittensor",
    },
    "fetch-ai": {
        "symbol": "FET",
        "name": "Artificial Superintelligence Alliance",
    },
    "solana": {
        "symbol": "SOL",
        "name": "Solana",
    },
    "ondo-finance": {
        "symbol": "ONDO",
        "name": "Ondo",
    },
    "render-token": {
        "symbol": "RENDER",
        "name": "Render",
    },
}

# BTC + ETH are market-regime references.
MARKET_CONTEXT = {
    "bitcoin": "BTC",
    "ethereum": "ETH",
}

ALL_TRACKED_IDS = list(HELD_COINS.keys()) + list(MARKET_CONTEXT.keys())

# ------------------------------------------------------------
# HTTP
# ------------------------------------------------------------

def http_get(url, headers=None, timeout=30):
    headers = headers or {}

    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "CryptoAI-Bot/4.0",
            **headers,
        },
    )

    last_error = None

    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))

        except Exception as e:
            last_error = e

            if attempt < 3:
                time.sleep(2 ** attempt)

    raise last_error


def http_post_json(url, payload, headers=None, timeout=90):
    headers = headers or {}

    body = json.dumps(payload).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "User-Agent": "CryptoAI-Bot/4.0",
            **headers,
        },
    )

    last_error = None

    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))

        except Exception as e:
            last_error = e

            if attempt < 2:
                time.sleep(3 * (attempt + 1))

    raise last_error


# ------------------------------------------------------------
# COINGECKO
# ------------------------------------------------------------

def cg_headers():
    if COINGECKO_API_KEY:
        return {
            "x-cg-demo-api-key": COINGECKO_API_KEY
        }

    return {}


def cg_get(path, params=None):
    base = "https://api.coingecko.com/api/v3"

    params = params or {}

    url = base + path

    if params:
        url += "?" + urllib.parse.urlencode(params)

    return http_get(url, headers=cg_headers())


# ------------------------------------------------------------
# TECHNICAL INDICATORS
# ------------------------------------------------------------

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

    for i in range(period, len(gains)):
        avg_gain = ((avg_gain * (period - 1)) + gains[i]) / period
        avg_loss = ((avg_loss * (period - 1)) + losses[i]) / period

    if avg_loss == 0:
        return 100

    rs = avg_gain / avg_loss

    return 100 - (100 / (1 + rs))


def macd(values):
    if len(values) < 35:
        return None, None, None

    ema12_values = []

    multiplier12 = 2 / 13
    current12 = sum(values[:12]) / 12

    for price in values[12:]:
        current12 = (price - current12) * multiplier12 + current12
        ema12_values.append(current12)

    ema26_values = []

    multiplier26 = 2 / 27
    current26 = sum(values[:26]) / 26

    for price in values[26:]:
        current26 = (price - current26) * multiplier26 + current26
        ema26_values.append(current26)

    # Align approximately by using the later series.
    min_len = min(len(ema12_values), len(ema26_values))

    macd_values = []

    for i in range(min_len):
        macd_values.append(
            ema12_values[-min_len + i] -
            ema26_values[-min_len + i]
        )

    if len(macd_values) < 9:
        return None, None, None

    signal = ema(macd_values, 9)

    if signal is None:
        return None, None, None

    current_macd = macd_values[-1]

    return current_macd, signal, current_macd - signal


def atr(highs, lows, closes, period=14):
    if len(closes) < period + 1:
        return None

    true_ranges = []

    for i in range(1, len(closes)):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )

        true_ranges.append(tr)

    return sum(true_ranges[-period:]) / period


def safe_round(value, decimals=4):
    if value is None:
        return None

    return round(value, decimals)


# ------------------------------------------------------------
# MARKET CHART / VOLUME
# ------------------------------------------------------------

def get_market_chart(coin_id, days=30):
    return cg_get(
        f"/coins/{coin_id}/market_chart",
        {
            "vs_currency": "usd",
            "days": days,
        },
    )


def extract_series(chart):
    prices = [
        float(x[1])
        for x in chart.get("prices", [])
    ]

    volumes = [
        float(x[1])
        for x in chart.get("total_volumes", [])
    ]

    return prices, volumes


def calculate_volume_pressure(prices, volumes):
    """
    This is NOT true buy/sell volume.
    It is a sell-pressure proxy based on:
      price direction
      volume expansion
      recent volume vs baseline
    """

    if len(prices) < 8 or len(volumes) < 8:
        return {
            "label": "UNKNOWN",
            "score": 0,
            "volume_change_pct": None,
            "price_change_pct": None,
        }

    current_price = prices[-1]
    previous_price = prices[-2]

    price_change = (
        (current_price / previous_price) - 1
    ) * 100

    recent_volumes = volumes[-6:-1]

    if not recent_volumes:
        return {
            "label": "UNKNOWN",
            "score": 0,
            "volume_change_pct": None,
            "price_change_pct": price_change,
        }

    baseline_volume = sum(recent_volumes) / len(recent_volumes)

    current_volume = volumes[-1]

    if baseline_volume <= 0:
        volume_change = 0
    else:
        volume_change = (
            (current_volume / baseline_volume) - 1
        ) * 100

    score = 0
    label = "NEUTRAL"

    # Strong price decline + volume expansion
    if price_change <= -3 and volume_change >= 50:
        score = 90
        label = "VERY_HIGH_SELL_PRESSURE"

    elif price_change <= -2 and volume_change >= 30:
        score = 75
        label = "HIGH_SELL_PRESSURE"

    elif price_change <= -1 and volume_change >= 20:
        score = 60
        label = "ELEVATED_SELL_PRESSURE"

    elif price_change >= 2 and volume_change >= 50:
        score = -75
        label = "STRONG_BUYING_PRESSURE_PROXY"

    elif price_change >= 1 and volume_change >= 30:
        score = -50
        label = "BUYING_PRESSURE_PROXY"

    return {
        "label": label,
        "score": score,
        "volume_change_pct": safe_round(volume_change, 1),
        "price_change_pct": safe_round(price_change, 2),
    }


# ------------------------------------------------------------
# SUPPORT / RESISTANCE
# ------------------------------------------------------------

def support_resistance(closes):
    if len(closes) < 20:
        return None, None

    recent = closes[-30:]

    support = min(recent)
    resistance = max(recent)

    current = closes[-1]

    # More useful local levels:
    local_lows = []
    local_highs = []

    for i in range(2, len(recent) - 2):
        if (
            recent[i] <= recent[i - 1]
            and recent[i] <= recent[i + 1]
        ):
            local_lows.append(recent[i])

        if (
            recent[i] >= recent[i - 1]
            and recent[i] >= recent[i + 1]
        ):
            local_highs.append(recent[i])

    lower_supports = [
        x for x in local_lows
        if x < current
    ]

    higher_resistances = [
        x for x in local_highs
        if x > current
    ]

    if lower_supports:
        support = max(lower_supports)

    if higher_resistances:
        resistance = min(higher_resistances)

    return support, resistance


# ------------------------------------------------------------
# COIN ANALYSIS DATA
# ------------------------------------------------------------

def build_coin_data(coin_id, market_row):
    chart = get_market_chart(coin_id, days=30)

    prices, volumes = extract_series(chart)

    if len(prices) < 50:
        raise ValueError(f"Not enough chart data for {coin_id}")

    current = prices[-1]

    ema20 = ema(prices, 20)
    ema50 = ema(prices, 50)
    ema200 = ema(prices, 200)

    rsi14 = rsi(prices, 14)

    macd_value, macd_signal, macd_hist = macd(prices)

    # Since 30 days may not always provide 200 points,
    # EMA200 is optional.
    atr14 = None

    if len(prices) >= 15:
        # Market chart is not OHLC, so approximate ATR from
        # price movements. This is deliberately labelled proxy.
        ranges = []

        for i in range(1, len(prices)):
            ranges.append(
                abs(prices[i] - prices[i - 1])
            )

        if len(ranges) >= 14:
            atr14 = sum(ranges[-14:]) / 14

    support, resistance = support_resistance(prices)

    volume_pressure = calculate_volume_pressure(
        prices,
        volumes
    )

    price_24h = market_row.get("price_change_percentage_24h")
    price_7d = market_row.get("price_change_percentage_7d_in_currency", {}).get("usd")
    price_30d = market_row.get("price_change_percentage_30d_in_currency", {}).get("usd")

    trend = "NEUTRAL"

    if ema20 and ema50:
        if current > ema20 > ema50:
            trend = "BULLISH"

        elif current < ema20 < ema50:
            trend = "BEARISH"

        else:
            trend = "MIXED"

    macd_state = "UNKNOWN"

    if macd_value is not None and macd_signal is not None:
        if macd_value > macd_signal:
            macd_state = "BULLISH"

        else:
            macd_state = "BEARISH"

    rsi_state = "UNKNOWN"

    if rsi14 is not None:
        if rsi14 >= 70:
            rsi_state = "OVERBOUGHT"

        elif rsi14 <= 30:
            rsi_state = "OVERSOLD"

        elif rsi14 >= 55:
            rsi_state = "BULLISH"

        elif rsi14 <= 45:
            rsi_state = "BEARISH"

        else:
            rsi_state = "NEUTRAL"

    return {
        "id": coin_id,
        "symbol": market_row.get("symbol", "").upper(),
        "name": market_row.get("name"),

        "price": current,

        "market_cap": market_row.get("market_cap"),
        "volume_24h": market_row.get("total_volume"),

        "price_change_24h_pct": price_24h,
        "price_change_7d_pct": price_7d,
        "price_change_30d_pct": price_30d,

        "ema20": safe_round(ema20, 6),
        "ema50": safe_round(ema50, 6),
        "ema200": safe_round(ema200, 6),

        "rsi14": safe_round(rsi14, 2),

        "macd": safe_round(macd_value, 8),
        "macd_signal": safe_round(macd_signal, 8),
        "macd_histogram": safe_round(macd_hist, 8),

        "atr14_proxy": safe_round(atr14, 6),

        "support": safe_round(support, 6),
        "resistance": safe_round(resistance, 6),

        "trend": trend,
        "macd_state": macd_state,
        "rsi_state": rsi_state,

        "volume_pressure": volume_pressure,
    }


# ------------------------------------------------------------
# MARKET DATA
# ------------------------------------------------------------

def get_global_market():
    return cg_get("/global")


def get_fear_greed():
    url = "https://api.alternative.me/fng/?limit=1"

    try:
        data = http_get(url)

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


def get_market_rows():
    ids = ",".join(ALL_TRACKED_IDS)

    return cg_get(
        "/coins/markets",
        {
            "vs_currency": "usd",
            "ids": ids,
            "order": "market_cap_desc",
            "sparkline": "false",
            "price_change_percentage": "24h,7d,30d",
        },
    )


# ------------------------------------------------------------
# NEW COIN SCANNER
# ------------------------------------------------------------

def get_top_market_candidates():
    """
    Pull a wider market universe.
    Gemini decides whether any coin has a genuinely attractive
    fundamental + technical opportunity.
    """

    try:
        rows = cg_get(
            "/coins/markets",
            {
                "vs_currency": "usd",
                "order": "market_cap_desc",
                "per_page": 100,
                "page": 1,
                "sparkline": "true",
                "price_change_percentage": "24h,7d,30d",
            },
        )

        candidates = []

        held_ids = set(HELD_COINS.keys())

        for row in rows:
            coin_id = row.get("id")

            if coin_id in held_ids:
                continue

            market_cap = row.get("market_cap") or 0
            volume = row.get("total_volume") or 0

            # Avoid tiny illiquid coins.
            if market_cap < 200_000_000:
                continue

            if volume < 10_000_000:
                continue

            candidates.append({
                "id": coin_id,
                "symbol": row.get("symbol", "").upper(),
                "name": row.get("name"),
                "price": row.get("current_price"),
                "market_cap": market_cap,
                "volume_24h": volume,
                "change_24h": row.get(
                    "price_change_percentage_24h"
                ),
                "change_7d": row.get(
                    "price_change_percentage_7d_in_currency",
                    {}
                ).get("usd"),
                "change_30d": row.get(
                    "price_change_percentage_30d_in_currency",
                    {}
                ).get("usd"),
            })

        return candidates[:60]

    except Exception:
        return []


# ------------------------------------------------------------
# COINTELEGRAPH RSS
# ------------------------------------------------------------

def get_news_rss(limit=12):
    url = (
        "https://cointelegraph.com/rss"
    )

    try:
        raw = urllib.request.urlopen(
            urllib.request.Request(
                url,
                headers={
                    "User-Agent": "CryptoAI-Bot/4.0"
                },
            ),
            timeout=20,
        ).read()

        root = ET.fromstring(raw)

        items = []

        for item in root.findall(".//item")[:limit]:
            title = item.findtext("title")
            link = item.findtext("link")
            pub_date = item.findtext("pubDate")

            if title:
                items.append({
                    "title": title,
                    "link": link,
                    "published": pub_date,
                })

        return items

    except Exception:
        return []


# ------------------------------------------------------------
# STATE
# ------------------------------------------------------------

def load_state():
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)

    except Exception:
        return {}


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
            indent=2,
        )


# ------------------------------------------------------------
# GEMINI JSON SCHEMA
# ------------------------------------------------------------

COIN_RESULT_SCHEMA = {
    "type": "object",
    "properties": {
        "symbol": {
            "type": "string"
        },
        "status": {
            "type": "string",
            "enum": [
                "NEW BUY",
                "ADD",
                "HOLD",
                "WAIT",
                "REDUCE",
                "TAKE PROFIT",
                "EXIT",
                "NO TRADE",
            ],
        },
        "opportunity_score": {
            "type": "integer"
        },
        "execution_score": {
            "type": "integer"
        },
        "confidence": {
            "type": "integer"
        },
        "technical_score": {
            "type": "integer"
        },
        "fundamental_score": {
            "type": "integer"
        },
        "fundamental_confidence": {
            "type": "integer"
        },
        "entry": {
            "type": ["number", "null"]
        },
        "stop": {
            "type": ["number", "null"]
        },
        "tp1": {
            "type": ["number", "null"]
        },
        "tp2": {
            "type": ["number", "null"]
        },
        "thesis": {
            "type": "string"
        },
        "fundamental_facts": {
            "type": "array",
            "items": {
                "type": "string"
            }
        },
        "sources": {
            "type": "array",
            "items": {
                "type": "string"
            }
        },
    },
    "required": [
        "symbol",
        "status",
        "opportunity_score",
        "execution_score",
        "confidence",
        "technical_score",
        "fundamental_score",
        "fundamental_confidence",
        "entry",
        "stop",
        "tp1",
        "tp2",
        "thesis",
        "fundamental_facts",
        "sources",
    ],
}


ANALYSIS_SCHEMA = {
    "type": "object",
    "properties": {
        "market_regime": {
            "type": "string",
            "enum": [
                "BULLISH",
                "NEUTRAL",
                "BEARISH",
                "CRITICAL",
            ],
        },
        "market_summary": {
            "type": "string"
        },
        "risk_level": {
            "type": "string",
            "enum": [
                "LOW",
                "MEDIUM",
                "HIGH",
                "CRITICAL",
            ],
        },
        "coins": {
            "type": "array",
            "items": COIN_RESULT_SCHEMA,
        },
        "new_coin": {
            "type": ["object", "null"],
            "properties": {
                "symbol": {"type": "string"},
                "name": {"type": "string"},
                "opportunity_score": {"type": "integer"},
                "execution_score": {"type": "integer"},
                "confidence": {"type": "integer"},
                "reason": {"type": "string"},
                "entry": {"type": ["number", "null"]},
                "stop": {"type": ["number", "null"]},
                "tp1": {"type": ["number", "null"]},
                "tp2": {"type": ["number", "null"]},
                "sources": {
                    "type": "array",
                    "items": {"type": "string"},
                },
            },
            "required": [
                "symbol",
                "name",
                "opportunity_score",
                "execution_score",
                "confidence",
                "reason",
                "entry",
                "stop",
                "tp1",
                "tp2",
                "sources",
            ],
        },
        "important_changes": {
            "type": "array",
            "items": {
                "type": "string"
            },
        },
    },
    "required": [
        "market_regime",
        "market_summary",
        "risk_level",
        "coins",
        "new_coin",
        "important_changes",
    ],
}


# ------------------------------------------------------------
# GEMINI
# ------------------------------------------------------------

def gemini_generate(prompt, schema):
    url = (
        "https://generativelanguage.googleapis.com/"
        f"v1beta/models/{GEMINI_MODEL}:generateContent"
    )

    payload = {
        "contents": [
            {
                "parts": [
                    {
                        "text": prompt
                    }
                ]
            }
        ],

        "tools": [
            {
                "google_search": {}
            }
        ],

        "generationConfig": {
            "temperature": 0.2,
            "responseFormat": {
                "text": {
                    "mimeType": "application/json",
                    "schema": schema,
                }
            },
        },
    }

    response = http_post_json(
        url,
        payload,
        headers={
            "x-goog-api-key": GEMINI_API_KEY,
        },
        timeout=120,
    )

    try:
        text = (
            response["candidates"][0]
            ["content"]["parts"][0]["text"]
        )

        return json.loads(text)

    except Exception:
        print(
            "Gemini raw response:",
            json.dumps(
                response,
                ensure_ascii=False,
                indent=2,
            )[:10000],
        )

        raise


# ------------------------------------------------------------
# R:R VALIDATION
# ------------------------------------------------------------

def calculate_rr(entry, stop, tp1):
    if not entry or not stop or not tp1:
        return None

    risk = entry - stop
    reward = tp1 - entry

    if risk <= 0:
        return None

    return reward / risk


def validate_trade(coin):
    status = coin.get("status")

    if status not in ["NEW BUY", "ADD"]:
        return coin

    entry = coin.get("entry")
    stop = coin.get("stop")
    tp1 = coin.get("tp1")

    rr = calculate_rr(
        entry,
        stop,
        tp1,
    )

    coin["rr"] = rr

    # No valid setup = no BUY
    if rr is None:
        coin["status"] = "WAIT"
        coin["validation"] = (
            "BUY/ADD blocked: incomplete setup"
        )

        return coin

    # Minimum R:R
    if rr < 2.0:
        coin["status"] = "WAIT"
        coin["validation"] = (
            f"BUY/ADD blocked: R:R {rr:.2f} < 2.0"
        )

    else:
        coin["validation"] = (
            f"R:R validated: {rr:.2f}"
        )

    return coin


# ------------------------------------------------------------
# MAIN ANALYSIS
# ------------------------------------------------------------

def run_analysis():
    print("Running MAIN ANALYSIS")

    global_market = get_global_market()
    fear_greed = get_fear_greed()
    market_rows = get_market_rows()

    market_by_id = {
        row["id"]: row
        for row in market_rows
    }

    coin_data = {}

    for coin_id in HELD_COINS:
        row = market_by_id.get(coin_id)

        if not row:
            continue

        try:
            coin_data[coin_id] = build_coin_data(
                coin_id,
                row
            )
        except Exception as e:
            print(
                f"Coin data error {coin_id}: {e}"
            )

    # BTC / ETH context
    market_context = {}

    for coin_id in MARKET_CONTEXT:
        row = market_by_id.get(coin_id)

        if not row:
            continue

        try:
            market_context[coin_id] = build_coin_data(
                coin_id,
                row
            )
        except Exception as e:
            print(
                f"Market context error {coin_id}: {e}"
            )

    news = get_news_rss()
    candidates = get_top_market_candidates()

    state = load_state()

    prompt = f"""
You are the main crypto investment analyst.

CURRENT TIME:
{datetime.now(timezone.utc).isoformat()}

LOCAL TIME:
{datetime.now(LOCAL_TZ).isoformat()}

IMPORTANT:
You are analyzing a real crypto portfolio.

HELD COINS:
AAVE, TAO, FET, SOL, ONDO, RENDER

BTC and ETH are market-regime references.

You have Google Search available.
USE GOOGLE SEARCH for CURRENT information.

Search and verify important developments from the last 24-72 hours.

Look specifically for:
- major crypto market news
- regulation
- ETF developments
- institutional adoption
- protocol upgrades
- partnerships
- hacks/exploits
- token unlocks
- tokenomics
- governance
- large ecosystem developments
- macro events
- Fed / rates / inflation
- geopolitical events affecting risk assets
- important coin-specific developments

Do NOT invent fundamentals.

If reliable current information is unavailable,
reduce FUNDAMENTAL CONFIDENCE.

========================
MARKET DATA
========================

GLOBAL:
{json.dumps(global_market, ensure_ascii=False)}

FEAR & GREED:
{json.dumps(fear_greed, ensure_ascii=False)}

BTC / ETH:
{json.dumps(market_context, ensure_ascii=False)}

========================
HELD COINS
========================

{json.dumps(coin_data, ensure_ascii=False)}

========================
COINTELEGRAPH RSS
========================

{json.dumps(news, ensure_ascii=False)}

========================
NEW COIN UNIVERSE
========================

These are candidates only.
Do not automatically recommend one.

{json.dumps(candidates, ensure_ascii=False)}

========================
SCORING
========================

Opportunity Score = 0-100%.

It answers:
"How attractive is this coin overall?"

Execution Score = 0-100%.

It answers:
"How good is the setup RIGHT NOW?"

Example:
Opportunity 92%
Execution 55%
=> excellent asset but poor entry.
Usually HOLD/WAIT.

Technical Score:
0-100.

Fundamental Score:
0-100.

Fundamental Confidence:
0-100.

Confidence:
How confident are you in the complete conclusion.

========================
IMPORTANT
========================

Do NOT invent support/resistance.

Use the supplied Python technical values.

Do NOT invent volume direction.

The supplied volume pressure is only a PROXY.
Do not call it true buy/sell volume.

For every coin:
- interpret technical data
- interpret current fundamentals
- explain the most important catalyst/risk
- decide status

Statuses:
NEW BUY
ADD
HOLD
WAIT
REDUCE
TAKE PROFIT
EXIT
NO TRADE

========================
TRADE SETUPS
========================

Only provide Entry/Stop/TP1/TP2 for NEW BUY or ADD.

For BUY/ADD:
- entry must make technical sense
- stop must be below entry
- TP1 must be above entry
- R:R must ideally be >= 2.0

Python will independently validate R:R.

Never force a BUY.

WAIT is better than a bad trade.

========================
NEW COIN
========================

Search for ONE new coin outside the current portfolio
only if there is a genuinely strong opportunity.

It should have:
- strong fundamental catalyst
- sufficient liquidity
- credible project
- attractive valuation OR exceptional growth
- technical setup
- asymmetric upside

Do NOT recommend a random small-cap.

If nothing qualifies:
new_coin = null.

========================
OUTPUT
========================

Return ONLY the required JSON.

No markdown.
No commentary outside JSON.
"""

    result = gemini_generate(
        prompt,
        ANALYSIS_SCHEMA
    )

    # Python validation
    for coin in result.get("coins", []):
        validate_trade(coin)

    # State
    new_state = {
        "timestamp_utc": datetime.now(
            timezone.utc
        ).isoformat(),

        "market_regime": result.get(
            "market_regime"
        ),

        "fear_greed": fear_greed,

        "coin_data": coin_data,

        "analysis": result,
    }

    save_state(new_state)

    message = format_analysis_message(
        result,
        coin_data,
        fear_greed,
    )

    send_telegram(message)


# ------------------------------------------------------------
# SAFETY MONITOR
# ------------------------------------------------------------

def run_safety_monitor():
    print("Running SAFETY MONITOR")

    market_rows = get_market_rows()

    market_by_id = {
        row["id"]: row
        for row in market_rows
    }

    safety_data = {}

    for coin_id in HELD_COINS:
        row = market_by_id.get(coin_id)

        if not row:
            continue

        try:
            data = build_coin_data(
                coin_id,
                row
            )

            safety_data[
                data["symbol"]
            ] = data

        except Exception as e:
            print(
                f"Safety error {coin_id}: {e}"
            )

    # BTC is critical to overall safety.
    btc_row = market_by_id.get("bitcoin")

    if btc_row:
        try:
            btc_data = build_coin_data(
                "bitcoin",
                btc_row
            )

            safety_data["BTC"] = btc_data

        except Exception:
            pass

    # --------------------------------------------------------
    # Calculate market risk
    # --------------------------------------------------------

    critical = []
    warning = []

    for symbol, data in safety_data.items():

        price_change = (
            data.get("volume_pressure", {})
            .get("price_change_pct")
        )

        volume_change = (
            data.get("volume_pressure", {})
            .get("volume_change_pct")
        )

        pressure = (
            data.get("volume_pressure", {})
            .get("label")
        )

        support = data.get("support")
        price = data.get("price")

        support_break = False

        if (
            price is not None
            and support is not None
            and price < support
        ):
            support_break = True

        # CRITICAL
        if (
            pressure == "VERY_HIGH_SELL_PRESSURE"
            or (
                price_change is not None
                and price_change <= -5
            )
            or (
                price_change is not None
                and price_change <= -3
                and volume_change is not None
                and volume_change >= 80
            )
        ):
            critical.append({
                "symbol": symbol,
                "price_change": price_change,
                "volume_change": volume_change,
                "pressure": pressure,
                "support_break": support_break,
            })

        # WARNING
        elif (
            pressure in [
                "HIGH_SELL_PRESSURE",
                "ELEVATED_SELL_PRESSURE",
            ]
            or (
                support_break
                and price_change is not None
                and price_change < 0
            )
        ):
            warning.append({
                "symbol": symbol,
                "price_change": price_change,
                "volume_change": volume_change,
                "pressure": pressure,
                "support_break": support_break,
            })

    # Count broad market weakness.
    altcoin_count = len(HELD_COINS)

    critical_ratio = (
        len([
            x for x in critical
            if x["symbol"] != "BTC"
        ]) / max(altcoin_count, 1)
    )

    warning_ratio = (
        len([
            x for x in warning
            if x["symbol"] != "BTC"
        ]) / max(altcoin_count, 1)
    )

    # CRITICAL if several held coins are collapsing.
    market_level = "NORMAL"

    if (
        len(critical) >= 3
        or critical_ratio >= 0.50
    ):
        market_level = "CRITICAL"

    elif (
        len(critical) >= 1
        or warning_ratio >= 0.50
    ):
        market_level = "WARNING"

    # BTC collapse makes it more serious.
    btc = safety_data.get("BTC")

    if btc:
        btc_change = (
            btc.get("volume_pressure", {})
            .get("price_change_pct")
        )

        if btc_change is not None:
            if btc_change <= -5:
                market_level = "CRITICAL"

            elif btc_change <= -3:
                if market_level == "NORMAL":
                    market_level = "WARNING"

    state = load_state()

    previous_safety = state.get(
        "safety_level",
        "NORMAL"
    )

    # Do not spam Telegram every 15 minutes.
    should_alert = False

    if market_level == "CRITICAL":
        if previous_safety != "CRITICAL":
            should_alert = True

    elif market_level == "WARNING":
        if previous_safety == "NORMAL":
            should_alert = True

    # Update state.
    state["safety_level"] = market_level
    state["safety_updated_utc"] = (
        datetime.now(timezone.utc).isoformat()
    )

    save_state(state)

    if should_alert:
        message = format_safety_message(
            market_level,
            critical,
            warning,
            safety_data,
        )

        send_telegram(message)

    print(
        f"Safety level: {market_level}"
    )


# ------------------------------------------------------------
# TELEGRAM FORMATTING
# ------------------------------------------------------------

def fmt_price(value):
    if value is None:
        return "N/A"

    if value >= 1000:
        return f"${value:,.0f}"

    if value >= 1:
        return f"${value:,.2f}"

    if value >= 0.01:
        return f"${value:,.4f}"

    return f"${value:.8f}"


def format_analysis_message(
    result,
    coin_data,
    fear_greed,
):
    now_local = datetime.now(
        LOCAL_TZ
    ).strftime("%d.%m.%Y %H:%M")

    lines = []

    lines.append(
        f"📊 CRYPTO AI ANALYSIS V4"
    )

    lines.append(
        f"🕒 {now_local} Bratislava"
    )

    lines.append("")

    lines.append(
        f"🌐 MARKET: {result.get('market_regime')}"
    )

    lines.append(
        f"⚠️ RISK: {result.get('risk_level')}"
    )

    lines.append(
        f"😨 Fear & Greed: "
        f"{fear_greed.get('value', 'N/A')}"
        f" ({fear_greed.get('classification', '')})"
    )

    lines.append("")

    lines.append(
        result.get(
            "market_summary",
            ""
        )
    )

    lines.append("")

    for coin in result.get("coins", []):

        symbol = coin.get("symbol")

        raw = None

        for key, value in coin_data.items():
            if value.get("symbol") == symbol:
                raw = value
                break

        lines.append(
            f"━━━━━━━━ {symbol} ━━━━━━━━"
        )

        if raw:
            lines.append(
                f"💰 Price: {fmt_price(raw.get('price'))}"
            )

            lines.append(
                f"📈 EMA20/50/200: "
                f"{fmt_price(raw.get('ema20'))} / "
                f"{fmt_price(raw.get('ema50'))} / "
                f"{fmt_price(raw.get('ema200'))}"
            )

            lines.append(
                f"RSI: {raw.get('rsi14', 'N/A')} "
                f"| MACD: {raw.get('macd_state', 'N/A')}"
            )

            lines.append(
                f"Support: {fmt_price(raw.get('support'))} "
                f"| Resistance: {fmt_price(raw.get('resistance'))}"
            )

            vp = raw.get(
                "volume_pressure",
                {}
            )

            lines.append(
                f"Volume pressure: "
                f"{vp.get('label', 'N/A')} "
                f"({vp.get('volume_change_pct', 'N/A')}%)"
            )

        lines.append("")

        lines.append(
            f"🎯 Status: {coin.get('status')}"
        )

        lines.append(
            f"⭐ Opportunity: "
            f"{coin.get('opportunity_score')}%"
        )

        lines.append(
            f"⚡ Execution: "
            f"{coin.get('execution_score')}%"
        )

        lines.append(
            f"🧠 Confidence: "
            f"{coin.get('confidence')}%"
        )

        lines.append(
            f"📊 Technical: "
            f"{coin.get('technical_score')}%"
        )

        lines.append(
            f"🏦 Fundamental: "
            f"{coin.get('fundamental_score')}%"
            f" "
            f"(confidence "
            f"{coin.get('fundamental_confidence')}%)"
        )

        if coin.get("status") in [
            "NEW BUY",
            "ADD",
        ]:
            lines.append("")

            lines.append(
                f"Entry: {fmt_price(coin.get('entry'))}"
            )

            lines.append(
                f"Stop: {fmt_price(coin.get('stop'))}"
            )

            lines.append(
                f"TP1: {fmt_price(coin.get('tp1'))}"
            )

            lines.append(
                f"TP2: {fmt_price(coin.get('tp2'))}"
            )

            rr = coin.get("rr")

            if rr:
                lines.append(
                    f"R:R: {rr:.2f}"
                )

            if coin.get("validation"):
                lines.append(
                    f"Validation: "
                    f"{coin.get('validation')}"
                )

        lines.append("")

        lines.append(
            f"💡 {coin.get('thesis', '')}"
        )

        facts = coin.get(
            "fundamental_facts",
            []
        )

        if facts:
            lines.append("")
            lines.append("📰 FACTS:")

            for fact in facts[:3]:
                lines.append(
                    f"• {fact}"
                )

    # New coin
    new_coin = result.get("new_coin")

    lines.append("")
    lines.append("━━━━━━━━ NEW OPPORTUNITY ━━━━━━━━")

    if new_coin:
        lines.append(
            f"🆕 {new_coin.get('symbol')} "
            f"({new_coin.get('name')})"
        )

        lines.append(
            f"Opportunity: "
            f"{new_coin.get('opportunity_score')}%"
        )

        lines.append(
            f"Execution: "
            f"{new_coin.get('execution_score')}%"
        )

        lines.append(
            f"Confidence: "
            f"{new_coin.get('confidence')}%"
        )

        lines.append(
            f"Reason: {new_coin.get('reason')}"
        )

    else:
        lines.append(
            "Žiadna nová minca momentálne "
            "nespĺňa požadovaný pomer potenciál/riziko."
        )

    # Important changes
    changes = result.get(
        "important_changes",
        []
    )

    if changes:
        lines.append("")
        lines.append("🔄 ZMENY:")

        for change in changes[:5]:
            lines.append(
                f"• {change}"
            )

    return "\n".join(lines)


def format_safety_message(
    level,
    critical,
    warning,
    safety_data,
):
    lines = []

    if level == "CRITICAL":
        lines.append(
            "🚨🚨 CRYPTO SAFETY ALERT"
        )

        lines.append(
            "🔴 MARKET SAFETY MODE: ON"
        )

        lines.append(
            "⛔ NOVÉ BUY/ADD SIGNÁLY SÚ DOČASNE BLOKOVANÉ"
        )

    else:
        lines.append(
            "⚠️ CRYPTO SAFETY WARNING"
        )

    lines.append("")

    lines.append(
        "Trh vykazuje zvýšený predajný tlak."
    )

    lines.append("")

    affected = critical + warning

    for item in affected:
        symbol = item["symbol"]

        lines.append(
            f"🔻 {symbol}: "
            f"{item['price_change']}% / 1h | "
            f"volume proxy "
            f"{item['volume_change']}% | "
            f"{item['pressure']}"
        )

        if item.get("support_break"):
            lines.append(
                "   ⚠️ SUPPORT PRERAZENÝ"
            )

    lines.append("")

    lines.append(
        "📌 Poznámka: volume pressure je "
        "proxy, nie priamy buy/sell order-flow."
    )

    lines.append("")

    lines.append(
        "Ak sa tlak zvyšuje, pravidelný bot "
        "nebude otvárať nové BUY/ADD pozície."
    )

    return "\n".join(lines)


# ------------------------------------------------------------
# TELEGRAM
# ------------------------------------------------------------

def send_telegram(message):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram secrets missing.")
        return

    url = (
        f"https://api.telegram.org/bot"
        f"{TELEGRAM_TOKEN}/sendMessage"
    )

    # Telegram limit ~4096 chars.
    chunks = []

    while len(message) > 3900:
        cut = message.rfind(
            "\n",
            0,
            3900
        )

        if cut < 1000:
            cut = 3900

        chunks.append(
            message[:cut]
        )

        message = message[cut:]

    chunks.append(message)

    for chunk in chunks:
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": chunk,
        }

        try:
            http_post_json(
                url,
                payload,
                timeout=30,
            )

        except Exception as e:
            print(
                "Telegram error:",
                e
            )


# ------------------------------------------------------------
# MAIN
# ------------------------------------------------------------

def main():

    if not GEMINI_API_KEY:
        raise RuntimeError(
            "Missing GEMINI_API_KEY"
        )

    if RUN_MODE == "safety":
        run_safety_monitor()
        return

    run_analysis()


if __name__ == "__main__":
    main()
