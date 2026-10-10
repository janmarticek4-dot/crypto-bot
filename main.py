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
# CRYPTO AI BOT V8.4
# Stručnejší výstup, Binance 4H OHLCV, Coinbase kontrola ceny
# ============================================================

VERSION = "8.4"

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()
COINGECKO_API_KEY = os.getenv("COINGECKO_API_KEY", "").strip()

# Model môžeš zmeniť cez GitHub Actions variable GEMINI_MODEL.
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

# Záložné ID pre prípad, že CoinGecko zmení identifikátor FET.
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

# Verejné trhové endpointy; nevyžadujú API kľúče.
BINANCE_SYMBOLS = {
    "BTC": "BTCUSDT", "AAVE": "AAVEUSDT", "TAO": "TAOUSDT",
    "FET": "FETUSDT", "SOL": "SOLUSDT", "ONDO": "ONDOUSDT",
    "RENDER": "RENDERUSDT",
}
COINBASE_PRODUCTS = {
    "BTC": "BTC-USD", "AAVE": "AAVE-USD", "TAO": "TAO-USD",
    "FET": "FET-USD", "SOL": "SOL-USD", "ONDO": "ONDO-USD",
    "RENDER": "RENDER-USD",
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

    us_now = now.astimezone(US_TZ)

    if us_now.hour == 9 and 15 <= us_now.minute < 45:
        return f"US_PREOPEN_{us_now.date().isoformat()}"

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

    if "US_PREOPEN" in slot:
        return True, "US_PREOPEN"

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

            # Pri chybe autentifikácie alebo nesprávnej URL
            # nemá zmysel opakovať identickú požiadavku.
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
    # Interval neurčujeme nasilu. Dostupná granularita sa môže
    # líšiť podľa obdobia a plánu CoinGecko.
    return coingecko_get(
        f"coins/{coin_id}/market_chart",
        {
            "vs_currency": "usd",
            "days": days,
        },
    )


def binance_4h_candles(symbol, limit=300):
    """Načíta iba uzavreté 4H sviečky z verejného Binance Spot API."""
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
            continue  # nikdy nepoužívaj ešte otvorenú 4H sviečku
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
    """Záložné 4H sviečky z Coinbase: stiahne 1H sviečky a bezpečne ich spojí."""
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
        # Coinbase format: [time, low, high, open, close, volume]
        if not isinstance(row, list) or len(row) < 6:
            continue
        ts = safe_float(row[0]); low = safe_float(row[1]); high = safe_float(row[2])
        opn = safe_float(row[3]); close = safe_float(row[4]); volume = safe_float(row[5], 0)
        if any(v is None for v in (ts, low, high, opn, close)) or close <= 0:
            continue
        bucket = int(ts // 14400) * 14400
        # Ignore any 4H candle that is still open.
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
    """Nezávislá kontrola ceny; produkt nemusí byť na Coinbase dostupný."""
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
    """Skóre trendu 0–10. Nie je to pravdepodobnosť zisku."""

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
            reasons.append(
                f"RSI {rsi_value:.1f}: pozitívne momentum"
            )
        elif rsi_value > 65:
            score += 0.3
            reasons.append(
                f"RSI {rsi_value:.1f}: silné, možná prekúpenosť"
            )
        elif 40 <= rsi_value < 50:
            score -= 0.2
            reasons.append(
                f"RSI {rsi_value:.1f}: neutrálne až slabšie"
            )
        elif 30 <= rsi_value < 40:
            score -= 0.6
            reasons.append(
                f"RSI {rsi_value:.1f}: slabé momentum"
            )
        else:
            score -= 0.3
            reasons.append(
                f"RSI {rsi_value:.1f}: extrémna zóna; možný odraz aj pokles"
            )

    histogram = safe_float(
        (tech.get("macd") or {}).get("histogram")
    )

    if histogram is not None:
        if histogram > 0:
            score += 0.6
            reasons.append("MACD histogram kladný")
        elif histogram < 0:
            score -= 0.6
            reasons.append("MACD histogram záporný")

    if known_emas < 4:
        reasons.append(
            "chýbajú niektoré EMA; skóre má nižšiu istotu"
        )

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

    # Binance je primárna živá cena, CoinGecko záloha. Coinbase je len nezávislá kontrola.
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

def shortlist_candidates():
    print("Shortlisting candidate coins...")

    markets = coingecko_markets(CANDIDATES)

    if not markets:
        return []

    portfolio_ids = set(PORTFOLIO.values())
    eligible = []

    for item in markets:
        coin_id = item.get("id")

        if coin_id in portfolio_ids:
            continue

        market_cap = safe_float(item.get("market_cap"), 0)
        volume = safe_float(item.get("total_volume"), 0)

        if market_cap > 100_000_000 and volume > 5_000_000:
            eligible.append(item)

    eligible.sort(
        key=lambda item: safe_float(item.get("total_volume"), 0),
        reverse=True,
    )

    return [item["id"] for item in eligible[:3]]


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
    """
    Orientačné interné rizikové skóre:
    NORMAL 0–2, WARNING 3–6, CRITICAL 7+.
    Nie je to pravdepodobnosť krachu.
    """

    score = 0
    reasons = []

    global_change = safe_float(
        global_data.get("data", {}).get(
            "market_cap_change_percentage_24h_usd"
        )
    )

    btc_change = safe_float(
        simple_prices.get("bitcoin", {}).get("usd_24h_change")
    )

    if global_change is not None:
        if global_change <= -5:
            score += 3
            reasons.append("celková kapitalizácia prudko klesá")
        elif global_change <= -3.5:
            score += 2
            reasons.append("celková kapitalizácia výrazne klesá")
        elif global_change <= -2:
            score += 1
            reasons.append("celková kapitalizácia klesá")

    if btc_change is not None:
        if btc_change <= -7:
            score += 3
            reasons.append("BTC prudko klesá")
        elif btc_change <= -5:
            score += 2
            reasons.append("BTC výrazne klesá")
        elif btc_change <= -3:
            score += 1
            reasons.append("BTC klesá")

    tech = (
        btc_data.get("technical_4h", {})
        if isinstance(btc_data, dict) else {}
    )

    price = safe_float(tech.get("price"))
    e20 = safe_float(tech.get("ema20"))
    e50 = safe_float(tech.get("ema50"))
    e100 = safe_float(tech.get("ema100"))
    e200 = safe_float(tech.get("ema200"))
    rsi_value = safe_float(tech.get("rsi14"))
    histogram = safe_float(
        (tech.get("macd") or {}).get("histogram")
    )

    below = {
        "EMA20": price is not None and e20 is not None and price < e20,
        "EMA50": price is not None and e50 is not None and price < e50,
        "EMA100": price is not None and e100 is not None and price < e100,
        "EMA200": price is not None and e200 is not None and price < e200,
    }

    if below["EMA50"]:
        score += 1
        reasons.append("BTC je pod 4H EMA50")

    if below["EMA100"]:
        score += 1
        reasons.append("BTC je pod 4H EMA100")

    if below["EMA200"]:
        score += 2
        reasons.append("BTC je pod 4H EMA200")

    if all(below.values()):
        score += 1
        reasons.append("BTC je pod všetkými štyrmi sledovanými EMA")

    if rsi_value is not None:
        if rsi_value < 30:
            score += 2
            reasons.append(
                "BTC RSI pod 30: extrémna slabosť alebo prepredanie"
            )
        elif rsi_value < 35:
            score += 2
            reasons.append("BTC RSI pod 35")
        elif rsi_value < 40:
            score += 1
            reasons.append("BTC RSI pod 40")

    if histogram is not None and histogram < 0:
        score += 1
        reasons.append("BTC MACD histogram je záporný")

    if (
        global_change is not None
        and btc_change is not None
        and global_change <= -2
        and btc_change <= -1.5
    ):
        score += 1
        reasons.append("BTC aj celý kryptotrh klesajú súčasne")

    state = (
        "CRITICAL" if score >= 7
        else "WARNING" if score >= 3
        else "NORMAL"
    )

    warnings = []

    if not isinstance(btc_data, dict) or not tech:
        warnings.append("BTC technické dáta chýbajú")

    if global_change is None:
        warnings.append("chýba zmena celkovej kapitalizácie")

    if btc_change is None:
        warnings.append("chýba 24h zmena BTC")

    if isinstance(btc_data, dict):
        warnings.extend(btc_data.get("data_warnings", []))

    return {
        "state": state,
        "score": score,
        "reasons": reasons,
        "market_cap_change_24h": global_change,
        "btc_change_24h": btc_change,
        "btc_price": price,
        "btc_ema20": e20,
        "btc_ema50": e50,
        "btc_ema100": e100,
        "btc_ema200": e200,
        "btc_rsi14": rsi_value,
        "btc_macd_histogram": histogram,
        "data_warnings": list(dict.fromkeys(warnings)),
    }


def should_send_safety_alert(current, state):
    level = current.get("state", "NORMAL")
    score = safe_float(current.get("score"), 0)
    previous_level = state.get("last_safety_state", "NORMAL")
    previous_score = safe_float(state.get("last_safety_score"), 0)

    if level == "NORMAL":
        return False, "NORMAL"

    # Nový WARNING alebo CRITICAL, prípadne prechod späť na
    # horší stav, sa oznámi hneď.
    if level != previous_level:
        return True, "STATE_CHANGE"

    # V rámci rovnakého stavu upozorni pri zhoršení o 2 body.
    if score >= previous_score + 2:
        return True, "SCORE_WORSENING"

    return False, "NO_NEW_ALERT"


# ============================================================
# TELEGRAM
# ============================================================

def telegram_send(message):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        raise RuntimeError(
            "Chýba TELEGRAM_TOKEN alebo TELEGRAM_CHAT_ID."
        )

    url = (
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    )

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
        raise RuntimeError(
            f"Telegram odmietol správu: {result}"
        )

    print("Telegram message sent.")
    return True


def telegram_send_long(message):
    # Rezerva pod limitom Telegramu 4096 znakov.
    max_chars = 3800
    chunks = []
    current = ""

    for line in message.splitlines():
        # Ošetrenie aj jedného mimoriadne dlhého riadka.
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


# ============================================================
# SPRÁVY A GEMINI
# ============================================================

def get_rss_news():
    all_items = []

    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; CryptoAIBot/8.1)",
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

                entry = {
                    "source": source,
                    "title": "",
                    "link": "",
                    "pub_date": "",
                }

                for child in item:
                    tag = child.tag.lower()

                    if tag.endswith("title"):
                        entry["title"] = (child.text or "").strip()
                    elif tag.endswith("link"):
                        entry["link"] = (child.text or "").strip()
                    elif tag.endswith("pubdate"):
                        entry["pub_date"] = (child.text or "").strip()

                if entry["title"]:
                    all_items.append(entry)
                    count += 1

                if count >= 10:
                    break

        except Exception as exc:
            print(f"RSS error {source}: {exc}")

    return all_items[:20]


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
            raise TimeoutError(
                "Gemini analýza trvá dlhšie ako 10 minút."
            )

        interaction = client.interactions.get(id=interaction_id)
        status = interaction.status

        if status == "completed":
            if not interaction.output_text:
                raise RuntimeError("Gemini vrátil prázdny výstup.")

            return parse_json_output(interaction.output_text)

        if status in {
            "failed",
            "cancelled",
            "expired",
            "incomplete",
            "requires_action",
        }:
            raise RuntimeError(
                f"Gemini analýza skončila: {status}"
            )

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
                "outlook_direction": coin.get("outlook_direction"),
                "outlook_pct": coin.get("outlook_pct"),
                "technical_score": coin.get("technical_score"),
                "fundamental_score": coin.get("fundamental_score"),
                "reason": coin.get("reason"),
            })

    accuracy = forecast_accuracy_summary(state)

    return f"""
Si disciplinovaný analytik kryptomien a správca rizika.
Píš po slovensky, zrozumiteľne a bez zbytočného žargónu.

Čas Bratislava: {iso_now()}
Portfólio: AAVE, TAO, FET, SOL, ONDO, RENDER.
APTOS nikdy neodporúčaj ako novú investíciu.

DÁTA A OVEROVANIE:
- Používaj dodané trhové dáta ako základ technickej analýzy.
- Google Search používaj na overovanie aktuálnych správ a fundamentov.
- Nezamieňaj cenu z vyhľadávania za dodanú aktuálnu cenu.
- Nevymýšľaj citácie, zdroje, ceny, partnerstvá, príjmy ani udalosti.
- Rozlišuj potvrdený fakt, odhad a nepotvrdenú správu.
- Titulok RSS sám osebe nepotvrdzuje pravdivosť správy.
- Ak sa zdroje rozchádzajú, vysvetli to.
- Ak chýbajú dáta, výslovne to uveď a zníž istotu.
- Nekombinuj ceny z rôznych časov bez upozornenia.
- Technické skóre z Pythonu musíš zachovať presne.
- Skóre techniky nie je pravdepodobnosť zisku.
- Nepredstieraj, že máš dáta o likvidáciách, on-chain aktivite
  alebo ETF tokoch, ak ich nemáš overené.

ODPORÚČANIA:
Pre každú mincu vyber jednu akciu:
BUY NOW, BUY PULLBACK, HOLD, REDUCE, SELL, NO TRADE.

BUY NOW:
Len pri potvrdenom trende, primeranom riziku a rozumnom pomere
možného zisku k strate. Nákup nesmie byť automatický len preto,
že cena klesla.

BUY PULLBACK:
Nákup až po dosiahnutí zóny a potvrdení obratu.
Samotné dosiahnutie ceny nepotvrdzuje odraz.

HOLD:
Držať existujúcu pozíciu. Nové nákupy posudzuj samostatne.

REDUCE:
Zmenšiť pozíciu len pri konkrétnom a potvrdenom zhoršení.
Uveď dôvod a čo by zmenilo názor.

SELL:
Úplný odchod vyžaduje silný dôvod. Jedno RSI, EMA alebo jedna
červená sviečka nestačí. Zohľadni trend, momentum, podporu,
fundament a riziko ďalšieho prudkého pohybu.

NO TRADE:
Nie je dostatočná výhoda alebo chýbajú kvalitné dáta.

TECHNICKÁ ANALÝZA:
- RSI pod 30 môže znamenať prepredanie aj pokračovanie poklesu.
- Cena pod EMA200 sama osebe nie je pokynom na predaj.
- Rozlišuj živú cenu a posledné uzavretie 4H grafu.
- Nepíš, že cena testuje podporu, ak je od nej ďaleko.
- Podpora z posledných 30 sviečok nie je automaticky dlhodobá podpora.
- Jedna živá cena pod podporou nepotvrdzuje prelomenie.
- Nevymýšľaj objemové signály ani on-chain údaje.

FUNDAMENT:
Skóre 0–10 odôvodni podľa využitia, adopcie, príjmov, tokenomiky,
odomknutí tokenov, konkurencie a overených správ.
Dobrá technológia automaticky neznamená lacný token.
Ak nemáš dostatok dôkazov, daj nízku istotu.

PRAVDEPODOBNOSTI:
Bull a bear musia spolu dať 100.
Sú to subjektívne odhady, nie štatisticky kalibrované pravdepodobnosti.
Nevytváraj falošnú presnosť. Pri nejasnom vývoji sa približ k 50/50.

NOVÉ PENIAZE:
Nedávaj BUY len preto, aby bol report akčný.
Ak neexistuje potvrdená výhoda, odporuč hotovosť.
Nová minca musí byť lepšia než existujúce alternatívy po zohľadnení
rizika a korelácie s portfóliom.

PREDCHÁDZAJÚCA ANALÝZA:
Porovnaj aktuálnu situáciu s minulou analýzou.
Nedrž staré odporúčanie len zo zotrvačnosti.
Vysvetli, čo sa zmenilo a čo by vyvrátilo aktuálny scenár.

POVINNÝ ŠTÝL VÝSTUPU:
- Analýza je určená na rýchle rozhodnutie, nie na dlhý komentár.
- Nevypisuj zdroje, názvy API, odkazy ani metodiku do Telegram výstupu.
- Pri každej minci uveď najviac: AKCIA, cena, dôvod v 1 vete,
  podmienka pre nákup/predaj a úroveň, pri ktorej sa scenár ruší.
- Nepíš samostatne bull/bear scenáre, fundamentálne dôkazy a technické signály,
  ak sa opakujú v dôvode alebo akcii.
- Nepoužívaj falošne presné percentá; ak nie sú dáta dostatočné, povedz to.
- Najprv jasný súhrn trhu a bezpečnostný stav, potom akčný plán portfólia,
  nakoniec maximálne 1 nová príležitosť a 2–3 podmienky, ktoré treba sledovať.
- Celý text pre Telegram má byť stručný; približne 1 000–1 500 znakov, ak to dáta umožňujú.

MARKET GLOBAL:
{json.dumps(market_global, ensure_ascii=False)}

FEAR & GREED:
{json.dumps(fear_greed, ensure_ascii=False)}

SAFETY:
{json.dumps(safety, ensure_ascii=False)}

BTC DATA:
{json.dumps(btc_data, ensure_ascii=False)}

PORTFOLIO DATA:
{json.dumps(portfolio_data, ensure_ascii=False)}

CANDIDATES:
{json.dumps(candidate_data, ensure_ascii=False)}

RSS NEWS:
{json.dumps(news, ensure_ascii=False)}

PREVIOUS ANALYSIS:
{json.dumps(prior_summary, ensure_ascii=False)}

HISTORICKÁ PRESNOSŤ:
{json.dumps(accuracy, ensure_ascii=False)}

Vráť iba validný JSON v tejto štruktúre:
{{
 "market_regime":"string",
 "market_summary":"string",
 "new_coin":"string",
 "new_coin_action":"BUY NOW or BUY PULLBACK or NO TRADE",
 "new_coin_reason":"string",
 "coins":[
  {{
   "symbol":"AAVE",
   "action":"HOLD",
   "buy_zone_1":"cenová zóna alebo N/A",
   "buy_zone_2":"cenová zóna alebo N/A",
   "invalidation":"cena a podmienka",
   "tp1":"cena alebo N/A",
   "tp2":"cena alebo N/A",
   "bull_probability":50,
   "bear_probability":50,
   "outlook_direction":"rast/pokles/do strany",
   "outlook_pct":0,
   "outlook_probability":50,
   "fundamental_score":5,
   "fundamental_confidence":"nízka/stredná/vysoká",
   "fundamental_evidence":"dôvody a limity dát",
   "reason":"rozhodnutie o existujúcej pozícii",
   "new_money_plan":"plán pre nové peniaze",
   "bear_case":"medvedí scenár",
   "bull_case":"býčí scenár",
   "confirmation_needed":"čo presne musí nastať",
   "previous_comparison":"zmena oproti minulosti"
  }}
 ],
 "best_opportunity":"string",
 "avoid":"string",
 "conditions_to_watch":["string"]
}}

V poli coins uveď presne AAVE, TAO, FET, SOL, ONDO, RENDER.
Každú mincu uveď raz. Nepoužívaj Markdown mimo JSON.
"""


# ============================================================
# VALIDÁCIA ODPORÚČANÍ
# ============================================================

def price_number(value):
    if value is None:
        return None

    text = str(value).replace("–", "-").replace("—", "-").replace("−", "-")
    text = text.replace(",", ".")

    matches = re.findall(
        r"(?<![A-Za-z])(?:\d+(?:\.\d+)?|\.\d+)",
        text,
    )

    try:
        return float(matches[0]) if matches else None
    except (ValueError, TypeError):
        return None


def price_range(value):
    if value is None:
        return None

    text = str(value).replace("–", "-").replace("—", "-").replace("−", "-")
    text = text.replace(",", ".")

    values = re.findall(
        r"(?<![A-Za-z])(?:\d+(?:\.\d+)?|\.\d+)",
        text,
    )

    try:
        numbers = [float(value) for value in values]

        if not numbers:
            return None

        return (
            min(numbers[:2]),
            max(numbers[:2]),
        )

    except ValueError:
        return None


def calculate_rr(buy_zone, invalidation, tp1, tp2):
    zone = price_range(buy_zone)
    invalid = price_number(invalidation)
    target1 = price_number(tp1)
    target2 = price_number(tp2)

    if (
        not zone
        or invalid is None
        or target1 is None
        or target2 is None
    ):
        return None

    entry = sum(zone) / 2
    risk = entry - invalid

    if risk <= 0 or target1 <= entry or target2 <= entry:
        return None

    return {
        "rr_tp1": (target1 - entry) / risk,
        "rr_tp2": (target2 - entry) / risk,
    }


def validate_and_correct_analysis(
    analysis,
    safety,
    portfolio_data,
    previous_analysis,
):
    if not isinstance(analysis, dict):
        raise RuntimeError("Gemini neposlal JSON objekt.")

    if not isinstance(analysis.get("coins"), list):
        raise RuntimeError("Gemini neposlal zoznam coins.")

    previous_coins = previous_analysis.get("coins", [])

    previous = {
        str(coin.get("symbol", "")).upper(): coin
        for coin in previous_coins
        if isinstance(coin, dict)
    }

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
                "reason": (
                    "Chýba platné odporúčanie; použitá bezpečná "
                    "náhrada HOLD."
                ),
                "fundamental_evidence": (
                    "Analýza pre túto mincu nebola dodaná."
                ),
            }

        coin["symbol"] = symbol

        data = portfolio_data.get(symbol, {})
        actual_price = safe_float(data.get("price_usd"))
        tech = data.get("technical_4h", {})
        calc = data.get("technical_score_calc", {})

        if actual_price is not None:
            coin["current_price"] = actual_price

        coin["technical_score"] = calc.get("score")
        coin["technical_score_label"] = calc.get(
            "label", "nedostatok dát"
        )
        coin["technical_score_reasons"] = calc.get("reasons", [])
        coin["data_warnings"] = data.get("data_warnings", [])

        if data.get("error") or actual_price is None:
            coin["action"] = "NO TRADE"
            coin["action_guard_note"] = (
                "Nedostatočné aktuálne dáta. Odporúčanie nákupu "
                "alebo predaja nemožno považovať za spoľahlivé."
            )

        # Nula je platná hodnota. Nepoužívame výraz x or 5,
        # ktorý by nulu nesprávne zmenil na päť.
        fundamental_score = safe_float(
            coin.get("fundamental_score"), 5
        )

        if fundamental_score is None:
            fundamental_score = 5

        coin["fundamental_score"] = round(
            clamp(fundamental_score, 0, 10), 1
        )

        confidence = str(
            coin.get("fundamental_confidence", "nízka")
        ).lower()

        if confidence not in {"nízka", "stredná", "vysoká"}:
            confidence = "nízka"

        coin["fundamental_confidence"] = confidence
        coin["fundamental_evidence"] = str(
            coin.get("fundamental_evidence", "Chýbajú dôkazy.")
        )

        action = str(coin.get("action", "HOLD")).upper().strip()

        if action not in VALID_ACTIONS:
            action = "HOLD"

        tech_price = safe_float(tech.get("price"))
        ema50_value = safe_float(tech.get("ema50"))
        ema200_value = safe_float(tech.get("ema200"))
        rsi_value = safe_float(tech.get("rsi14"))
        histogram = safe_float(
            (tech.get("macd") or {}).get("histogram")
        )
        support = safe_float(tech.get("support_30_candles"))

        below_50_200 = (
            tech_price is not None
            and ema50_value is not None
            and ema200_value is not None
            and tech_price < ema50_value
            and tech_price < ema200_value
        )

        momentum_negative = (
            histogram is not None and histogram < 0
        )

        support_broken = (
            tech_price is not None
            and support is not None
            and tech_price < support * 0.995
        )

        bearish_signals = sum([
            bool(below_50_200),
            bool(momentum_negative),
            bool(support_broken),
        ])

        # Predaj vyžaduje aspoň dva signály zhoršenia.
        if action in {"SELL", "REDUCE"} and bearish_signals < 2:
            coin["action_guard_note"] = (
                "Predaj upravený na HOLD: neboli zistené aspoň "
                "dva nezávislé technické signály zhoršenia."
            )
            action = "HOLD"

        # Ak je RSI pod 30, úplný predaj vyžaduje všetky tri
        # technické signály. Prepredanie môže pokračovať, ale
        # môže tiež nasledovať prudký odraz.
        elif (
            action == "SELL"
            and rsi_value is not None
            and rsi_value < 30
            and bearish_signals < 3
        ):
            coin["action_guard_note"] = (
                "SELL upravený na HOLD: RSI je pod 30 a pokles "
                "nie je potvrdený všetkými tromi signálmi."
            )
            action = "HOLD"

        if safety.get("state") == "CRITICAL" and action == "BUY NOW":
            coin["action_guard_note"] = (
                str(coin.get("action_guard_note", "")) +
                " Safety CRITICAL: BUY NOW upravené na BUY PULLBACK."
            ).strip()
            action = "BUY PULLBACK"

        if (
            calc.get("score") is None
            and action in {"BUY NOW", "BUY PULLBACK"}
        ):
            action = "NO TRADE"
            coin["action_guard_note"] = (
                "Nákup zablokovaný: chýbajú technické dáta."
            )

        coin["action"] = action

        bull = safe_float(coin.get("bull_probability"), 50)

        if bull is None:
            bull = 50

        if 0 < bull <= 1:
            bull *= 100

        bull = clamp(bull, 0, 100)

        if safety.get("state") == "WARNING":
            bull = min(bull, 65)
        elif safety.get("state") == "CRITICAL":
            bull = min(bull, 55)

        coin["bull_probability"] = round(bull)
        coin["bear_probability"] = round(100 - bull)

        outlook_prob = safe_float(
            coin.get("outlook_probability"), 50
        )

        if outlook_prob is None:
            outlook_prob = 50

        coin["outlook_probability"] = round(
            clamp(outlook_prob, 5, 95)
        )

        outlook_pct = safe_float(coin.get("outlook_pct"), 0)

        if outlook_pct is None:
            outlook_pct = 0

        coin["outlook_pct"] = round(
            clamp(outlook_pct, -30, 30), 2
        )

        direction = str(
            coin.get("outlook_direction", "do strany")
        ).lower().strip()

        if direction not in {"rast", "pokles", "do strany"}:
            direction = "do strany"

        coin["outlook_direction"] = direction

        old = previous.get(symbol, {})
        old_action = str(old.get("action", "")).upper()

        if old:
            coin["action_change"] = (
                f"{old_action} → {action}"
                if old_action and old_action != action
                else "Akcia bez zmeny"
            )

            coin["previous_price"] = old.get("current_price")

            old_price = safe_float(old.get("current_price"))
            old_score = safe_float(old.get("technical_score"))
            new_score = safe_float(calc.get("score"))
            price_change = pct_change(old_price, actual_price)

            comparison_parts = []
            if old_price is not None and actual_price is not None and old_price > 0:
                comparison_parts.append(
                    f"cena {format_price(old_price)} → {format_price(actual_price)} "
                    f"({price_change:+.2f}%)"
                    if price_change is not None
                    else f"cena {format_price(old_price)} → {format_price(actual_price)}"
                )
            else:
                comparison_parts.append("chýba porovnateľná staršia cena")

            if old_score is not None and new_score is not None:
                comparison_parts.append(
                    f"technika {old_score:.1f} → {new_score:.1f}/10"
                )

            if old_action:
                comparison_parts.append(f"akcia {old_action} → {action}")

            # Nepoužívame voľný text od Gemini pre historické porovnanie:
            # porovnanie sa počíta z reálne uložených cien a skóre.
            coin["previous_comparison"] = "; ".join(comparison_parts)
        else:
            coin["action_change"] = "Prvá uložená analýza"
            coin["previous_comparison"] = (
                "Zatiaľ nie je staršia analýza na porovnanie."
            )

        rr = calculate_rr(
            coin.get("buy_zone_1"),
            coin.get("invalidation"),
            coin.get("tp1"),
            coin.get("tp2"),
        )

        coin["risk_reward"] = (
            f"1:{rr['rr_tp1']:.1f} / 1:{rr['rr_tp2']:.1f}"
            if rr else "N/A"
        )

        validated.append(coin)

    analysis["coins"] = validated
    analysis["action"] = "INDIVIDUAL COIN ACTIONS"

    new_coin_action = str(
        analysis.get("new_coin_action", "NO TRADE")
    ).upper().strip()

    if new_coin_action not in {"BUY NOW", "BUY PULLBACK", "NO TRADE"}:
        new_coin_action = "NO TRADE"

    if safety.get("state") == "CRITICAL" and new_coin_action == "BUY NOW":
        new_coin_action = "BUY PULLBACK"

    analysis["new_coin_action"] = new_coin_action

    if new_coin_action == "NO TRADE":
        analysis["new_coin"] = "NO TRADE"

    return analysis


# ============================================================
# KONTROLA PREDCHÁDZAJÚCICH PREDPOVEDÍ
# ============================================================

def evaluate_previous_forecasts(state, current_data):
    """
    Vyhodnocuje predpovede po najmenej 23 hodinách.
    Každá predpoveď má vlastnú časovú značku a vyhodnotí sa raz.
    """

    forecasts = state.get("forecast_history", [])
    evaluations = state.get("forecast_evaluations", [])

    evaluated_keys = {
        (
            item.get("forecast_timestamp"),
            item.get("symbol"),
        )
        for item in evaluations
        if isinstance(item, dict)
    }

    now = datetime.now(timezone.utc)
    results = []

    for forecast in forecasts[-500:]:
        try:
            if not isinstance(forecast, dict):
                continue

            symbol = forecast.get("symbol")
            timestamp = forecast.get("timestamp")

            if not symbol or not timestamp:
                continue

            key = (timestamp, symbol)

            if key in evaluated_keys:
                continue

            created = parse_timestamp(timestamp)

            if created is None:
                continue

            age_hours = (now - created).total_seconds() / 3600

            if age_hours < 23:
                continue

            price_now = safe_float(
                current_data.get(symbol, {}).get("price_usd")
            )
            price_then = safe_float(forecast.get("price"))

            if price_now is None or price_then is None:
                continue

            if price_now <= 0 or price_then <= 0:
                continue

            actual_pct = pct_change(price_then, price_now)

            if actual_pct is None:
                continue

            predicted_pct = safe_float(forecast.get("outlook_pct"), 0)

            if predicted_pct is None:
                predicted_pct = 0

            predicted_dir = str(
                forecast.get("outlook_direction", "do strany")
            ).lower()

            actual_dir = (
                "rast" if actual_pct > 0.5
                else "pokles" if actual_pct < -0.5
                else "do strany"
            )

            results.append({
                "forecast_timestamp": timestamp,
                "symbol": symbol,
                "predicted_pct": round(predicted_pct, 2),
                "actual_pct": round(actual_pct, 2),
                "predicted_direction": predicted_dir,
                "actual_direction": actual_dir,
                "direction_hit": predicted_dir == actual_dir,
                "absolute_error_pct": round(
                    abs(predicted_pct - actual_pct), 2
                ),
                "age_hours": round(age_hours, 1),
            })

            evaluated_keys.add(key)

        except Exception as exc:
            print(f"Forecast evaluation error: {exc}")

    return results


def forecast_accuracy_summary(state):
    history = state.get("forecast_evaluations", [])

    usable = [
        item for item in history
        if isinstance(item, dict)
        and "direction_hit" in item
        and safe_float(item.get("absolute_error_pct")) is not None
    ]

    if not usable:
        return {
            "sample_size": 0,
            "direction_accuracy_pct": None,
            "mean_absolute_error_pct": None,
        }

    hits = sum(bool(item["direction_hit"]) for item in usable)

    errors = [
        safe_float(item.get("absolute_error_pct"))
        for item in usable
    ]

    return {
        "sample_size": len(usable),
        "direction_accuracy_pct": round(
            hits / len(usable) * 100, 1
        ),
        "mean_absolute_error_pct": round(
            sum(errors) / len(errors), 2
        ),
    }


# ============================================================
# FORMÁTOVANIE SPRÁV
# ============================================================

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


def format_safety_alert(safety, fear_greed, portfolio_analysis=None):
    critical = safety.get("state") == "CRITICAL"

    lines = [
        (
            "🚨 CRYPTO AI BOT — KRÍZOVÝ ALERT"
            if critical
            else "⚠️ CRYPTO AI BOT — BEZPEČNOSTNÝ ALERT"
        ),
        "",
        f"🛡 Safety: {safety.get('state')} "
        f"({safety.get('score', 0)})",
        "Upozornenie na riziko, nie automatický pokyn na predaj.",
    ]

    for key, label in [
        ("btc_change_24h", "BTC 24h"),
        ("market_cap_change_24h", "Market cap 24h"),
    ]:
        value = safe_float(safety.get(key))

        if value is not None:
            lines.append(f"{label}: {value:+.2f}%")

    for key, label in [
        ("btc_ema20", "BTC 4H EMA20"),
        ("btc_ema50", "BTC 4H EMA50"),
        ("btc_ema100", "BTC 4H EMA100"),
        ("btc_ema200", "BTC 4H EMA200"),
    ]:
        value = safe_float(safety.get(key))

        if value is not None:
            lines.append(f"{label}: {format_price(value)}")

    rsi_value = safe_float(safety.get("btc_rsi14"))

    if rsi_value is not None:
        lines.append(f"BTC 4H RSI: {rsi_value:.1f}")

    if fear_greed.get("value") is not None:
        lines.append(
            f"Fear & Greed: {fear_greed['value']}/100 "
            f"({fear_greed.get('classification', '')})"
        )

    if safety.get("reasons"):
        lines.extend([
            "",
            "Dôvody:",
            *[f"• {reason}" for reason in safety["reasons"][:8]],
        ])

    if safety.get("data_warnings"):
        lines.extend([
            "",
            "Upozornenia na dáta:",
            *[
                f"• {warning}"
                for warning in safety["data_warnings"][:4]
            ],
        ])

    if portfolio_analysis:
        lines.extend(["", "📊 PORTFÓLIO — KONTEXT:"])

        for item in portfolio_analysis:
            lines.append(
                f"• {item['symbol']} {format_price(item.get('price'))}: "
                f"posledná akcia {item.get('action', 'N/A')}; "
                f"RSI {item.get('rsi', 'N/A')}; "
                f"technika {item.get('technical_score', 'N/A')}/10"
            )

            lines.append(f"  {item.get('interpretation', '')}")

    lines.extend([
        "",
        "RSI, EMA200 ani vzdialenosť od podpory samy osebe "
        "nepotvrdzujú budúci prepad.",
        "Pozn.: 4H ukazovatele sú približne odvodené z cenových bodov CoinGecko, nie z burzových OHLC sviečok.",
        "Sleduj uzavretie 4H sviečok, podporu, MACD a širší trh.",
    ])

    return "\n".join(lines)


def coin_priority(coin):
    return {
        "SELL": 0,
        "REDUCE": 1,
        "BUY NOW": 2,
        "BUY PULLBACK": 3,
        "HOLD": 4,
        "NO TRADE": 5,
    }.get(str(coin.get("action", "")).upper(), 6)


def format_bot_message(analysis, safety, fear_greed, forecast_results=None, accuracy=None):
    """Krátky Telegram výstup: jasné rozhodnutia bez zoznamu zdrojov a opakovaní."""
    coins = sorted(analysis.get("coins", []), key=coin_priority)
    lines = [
        f"📊 CRYPTO BOT V{VERSION} | 4H",
        f"🕒 {now_local().strftime('%d.%m. %H:%M')}",
        f"🌐 Trh: {analysis.get('market_regime', 'N/A')} | Riziko: {safety.get('state', 'N/A')} ({safety.get('score', 0)})",
    ]
    reasons = safety.get("reasons", [])
    if reasons:
        lines.append("⚠️ " + "; ".join(str(x) for x in reasons[:2]))
    if fear_greed.get("value") is not None:
        lines.append(f"Sentiment: {fear_greed['value']}/100 ({fear_greed.get('classification', '')})")
    lines.extend(["", "📌 AKČNÝ PLÁN"])
    for coin in coins:
        action = str(coin.get("action", "HOLD")).upper()
        symbol = coin.get("symbol", "?")
        emoji = "🔴" if action in {"SELL", "REDUCE"} else "🟢" if action.startswith("BUY") else "🟡"
        price = format_price(coin.get("current_price"))
        reason = str(coin.get("reason") or coin.get("new_money_plan") or "Bez jasného nového signálu.").strip()
        reason = re.sub(r"\s+", " ", reason)
        if len(reason) > 170:
            reason = reason[:167].rstrip() + "..."
        lines.append(f"{emoji} {symbol} — {action} | {price}")
        lines.append(f"   {reason}")
        if action in {"BUY NOW", "BUY PULLBACK"}:
            zone = coin.get("buy_zone_1") or coin.get("buy_zone_2") or "potvrdenie trendu"
            invalid = coin.get("invalidation")
            lines.append(f"   Nákup: {zone}" + (f" | Zrušiť plán: {invalid}" if invalid and invalid != "N/A" else ""))
        elif action in {"REDUCE", "SELL"}:
            invalid = coin.get("invalidation")
            if invalid and invalid != "N/A":
                lines.append(f"   Hranica scenára: {invalid}")
    best = str(analysis.get("best_opportunity", "")).strip()
    if best and best.lower() not in {"n/a", "none", "žiadna"}:
        if len(best) > 220:
            best = best[:217].rstrip() + "..."
        lines.extend(["", f"⭐ Najlepšia príležitosť: {best}"])
    new_coin = str(analysis.get("new_coin", "NO TRADE")).strip()
    new_action = str(analysis.get("new_coin_action", "NO TRADE")).upper()
    if new_coin and new_coin.upper() not in {"NO TRADE", "N/A", "NONE", "ŽIADNA"} and new_action in {"BUY NOW", "BUY PULLBACK"}:
        new_reason = str(analysis.get("new_coin_reason", "")).strip()
        if len(new_reason) > 180:
            new_reason = new_reason[:177].rstrip() + "..."
        lines.extend(["", f"🆕 Kandidát: {new_coin} — {new_action}"])
        if new_reason:
            lines.append(new_reason)
    avoid = str(analysis.get("avoid", "")).strip()
    if avoid and avoid.lower() not in {"n/a", "none"}:
        if len(avoid) > 180:
            avoid = avoid[:177].rstrip() + "..."
        lines.extend(["", f"⛔ Vyhnúť sa: {avoid}"])
    conditions = analysis.get("conditions_to_watch", [])
    if conditions:
        lines.extend(["", "👀 Sleduj: " + " | ".join(str(x) for x in conditions[:3])])
    if accuracy and accuracy.get("sample_size", 0) >= 10:
        lines.extend(["", f"📏 Kontrola minulých odhadov: {accuracy.get('direction_accuracy_pct', 'N/A')} % správny smer ({accuracy.get('sample_size')} prípadov)"])
    lines.extend(["", "Odhady nie sú zárukou. Bot nevykonáva obchody."])
    return "\n".join(lines)


# ============================================================
# BEZPEČNOSTNÝ MONITOR
# ============================================================

def run_safety_monitor():
    market_global = coingecko_get("global")
    simple = coingecko_simple_price(["bitcoin"])
    fear = get_fear_greed()

    try:
        btc = collect_coin_data("BTC", "bitcoin", days=35)
    except Exception as exc:
        print(f"BTC technical data error: {exc}")
        btc = {
            "data_warnings": [
                f"Zber BTC technických dát zlyhal: {exc}"
            ],
            "technical_4h": {},
        }

    safety = market_safety(market_global, simple, btc)
    state = load_state()
    previous = state.get("last_analysis", {})

    prev_coins = {
        str(coin.get("symbol", "")).upper(): coin
        for coin in previous.get("coins", [])
        if isinstance(coin, dict)
    }

    portfolio_context = []

    for symbol, coin_id in PORTFOLIO.items():
        try:
            data = collect_coin_data(
                symbol, coin_id, days=35
            )

            tech = data.get("technical_4h", {})
            price = safe_float(data.get("price_usd"))
            rsi_value = safe_float(tech.get("rsi14"))
            previous_coin = prev_coins.get(symbol, {})

            if rsi_value is not None and rsi_value < 30:
                interpretation = (
                    "Prepredané; možný odraz aj pokračovanie poklesu. "
                    "Nie je to samostatný signál na predaj."
                )
            elif tech.get("above_ema200") is False:
                interpretation = (
                    "Zvýšené riziko, ale samotná EMA200 "
                    "nepotvrdzuje predaj."
                )
            else:
                interpretation = (
                    "Indikátory samy osebe nepotvrdzujú nútený predaj."
                )

            portfolio_context.append({
                "symbol": symbol,
                "price": price,
                "rsi": (
                    round(rsi_value, 1)
                    if rsi_value is not None else "N/A"
                ),
                "technical_score": data.get(
                    "technical_score_calc", {}
                ).get("score"),
                "action": previous_coin.get("action", "N/A"),
                "interpretation": interpretation,
            })

        except Exception as exc:
            print(f"Safety monitor error for {symbol}: {exc}")

    should_alert, reason = should_send_safety_alert(
        safety, state
    )

    if should_alert:
        telegram_send_long(
            format_safety_alert(
                safety, fear, portfolio_context
            )
        )

        state["last_safety_alert"] = iso_now()
        state["last_safety_alert_reason"] = reason

    state["last_safety_state"] = safety.get("state", "NORMAL")
    state["last_safety_score"] = safety.get("score", 0)
    state["last_safety_check"] = iso_now()
    state["market_safety"] = safety
    state["fear_greed"] = fear
    state["bot_version"] = VERSION

    save_state(state)
    return safety


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

    portfolio_data = {}

    for symbol, coin_id in PORTFOLIO.items():
        try:
            portfolio_data[symbol] = collect_coin_data(
                symbol, coin_id
            )

        except Exception as exc:
            print(f"Portfolio data error {symbol}: {exc}")

            portfolio_data[symbol] = {
                "symbol": symbol,
                "coin_id": coin_id,
                "error": str(exc),
                "data_warnings": [
                    "Zber dát zlyhal; odporúčania tejto mince sú obmedzené."
                ],
                "technical_4h": {},
                "technical_score_calc": {
                    "score": None,
                    "label": "nedostatok dát",
                    "reasons": [],
                    "known_emas": 0,
                },
            }

    candidate_data = {}

    try:
        candidate_ids = shortlist_candidates()
    except Exception as exc:
        print(f"Candidate shortlist error: {exc}")
        candidate_ids = []

    for coin_id in candidate_ids:
        try:
            candidate_data[coin_id.upper()] = collect_coin_data(
                coin_id.upper(), coin_id
            )

        except Exception as exc:
            print(f"Candidate data error {coin_id}: {exc}")

            candidate_data[coin_id.upper()] = {
                "coin_id": coin_id,
                "error": str(exc),
                "data_warnings": ["Zber dát kandidáta zlyhal."],
            }

    state = load_state()
    previous_analysis = state.get("last_analysis", {})

    prompt = build_prompt(
        market_global,
        fear,
        safety,
        news,
        portfolio_data,
        candidate_data,
        btc_data,
        state,
    )

    analysis = gemini_analyze(prompt)

    analysis = validate_and_correct_analysis(
        analysis,
        safety,
        portfolio_data,
        previous_analysis,
    )

    # Vyhodnotenie starých predpovedí pred pridaním nových.
    forecast_results = evaluate_previous_forecasts(
        state, portfolio_data
    )

    evaluations = state.get("forecast_evaluations", [])

    existing_keys = {
        (
            item.get("forecast_timestamp"),
            item.get("symbol"),
        )
        for item in evaluations
        if isinstance(item, dict)
    }

    for result in forecast_results:
        key = (
            result.get("forecast_timestamp"),
            result.get("symbol"),
        )

        if key in existing_keys:
            continue

        evaluations.append({
            **result,
            "evaluated_at": utc_now_iso(),
        })

        existing_keys.add(key)

    state["forecast_evaluations"] = evaluations[-500:]
    accuracy = forecast_accuracy_summary(state)

    message = format_bot_message(
        analysis,
        safety,
        fear,
        forecast_results,
        accuracy,
    )

    # Predpovede sa ukladajú s presnou časovou značkou a cenou.
    # Táto značka sa používa na jednoznačné vyhodnotenie o deň neskôr.
    history = state.get("forecast_history", [])
    now_utc = utc_now_iso()

    for coin in analysis.get("coins", []):
        history.append({
            "timestamp": now_utc,
            "symbol": coin["symbol"],
            "price": safe_float(coin.get("current_price")),
            "outlook_direction": str(
                coin.get("outlook_direction", "do strany")
            ).lower(),
            "outlook_pct": safe_float(
                coin.get("outlook_pct"), 0
            ),
        })

    state["forecast_history"] = history[-500:]

    # Najprv doruč správu. Až potom označ časový slot ako hotový.
    telegram_send_long(message)

    state["last_run"] = iso_now()
    state["last_full_analysis"] = iso_now()
    state["last_analysis_reason"] = schedule_reason
    state["market_safety"] = safety
    state["fear_greed"] = fear
    state["btc_data"] = btc_data
    state["last_analysis"] = analysis
    state["last_main_schedule"] = schedule_reason
    state["last_safety_state"] = safety.get("state", "NORMAL")
    state["last_safety_score"] = safety.get("score", 0)
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
        raise RuntimeError(
            "Chýba TELEGRAM_TOKEN alebo TELEGRAM_CHAT_ID."
        )

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
