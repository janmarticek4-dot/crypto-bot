import os
import json
import time
import re
import urllib.request
import urllib.parse
import urllib.error
import xml.etree.ElementTree as ET
from datetime import datetime
from zoneinfo import ZoneInfo

from google import genai


# ============================================================
# CRYPTO AI BOT V5.3 (Slovenská verzia - Plain Text Telegram)
# ============================================================
# CoinGecko
# Alternative.me Fear & Greed
# CoinTelegraph + CoinDesk RSS
# Gemini 3.8 Flash
# Gemini Interactions API
# Background execution
# Google Search
# Telegram
# bot_state.json
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
        return float(value)
    except Exception:
        return default


def pct_change(old, new):
    if old in (None, 0) or new is None:
        return None

    return ((new - old) / old) * 100.0


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
        "User-Agent": "CryptoAIBot/5.3"
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
# CHART / TECHNICAL DATA
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
            "price": (
                closes[-1]
                if closes
                else None
            )
        }

    ema20 = ema(
        closes,
        20
    )

    ema50 = ema(
        closes,
        50
    )

    ema100 = ema(
        closes,
        100
    )

    ema200 = ema(
        closes,
        200
    )

    current = closes[-1]

    e20 = last_valid(
        ema20
    )

    e50 = last_valid(
        ema50
    )

    e100 = last_valid(
        ema100
    )

    e200 = last_valid(
        ema200
    )

    return {
        "price": current,
        "ema20": e20,
        "ema50": e50,
        "ema100": e100,
        "ema200": e200,
        "rsi14": rsi(closes, 14),
        "macd": macd(closes),
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
