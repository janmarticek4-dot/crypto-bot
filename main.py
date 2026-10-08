import os
import json
import time
import re
import urllib.request
import urllib.parse
import urllib.error
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from google import genai


# ============================================================
# CRYPTO AI BOT V5.4
# ============================================================
# HLAVNÉ ANALÝZY:
#   07:00 Europe/Bratislava
#   09:15 America/New_York  = pred otvorením USA trhu
#   20:00 Europe/Bratislava
#
# MEDZI TÝM:
#   iba bezpečnostný monitoring
#
# SAFETY ALERT:
#   NORMAL -> WARNING
#   WARNING -> CRITICAL
#   alebo výrazné zhoršenie situácie
# ============================================================


# ============================================================
# CONFIG
# ============================================================

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()
COINGECKO_API_KEY = os.getenv("COINGECKO_API_KEY", "").strip()

GEMINI_MODEL = "gemini-3.8-flash"

REQUEST_TIMEOUT = 120
GEMINI_MAX_WAIT = 600
POLL_INTERVAL = 5

STATE_FILE = "bot_state.json"

TZ = ZoneInfo("Europe/Bratislava")
US_TZ = ZoneInfo("America/New_York")


# ============================================================
# MAIN ANALYSIS SCHEDULE
# ============================================================

BRATISLAVA_MAIN_HOURS = {
    7,
    20,
}

# 09:15 New York = 45 min pred otvorením NYSE/Nasdaq
US_PREOPEN_HOUR = 9
US_PREOPEN_MINUTE = 15


# ============================================================
# PORTFOLIO
# ============================================================

PORTFOLIO = {
    "AAVE": "aave",
    "TAO": "bittensor",
    "FET": "fetch-ai",
    "SOL": "solana",
    "ONDO": "ondo-finance",
    "RENDER": "render-token",
}


# ============================================================
# CANDIDATES
# ============================================================

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


# ============================================================
# RSS
# ============================================================

RSS_FEEDS = [
    (
        "CoinTelegraph",
        "https://cointelegraph.com/rss"
    ),
    (
        "CoinDesk",
        "https://www.coindesk.com/arc/outboundfeeds/rss/"
    ),
]


# ============================================================
# BASIC HELPERS
# ============================================================

def now_local():
    return datetime.now(TZ)


def iso_now():
    return now_local().isoformat()


def safe_float(value, default=None):
    try:
        if value is None:
            return default

        if isinstance(value, str):
            value = (
                value
                .replace("$", "")
                .replace(",", "")
                .strip()
            )

        return float(value)

    except Exception:
        return default


def pct_change(old, new):
    if old in (None, 0) or new is None:
        return None

    return ((new - old) / old) * 100.0


def clamp(value, minimum, maximum):
    return max(minimum, min(maximum, value))


# ============================================================
# SCHEDULING
# ============================================================

def manual_analysis_requested():
    value = os.getenv(
        "MANUAL_ANALYSIS",
        ""
    ).strip().lower()

    return value in {
        "true",
        "1",
        "yes",
        "y",
        "on"
    }


def is_main_analysis_time(now=None):
    """
    Hlavná analýza:
      - 07:00 Bratislava
      - 20:00 Bratislava
      - 09:15 New York

    GitHub Action beží každých 15 minút.
    """

    if now is None:
        now = datetime.now(TZ)

    # Manuálne spustenie
    if manual_analysis_requested():
        return True, "MANUAL"

    # Bratislava 07:00 / 20:00
    if (
        now.minute == 0
        and now.hour in BRATISLAVA_MAIN_HOURS
    ):
        return True, f"BRATISLAVA_{now.hour:02d}:00"

    # USA pred-open
    us_now = datetime.now(US_TZ)

    if (
        us_now.hour == US_PREOPEN_HOUR
        and us_now.minute == US_PREOPEN_MINUTE
    ):
        return True, "US_PREOPEN"

    return False, "SAFETY_MONITOR"


# ============================================================
# HTTP
# ============================================================

def http_request(
    req,
    timeout=REQUEST_TIMEOUT,
    retries=4
):

    last_error = None

    for attempt in range(retries):

        try:

            with urllib.request.urlopen(
                req,
                timeout=timeout
            ) as response:

                return response.read()

        except urllib.error.HTTPError as e:

            last_error = e

            print(
                f"HTTP {e.code} "
                f"(pokus {attempt + 1}/{retries}): "
                f"{e.reason}"
            )

            if e.code in {
                400,
                401,
                403,
                404
            }:
                raise

            if attempt < retries - 1:

                wait = 2 ** attempt

                print(
                    f"Retry o {wait} sekúnd..."
                )

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
                f"(pokus {attempt + 1}/{retries}): "
                f"{e}"
            )

            if attempt < retries - 1:

                wait = 2 ** attempt

                print(
                    f"Retry o {wait} sekúnd..."
                )

                time.sleep(wait)

    if last_error:
        raise last_error

    raise RuntimeError(
        "HTTP request zlyhal."
    )


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

    raw = http_request(
        req,
        timeout=timeout,
        retries=retries
    )

    return json.loads(
        raw.decode("utf-8")
    )


# ============================================================
# COINGECKO
# ============================================================

def coingecko_headers():

    headers = {
        "Accept": "application/json",
        "User-Agent": "CryptoAIBot/5.4"
    }

    if COINGECKO_API_KEY:

        headers["x-cg-demo-api-key"] = (
            COINGECKO_API_KEY
        )

    return headers


def coingecko_get(
    endpoint,
    params=None
):

    base = (
        "https://api.coingecko.com/api/v3"
    )

    if params:

        query = urllib.parse.urlencode(
            params
        )

        url = (
            f"{base}/{endpoint}?{query}"
        )

    else:

        url = (
            f"{base}/{endpoint}"
        )

    return http_json(
        url,
        headers=coingecko_headers()
    )


def coingecko_simple_price(ids):

    if not ids:
        return {}

    return coingecko_get(
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


def coingecko_markets(ids):

    if not ids:
        return []

    return coingecko_get(
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


def coingecko_chart(
    coin_id,
    days=90
):

    return coingecko_get(
        f"coins/{coin_id}/market_chart",
        {
            "vs_currency": "usd",
            "days": days,
            "interval": "hourly",
        }
    )


# ============================================================
# CHART DATA
# ============================================================

def closes_from_chart(chart):

    prices = chart.get(
        "prices",
        []
    )

    return [
        {
            "timestamp": p[0],
            "price": safe_float(p[1])
        }
        for p in prices
        if len(p) >= 2
        and safe_float(p[1]) is not None
    ]


def aggregate_candles(
    prices,
    hours=4
):

    if not prices:
        return []

    buckets = {}

    bucket_ms = (
        hours * 60 * 60 * 1000
    )

    for p in prices:

        timestamp = int(
            p["timestamp"]
        )

        price = p["price"]

        bucket = (
            timestamp // bucket_ms
        ) * bucket_ms

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
        buckets[key]
        for key in sorted(
            buckets.keys()
        )
    ]


# ============================================================
# TECHNICAL INDICATORS
# ============================================================

def ema(values, period):

    if not values:
        return []

    if len(values) < period:
        return [None] * len(values)

    result = [None] * len(values)

    sma = (
        sum(values[:period])
        / period
    )

    result[period - 1] = sma

    multiplier = (
        2 / (period + 1)
    )

    previous = sma

    for i in range(
        period,
        len(values)
    ):

        current = (
            (values[i] - previous)
            * multiplier
            + previous
        )

        result[i] = current
        previous = current

    return result


def rsi(
    values,
    period=14
):

    if len(values) < period + 1:
        return None

    gains = []
    losses = []

    for i in range(
        1,
        len(values)
    ):

        change = (
            values[i]
            - values[i - 1]
        )

        gains.append(
            max(change, 0)
        )

        losses.append(
            max(-change, 0)
        )

    avg_gain = (
        sum(gains[:period])
        / period
    )

    avg_loss = (
        sum(losses[:period])
        / period
    )

    if avg_loss == 0:
        return 100.0

    rs = (
        avg_gain
        / avg_loss
    )

    current_rsi = (
        100
        - (
            100
            / (1 + rs)
        )
    )

    for i in range(
        period,
        len(gains)
    ):

        avg_gain = (
            (
                avg_gain
                * (period - 1)
            )
            + gains[i]
        ) / period

        avg_loss = (
            (
                avg_loss
                * (period - 1)
            )
            + losses[i]
        ) / period

        if avg_loss == 0:

            current_rsi = 100.0

        else:

            rs = (
                avg_gain
                / avg_loss
            )

            current_rsi = (
                100
                - (
                    100
                    / (1 + rs)
                )
            )

    return current_rsi


def macd(values):

    if len(values) < 35:

        return {
            "macd": None,
            "signal": None,
            "histogram": None
        }

    ema12 = ema(
        values,
        12
    )

    ema26 = ema(
        values,
        26
    )

    macd_values = []

    for a, b in zip(
        ema12,
        ema26
    ):

        if a is None or b is None:

            macd_values.append(None)

        else:

            macd_values.append(
                a - b
            )

    valid = [
        x
        for x in macd_values
        if x is not None
    ]

    signal_values = ema(
        valid,
        9
    )

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

        histogram = (
            current_macd
            - current_signal
        )

    return {
        "macd": current_macd,
        "signal": current_signal,
        "histogram": histogram
    }


def last_valid(values):

    for value in reversed(values):

        if value is not None:
            return value

    return None


def atr(candles, period=14):

    if len(candles) < period + 1:
        return None

    true_ranges = []

    for i in range(
        1,
        len(candles)
    ):

        current = candles[i]
        previous = candles[i - 1]

        high = current["high"]
        low = current["low"]
        prev_close = previous["close"]

        tr = max(
            high - low,
            abs(high - prev_close),
            abs(low - prev_close)
        )

        true_ranges.append(tr)

    if len(true_ranges) < period:
        return None

    return (
        sum(true_ranges[-period:])
        / period
    )


def recent_support_resistance(
    candles,
    lookback=30
):

    if not candles:
        return {
            "support": None,
            "resistance": None
        }

    recent = candles[-lookback:]

    lows = [
        c["low"]
        for c in recent
        if c.get("low") is not None
    ]

    highs = [
        c["high"]
        for c in recent
        if c.get("high") is not None
    ]

    return {
        "support": min(lows) if lows else None,
        "resistance": max(highs) if highs else None
    }


def technical_summary(candles):

    if not candles:
        return {}

    closes = [
        c["close"]
        for c in candles
        if c.get("close") is not None
    ]

    if not closes:
        return {}

    current = closes[-1]

    ema20 = ema(closes, 20)
    ema50 = ema(closes, 50)
    ema100 = ema(closes, 100)
    ema200 = ema(closes, 200)

    e20 = last_valid(ema20)
    e50 = last_valid(ema50)
    e100 = last_valid(ema100)
    e200 = last_valid(ema200)

    sr = recent_support_resistance(
        candles,
        30
    )

    current_atr = atr(
        candles,
        14
    )

    current_rsi = rsi(
        closes,
        14
    )

    current_macd = macd(
        closes
    )

    return {
        "price": current,

        "ema20": e20,
        "ema50": e50,
        "ema100": e100,
        "ema200": e200,

        "rsi14": current_rsi,

        "macd": current_macd,

        "atr14": current_atr,

        "atr_percent": (
            current_atr / current * 100
            if current_atr is not None
            and current
            else None
        ),

        "support_30_candles": sr["support"],
        "resistance_30_candles": sr["resistance"],

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

        "above_ema100": (
            current > e100
            if e100 is not None
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

    periods = {
        "24h": 6,
        "7d": 42,
        "30d": 180,
    }

    result = {}

    for name, bars in periods.items():

        if len(closes) > bars:

            old = closes[
                -bars - 1
            ]

            result[name] = pct_change(
                old,
                current
            )

    return result


# ============================================================
# COIN DATA
# ============================================================

def collect_coin_data(
    symbol,
    coin_id
):

    print(
        f"Collecting: {symbol}"
    )

    simple = coingecko_simple_price(
        [coin_id]
    )

    current = simple.get(
        coin_id,
        {}
    )

    chart = coingecko_chart(
        coin_id,
        days=90
    )

    prices = closes_from_chart(
        chart
    )

    candles = aggregate_candles(
        prices,
        hours=4
    )

    technical = technical_summary(
        candles
    )

    closes = [
        x["close"]
        for x in candles
    ]

    return {
        "symbol": symbol,
        "coin_id": coin_id,

        "price_usd": current.get(
            "usd"
        ),

        "market_cap": current.get(
            "usd_market_cap"
        ),

        "volume_24h": current.get(
            "usd_24h_vol"
        ),

        "change_24h": current.get(
            "usd_24h_change"
        ),

        "last_updated": current.get(
            "last_updated_at"
        ),

        "technical_4h": technical,

        "returns": recent_returns(
            closes
        ),
    }


# ============================================================
# CANDIDATE SHORTLIST
# ============================================================

def shortlist_candidates():

    print(
        "Shortlisting candidate coins..."
    )

    market_data = coingecko_markets(
        CANDIDATES
    )

    if not market_data:
        return CANDIDATES[:3]

    portfolio_ids = set(
        PORTFOLIO.values()
    )

    filtered = [
        x
        for x in market_data
        if x.get("id")
        not in portfolio_ids
    ]

    filtered = [
        x
        for x in filtered
        if safe_float(
            x.get("market_cap"),
            0
        ) > 100_000_000
    ]

    filtered.sort(
        key=lambda x: (
            safe_float(
                x.get("total_volume"),
                0
            ),
            safe_float(
                x.get("market_cap"),
                0
            )
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


# ============================================================
# MARKET
# ============================================================

def get_market_global():

    return coingecko_get(
        "global"
    )


def get_fear_greed():

    try:

        data = http_json(
            "https://api.alternative.me/fng/?limit=1",
            headers={
                "User-Agent":
                    "CryptoAIBot/5.4"
            }
        )

        item = data["data"][0]

        return {
            "value": int(
                item["value"]
            ),

            "classification":
                item["value_classification"],

            "timestamp":
                item.get("timestamp"),
        }

    except Exception as e:

        print(
            f"Fear & Greed error: {e}"
        )

        return {
            "value": None,
            "classification":
                "UNKNOWN",
            "timestamp": None,
        }


# ============================================================
# MARKET SAFETY
# ============================================================

def market_safety(
    global_data,
    simple_prices
):

    score = 0
    reasons = []

    global_change = None
    btc_change = None

    # --------------------------------------------------------
    # TOTAL MARKET CAP
    # --------------------------------------------------------

    try:

        global_change = safe_float(
            global_data["data"].get(
                "market_cap_change_percentage_24h_usd"
            )
        )

        if global_change is not None:

            if global_change <= -5:

                score += 2

                reasons.append(
                    "celková kapitalizácia prudko klesá"
                )

            elif global_change <= -2:

                score += 1

                reasons.append(
                    "celková kapitalizácia klesá"
                )

    except Exception:
        pass

    # --------------------------------------------------------
    # BTC
    # --------------------------------------------------------

    try:

        btc = simple_prices.get(
            "bitcoin",
            {}
        )

        btc_change = safe_float(
            btc.get(
                "usd_24h_change"
            )
        )

        if btc_change is not None:

            if btc_change <= -7:

                score += 3

                reasons.append(
                    "BTC prudko klesá"
                )

            elif btc_change <= -3:

                score += 2

                reasons.append(
                    "BTC výrazne klesá"
                )

            elif btc_change <= -1.5:

                score += 1

                reasons.append(
                    "BTC klesá"
                )

    except Exception:
        pass

    # --------------------------------------------------------
    # KOMBINOVANÝ TLAK
    # --------------------------------------------------------

    if (
        global_change is not None
        and btc_change is not None
        and global_change <= -2
        and btc_change <= -1.5
    ):

        score += 1

        reasons.append(
            "BTC aj celý kryptotrh klesajú súčasne"
        )

    # --------------------------------------------------------
    # STATE
    # --------------------------------------------------------

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
        "market_cap_change_24h": global_change,
        "btc_change_24h": btc_change,
    }


# ============================================================
# SAFETY ALERT LOGIC
# ============================================================

def should_send_safety_alert(
    current_safety,
    state
):

    current_state = current_safety.get(
        "state",
        "NORMAL"
    )

    current_score = safe_float(
        current_safety.get(
            "score",
            0
        ),
        0
    )

    previous_state = state.get(
        "last_safety_state",
        "NORMAL"
    )

    previous_score = safe_float(
        state.get(
            "last_safety_score",
            0
        ),
        0
    )

    # Ak sme NORMAL, netreba alert
    if current_state == "NORMAL":
        return False, "NORMAL"

    # Pri prechode do WARNING/CRITICAL
    if (
        previous_state == "NORMAL"
        and current_state in {
            "WARNING",
            "CRITICAL"
        }
    ):
        return True, "STATE_CHANGE"

    if (
        previous_state == "WARNING"
        and current_state == "CRITICAL"
    ):
        return True, "STATE_ESCALATION"

    # Ak sa score výrazne zhorší
    if (
        current_score >= previous_score + 2
    ):
        return True, "SCORE_WORSENING"

    # Pri prvom spustení, ak už je trh v CRITICAL
    if (
        previous_state == "NORMAL"
        and current_state == "CRITICAL"
    ):
        return True, "CRITICAL"

    return False, "NO_NEW_ALERT"


def format_safety_alert(
    safety,
    fear_greed
):

    state = safety.get(
        "state",
        "NORMAL"
    )

    score = safety.get(
        "score",
        0
    )

    btc_change = safety.get(
        "btc_change_24h"
    )

    market_change = safety.get(
        "market_cap_change_24h"
    )

    if state == "CRITICAL":

        title = (
            "🚨 CRYPTO AI BOT — "
            "BEZPEČNOSTNÝ ALERT"
        )

        message = (
            "Hrozí výraznejší prepad "
            "alebo pokračovanie korekcie."
        )

    else:

        title = (
            "⚠️ CRYPTO AI BOT — "
            "BEZPEČNOSTNÝ ALERT"
        )

        message = (
            "Trh sa zhoršuje a rastie riziko "
            "väčšej korekcie."
        )

    lines = [
        title,
        "",
        f"🛡 Safety: {state} ({score})",
        message,
        "",
    ]

    if btc_change is not None:

        lines.append(
            f"₿ BTC 24h: {btc_change:+.2f}%"
        )

    if market_change is not None:

        lines.append(
            f"🌐 Market cap 24h: "
            f"{market_change:+.2f}%"
        )

    fg = fear_greed.get(
        "value"
    )

    if fg is not None:

        lines.append(
            f"😱 Fear & Greed: "
            f"{fg}/100 "
            f"({fear_greed.get('classification', '')})"
        )

    reasons = safety.get(
        "reasons",
        []
    )

    if reasons:

        lines.append("")
        lines.append("Dôvod:")

        for reason in reasons[:5]:

            lines.append(
                f"• {reason}"
            )

    lines.extend([
        "",
        "➡️ Zatiaľ neotvárať nové pozície "
        "agresívne.",
        "➡️ Počkať na stabilizáciu BTC "
        "a trhu.",
        "➡️ Hlavná analýza príde v najbližšom "
        "plánovanom termíne.",
    ])

    return "\n".join(lines)


# ============================================================
# RSS
# ============================================================

def get_rss_news():

    headers = {
        "User-Agent": (
            "Mozilla/5.0 "
            "(compatible; CryptoAIBot/5.4)"
        ),
        "Accept": (
            "application/rss+xml,"
            "application/xml,"
            "text/xml,"
            "*/*"
        ),
    }

    all_items = []

    for source_name, url in RSS_FEEDS:

        try:

            print(
                f"RSS: {source_name}"
            )

            req = urllib.request.Request(
                url,
                headers=headers,
                method="GET"
            )

            raw = http_request(
                req,
                timeout=30,
                retries=2
            )

            root = ET.fromstring(
                raw
            )

            count = 0

            for item in root.iter():

                if not item.tag.lower().endswith(
                    "item"
                ):
                    continue

                title = ""
                link = ""
                pub_date = ""

                for child in item:

                    tag = child.tag.lower()

                    if tag.endswith(
                        "title"
                    ):

                        title = (
                            child.text
                            or ""
                        ).strip()

                    elif tag.endswith(
                        "link"
                    ):

                        link = (
                            child.text
                            or ""
                        ).strip()

                    elif tag.endswith(
                        "pubdate"
                    ):

                        pub_date = (
                            child.text
                            or ""
                        ).strip()

                if title:

                    all_items.append({
                        "source":
                            source_name,

                        "title":
                            title,

                        "link":
                            link,

                        "pub_date":
                            pub_date,
                    })

                    count += 1

                if count >= 10:
                    break

            print(
                f"RSS {source_name}: "
                f"{count} článkov"
            )

        except Exception as e:

            print(
                f"RSS error "
                f"{source_name}: {e}"
            )

    return all_items[:20]


# ============================================================
# GEMINI JSON PARSER
# ============================================================

def parse_json_output(text):

    if not text:

        raise RuntimeError(
            "Gemini neposlal výstup."
        )

    text = text.strip()

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

        return json.loads(
            text
        )

    except json.JSONDecodeError:
        pass

    start = text.find("{")
    end = text.rfind("}")

    if start >= 0 and end > start:

        candidate = text[
            start:end + 1
        ]

        try:

            return json.loads(
                candidate
            )

        except json.JSONDecodeError:
            pass

    raise RuntimeError(
        "Gemini output nie je validný JSON:\n"
        + text[:5000]
    )


# ============================================================
# GEMINI
# ============================================================

def gemini_analyze(prompt):

    if not GEMINI_API_KEY:

        raise RuntimeError(
            "GEMINI_API_KEY nie je nastavený."
        )

    print(
        "Spúšťam Gemini background analysis..."
    )

    client = genai.Client(
        api_key=GEMINI_API_KEY
    )

    interaction = client.interactions.create(

        model=GEMINI_MODEL,

        input=prompt,

        background=True,

        tools=[
            {
                "type": "google_search"
            }
        ],

        generation_config={
            "thinking_level": "high"
        },

        store=True,

        timeout=120,
    )

    interaction_id = interaction.id

    print(
        "Gemini interaction ID:",
        interaction_id
    )

    started = time.time()

    while True:

        elapsed = (
            time.time()
            - started
        )

        if elapsed > GEMINI_MAX_WAIT:

            raise TimeoutError(
                "Gemini background analysis "
                "trvá dlhšie ako 10 minút."
            )

        interaction = (
            client.interactions.get(
                id=interaction_id
            )
        )

        status = interaction.status

        print(
            f"Gemini status: "
            f"{status} "
            f"({int(elapsed)}s)"
        )

        if status == "completed":

            output_text = (
                interaction.output_text
            )

            if not output_text:

                raise RuntimeError(
                    "Gemini completed, "
                    "ale output_text je prázdny."
                )

            return parse_json_output(
                output_text
            )

        if status in {
            "failed",
            "cancelled",
            "expired",
            "incomplete"
        }:

            raise RuntimeError(
                "Gemini interaction skončila "
                f"stavom {status}."
            )

        if status == "requires_action":

            raise RuntimeError(
                "Gemini vyžaduje ďalšiu akciu."
            )

        time.sleep(
            POLL_INTERVAL
        )


# ============================================================
# GEMINI PROMPT
# ============================================================

def build_prompt(
    market_global,
    fear_greed,
    safety,
    news,
    portfolio_data,
    candidate_data,
    btc_data
):

    return f"""
You are the main investment intelligence engine
of a crypto trading bot.

==================================================
LANGUAGE
==================================================

All descriptive output MUST be in Slovak.

Crypto symbols and numerical values stay standard.

==================================================
CURRENT TIME
==================================================

Bratislava:
{iso_now()}

==================================================
IMPORTANT USER PREFERENCES
==================================================

Investment horizon:
now through approximately April 2027.

Technical horizon:
hours to several weeks.

The user prefers:
- buying pullbacks
- capital preservation
- asymmetric setups
- clear BUY / WAIT / HOLD decisions
- NO TRADE when setup is weak

The user does NOT want additional APT exposure.

The user already owns:
AAVE
TAO
FET
SOL
ONDO
RENDER

A missed trade is better than a bad trade.

Do NOT recommend APT.

==================================================
CURRENT INFORMATION
==================================================

Use Google Search for CURRENT fundamental/news information.

Do NOT rely on old knowledge for:
- regulation
- ETFs
- institutional adoption
- partnerships
- token unlocks
- tokenomics
- ecosystem activity
- current catalysts
- current market events
- current geopolitical events

==================================================
GLOBAL MARKET
==================================================

{json.dumps(
    market_global,
    ensure_ascii=False,
    indent=2
)}

==================================================
FEAR & GREED
==================================================

{json.dumps(
    fear_greed,
    ensure_ascii=False,
    indent=2
)}

==================================================
MARKET SAFETY
==================================================

{json.dumps(
    safety,
    ensure_ascii=False,
    indent=2
)}

IMPORTANT:
Safety states are ONLY:
NORMAL
WARNING
CRITICAL

Never write SAFE.

If WARNING:
be conservative.

If CRITICAL:
prioritize capital preservation and use NO TRADE
unless there is an exceptionally strong setup.

==================================================
BTC TECHNICAL DATA
==================================================

This data was calculated by Python directly from
CoinGecko 4H price history.

{json.dumps(
    btc_data,
    ensure_ascii=False,
    indent=2
)}

==================================================
RECENT NEWS
==================================================

{json.dumps(
    news,
    ensure_ascii=False,
    indent=2
)}

==================================================
USER PORTFOLIO
==================================================

{json.dumps(
    portfolio_data,
    ensure_ascii=False,
    indent=2
)}

==================================================
NEW COIN CANDIDATES
==================================================

{json.dumps(
    candidate_data,
    ensure_ascii=False,
    indent=2
)}

==================================================
CRITICAL TECHNICAL RULE
==================================================

Technical data such as:

EMA20
EMA50
EMA100
EMA200
RSI
MACD
ATR
support
resistance

has been calculated by Python.

You MUST NOT invent, estimate or hallucinate
technical indicator values.

If you mention EMA, RSI, support, resistance,
MACD or ATR, use ONLY the supplied values.

==================================================
PORTFOLIO ANALYSIS
==================================================

Analyze:

AAVE
TAO
FET
SOL
ONDO
RENDER

For every coin choose exactly one:

BUY NOW
BUY PULLBACK
HOLD
REDUCE
SELL
NO TRADE

Provide:

- current price
- buy zone 1
- buy zone 2
- invalidation
- TP1
- TP2
- risk/reward
- bull probability
- bear probability
- technical score 0-10
- fundamental score 0-10
- short reason in Slovak

==================================================
PRICE LEVEL RULES
==================================================

Do NOT invent arbitrary price levels.

Use:
- actual support
- actual resistance
- EMA
- RSI
- MACD
- ATR
- market structure
- recent volatility
- current trend
- BTC conditions

BUY PULLBACK:
The buy zone should normally be BELOW current price.

BUY NOW:
Only use if current price itself offers a reasonable
risk/reward setup.

BUY zones must make sense relative to invalidation.

For a long setup:

invalidation < buy zone < TP1 < TP2

If this structure does not make sense:
use NO TRADE.

==================================================
RISK/REWARD
==================================================

IMPORTANT:

Python will calculate the final R:R after your answer.

Therefore do NOT try to manipulate the R:R.

Give realistic:
- BUY zone
- invalidation
- TP1
- TP2

The final Telegram R:R will be mathematically
calculated by Python.

Preferred setup:
R:R to TP2 >= 2.0

If R:R is poor:
prefer NO TRADE.

==================================================
PROBABILITIES
==================================================

Bull and bear probabilities must be realistic.

They must sum to 100.

Do NOT automatically give optimistic probabilities.

If MARKET SAFETY = WARNING:
bull probability should normally NOT exceed 65%.

If MARKET SAFETY = CRITICAL:
bull probability should normally NOT exceed 55%.

A high probability requires strong technical
and fundamental evidence.

==================================================
FUNDAMENTALS
==================================================

Consider:

- adoption
- revenue / fees
- TVL where relevant
- developer activity
- institutional adoption
- token utility
- token unlocks
- inflation
- competition
- ecosystem growth
- regulation
- current catalysts
- valuation

Use current Google Search information where needed.

==================================================
NEW COIN
==================================================

Analyze the shortlisted new coins.

Choose AT MOST ONE.

Compare it against the user's existing portfolio.

If an existing coin is a better place for additional
capital:

new_coin_action = NO TRADE

Do NOT recommend APT.

Do NOT recommend a coin merely because theoretical
upside is high.

A new coin must have:

- strong fundamentals
- sufficient liquidity
- reasonable valuation
- strong narrative/catalyst
- reasonable technical entry
- asymmetric upside/downside

If a coin has recently pumped heavily:
prefer BUY PULLBACK.

==================================================
MARKET REGIME
==================================================

Choose one:

bullish
neutral
corrective
bearish
capitulation

==================================================
OUTPUT
==================================================

Return ONLY valid JSON.

Structure:

{{
  "market_regime": "string",
  "market_summary": "string",
  "action": "string",
  "new_coin": "string",
  "new_coin_action": "string",
  "new_coin_reason": "string",

  "coins": [
    {{
      "symbol": "AAVE",
      "action": "string",
      "current_price": 0.0,
      "buy_zone_1": "string",
      "buy_zone_2": "string",
      "invalidation": "string",
      "tp1": "string",
      "tp2": "string",
      "risk_reward": "Python will calculate this",
      "bull_probability": 0,
      "bear_probability": 0,
      "technical_score": 0,
      "fundamental_score": 0,
      "reason": "string"
    }}
  ],

  "best_opportunity": "string",
  "avoid": "string",
  "conditions_to_watch": [
    "string"
  ]
}}

No markdown.
No explanations outside JSON.
"""


# ============================================================
# PRICE PARSING
# ============================================================

def extract_numbers(value):

    if value is None:
        return []

    text = str(value)

    # normalizácia rôznych pomlčiek
    text = (
        text
        .replace("–", "-")
        .replace("—", "-")
        .replace("−", "-")
    )

    matches = re.findall(
        r"(?<!\d)(?:\d+(?:[.,]\d+)?|\.\d+)(?!\d)",
        text
    )

    result = []

    for item in matches:

        item = item.replace(
            ",",
            "."
        )

        try:
            result.append(
                float(item)
            )
        except Exception:
            pass

    return result


def parse_price_level(value):

    numbers = extract_numbers(
        value
    )

    if not numbers:
        return None

    return numbers[0]


def parse_price_range(value):

    numbers = extract_numbers(
        value
    )

    if not numbers:
        return None

    if len(numbers) == 1:

        return (
            numbers[0],
            numbers[0]
        )

    return (
        min(numbers[0], numbers[1]),
        max(numbers[0], numbers[1])
    )


# ============================================================
# R:R CALCULATION
# ============================================================

def calculate_rr(
    buy_zone,
    invalidation,
    tp1,
    tp2
):

    zone = parse_price_range(
        buy_zone
    )

    invalidation_value = (
        parse_price_level(
            invalidation
        )
    )

    tp1_value = parse_price_level(
        tp1
    )

    tp2_value = parse_price_level(
        tp2
    )

    if (
        zone is None
        or invalidation_value is None
        or tp1_value is None
        or tp2_value is None
    ):
        return None

    entry = (
        zone[0] + zone[1]
    ) / 2

    risk = entry - invalidation_value

    reward1 = tp1_value - entry
    reward2 = tp2_value - entry

    if risk <= 0:
        return None

    if reward1 <= 0 or reward2 <= 0:
        return None

    rr1 = reward1 / risk
    rr2 = reward2 / risk

    return {
        "entry": entry,
        "risk": risk,
        "tp1_reward": reward1,
        "tp2_reward": reward2,
        "rr_tp1": rr1,
        "rr_tp2": rr2,
    }


def format_rr(rr):

    if not rr:
        return "N/A"

    return (
        f"1:{rr['rr_tp1']:.1f} / "
        f"1:{rr['rr_tp2']:.1f}"
    )


# ============================================================
# ANALYSIS VALIDATION / CORRECTION
# ============================================================

def validate_and_correct_analysis(
    analysis,
    safety,
    portfolio_data
):

    if not isinstance(
        analysis,
        dict
    ):
        raise RuntimeError(
            "Gemini analysis nie je objekt."
        )

    coins = analysis.get(
        "coins",
        []
    )

    if not isinstance(
        coins,
        list
    ):
        raise RuntimeError(
            "Gemini coins nie je zoznam."
        )

    safety_state = safety.get(
        "state",
        "NORMAL"
    )

    for coin in coins:

        symbol = str(
            coin.get(
                "symbol",
                ""
            )
        ).upper()

        # ----------------------------------------------------
        # PRICE - preferuj CoinGecko
        # ----------------------------------------------------

        if symbol in portfolio_data:

            actual_price = safe_float(
                portfolio_data[symbol].get(
                    "price_usd"
                )
            )

            if actual_price is not None:

                coin["current_price"] = (
                    actual_price
                )

        # ----------------------------------------------------
        # PROBABILITIES
        # ----------------------------------------------------

        bull = safe_float(
            coin.get(
                "bull_probability"
            )
        )

        bear = safe_float(
            coin.get(
                "bear_probability"
            )
        )

        if bull is None:
            bull = 50

        # Ak Gemini omylom vráti 0-1
        if 0 < bull <= 1:
            bull *= 100

        bull = clamp(
            bull,
            0,
            100
        )

        # WARNING / CRITICAL caps
        if safety_state == "WARNING":
            bull = min(
                bull,
                65
            )

        elif safety_state == "CRITICAL":
            bull = min(
                bull,
                55
            )

        bear = 100 - bull

        coin["bull_probability"] = round(
            bull
        )

        coin["bear_probability"] = round(
            bear
        )

        # ----------------------------------------------------
        # SCORES
        # ----------------------------------------------------

        technical = safe_float(
            coin.get(
                "technical_score"
            )
        )

        fundamental = safe_float(
            coin.get(
                "fundamental_score"
            )
        )

        if technical is not None:

            coin["technical_score"] = round(
                clamp(
                    technical,
                    0,
                    10
                ),
                1
            )

        if fundamental is not None:

            coin["fundamental_score"] = round(
                clamp(
                    fundamental,
                    0,
                    10
                ),
                1
            )

        # ----------------------------------------------------
        # R:R
        # ----------------------------------------------------

        rr = calculate_rr(
            coin.get(
                "buy_zone_1"
            ),
            coin.get(
                "invalidation"
            ),
            coin.get(
                "tp1"
            ),
            coin.get(
                "tp2"
            )
        )

        coin["_calculated_rr"] = rr

        coin["risk_reward"] = format_rr(
            rr
        )

        # ----------------------------------------------------
        # PRICE STRUCTURE VALIDATION
        # ----------------------------------------------------

        zone = parse_price_range(
            coin.get(
                "buy_zone_1"
            )
        )

        invalidation = parse_price_level(
            coin.get(
                "invalidation"
            )
        )

        tp1 = parse_price_level(
            coin.get(
                "tp1"
            )
        )

        tp2 = parse_price_level(
            coin.get(
                "tp2"
            )
        )

        current = safe_float(
            coin.get(
                "current_price"
            )
        )

        action = str(
            coin.get(
                "action",
                ""
            )
        ).upper()

        valid_long_structure = (
            zone is not None
            and invalidation is not None
            and tp1 is not None
            and tp2 is not None
            and invalidation < zone[0]
            and tp1 > zone[1]
            and tp2 > tp1
        )

        # ----------------------------------------------------
        # BAD SETUP -> NO TRADE
        # ----------------------------------------------------

        if action in {
            "BUY NOW",
            "BUY PULLBACK"
        }:

            if not valid_long_structure:

                coin["action"] = "NO TRADE"

                coin["reason"] = (
                    str(
                        coin.get(
                            "reason",
                            ""
                        )
                    )
                    + " "
                    "Setup neprešiel matematickou "
                    "kontrolou vstupu, invalidácie "
                    "a profit targetov."
                )

            elif rr is None:

                coin["action"] = "NO TRADE"

                coin["reason"] = (
                    str(
                        coin.get(
                            "reason",
                            ""
                        )
                    )
                    + " "
                    "Nebolo možné spoľahlivo vypočítať R:R."
                )

            elif rr["rr_tp2"] < 1.5:

                coin["action"] = "NO TRADE"

                coin["reason"] = (
                    str(
                        coin.get(
                            "reason",
                            ""
                        )
                    )
                    + " "
                    f"Matematické R:R do TP2 je iba "
                    f"1:{rr['rr_tp2']:.1f}."
                )

        # ----------------------------------------------------
        # BUY PULLBACK MUSÍ BYŤ POD CENOU
        # ----------------------------------------------------

        if (
            coin.get("action") == "BUY PULLBACK"
            and current is not None
            and zone is not None
        ):

            # Ak celý BUY1 leží nad aktuálnou cenou,
            # nie je to pullback.
            if zone[0] >= current:

                coin["action"] = "NO TRADE"

                coin["reason"] = (
                    str(
                        coin.get(
                            "reason",
                            ""
                        )
                    )
                    + " "
                    "BUY PULLBACK zóna nie je pod aktuálnou cenou."
                )

    return analysis


# ============================================================
# TELEGRAM
# ============================================================

def telegram_send(text):

    if not TELEGRAM_TOKEN:

        print(
            "TELEGRAM_TOKEN nie je nastavený."
        )

        return

    if not TELEGRAM_CHAT_ID:

        print(
            "TELEGRAM_CHAT_ID nie je nastavený."
        )

        return

    url = (
        "https://api.telegram.org"
        f"/bot{TELEGRAM_TOKEN}"
        "/sendMessage"
    )

    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
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
            "Content-Type":
                "application/json"
        },
        method="POST"
    )

    try:

        with urllib.request.urlopen(
            req,
            timeout=30
        ) as response:

            print(
                f"Telegram response status: "
                f"{response.status}"
            )

    except Exception as e:

        print(
            f"Telegram error: {e}"
        )


def format_price(value):

    value = safe_float(
        value
    )

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
        "📊 CRYPTO AI BOT — 4H ANALÝZA"
    )

    lines.append(
        f"🕒 {iso_now()}"
    )

    lines.append("")

    lines.append(
        "🌐 Trh: "
        + str(
            analysis.get(
                "market_regime",
                "N/A"
            )
        )
    )

    lines.append(
        "🛡 Safety: "
        + str(
            safety.get(
                "state",
                "N/A"
            )
        )
        + f" ({safety.get('score', 0)})"
    )

    for reason in safety.get(
        "reasons",
        []
    ):

        lines.append(
            " • "
            + str(reason)
        )

    fg = fear_greed.get(
        "value"
    )

    if fg is not None:

        lines.append(
            f"😱 Fear & Greed: "
            f"{fg}/100 "
            f"({fear_greed.get('classification', '')})"
        )

    lines.append("")

    lines.append(
        "🧠 Makro:"
    )

    lines.append(
        str(
            analysis.get(
                "market_summary",
                ""
            )
        )
    )

    lines.append("")

    for coin in analysis.get(
        "coins",
        []
    ):

        symbol = coin.get(
            "symbol",
            "?"
        )

        lines.append(
            f"━━ {symbol} ━━"
        )

        lines.append(
            "Akcia: "
            + str(
                coin.get(
                    "action",
                    "N/A"
                )
            )
        )

        lines.append(
            "Cena: "
            + format_price(
                coin.get(
                    "current_price"
                )
            )
        )

        lines.append(
            "BUY 1: "
            + str(
                coin.get(
                    "buy_zone_1",
                    "N/A"
                )
            )
        )

        lines.append(
            "BUY 2: "
            + str(
                coin.get(
                    "buy_zone_2",
                    "N/A"
                )
            )
        )

        lines.append(
            "Invalidácia: "
            + str(
                coin.get(
                    "invalidation",
                    "N/A"
                )
            )
        )

        lines.append(
            "TP1: "
            + str(
                coin.get(
                    "tp1",
                    "N/A"
                )
            )
        )

        lines.append(
            "TP2: "
            + str(
                coin.get(
                    "tp2",
                    "N/A"
                )
            )
        )

        lines.append(
            "R:R: "
            + str(
                coin.get(
                    "risk_reward",
                    "N/A"
                )
            )
        )

        bull = safe_float(
            coin.get(
                "bull_probability"
            )
        )

        bear = safe_float(
            coin.get(
                "bear_probability"
            )
        )

        if bull is not None:

            lines.append(
                f"🐂 Bull: "
                f"{bull:.0f}%"
                + (
                    f" | 🐻 Bear: "
                    f"{bear:.0f}%"
                    if bear is not None
                    else ""
                )
            )

        lines.append(
            "Technika: "
            + str(
                coin.get(
                    "technical_score",
                    "N/A"
                )
            )
            + "/10"
        )

        lines.append(
            "Fundament: "
            + str(
                coin.get(
                    "fundamental_score",
                    "N/A"
                )
            )
            + "/10"
        )

        lines.append(
            str(
                coin.get(
                    "reason",
                    ""
                )
            )
        )

        lines.append("")

    lines.append(
        "🚀 Najlepšia príležitosť:"
    )

    lines.append(
        str(
            analysis.get(
                "best_opportunity",
                "N/A"
            )
        )
    )

    lines.append("")

    lines.append(
        "🆕 Nová kryptomena: "
        + str(
            analysis.get(
                "new_coin",
                "NO TRADE"
            )
        )
    )

    lines.append(
        "Akcia: "
        + str(
            analysis.get(
                "new_coin_action",
                "NO TRADE"
            )
        )
    )

    lines.append(
        "Dôvod: "
        + str(
            analysis.get(
                "new_coin_reason",
                ""
            )
        )
    )

    lines.append("")

    lines.append(
        "⚠️ Vyhnúť sa: "
        + str(
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
            "👀 Sledovať:"
        )

        for condition in conditions[:6]:

            lines.append(
                "• "
                + str(condition)
            )

    lines.append("")

    lines.append(
        "Nie je to finančné poradenstvo."
    )

    message = "\n".join(
        lines
    )

    if len(message) <= 4000:
        return [message]

    chunks = []
    current = ""

    for line in lines:

        if (
            len(current)
            + len(line)
            + 1
            > 3900
        ):

            chunks.append(
                current
            )

            current = line

        else:

            current += (
                "\n"
                if current
                else ""
            ) + line

    if current:
        chunks.append(
            current
        )

    return chunks


# ============================================================
# STATE
# ============================================================

def load_state():

    if not os.path.exists(
        STATE_FILE
    ):
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


# ============================================================
# SAFETY MONITOR
# ============================================================

def run_safety_monitor():

    print(
        "Running safety monitor..."
    )

    market_global = (
        get_market_global()
    )

    simple_prices = (
        coingecko_simple_price(
            [
                "bitcoin"
            ]
        )
    )

    fear_greed = (
        get_fear_greed()
    )

    safety = market_safety(
        market_global,
        simple_prices
    )

    state = load_state()

    should_alert, reason = (
        should_send_safety_alert(
            safety,
            state
        )
    )

    print(
        "Safety:",
        safety
    )

    print(
        "Safety alert:",
        should_alert,
        reason
    )

    if should_alert:

        alert = format_safety_alert(
            safety,
            fear_greed
        )

        telegram_send(
            alert
        )

        state["last_safety_alert"] = (
            iso_now()
        )

        state["last_safety_alert_reason"] = (
            reason
        )

    state["last_safety_state"] = (
        safety.get(
            "state",
            "NORMAL"
        )
    )

    state["last_safety_score"] = (
        safety.get(
            "score",
            0
        )
    )

    state["last_safety_check"] = (
        iso_now()
    )

    state["market_safety"] = (
        safety
    )

    state["fear_greed"] = (
        fear_greed
    )

    save_state(
        state
    )

    return safety


# ============================================================
# FULL MAIN ANALYSIS
# ============================================================

def run_full_analysis(
    schedule_reason
):

    print(
        "========================================"
    )

    print(
        "FULL ANALYSIS:",
        schedule_reason
    )

    print(
        "========================================"
    )

    # --------------------------------------------------------
    # GLOBAL MARKET
    # --------------------------------------------------------

    print(
        "Collecting global market..."
    )

    market_global = (
        get_market_global()
    )

    # --------------------------------------------------------
    # FEAR & GREED
    # --------------------------------------------------------

    print(
        "Collecting Fear & Greed..."
    )

    fear_greed = (
        get_fear_greed()
    )

    # --------------------------------------------------------
    # SIMPLE PRICES
    # --------------------------------------------------------

    all_ids = list(
        dict.fromkeys(
            list(
                PORTFOLIO.values()
            )
            + CANDIDATES
            + [
                "bitcoin"
            ]
        )
    )

    simple_prices = (
        coingecko_simple_price(
            all_ids
        )
    )

    # --------------------------------------------------------
    # SAFETY
    # --------------------------------------------------------

    safety = market_safety(
        market_global,
        simple_prices
    )

    print(
        "MARKET SAFETY:",
        safety
    )

    # --------------------------------------------------------
    # NEWS
    # --------------------------------------------------------

    news = get_rss_news()

    # --------------------------------------------------------
    # BTC TECHNICAL DATA
    # --------------------------------------------------------

    print(
        "Collecting BTC technical data..."
    )

    btc_data = collect_coin_data(
        "BTC",
        "bitcoin"
    )

    # --------------------------------------------------------
    # PORTFOLIO
    # --------------------------------------------------------

    portfolio_data = {}

    for symbol, coin_id in (
        PORTFOLIO.items()
    ):

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
                "symbol":
                    symbol,

                "coin_id":
                    coin_id,

                "error":
                    str(e),
            }

    # --------------------------------------------------------
    # CANDIDATES
    # --------------------------------------------------------

    shortlist = (
        shortlist_candidates()
    )

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
                f"candidate {coin_id}: "
                f"{e}"
            )

            candidate_data[symbol] = {
                "coin_id":
                    coin_id,

                "error":
                    str(e),
            }

    # --------------------------------------------------------
    # PROMPT
    # --------------------------------------------------------

    prompt = build_prompt(
        market_global=
            market_global,

        fear_greed=
            fear_greed,

        safety=
            safety,

        news=
            news,

        portfolio_data=
            portfolio_data,

        candidate_data=
            candidate_data,

        btc_data=
            btc_data,
    )

    # --------------------------------------------------------
    # GEMINI
    # --------------------------------------------------------

    print(
        "Sending data to Gemini..."
    )

    analysis = (
        gemini_analyze(
            prompt
        )
    )

    print(
        "Gemini analysis completed."
    )

    # --------------------------------------------------------
    # VALIDATION
    # --------------------------------------------------------

    print(
        "Validating analysis..."
    )

    analysis = (
        validate_and_correct_analysis(
            analysis,
            safety,
            portfolio_data
        )
    )

    # --------------------------------------------------------
    # STATE
    # --------------------------------------------------------

    state = load_state()

    state["last_run"] = (
        iso_now()
    )

    state["last_full_analysis"] = (
        iso_now()
    )

    state["last_analysis_reason"] = (
        schedule_reason
    )

    state["market_safety"] = (
        safety
    )

    state["fear_greed"] = (
        fear_greed
    )

    state["btc_data"] = (
        btc_data
    )

    state["last_analysis"] = (
        analysis
    )

    state["last_main_schedule"] = (
        schedule_reason
    )

    state["last_safety_state"] = (
        safety.get(
            "state",
            "NORMAL"
        )
    )

    state["last_safety_score"] = (
        safety.get(
            "score",
            0
        )
    )

    save_state(
        state
    )

    # --------------------------------------------------------
    # TELEGRAM
    # --------------------------------------------------------

    messages = (
        format_bot_message(
            analysis,
            safety,
            fear_greed
        )
    )

    for message in messages:

        telegram_send(
            message
        )

        time.sleep(1)

    print(
        "Full analysis sent."
    )


# ============================================================
# MAIN
# ============================================================

def main():

    print(
        "========================================"
    )

    print(
        "Crypto AI Bot V5.4"
    )

    print(
        "Time:",
        iso_now()
    )

    print(
        "========================================"
    )

    if not GEMINI_API_KEY:

        raise RuntimeError(
            "Chýba GEMINI_API_KEY."
        )

    should_run, reason = (
        is_main_analysis_time()
    )

    print(
        "Run type:",
        reason
    )

    # ========================================================
    # FULL ANALYSIS
    # ========================================================

    if should_run:

        run_full_analysis(
            reason
        )

        return

    # ========================================================
    # SAFETY ONLY
    # ========================================================

    run_safety_monitor()

    print(
        "Safety monitor finished."
    )


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":
    main()
