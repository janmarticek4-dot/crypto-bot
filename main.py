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

from google import genai


# ============================================================
# CRYPTO AI BOT V10.2
# Vylepšenia: TP & R:R, časové horizonty, striktné fázy trhu,
# umiernený tón, orientačné skóre a explicitné dôvody pohybov.
# ============================================================

VERSION = "10.2"

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()
COINGECKO_API_KEY = os.getenv("COINGECKO_API_KEY", "").strip()

GEMINI_MODEL = (os.getenv("GEMINI_MODEL", "").strip() or "gemini-3.8-flash")

REQUEST_TIMEOUT = 45
GEMINI_MAX_WAIT = 600
POLL_INTERVAL = 5
STATE_FILE = "bot_state.json"

TZ = ZoneInfo("Europe/Bratislava")
US_TZ = ZoneInfo("America/New_York")

PORTFOLIO = {
    "AAVE": "aave",
    "TAO": "bittensor",
    "FET": "artificial-superintelligence-alliance",
    "SOL": "solana",
    "ONDO": "ondo-finance",
    "RENDER": "render-token",
}

COIN_ID_ALIASES = {
    "FET": [
        "artificial-superintelligence-alliance",
        "fetch-ai",
    ]
}

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
CANDIDATE_SYMBOLS = {
    "sui": "SUI", "chainlink": "LINK",
    "compound-governance-token": "COMP", "avalanche-2": "AVAX",
    "hyperliquid": "HYPE", "near": "NEAR",
    "injective-protocol": "INJ", "uniswap": "UNI",
    "arbitrum": "ARB", "optimism": "OP",
    "maker": "MKR", "mantle": "MNT",
}

RSS_FEEDS = [
    ("CoinTelegraph", "https://cointelegraph.com/rss"),
    ("CoinDesk", "https://www.coindesk.com/arc/outboundfeeds/rss/"),
]

VALID_ACTIONS = {
    "BUY NOW",
    "BUY PULLBACK",
    "HOLD",
    "REDUCE",
    "SELL",
    "NO TRADE",
}

REQUIRED_SYMBOLS = list(PORTFOLIO.keys())

BINANCE_SYMBOLS = {
    "BTC": "BTCUSDT", "AAVE": "AAVEUSDT", "TAO": "TAOUSDT",
    "FET": "FETUSDT", "SOL": "SOLUSDT", "ONDO": "ONDOUSDT",
    "RENDER": "RENDERUSDT", "SUI": "SUIUSDT", "LINK": "LINKUSDT",
    "COMP": "COMPUSDT", "AVAX": "AVAXUSDT", "HYPE": "HYPEUSDT",
    "NEAR": "NEARUSDT", "INJ": "INJUSDT", "UNI": "UNIUSDT",
    "ARB": "ARBUSDT", "OP": "OPUSDT", "MNT": "MNTUSDT",
}
COINBASE_PRODUCTS = {
    "BTC": "BTC-USD", "AAVE": "AAVE-USD", "TAO": "TAO-USD",
    "FET": "FET-USD", "SOL": "SOL-USD", "ONDO": "ONDO-USD",
    "RENDER": "RENDER-USD", "SUI": "SUI-USD", "LINK": "LINK-USD",
    "COMP": "COMP-USD", "AVAX": "AVAX-USD", "NEAR": "NEAR-USD",
    "INJ": "INJ-USD", "UNI": "UNI-USD", "ARB": "ARB-USD",
    "OP": "OP-USD", "MKR": "MKR-USD",
}


# ============================================================
# POMOCNÉ FUNKCIE
# ============================================================

def now_local():
    return datetime.now(TZ)


def iso_now():
    return now_local().isoformat()


def utc_now_iso():
    return datetime.now(timezone.utc).isoformat()


def safe_float(value, default=None):
    try:
        if value is None or isinstance(value, bool):
            return default

        if isinstance(value, str):
            value = value.replace("$", "").replace(",", "").strip()

        result = float(value)
        return result if math.isfinite(result) else default

    except (ValueError, TypeError, OverflowError):
        return default


def clamp(value, low, high):
    return max(low, min(high, value))


def pct_change(old, new):
    if old is None or new is None or old == 0:
        return None

    return (new - old) / old * 100.0


def manual_analysis_requested():
    return os.getenv("MANUAL_ANALYSIS", "").strip().lower() in {
        "true", "1", "yes", "y", "on"
    }


def load_state():
    if not os.path.exists(STATE_FILE):
        return {}

    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        return data if isinstance(data, dict) else {}

    except Exception as exc:
        print(f"State read error: {exc}")
        return {}


def save_state(state):
    temp = STATE_FILE + ".tmp"

    with open(temp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

    os.replace(temp, STATE_FILE)


def parse_timestamp(value):
    if not value:
        return None

    try:
        result = datetime.fromisoformat(
            str(value).replace("Z", "+00:00")
        )

        if result.tzinfo is None:
            result = result.replace(tzinfo=timezone.utc)

        return result.astimezone(timezone.utc)

    except (ValueError, TypeError):
        return None


# ============================================================
# ČASOVÝ PLÁN
# ============================================================

def get_main_analysis_slot(now=None):
    now = now or now_local()

    if now.hour == 7 and now.minute < 30:
        return f"BRATISLAVA_{now.date().isoformat()}_07:00"

    if now.hour == 15 and now.minute < 30:
        return f"BRATISLAVA_{now.date().isoformat()}_15:00"

    if now.hour == 20 and now.minute < 30:
        return f"BRATISLAVA_{now.date().isoformat()}_20:00"

    return None


def is_main_analysis_time(now=None):
    if manual_analysis_requested():
        return True, "MANUAL"

    slot = get_main_analysis_slot(now)

    if not slot:
        return False, "SAFETY_MONITOR"

    if load_state().get("last_main_slot") == slot:
        return False, "SAFETY_MONITOR"

    if "07:00" in slot:
        return True, "BRATISLAVA_07:00"

    if "15:00" in slot:
        return True, "BRATISLAVA_15:00"

    if "20:00" in slot:
        return True, "BRATISLAVA_20:00"

    return False, "SAFETY_MONITOR"


# ============================================================
# HTTP A COINGECKO
# ============================================================

def http_request(req, timeout=REQUEST_TIMEOUT, retries=3):
    last_error = None

    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                return response.read()

        except urllib.error.HTTPError as exc:
            last_error = exc

            if exc.code in {400, 401, 403, 404}:
                raise

        except (
            urllib.error.URLError,
            TimeoutError,
            ConnectionError,
            OSError,
        ) as exc:
            last_error = exc

        if attempt < retries - 1:
            time.sleep(2 ** attempt)

    raise last_error or RuntimeError("HTTP požiadavka zlyhala.")


def http_json(url, headers=None, timeout=REQUEST_TIMEOUT, retries=3):
    req = urllib.request.Request(
        url,
        headers=headers or {},
        method="GET",
    )

    raw = http_request(req, timeout, retries)
    return json.loads(raw.decode("utf-8"))


def coingecko_headers():
    headers = {
        "Accept": "application/json",
        "User-Agent": f"CryptoAIBot/{VERSION}",
    }

    if COINGECKO_API_KEY:
        headers["x-cg-demo-api-key"] = COINGECKO_API_KEY

    return headers


def coingecko_get(endpoint, params=None):
    url = f"https://api.coingecko.com/api/v3/{endpoint}"

    if params:
        url += "?" + urllib.parse.urlencode(params)

    return http_json(url, headers=coingecko_headers())


def coingecko_simple_price(ids):
    ids = list(dict.fromkeys(ids))

    if not ids:
        return {}

    return coingecko_get("simple/price", {
        "ids": ",".join(ids),
        "vs_currencies": "usd",
        "include_market_cap": "true",
        "include_24hr_vol": "true",
        "include_24hr_change": "true",
        "include_last_updated_at": "true",
    })


def coingecko_markets(ids):
    if not ids:
        return []

    return coingecko_get("coins/markets", {
        "vs_currency": "usd",
        "ids": ",".join(ids),
        "order": "market_cap_desc",
        "per_page": min(len(ids), 100),
        "page": 1,
        "sparkline": "false",
        "price_change_percentage": "24h,7d",
    })


def coingecko_chart(coin_id, days=90):
    return coingecko_get(
        f"coins/{coin_id}/market_chart",
        {
            "vs_currency": "usd",
            "days": days,
        },
    )


def binance_4h_candles(symbol, limit=300):
    pair = BINANCE_SYMBOLS.get(symbol.upper())
    if not pair:
        raise RuntimeError(f"Binance pár nie je nastavený pre {symbol}")
    url = "https://data-api.binance.vision/api/v3/klines?" + urllib.parse.urlencode({
        "symbol": pair, "interval": "4h", "limit": min(limit, 1000)
    })
    rows = http_json(url, headers={"User-Agent": f"CryptoAIBot/{VERSION}"})
    now_ms = int(time.time() * 1000)
    candles = []
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, list) or len(row) < 7:
            continue
        close_time = safe_float(row[6])
        if close_time is None or close_time >= now_ms:
            continue
        vals = [safe_float(row[i]) for i in (1, 2, 3, 4, 5)]
        if any(v is None for v in vals) or vals[3] <= 0:
            continue
        candles.append({
            "timestamp": int(safe_float(row[0])),
            "open": vals[0], "high": vals[1], "low": vals[2],
            "close": vals[3], "volume": vals[4],
        })
    if len(candles) < 35:
        raise RuntimeError(f"Binance poskytol málo uzavretých sviečok pre {symbol}")
    return candles


def binance_live_price(symbol):
    pair = BINANCE_SYMBOLS.get(symbol.upper())
    if not pair:
        return None
    url = "https://data-api.binance.vision/api/v3/ticker/price?" + urllib.parse.urlencode({"symbol": pair})
    data = http_json(url, headers={"User-Agent": f"CryptoAIBot/{VERSION}"})
    price = safe_float(data.get("price")) if isinstance(data, dict) else None
    return price if price and price > 0 else None


def coinbase_4h_candles(symbol):
    product = COINBASE_PRODUCTS.get(symbol.upper())
    if not product:
        raise RuntimeError(f"Coinbase produkt nie je nastavený pre {symbol}")
    end_ts = int(time.time())
    start_ts = end_ts - 300 * 3600
    params = {
        "granularity": 3600,
        "start": datetime.fromtimestamp(start_ts, timezone.utc).isoformat(),
        "end": datetime.fromtimestamp(end_ts, timezone.utc).isoformat(),
    }
    url = f"https://api.exchange.coinbase.com/products/{product}/candles?" + urllib.parse.urlencode(params)
    rows = http_json(url, headers={
        "User-Agent": f"CryptoAIBot/{VERSION}", "Accept": "application/json"
    }, retries=1)
    now = int(time.time())
    buckets = {}
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, list) or len(row) < 6:
            continue
        ts = safe_float(row[0]); low = safe_float(row[1]); high = safe_float(row[2])
        opn = safe_float(row[3]); close = safe_float(row[4]); volume = safe_float(row[5], 0)
        if any(v is None for v in (ts, low, high, opn, close)) or close <= 0:
            continue
        bucket = int(ts // 14400) * 14400
        if bucket + 14400 > now:
            continue
        if bucket not in buckets:
            buckets[bucket] = {"timestamp": bucket * 1000, "open": opn,
                               "high": high, "low": low, "close": close,
                               "volume": volume or 0, "_first": int(ts)}
        else:
            candle = buckets[bucket]
            if int(ts) < candle["_first"]:
                candle["open"] = opn; candle["_first"] = int(ts)
            candle["high"] = max(candle["high"], high)
            candle["low"] = min(candle["low"], low)
            if int(ts) > candle.get("_last", -1):
                candle["close"] = close; candle["_last"] = int(ts)
            candle["volume"] += volume or 0
    candles = []
    for key in sorted(buckets):
        item = dict(buckets[key]); item.pop("_first", None); item.pop("_last", None)
        candles.append(item)
    if len(candles) < 35:
        raise RuntimeError(f"Coinbase poskytol málo uzavretých 4H sviečok pre {symbol}")
    return candles


def coinbase_live_price(symbol):
    product = COINBASE_PRODUCTS.get(symbol.upper())
    if not product:
        return None
    url = f"https://api.exchange.coinbase.com/products/{product}/ticker"
    try:
        data = http_json(url, headers={
            "User-Agent": f"CryptoAIBot/{VERSION}",
            "Accept": "application/json",
        }, retries=1)
        price = safe_float(data.get("price")) if isinstance(data, dict) else None
        return price if price and price > 0 else None
    except Exception as exc:
        print(f"Coinbase price check unavailable for {symbol}: {exc}")
        return None


def get_coin_price_with_fallback(symbol, coin_id):
    ids_to_try = COIN_ID_ALIASES.get(symbol, [coin_id])

    if coin_id not in ids_to_try:
        ids_to_try = [coin_id] + ids_to_try

    last_error = None

    for candidate_id in ids_to_try:
        try:
            data = coingecko_simple_price([candidate_id])
            current = data.get(candidate_id, {})

            if safe_float(current.get("usd")):
                return candidate_id, current

        except Exception as exc:
            last_error = exc
            print(f"CoinGecko fallback {symbol}/{candidate_id}: {exc}")

    if last_error:
        raise RuntimeError(
            f"CoinGecko neposkytol cenu pre {symbol}: {last_error}"
        )

    raise RuntimeError(
        f"CoinGecko neposkytol platnú cenu pre {symbol}."
    )


# ============================================================
# TECHNICKÉ UKAZOVATELE
# ============================================================

def closes_from_chart(chart):
    result = []

    for point in chart.get("prices", []):
        if not isinstance(point, list) or len(point) < 2:
            continue

        timestamp = safe_float(point[0])
        price = safe_float(point[1])

        if timestamp is None or price is None:
            continue

        result.append({
            "timestamp": int(timestamp),
            "price": price,
        })

    return result


def aggregate_candles(prices, hours=4):
    buckets = {}
    width = hours * 60 * 60 * 1000

    for point in prices:
        timestamp = int(point["timestamp"])
        price = point["price"]
        bucket = (timestamp // width) * width

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
                buckets[bucket]["high"], price
            )
            buckets[bucket]["low"] = min(
                buckets[bucket]["low"], price
            )
            buckets[bucket]["close"] = price

    return [buckets[key] for key in sorted(buckets)]


def ema(values, period):
    if len(values) < period:
        return [None] * len(values)

    result = [None] * len(values)
    previous = sum(values[:period]) / period
    result[period - 1] = previous
    multiplier = 2 / (period + 1)

    for i in range(period, len(values)):
        previous += (values[i] - previous) * multiplier
        result[i] = previous

    return result


def last_valid(values):
    for value in reversed(values):
        if value is not None:
            return value

    return None


def rsi(values, period=14):
    if len(values) < period + 1:
        return None

    changes = [
        values[i] - values[i - 1]
        for i in range(1, len(values))
    ]

    gains = [max(change, 0) for change in changes]
    losses = [max(-change, 0) for change in changes]

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    for i in range(period, len(gains)):
        avg_gain = (
            avg_gain * (period - 1) + gains[i]
        ) / period

        avg_loss = (
            avg_loss * (period - 1) + losses[i]
        ) / period

    if avg_loss == 0:
        return 100.0 if avg_gain > 0 else 50.0

    rs = avg_gain / avg_loss
    return 100 - 100 / (1 + rs)


def macd(values):
    if len(values) < 35:
        return {
            "macd": None,
            "signal": None,
            "histogram": None,
        }

    e12 = ema(values, 12)
    e26 = ema(values, 26)

    series = [
        a - b if a is not None and b is not None else None
        for a, b in zip(e12, e26)
    ]

    valid = [value for value in series if value is not None]

    if len(valid) < 9:
        return {
            "macd": None,
            "signal": None,
            "histogram": None,
        }

    signal = last_valid(ema(valid, 9))
    current = valid[-1]

    return {
        "macd": current,
        "signal": signal,
        "histogram": (
            current - signal if signal is not None else None
        ),
    }


def atr(candles, period=14):
    if len(candles) < period + 1:
        return None

    ranges = []

    for i in range(1, len(candles)):
        current = candles[i]
        previous = candles[i - 1]

        ranges.append(max(
            current["high"] - current["low"],
            abs(current["high"] - previous["close"]),
            abs(current["low"] - previous["close"]),
        ))

    return sum(ranges[-period:]) / period if ranges else None


def recent_support_resistance(candles, lookback=30):
    recent = candles[-lookback:]

    if not recent:
        return {
            "support": None,
            "resistance": None,
        }

    return {
        "support": min(candle["low"] for candle in recent),
        "resistance": max(candle["high"] for candle in recent),
    }


def technical_summary(candles, live_price=None):
    if not candles:
        return {}

    closes = [candle["close"] for candle in candles]
    chart_price = closes[-1]
    price = safe_float(live_price, chart_price)

    averages = {
        f"ema{period}": last_valid(ema(closes, period))
        for period in (20, 50, 100, 200)
    }

    above = {
        f"above_ema{period}": (
            price > averages[f"ema{period}"]
            if averages[f"ema{period}"] is not None
            else None
        )
        for period in (20, 50, 100, 200)
    }

    sr = recent_support_resistance(candles)
    current_atr = atr(candles)

    return {
        "price": price,
        "chart_last_close": chart_price,
        **averages,
        **above,
        "rsi14": rsi(closes),
        "macd": macd(closes),
        "atr14": current_atr,
        "atr_percent": (
            current_atr / price * 100
            if current_atr is not None and price else None
        ),
        "support_30_candles": sr["support"],
        "resistance_30_candles": sr["resistance"],
        "candles_4h_available": len(candles),
        "last_chart_timestamp": candles[-1]["timestamp"],
    }


def recent_returns(closes):
    result = {}

    for name, bars in {
        "24h": 6,
        "7d": 42,
        "30d": 180,
    }.items():
        if len(closes) > bars:
            change = pct_change(closes[-bars - 1], closes[-1])

            if change is not None:
                result[name] = round(change, 3)

    return result


def calculate_technical_score(tech):
    """Skóre trendu 0–10."""
    if not tech or safe_float(tech.get("price")) is None:
        return {
            "score": None,
            "label": "nedostatok dát",
            "reasons": [],
            "known_emas": 0,
        }

    score = 5.0
    reasons = []
    known_emas = 0

    for key, weight, label in [
        ("above_ema20", 0.45, "EMA20"),
        ("above_ema50", 0.80, "EMA50"),
        ("above_ema100", 0.65, "EMA100"),
        ("above_ema200", 1.00, "EMA200"),
    ]:
        value = tech.get(key)

        if value is True:
            score += weight
            known_emas += 1
            reasons.append(f"cena nad {label}")

        elif value is False:
            score -= weight
            known_emas += 1
            reasons.append(f"cena pod {label}")

    rsi_value = safe_float(tech.get("rsi14"))

    if rsi_value is not None:
        if 50 <= rsi_value <= 65:
            score += 0.8
            reasons.append(f"RSI {rsi_value:.1f}: pozitívne momentum")
        elif rsi_value > 65:
            score += 0.3
            reasons.append(f"RSI {rsi_value:.1f}: silné, možná prekúpenosť")
        elif 40 <= rsi_value < 50:
            score -= 0.2
            reasons.append(f"RSI {rsi_value:.1f}: neutrálne až slabšie")
        elif 30 <= rsi_value < 40:
            score -= 0.6
            reasons.append(f"RSI {rsi_value:.1f}: slabé momentum")
        else:
            score -= 0.3
            reasons.append(f"RSI {rsi_value:.1f}: extrémna zóna")

    histogram = safe_float((tech.get("macd") or {}).get("histogram"))

    if histogram is not None:
        if histogram > 0:
            score += 0.6
            reasons.append("MACD histogram kladný")
        elif histogram < 0:
            score -= 0.6
            reasons.append("MACD histogram záporný")

    if known_emas < 4:
        reasons.append("chýbajú niektoré EMA")

    score = round(clamp(score, 0, 10), 1)

    return {
        "score": score,
        "label": (
            "silná" if score >= 7
            else "slabá" if score <= 3
            else "zmiešaná"
        ),
        "reasons": reasons,
        "known_emas": known_emas,
    }


# ============================================================
# ZBER DÁT A KONTROLA KVALITY
# ============================================================

def collect_coin_data(symbol, coin_id, days=90):
    print(f"Collecting: {symbol}")
    actual_id, current = get_coin_price_with_fallback(symbol, coin_id)
    cg_price = safe_float(current.get("usd"))
    if cg_price is None or cg_price <= 0:
        raise RuntimeError(f"CoinGecko neposkytol platnú cenu pre {symbol}.")

    warnings = []
    candles = []
    candle_source = "Binance Spot 4H"
    try:
        candles = binance_4h_candles(symbol)
    except Exception as exc:
        print(f"Binance candle fallback for {symbol}: {exc}")
        warnings.append("Binance 4H dáta nedostupné; použitá záložná burza alebo núdzové dáta.")
        try:
            candles = coinbase_4h_candles(symbol)
            candle_source = "Coinbase 1H agregované na 4H"
            warnings.append("Záložné Coinbase dáta majú kratšiu históriu; dlhé priemery môžu chýbať.")
        except Exception as coinbase_exc:
            print(f"Coinbase candle fallback for {symbol}: {coinbase_exc}")
            candle_source = "CoinGecko fallback"
            try:
                chart = coingecko_chart(actual_id, days=days)
                candles = aggregate_candles(closes_from_chart(chart))
            except Exception as chart_exc:
                raise RuntimeError(f"Chýbajú technické dáta pre {symbol}: {chart_exc}")

    binance_price = None
    try:
        binance_price = binance_live_price(symbol)
    except Exception as exc:
        print(f"Binance live price unavailable for {symbol}: {exc}")

    live_price = binance_price or cg_price
    coinbase_price = coinbase_live_price(symbol)
    if coinbase_price and live_price:
        diff = abs(coinbase_price / live_price - 1) * 100
        if diff > 1.5:
            warnings.append(f"Coinbase a hlavná cena sa líšia o {diff:.1f} %; signál over opatrne.")

    tech = technical_summary(candles, live_price)
    if not tech:
        raise RuntimeError(f"Nedostatočné technické dáta: {symbol}")

    last_updated = safe_float(current.get("last_updated_at"))
    data_age_seconds = max(0, time.time() - last_updated) if last_updated else None
    
    if len(candles) < 200:
        warnings.append(f"Len {len(candles)} sviečok; EMA200 môže chýbať.")
    if data_age_seconds is None:
        warnings.append("Chýba čas aktualizácie záložnej ceny.")
    elif data_age_seconds > 900 and not binance_price:
        warnings.append("Záložná cena môže byť zastaraná.")
        
    chart_price = safe_float(tech.get("chart_last_close"))
    if chart_price and abs(live_price / chart_price - 1) > 0.05:
        warnings.append("Živá cena sa líši od poslednej uzavretej sviečky o viac než 5 %.")
    if safe_float(tech.get("rsi14")) is None:
        warnings.append("RSI sa nedá vypočítať z dostupných dát.")
    if safe_float(tech.get("ema50")) is None:
        warnings.append("EMA50 nie je dostupná.")
    if safe_float(tech.get("ema200")) is None:
        warnings.append("EMA200 nie je dostupná.")

    score = calculate_technical_score(tech)
    return {
        "symbol": symbol, "coin_id": actual_id, "price_usd": live_price,
        "market_cap": safe_float(current.get("usd_market_cap")),
        "volume_24h": safe_float(current.get("usd_24h_vol")),
        "change_24h": safe_float(current.get("usd_24h_change")),
        "last_updated": last_updated,
        "data_age_seconds": round(data_age_seconds) if data_age_seconds is not None else None,
        "data_warnings": warnings, "technical_4h": tech,
        "technical_score_calc": score,
        "returns": recent_returns([candle["close"] for candle in candles]),
        "_candle_source": candle_source,
        "_coinbase_price": coinbase_price,
    }


# ============================================================
# FEAR & GREED A BEZPEČNOSŤ TRHU
# ============================================================

def get_fear_greed():
    try:
        response = http_json(
            "https://api.alternative.me/fng/?limit=1",
            headers={"User-Agent": f"CryptoAIBot/{VERSION}"},
        )
        item = response["data"][0]
        return {
            "value": int(item["value"]),
            "classification": item["value_classification"],
            "timestamp": item.get("timestamp"),
            "source": "Alternative.me",
        }
    except Exception as exc:
        print(f"Fear & Greed error: {exc}")
        return {
            "value": None,
            "classification": "UNKNOWN",
            "timestamp": None,
            "source": "Alternative.me",
            "error": str(exc),
        }


def market_safety(global_data, simple_prices, btc_data=None):
    score = 0
    reasons = []

    global_change = safe_float(
        global_data.get("data", {}).get("market_cap_change_percentage_24h_usd")
    )

    btc_change = safe_float(
        simple_prices.get("bitcoin", {}).get("usd_24h_change")
    )

    tech = (btc_data.get("technical_4h", {}) if isinstance(btc_data, dict) else {})
    price = safe_float(tech.get("price"))
    e200 = safe_float(tech.get("ema200"))

    # Bezpečnostný alert spúšťame výhradne pri špecifických rizikových podmienkach
    if global_change is not None and global_change <= -4.0:
        score += 3
        reasons.append("celková trhová kapitalizácia zaznamenáva prudký pokles")
    if btc_change is not None and btc_change <= -6.0:
        score += 3
        reasons.append("Bitcoin prudko padá a ohrozuje kľúčové podpory")

    state = (
        "CRITICAL" if score >= 6
        else "WARNING" if score >= 3
        else "NORMAL"
    )

    return {
        "state": state,
        "score": score,
        "reasons": reasons,
        "market_cap_change_24h": global_change,
        "btc_change_24h": btc_change,
    }


def should_send_smart_pump_alerts(portfolio_data, state):
    alerts_state = state.get("coin_change_alerts", {})
    if not isinstance(alerts_state, dict):
        alerts_state = {}

    triggered = []
    for symbol, data in (portfolio_data or {}).items():
        if not isinstance(data, dict) or data.get("error"):
            continue
        change_since_last = safe_float(data.get("change_since_last"), 0.0)
        last_alerted = safe_float(alerts_state.get(symbol), 0.0)

        diff = change_since_last - last_alerted
        if diff >= 3.0 or diff <= -5.0:
            triggered.append({
                "symbol": symbol,
                "change_since_last": change_since_last,
                "price": data.get("price_usd"),
                "diff": diff,
            })
            alerts_state[symbol] = change_since_last

    state["coin_change_alerts"] = alerts_state
    return triggered


# ============================================================
# TELEGRAM A RSS
# ============================================================

def telegram_send(message):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        raise RuntimeError("Chýba TELEGRAM_TOKEN alebo TELEGRAM_CHAT_ID.")

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "disable_web_page_preview": True,
    }

    request = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    raw = http_request(request, timeout=30, retries=3)
    result = json.loads(raw.decode("utf-8"))

    if not result.get("ok"):
        raise RuntimeError(f"Telegram odmietol správu: {result}")

    print("Telegram message sent.")
    return True


def telegram_send_long(message):
    max_chars = 3800
    chunks = []
    current = ""

    for line in message.splitlines():
        while len(line) > max_chars:
            if current:
                chunks.append(current)
                current = ""
            chunks.append(line[:max_chars])
            line = line[max_chars:]

        addition = ("\n" if current else "") + line

        if len(current) + len(addition) > max_chars:
            if current:
                chunks.append(current)
            current = line
        else:
            current += addition

    if current:
        chunks.append(current)

    for chunk in chunks:
        telegram_send(chunk)
        time.sleep(1)


def get_rss_news():
    all_items = []
    headers = {
        "User-Agent": f"Mozilla/5.0 (compatible; CryptoAIBot/{VERSION})",
        "Accept": "application/rss+xml,application/xml,text/xml,*/*",
    }

    for source, url in RSS_FEEDS:
        try:
            raw = http_request(
                urllib.request.Request(url, headers=headers),
                timeout=25,
                retries=2,
            )
            root = ET.fromstring(raw)
            count = 0

            for item in root.iter():
                if not item.tag.lower().endswith("item"):
                    continue
                entry = {"source": source, "title": "", "link": "", "pub_date": ""}
                for child in item:
                    tag = child.tag.lower()
                    if tag.endswith("title"): entry["title"] = (child.text or "").strip()
                    elif tag.endswith("link"): entry["link"] = (child.text or "").strip()
                    elif tag.endswith("pubdate"): entry["pub_date"] = (child.text or "").strip()

                if entry["title"]:
                    all_items.append(entry)
                    count += 1
                if count >= 10:
                    break
        except Exception as exc:
            print(f"RSS error {source}: {exc}")

    return all_items[:20]


# ============================================================
# SPRÁVY A GEMINI
# ============================================================

def parse_json_output(text):
    if not text:
        raise RuntimeError("Gemini neposlal výstup.")

    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
    text = re.sub(r"\s*```$", "", text)

    try:
        result = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            raise RuntimeError("Gemini neposlal validný JSON.")
        result = json.loads(text[start:end + 1])

    if not isinstance(result, dict):
        raise RuntimeError("Výstup Gemini nie je JSON objekt.")

    return result


def gemini_analyze(prompt):
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY nie je nastavený.")

    client = genai.Client(api_key=GEMINI_API_KEY)
    print(f"Gemini model: {GEMINI_MODEL}")

    interaction = client.interactions.create(
        model=GEMINI_MODEL,
        input=prompt,
        background=True,
        tools=[{"type": "google_search"}],
        generation_config={"thinking_level": "high"},
        store=True,
        timeout=120,
    )

    interaction_id = interaction.id
    started = time.time()

    while True:
        if time.time() - started > GEMINI_MAX_WAIT:
            raise TimeoutError("Gemini analýza trvá dlhšie ako 10 minút.")

        interaction = client.interactions.get(id=interaction_id)
        status = interaction.status

        if status == "completed":
            if not interaction.output_text:
                raise RuntimeError("Gemini vrátil prázdny výstup.")
            return parse_json_output(interaction.output_text)

        if status in {"failed", "cancelled", "expired", "incomplete", "requires_action"}:
            raise RuntimeError(f"Gemini analýza skončila: {status}")

        time.sleep(POLL_INTERVAL)


def build_prompt(
    market_global,
    fear_greed,
    safety,
    news,
    portfolio_data,
    candidate_data,
    btc_data,
    state,
):
    previous = state.get("last_analysis", {})
    previous_coins = (
        previous.get("coins", [])
        if isinstance(previous, dict) else []
    )

    prior_summary = []
    for coin in previous_coins:
        if isinstance(coin, dict):
            prior_summary.append({
                "symbol": coin.get("symbol"),
                "action": coin.get("action"),
                "price": coin.get("current_price"),
                "market_cap": coin.get("market_cap"),
                "volume_24h": coin.get("volume_24h"),
                "outlook_direction": coin.get("outlook_direction"),
            })

    return f"""
Si disciplinovaný analytik kryptomien a správca rizika.
Píš po slovensky, zrozumiteľne, kompletne a bez skratiek. **Všetky vety musia byť plne dokončené.**

Čas Bratislava: {iso_now()}
Portfólio: AAVE, TAO, FET, SOL, ONDO, RENDER.

FORMÁTOVANIE A PRAVIDLÁ:
- Všetky čísla, sumy, percentá, kapitalizácie, podiely **musíš písať výhradne ako číslice** (napr. 2.83T USD, 1.34%, 59.68%, 18.5B USD, 0.45%), nikdy nie slovami.
- **TÓN A REALISTICKÝ POHĽAD**: Vyvaruj sa prehnane sebavedomým slovám ako „jednoznačne“ či „spoľahlivo“, nakoľko základné indikátory (MACD, RSI) poskytujú len pravdepodobnostný pohľad. Súčasná hodnota Fear & Greed sa blíži k extrémnej chamtivosti, čo v analýze zohľadniť ako dôvod na zvýšenú opatrnosť a obozretnosť pri nákupoch.
- **FÁZY TRHU**: Trhový režim (market_regime) striktne rozlišuj na základe dát do jednej z troch kategórií:
  1. **Odraz** (ceny sa po predchádzajúcom poklese zotavujú, ale ďalší smer a stabilita ešte nie sú potvrdené).
  2. **Konsolidácia** (ceny sa pohybujú do strany, trh aktívne hľadá nový smer).
  3. **Potvrdený rast** (tvorba vyšších maxím a miním, podporená rastúcim objemom a zlepšením širšieho trhu).
- **ODDELENIE SMERU TRHU OD ALERTU**: Smer trhu opisuj čisto podľa technických a trhových reálií (rastúci / klesajúci / konsolidácia). Bezpečnostný alert zapoj do úvahy len vtedy, ak sú splnené reálne rizikové podmienky v poli SAFETY.
- **DÔVOD POHYBU**: Vždy explicitne uveď dôvod pohybu trhu alebo aktíva (napr. odraz Bitcoinu, nárast objemu, sektorový záujem o altcoiny). Ak dôvod nie je možné spoľahlivo identifikovať z dostupných dát, otvorene to priznaj.
- **PREDIKCIA A HORIZONT**: Každá predikcia (outlook_direction) musí obsahovať nielen slovný smer, ale aj **explicitný cenový cieľ** a **časový horizont** v poli `target_horizon` (napr. 4H alebo 24H).
- **TAKE-PROFITY**: Pre každú mincu povinne uveď hodnoty **tp1** a **tp2** rešpektujúce logické hladiny rezistencií.
- **ORIENTAČNÉ SKÓRE**: Namiesto vymyslených presných pravdepodobností používaj **orientačné skóre** v poli `outlook_score` (napr. "Orientačné skóre 6.5/10").
- **VŠETKY HODNOTY A ZMENY OD POSLEDNEJ ANALÝZY (4H INTERVALY)**: Všetky zmeny percent (kapitalizácie, ceny aj objemu obchodovania) sa vzťahujú **výhradne k stavu z predchádzajúcej analýzy (medzi 4H slotmi)**.

MARKET GLOBAL:
{json.dumps(market_global, ensure_ascii=False)}

PREDCHÁDZAJÚCI STAV MINCI (pre výpočet zmeny od posledného behu):
{json.dumps(prior_summary, ensure_ascii=False)}

FEAR & GREED:
{json.dumps(fear_greed, ensure_ascii=False)}

SAFETY:
{json.dumps(safety, ensure_ascii=False)}

PORTFOLIO DATA (vrátane zmien od poslednej analýzy):
{json.dumps(portfolio_data, ensure_ascii=False)}

Vráť iba validný JSON v tejto štruktúre bez Markdown syntaxe:
{{
 "market_regime":"Odraz / Konsolidácia / Potvrdený rast",
 "market_summary":"zhrnutie trhu, vývoj od poslednej analýzy, dôvod pohybu, zohľadnenie sentimentu a likvidity",
 "coins":[
  {{
   "symbol":"AAVE",
   "action":"BUY PULLBACK",
   "current_price":0.0,
   "market_cap":0.0,
   "market_cap_change_pct":0.0,
   "market_share_pct":0.0,
   "volume_24h":0.0,
   "volume_change_pct":0.0,
   "entry_price":0.0,
   "hard_stop_level":0.0,
   "tp1":0.0,
   "tp2":0.0,
   "target_horizon":"4H",
   "outlook_direction":"mierny rast na úroveň $XXX",
   "outlook_score":"Orientačné skóre 6.5/10",
   "reason":"odôvodnenie rešpektujúce zmenu od poslednej analýzy, dôvod pohybu, umiernený tón a interpretáciu indikátorov",
   "confirmation_needed":"podmienka"
  }}
 ],
 "conditions_to_watch":["string"]
}}
"""


# ============================================================
# VÝPOČET R:R
# ============================================================

def calculate_rr(entry, hard_stop, tp1, tp2):
    entry = safe_float(entry)
    hard_stop = safe_float(hard_stop)
    target1 = safe_float(tp1)
    target2 = safe_float(tp2)

    if None in (entry, hard_stop, target1) or entry <= hard_stop:
        return None, None

    risk = entry - hard_stop
    if risk <= 0 or target1 <= entry:
        return None, None

    rr1 = round((target1 - entry) / risk, 2)
    rr2 = round((target2 - entry) / risk, 2) if target2 and target2 > entry else None
    return rr1, rr2


def validate_and_correct_analysis(
    analysis,
    safety,
    portfolio_data,
    previous_analysis,
    candidate_data=None,
):
    if not isinstance(analysis, dict):
        raise RuntimeError("Gemini neposlal JSON objekt.")

    if not isinstance(analysis.get("coins"), list):
        raise RuntimeError("Gemini neposlal zoznam coins.")

    by_symbol = {}
    for coin in analysis["coins"]:
        if not isinstance(coin, dict):
            continue
        symbol = str(coin.get("symbol", "")).upper().strip()
        if symbol in REQUIRED_SYMBOLS and symbol not in by_symbol:
            by_symbol[symbol] = coin

    validated = []

    for symbol in REQUIRED_SYMBOLS:
        coin = by_symbol.get(symbol)
        if coin is None:
            coin = {
                "symbol": symbol,
                "action": "HOLD",
                "reason": "Chýba platné odporúčanie; použitá bezpečná náhrada HOLD.",
            }

        coin["symbol"] = symbol
        data = portfolio_data.get(symbol, {})
        actual_price = safe_float(data.get("price_usd"))

        if actual_price is not None:
            coin["current_price"] = actual_price

        coin["market_cap"] = safe_float(data.get("market_cap"), coin.get("market_cap", 0))
        coin["volume_24h"] = safe_float(data.get("volume_24h"), coin.get("volume_24h", 0))

        validated.append(coin)

    analysis["coins"] = validated
    analysis["opportunity_ranking"] = []
    return analysis


# ============================================================
# FORMÁTOVANIE SPRÁV
# ============================================================

def format_price(value):
    value = safe_float(value)
    if value is None: return "N/A"
    if value >= 1000: return f"${value:,.0f}"
    if value >= 100: return f"${value:,.2f}"
    if value >= 1: return f"${value:,.3f}"
    if value >= 0.01: return f"${value:,.4f}"
    return f"${value:.8f}"


def format_smart_pump_alert(triggered_items):
    lines = [
        "🚀 CRYPTO AI BOT — ALERT ZMENY TRHU",
        "",
        "Nasledujúce aktíva zaznamenali významnú zmenu od poslednej kontroly:",
    ]
    for item in triggered_items:
        lines.append(f"• {item['symbol']} — Cena: {format_price(item['price'])} | Zmena od posledného slotu: {item['change_since_last']:+.2f}%")
    return "\n".join(lines)


def format_bot_message(analysis, safety, fear_greed):
    coins = analysis.get("coins", [])
    
    lines = [
        f"📊 CRYPTO BOT V{VERSION} | 4H",
        f"🕒 {now_local().strftime('%d.%m. %H:%M')}",
        f"🌐 TRH: {analysis.get('market_regime', 'N/A')}",
    ]
    
    market_summary = analysis.get("market_summary", "")
    if market_summary: 
        lines.append(f"📈 {market_summary}")
        
    lines.extend(["", "📌 PORTFÓLIO A KAPITALIZÁCIE AKTÍV"])
    for coin in coins:
        action = str(coin.get("action", "HOLD")).upper()
        symbol = coin.get("symbol", "?")
        emoji = "🟢" if action.startswith("BUY") else "🟡"
        price = format_price(coin.get("current_price"))
        
        cap = safe_float(coin.get("market_cap"))
        cap_str = f"${cap/1e9:.2f}B" if cap and cap >= 1e9 else f"${cap/1e6:.1f}M" if cap else "N/A"
        cap_change = safe_float(coin.get("market_cap_change_pct"), 0.0)
        share = safe_float(coin.get("market_share_pct"), 0.0)
        
        vol = safe_float(coin.get("volume_24h"))
        vol_str = f"${vol/1e9:.2f}B" if vol and vol >= 1e9 else f"${vol/1e6:.1f}M" if vol else "N/A"
        vol_change = safe_float(coin.get("volume_change_pct"), 0.0)
        
        direction = str(coin.get("outlook_direction", "mierny rast"))
        score = str(coin.get("outlook_score", "Orientačné skóre: N/A"))
        horizon = str(coin.get("target_horizon", "4H"))

        lines.append(f"{emoji} {symbol} — {action} | Cena: {price}")
        lines.append(f"   Kapitalizácia: {cap_str} (Zmena od posl. analýzy: {cap_change:+.2f}% | Podiel na trhu: {share:.3f}%)")
        lines.append(f"   Objem 24h: {vol_str} (Zmena objemu od posl. analýzy: {vol_change:+.2f}%)")
        lines.append(f"   Predikcia: {direction} (Horizont: {horizon}) | {score}")
        lines.append(f"   Analýza: {coin.get('reason', '—')}")

        entry = safe_float(coin.get("entry_price"))
        stop = safe_float(coin.get("hard_stop_level"))
        tp1 = safe_float(coin.get("tp1"))
        tp2 = safe_float(coin.get("tp2"))

        if entry is not None and action.startswith("BUY"):
            rr1, rr2 = calculate_rr(entry, stop, tp1, tp2)
            rr_str = f"R:R TP1: 1:{rr1}" if rr1 else "R:R: N/A"
            if rr2:
                rr_str += f" | TP2: 1:{rr2}"

            lines.append(f"   Vstup: {format_price(entry)} | Stop-Loss: {format_price(stop)}")
            lines.append(f"   Take-Profit: TP1 {format_price(tp1)} | TP2 {format_price(tp2)} ({rr_str})")

    conditions = analysis.get("conditions_to_watch", [])
    if conditions:
        lines.extend(["", "👀 Sledovať: " + " | ".join(str(x) for x in conditions[:2])])
        
    return "\n".join(lines)


# ============================================================
# BEZPEČNOSTNÝ MONITOR
# ============================================================

def run_safety_monitor():
    market_global = coingecko_get("global")
    fear = get_fear_greed()

    state = load_state()
    previous_analysis = state.get("last_analysis", {})
    previous_coins_map = {}
    for coin in previous_analysis.get("coins", []):
        if isinstance(coin, dict):
            sym = coin.get("symbol")
            if sym:
                previous_coins_map[sym] = safe_float(coin.get("current_price"))

    portfolio_data = {}
    for symbol, coin_id in PORTFOLIO.items():
        try:
            data = collect_coin_data(symbol, coin_id, days=35)
            curr_price = data["price_usd"]
            prev_price = previous_coins_map.get(symbol)
            
            change_since_last = pct_change(prev_price, curr_price) if prev_price else 0.0
            data["change_since_last"] = change_since_last
            portfolio_data[symbol] = data
        except Exception as exc:
            print(f"Safety monitor error for {symbol}: {exc}")

    triggered_alerts = should_send_smart_pump_alerts(portfolio_data, state)
    
    if triggered_alerts:
        telegram_send_long(format_smart_pump_alert(triggered_alerts))

    save_state(state)
    return {"state": "NORMAL", "score": 0}


# ============================================================
# HLAVNÁ ANALÝZA
# ============================================================

def run_full_analysis(schedule_reason, schedule_slot=None):
    print(f"Starting full analysis V{VERSION}: {schedule_reason}")

    market_global = coingecko_get("global")
    fear = get_fear_greed()

    all_ids = list(dict.fromkeys(
        list(PORTFOLIO.values())
        + CANDIDATES
        + ["bitcoin"]
        + COIN_ID_ALIASES.get("FET", [])
    ))

    simple = coingecko_simple_price(all_ids)
    news = get_rss_news()

    btc_data = collect_coin_data("BTC", "bitcoin")
    safety = market_safety(market_global, simple, btc_data)

    state = load_state()
    previous_analysis = state.get("last_analysis", {})
    previous_coins_map = {}
    for coin in previous_analysis.get("coins", []):
        if isinstance(coin, dict):
            sym = coin.get("symbol")
            if sym:
                previous_coins_map[sym] = {
                    "price": safe_float(coin.get("current_price")),
                    "market_cap": safe_float(coin.get("market_cap")),
                    "volume_24h": safe_float(coin.get("volume_24h")),
                }

    portfolio_data = {}
    total_market_cap = safe_float(market_global.get("data", {}).get("total_market_cap", {}).get("usd"), 2.83e12)

    for symbol, coin_id in PORTFOLIO.items():
        try:
            data = collect_coin_data(symbol, coin_id)
            cap = safe_float(data.get("market_cap"), 0)
            data["market_share_pct"] = (cap / total_market_cap * 100) if total_market_cap > 0 else 0.0

            # Výpočet zmien od poslednej analýzy (medzi slotmi)
            prev = previous_coins_map.get(symbol, {})
            prev_price = prev.get("price")
            prev_mcap = prev.get("market_cap")
            prev_vol = prev.get("volume_24h")

            curr_price = data["price_usd"]
            curr_vol = data["volume_24h"]

            price_change_since_last = pct_change(prev_price, curr_price) if prev_price else 0.0
            mcap_change_since_last = pct_change(prev_mcap, cap) if prev_mcap else 0.0
            vol_change_since_last = pct_change(prev_vol, curr_vol) if prev_vol else 0.0

            data["change_since_last"] = price_change_since_last
            data["mcap_change_since_last"] = mcap_change_since_last
            data["vol_change_since_last"] = vol_change_since_last

            portfolio_data[symbol] = data
        except Exception as exc:
            print(f"Portfolio data error {symbol}: {exc}")
            portfolio_data[symbol] = {
                "symbol": symbol, "error": str(exc), "market_cap": 0, "market_share_pct": 0,
                "change_since_last": 0.0, "mcap_change_since_last": 0.0, "vol_change_since_last": 0.0,
            }

    prompt = build_prompt(
        market_global,
        fear,
        safety,
        news,
        portfolio_data,
        {},
        btc_data,
        state,
    )

    analysis = gemini_analyze(prompt)
    analysis = validate_and_correct_analysis(analysis, safety, portfolio_data, previous_analysis)

    # Priradenie reálnych hodnôt zmien od poslednej analýzy do výstupu
    for coin in analysis.get("coins", []):
        sym = coin.get("symbol")
        if sym in portfolio_data:
            d = portfolio_data[sym]
            coin["market_cap"] = d.get("market_cap")
            coin["market_share_pct"] = d.get("market_share_pct")
            coin["volume_24h"] = d.get("volume_24h")
            coin["market_cap_change_pct"] = d.get("mcap_change_since_last", 0.0)
            coin["volume_change_pct"] = d.get("vol_change_since_last", 0.0)

    message = format_bot_message(analysis, safety, fear)

    telegram_send_long(message)

    state["last_run"] = iso_now()
    state["last_full_analysis"] = iso_now()
    state["last_analysis"] = analysis
    state["market_safety"] = safety
    state["fear_greed"] = fear
    state["bot_version"] = VERSION

    if schedule_slot and schedule_reason != "MANUAL":
        state["last_main_slot"] = schedule_slot

    save_state(state)
    print("Hlavná analýza bola odoslaná a uložená.")


# ============================================================
# SPUSTENIE
# ============================================================

def main():
    if not GEMINI_API_KEY:
        raise RuntimeError("Chýba GEMINI_API_KEY.")

    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        raise RuntimeError("Chýba TELEGRAM_TOKEN alebo TELEGRAM_CHAT_ID.")

    run_main, reason = is_main_analysis_time()

    slot = (
        get_main_analysis_slot()
        if run_main and reason != "MANUAL"
        else None
    )

    if run_main:
        run_full_analysis(reason, slot)
    else:
        run_safety_monitor()


if __name__ == "__main__":
    main()
