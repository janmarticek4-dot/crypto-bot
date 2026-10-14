import os
import json
import time
import re
import math
import urllib.request
import urllib.parse
import urllib.error
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo

from google import genai


# ============================================================
# CRYPTO AI BOT V10.3
# Inteligentný analytik kryptomien a ochranca investičného portfólia.
#
# Princíp: čísla, signály, bezpečnostné stavy a hladiny počíta KÓD.
# Gemini (1) vyhľadáva fundamentálne podklady (len 07:00 a pri prepade
# nad 10 %) a (2) vysvetľuje hotové čísla. Gemini nikdy nemení signál.
# Bot neobchoduje, iba analyzuje a upozorňuje.
# ============================================================

VERSION = "10.3"

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

COIN_NAMES = {
    "BTC": "Bitcoin",
    "AAVE": "Aave",
    "TAO": "Bittensor",
    "FET": "Artificial Superintelligence Alliance (FET, bývalý Fetch.ai)",
    "SOL": "Solana",
    "ONDO": "Ondo Finance",
    "RENDER": "Render (RENDER)",
}

# Kľúčové slová na priradenie RSS titulkov k minciam
NEWS_KEYWORDS = {
    "BTC": ["bitcoin", "btc"],
    "AAVE": ["aave"],
    "TAO": ["bittensor", "tao "],
    "FET": ["fetch.ai", "fetch ai", "superintelligence alliance", "asi alliance", "singularitynet", "ocean protocol"],
    "SOL": ["solana"],
    "ONDO": ["ondo"],
    "RENDER": ["render network", "render token", "rndr"],
}

RSS_FEEDS = [
    ("CoinTelegraph", "https://cointelegraph.com/rss"),
    ("CoinDesk", "https://www.coindesk.com/arc/outboundfeeds/rss/"),
]

VALID_ACTIONS = {
    "BUY NOW",
    "BUY PULLBACK",
    "HOLD",
    "WAIT",
    "REDUCE",
    "SELL",
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
# KONFIGURÁCIA PRAHOV — všetko na jednom mieste
# ============================================================

CONFIG = {
    # --- Pokles od lokálneho maxima (7 dní) ---
    "drawdown_review_pct": 6.0,         # spustí podrobné posúdenie rizika
    "drawdown_review_adaptive": True,   # prah = max(6 %, násobok dennej volatility mince)
    "drawdown_review_vol_mult": 1.0,
    "drawdown_deep_pct": 10.0,          # hlboký prepad -> hlboké hľadanie príčin
    "peak_lookback_candles": 42,        # 42 x 4H = 7 dní

    # --- Bezpečnostný stav trhu (so setrvačnosťou, aby stav neblikal) ---
    "safety_warning_score": 4,
    "safety_critical_score": 8,
    "safety_exit_warning_below": 3,     # z WARNING späť na NORMAL až pod toto skóre
    "safety_exit_critical_below": 6,    # z CRITICAL späť až pod toto skóre

    # --- Rizikové body mince -> úroveň rizika ---
    "risk_elevated_pts": 3,
    "risk_high_pts": 5,
    "risk_severe_pts": 7,
    "sell_pts": 8,                      # SELL vyžaduje aj slabý trend (skóre <= 3.5)

    # --- Signály nákupu ---
    "buy_now_min_score": 6.5,
    "buy_pullback_min_score": 5.0,
    "stabilized_dip_min_drawdown": 4.0,
    "greed_caution_value": 80,          # Fear & Greed >= toto: BUY NOW sa zmení na BUY PULLBACK

    # --- Alerty ---
    "alert_worsen_pp": 3.0,             # nový alert na tú istú mincu až po zhoršení o 3 p. b.
    "safety_alert_worsen_pts": 2,
    "pump_alert_pct": 7.0,              # upozornenie na výrazný rast od poslednej analýzy
    "pump_alert_step_pct": 3.0,

    # --- Hlboké hľadanie (Google Search cez Gemini) ---
    "deep_search_cooldown_hours": 12,
    "deep_search_worsen_pp": 5.0,
    "fundamentals_max_age_hours": 72,   # staršie správy sa zahodia
    "fundamentals_reuse_hours": 30,     # ranný fundament sa používa aj večer
    "alert_research_reuse_hours": 24,

    # --- Správy a príčiny pohybov ---
    "news_max_age_hours": 48,
    "significant_move_pct": 5.0,        # 24h pohyb, pri ktorom sa hľadá príčina
}

# Hlavné analýzy: (hodina, minúta, názov). Hlboké hľadanie len pri "07:00".
MAIN_SLOTS = [(7, 0, "07:00"), (15, 0, "15:00"), (20, 0, "20:00")]
SLOT_GRACE_MINUTES = 90                 # GitHub Actions často mešká
DEEP_SEARCH_SLOT = "07:00"

CAUSE_CONFIRMED = "Potvrdená správa alebo udalosť"
CAUSE_PROBABLE = "Pravdepodobná príčina"
CAUSE_MARKET = "Pohyb celého trhu"
CAUSE_TECHNICAL = "Technický pohyb"
CAUSE_UNKNOWN = "Príčina nezistená"
CAUSE_CATEGORIES = {
    CAUSE_CONFIRMED, CAUSE_PROBABLE, CAUSE_MARKET, CAUSE_TECHNICAL, CAUSE_UNKNOWN,
}

SAFETY_RANK = {"NORMAL": 0, "WARNING": 1, "CRITICAL": 2}

ACTION_EMOJI = {
    "BUY NOW": "🟢",
    "BUY PULLBACK": "🟡",
    "HOLD": "⚪",
    "WAIT": "⏳",
    "REDUCE": "🟠",
    "SELL": "🔴",
}
SAFETY_EMOJI = {"NORMAL": "🟢", "WARNING": "🟠", "CRITICAL": "🔴"}


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
    structure = compute_structure(candles, live_price)

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
        "data_warnings": warnings, "technical_4h": tech, "structure": structure,
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


def format_price(value):
    value = safe_float(value)
    if value is None: return "N/A"
    if value >= 1000: return f"${value:,.0f}"
    if value >= 100: return f"${value:,.2f}"
    if value >= 1: return f"${value:,.3f}"
    if value >= 0.01: return f"${value:,.4f}"
    return f"${value:.8f}"



# ============================================================
# ČASOVÝ PLÁN
# ============================================================

def slot_label(slot):
    """'BRATISLAVA_2026-10-14_07:00' -> '07:00'."""
    return str(slot).rsplit("_", 1)[-1] if slot else None


def get_main_analysis_slot(now=None):
    now = now or now_local()

    for hour, minute, label in MAIN_SLOTS:
        start = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if start <= now < start + timedelta(minutes=SLOT_GRACE_MINUTES):
            return f"BRATISLAVA_{now.date().isoformat()}_{label}"

    return None


def is_main_analysis_time(now=None):
    if manual_analysis_requested():
        return True, "MANUAL"

    slot = get_main_analysis_slot(now)

    if not slot:
        return False, "SAFETY_MONITOR"

    if load_state().get("last_main_slot") == slot:
        return False, "SAFETY_MONITOR"

    return True, f"BRATISLAVA_{slot_label(slot)}"


def deep_search_allowed(reason, slot):
    """Hlboké hľadanie: iba ranná analýza 07:00 (alebo ručne s MANUAL_DEEP_SEARCH)."""
    if slot_label(slot) == DEEP_SEARCH_SLOT:
        return True

    if reason == "MANUAL":
        return os.getenv("MANUAL_DEEP_SEARCH", "").strip().lower() in {
            "true", "1", "yes", "y", "on"
        }

    return False


# ============================================================
# ŠTRUKTÚRA CENY (support, rezistencia, objem, lokálne maximum)
# ============================================================

def compute_structure(candles, live_price):
    n = len(candles)
    lookback = CONFIG["peak_lookback_candles"]
    window = candles[-lookback:]

    high_candle = max(window, key=lambda c: c["high"])
    previous = candles[-31:-1] if n > 31 else candles[:-1]

    support_prev = min((c["low"] for c in previous), default=None)
    resistance_prev = max((c["high"] for c in previous), default=None)

    volumes = [c.get("volume") for c in candles]
    vol_ratio = None
    if n >= 36 and all(v is not None for v in volumes[-36:]):
        recent = sum(volumes[-6:]) / 6
        base = sum(volumes[-36:-6]) / 30
        vol_ratio = recent / base if base > 0 else None

    change_24h = pct_change(candles[-7]["close"], candles[-1]["close"]) if n >= 7 else None
    price = safe_float(live_price)

    support_broken = bool(
        support_prev and price and price < support_prev * 0.995
    )
    resistance_broken = bool(
        resistance_prev and price and price > resistance_prev * 1.005
    )
    sell_pressure = bool(
        vol_ratio is not None and vol_ratio >= 1.3
        and change_24h is not None and change_24h < -2.0
    )

    return {
        "window_high": high_candle["high"],
        "window_high_ts": high_candle["timestamp"],
        "support_prev": support_prev,
        "resistance_prev": resistance_prev,
        "volume_ratio": vol_ratio,
        "change_24h_candles": change_24h,
        "support_broken": support_broken,
        "resistance_broken": resistance_broken,
        "sell_pressure": sell_pressure,
    }


def update_peak(state, symbol, structure, price):
    """Lokálne maximum = najvyššia cena za posledných 7 dní (uložené v stave)."""
    peaks = state.setdefault("peaks", {})
    now_utc = datetime.now(timezone.utc)
    max_age = timedelta(hours=CONFIG["peak_lookback_candles"] * 4)

    candidates = []

    window_high = safe_float(structure.get("window_high"))
    window_ts = safe_float(structure.get("window_high_ts"))
    if window_high:
        when = (
            datetime.fromtimestamp(window_ts / 1000, timezone.utc)
            if window_ts else now_utc
        )
        candidates.append((window_high, when))

    if price:
        candidates.append((price, now_utc))

    stored = peaks.get(symbol) or {}
    stored_price = safe_float(stored.get("price"))
    stored_ts = parse_timestamp(stored.get("ts"))
    if stored_price and stored_ts and now_utc - stored_ts <= max_age:
        candidates.append((stored_price, stored_ts))

    if not candidates:
        return None

    best = max(candidates, key=lambda item: item[0])
    peaks[symbol] = {"price": best[0], "ts": best[1].isoformat()}
    return best[0]


def review_threshold(tech):
    """Prah podrobného posúdenia: 6 % alebo dennú volatilitu mince, čo je vyššie."""
    base = CONFIG["drawdown_review_pct"]
    deep = CONFIG["drawdown_deep_pct"]

    if CONFIG["drawdown_review_adaptive"]:
        atr_pct = safe_float((tech or {}).get("atr_percent"))
        if atr_pct is not None:
            daily_vol = atr_pct * math.sqrt(6)
            base = max(base, CONFIG["drawdown_review_vol_mult"] * daily_vol)

    return round(min(base, deep - 1.0), 1)


def coin_metrics(symbol, data, state):
    """Čisté metriky bez rozhodnutia (vstup pre bezpečnostný stav aj signál)."""
    tech = data.get("technical_4h") or {}
    struct = data.get("structure") or {}
    price = safe_float(data.get("price_usd"))

    peak = update_peak(state, symbol, struct, price) if price else None
    drawdown = (
        max(0.0, (peak - price) / peak * 100.0) if peak and price else 0.0
    )

    return {
        "symbol": symbol,
        "price": price,
        "peak": peak,
        "drawdown_pct": round(drawdown, 2),
        "review_thr": review_threshold(tech),
        "deep_thr": CONFIG["drawdown_deep_pct"],
        "support_broken": bool(struct.get("support_broken")),
        "resistance_broken": bool(struct.get("resistance_broken")),
        "sell_pressure": bool(struct.get("sell_pressure")),
        "volume_ratio": struct.get("volume_ratio"),
        "support": struct.get("support_prev"),
        "resistance": struct.get("resistance_prev"),
    }


# ============================================================
# BEZPEČNOSTNÝ STAV TRHU (pravidlá a merateľné údaje, nie názor AI)
# ============================================================

def market_safety_v2(ctx, metrics_map, state, fund=None):
    points = []   # (body, dôvod)

    global_change = ctx.get("global_change")
    if global_change is not None:
        if global_change <= -7:
            points.append((3, f"celková trhová kapitalizácia {global_change:+.1f}% za 24h"))
        elif global_change <= -4:
            points.append((2, f"celková trhová kapitalizácia {global_change:+.1f}% za 24h"))
        elif global_change <= -2.5:
            points.append((1, f"trhová kapitalizácia klesla o {abs(global_change):.1f}% za 24h"))

    btc_change = ctx.get("btc_change_24h")
    if btc_change is not None:
        if btc_change <= -8:
            points.append((3, f"Bitcoin {btc_change:+.1f}% za 24h"))
        elif btc_change <= -5:
            points.append((2, f"Bitcoin {btc_change:+.1f}% za 24h"))
        elif btc_change <= -3:
            points.append((1, f"Bitcoin {btc_change:+.1f}% za 24h"))

    btc_m = metrics_map.get("BTC") or {}
    btc_tech = (ctx.get("btc_data") or {}).get("technical_4h") or {}
    btc_price = safe_float(btc_tech.get("price"))

    btc_dd = btc_m.get("drawdown_pct", 0.0)
    if btc_dd >= 10:
        points.append((2, f"Bitcoin je o {btc_dd:.1f}% pod 7-dňovým maximom"))
    elif btc_dd >= btc_m.get("review_thr", 6.0):
        points.append((1, f"Bitcoin je o {btc_dd:.1f}% pod 7-dňovým maximom"))

    btc_tech_points = []
    if btc_price and safe_float(btc_tech.get("ema200")) and btc_price < btc_tech["ema200"]:
        btc_tech_points.append((1, "Bitcoin pod EMA200"))
    if btc_price and safe_float(btc_tech.get("ema50")) and btc_price < btc_tech["ema50"]:
        btc_tech_points.append((1, "Bitcoin pod EMA50"))
    if btc_m.get("support_broken"):
        btc_tech_points.append((2, "Bitcoin prelomil support"))
    hist = safe_float((btc_tech.get("macd") or {}).get("histogram"))
    if hist is not None and hist < 0:
        btc_tech_points.append((1, "MACD Bitcoinu je záporný"))
    # technické body Bitcoinu najviac 3, aby samy nespustili CRITICAL
    running = 0
    for pts, why in btc_tech_points:
        if running >= 3:
            break
        points.append((pts, why))
        running += pts

    alts = {s: m for s, m in metrics_map.items() if s != "BTC"}
    weak = [s for s, m in alts.items() if m["drawdown_pct"] >= m["review_thr"]]
    if len(weak) >= 5:
        points.append((3, f"{len(weak)} z {len(alts)} altcoinov je pod prahom poklesu"))
    elif len(weak) >= 3:
        points.append((2, f"{len(weak)} z {len(alts)} altcoinov je pod prahom poklesu"))

    broken = [s for s, m in alts.items() if m["support_broken"]]
    if len(broken) >= 2:
        points.append((1, f"prelomený support: {', '.join(broken)}"))

    selling = [s for s, m in alts.items() if m["sell_pressure"]]
    if len(selling) >= 3:
        points.append((1, f"rastúci predajný objem pri poklese: {', '.join(selling)}"))

    technical_total = sum(p for p, _ in points)

    # Fundament smie riziko len mierne zvýšiť a len ak už existujú technické varovania
    fund_pts = 0
    if fund and technical_total >= 2:
        fund_pts = min(1, int((fund.get("market") or {}).get("risk_pts", 0) or 0))
        if fund_pts:
            points.append((fund_pts, "negatívne fundamentálne správy o trhu (potvrdené zdrojom)"))

    score = sum(p for p, _ in points)

    previous = (state.get("safety") or {}).get("state", "NORMAL")
    if previous not in SAFETY_RANK:
        previous = "NORMAL"

    raw = (
        "CRITICAL" if score >= CONFIG["safety_critical_score"]
        else "WARNING" if score >= CONFIG["safety_warning_score"]
        else "NORMAL"
    )

    # Setrvačnosť: z vyššieho stavu sa vychádza až pri jasnom zlepšení
    final = raw
    if previous == "CRITICAL" and score >= CONFIG["safety_exit_critical_below"]:
        final = "CRITICAL"
    elif previous in {"WARNING", "CRITICAL"} and score >= CONFIG["safety_exit_warning_below"]:
        final = max(raw, "WARNING", key=lambda s: SAFETY_RANK[s])

    return {
        "state": final,
        "previous_state": previous,
        "score": score,
        "reasons": [why for _, why in sorted(points, key=lambda p: -p[0])],
        "market_cap_change_24h": global_change,
        "btc_change_24h": btc_change,
        "weak_altcoins": weak,
    }


# ============================================================
# ROZHODOVANIE O MINCI (signál počíta kód)
# ============================================================

def entry_tiers(price, tech, struct):
    """Až 3 plánované nákupné úrovne pod cenou (EMA20, EMA50, support)."""
    cands = []
    for key in ("ema20", "ema50"):
        v = safe_float(tech.get(key))
        if v:
            cands.append(v)
    support = safe_float(struct.get("support_prev"))
    if support:
        cands.append(support)

    tiers = sorted(
        {round(v, 8) for v in cands if price * 0.6 <= v < price * 0.995},
        reverse=True,
    )
    return tiers[:3]


def classify_cause(data, metrics, ctx, fund_coin):
    change = safe_float(data.get("change_24h"))
    if change is None or abs(change) < CONFIG["significant_move_pct"]:
        return None

    findings = (fund_coin or {}).get("findings") or []
    category = (fund_coin or {}).get("cause_category")

    if category == CAUSE_CONFIRMED and findings:
        return CAUSE_CONFIRMED

    btc_change = ctx.get("btc_change_24h")
    if (
        btc_change is not None and abs(btc_change) >= 2
        and btc_change * change > 0 and abs(change) <= abs(btc_change) * 2.5
    ):
        return CAUSE_MARKET

    vol_ratio = safe_float(metrics.get("volume_ratio"))
    if (
        metrics.get("support_broken") or metrics.get("resistance_broken")
        or (vol_ratio is not None and vol_ratio >= 1.5)
    ):
        return CAUSE_TECHNICAL

    if category == CAUSE_PROBABLE and findings:
        return CAUSE_PROBABLE

    return CAUSE_UNKNOWN


def smooth_action(previous, new, score, pts):
    """Zabraňuje protichodným odporúčaniam bez vysvetlenia."""
    if not previous or previous == new:
        return new, None

    if previous in {"SELL", "REDUCE"} and new in {"BUY NOW", "BUY PULLBACK"} and pts > 1:
        return "WAIT", f"po {previous} sa nákup neodporúča hneď; čaká sa na pokles rizika"

    if previous in {"SELL", "REDUCE"} and new in {"HOLD", "WAIT"} and pts >= 4:
        return previous, f"{previous} stále platí, riziko pretrváva"

    if previous in {"WAIT", "BUY PULLBACK"} and new == "BUY NOW" and (score or 0) < 7.0:
        return "BUY PULLBACK", "nákup za aktuálnu cenu zatiaľ nie je dostatočne potvrdený"

    return new, None


def decide_coin(symbol, data, metrics, safety, ctx, state, fund_coin):
    prev_info = (state.get("last_actions") or {}).get(symbol) or {}
    previous_action = prev_info.get("action")

    ev = {
        "symbol": symbol,
        "price": metrics["price"],
        "drawdown_pct": metrics["drawdown_pct"],
        "review_thr": metrics["review_thr"],
        "peak": metrics["peak"],
        "previous_action": previous_action,
        "action_note": None,
        "status": "potvrdený",
        "entry": None, "stop": None, "tp1": None, "tp2": None,
        "tiers": [], "signals": [],
    }

    tech = data.get("technical_4h") or {}
    struct = data.get("structure") or {}
    price = metrics["price"]
    tscore = data.get("technical_score_calc") or {}
    score = safe_float(tscore.get("score"))

    if data.get("error") or price is None or score is None:
        ev.update({
            "action": "WAIT", "status": "nedostatok dát", "trend_score": None,
            "trend_label": "nedostatok dát", "risk_pts": 0, "risk_level": "NEZNÁME",
            "signals": ["údaje o minci sú nedostupné alebo neúplné"],
            "cause_category": None, "flip": "Počká sa na úplné údaje.",
        })
        return ev

    rsi_v = safe_float(tech.get("rsi14"))
    hist = safe_float((tech.get("macd") or {}).get("histogram"))
    ema20 = safe_float(tech.get("ema20"))
    ema50 = safe_float(tech.get("ema50"))
    ema200 = safe_float(tech.get("ema200"))
    atr_pct = safe_float(tech.get("atr_percent"))
    atr_abs = safe_float(tech.get("atr14"))
    fg = safe_float((ctx.get("fear") or {}).get("value"))

    # ---- rizikové body ----
    pts = 0
    reasons = []

    dd = metrics["drawdown_pct"]
    if dd >= metrics["deep_thr"]:
        pts += 3
        reasons.append(f"hlboký pokles {dd:.1f}% od lokálneho maxima")
    elif dd >= metrics["review_thr"]:
        pts += 1
        reasons.append(f"pokles {dd:.1f}% od lokálneho maxima (prah {metrics['review_thr']:.1f}%)")

    if metrics["support_broken"]:
        pts += 2
        reasons.append(f"prelomený support {format_price(metrics['support'])}")
    if metrics["sell_pressure"]:
        pts += 1
        reasons.append("rastúci predajný objem pri poklese")
    if ema50 and price < ema50:
        pts += 1
        reasons.append("cena pod EMA50")
    if ema200 and price < ema200:
        pts += 1
        reasons.append("cena pod EMA200")
    if hist is not None and hist < 0:
        pts += 1
        reasons.append("MACD histogram záporný")
    if score <= 3.0:
        pts += 1
        reasons.append(f"slabý trend (skóre {score}/10)")

    if safety["state"] == "WARNING":
        pts += 1
        reasons.append("bezpečnostný stav trhu: WARNING")
    elif safety["state"] == "CRITICAL":
        pts += 2
        reasons.append("bezpečnostný stav trhu: CRITICAL")

    fund_pts = min(1, int((fund_coin or {}).get("risk_pts", 0) or 0))
    if fund_pts and pts >= 1:
        pts += fund_pts
        reasons.append("negatívna správa o projekte (potvrdená zdrojom)")

    if pts >= CONFIG["risk_severe_pts"]:
        risk_level = "VEĽMI VYSOKÉ"
    elif pts >= CONFIG["risk_high_pts"]:
        risk_level = "VYSOKÉ"
    elif pts >= CONFIG["risk_elevated_pts"]:
        risk_level = "ZVÝŠENÉ"
    else:
        risk_level = "NÍZKE"

    # ---- signál ----
    extended_pct = max(3.0, 1.5 * (atr_pct or 0))
    above_ema20_pct = pct_change(ema20, price) if ema20 else 0.0
    extended = above_ema20_pct is not None and above_ema20_pct > extended_pct
    tiers = entry_tiers(price, tech, struct)
    greed = fg is not None and fg >= CONFIG["greed_caution_value"]

    stabilized_dip = bool(
        dd >= CONFIG["stabilized_dip_min_drawdown"] and score >= 4.5 and pts <= 2
        and hist is not None and hist > 0 and not metrics["support_broken"]
        and rsi_v is not None and 35 <= rsi_v <= 60
    )
    buy_now_ok = bool(
        score >= CONFIG["buy_now_min_score"] and pts <= 1 and not extended
        and rsi_v is not None and 40 <= rsi_v <= 68
        and safety["state"] == "NORMAL" and not greed
    )

    if pts >= CONFIG["sell_pts"] and score <= 3.5:
        action = "SELL"
    elif pts >= CONFIG["risk_high_pts"]:
        action = "REDUCE"
    elif dd >= metrics["review_thr"] and (pts >= 3 or score <= 4.5):
        action = "WAIT"
    elif buy_now_ok or (stabilized_dip and safety["state"] == "NORMAL"):
        action = "BUY NOW"
    elif score >= CONFIG["buy_pullback_min_score"] and pts <= 2 and tiers:
        action = "BUY PULLBACK"
    elif pts >= 3 or score <= 4.0:
        action = "WAIT"
    else:
        action = "HOLD"

    action, note = smooth_action(previous_action, action, score, pts)
    ev["action_note"] = note

    # ---- hladiny ----
    entry = None
    if action == "BUY NOW":
        entry = price
    elif action == "BUY PULLBACK":
        entry = tiers[0] if tiers else price * 0.97
        ev["status"] = "podmienený"

    if entry is not None:
        support = safe_float(metrics.get("support"))
        base = min(entry, support) if support else entry
        stop = base - 1.5 * atr_abs if atr_abs else entry * 0.92
        if stop >= entry:
            stop = entry * 0.92
        risk = entry - stop
        resistance = safe_float(metrics.get("resistance"))
        tp1 = resistance if resistance and resistance > entry * 1.015 else entry + 1.5 * risk
        tp2 = entry + 3 * risk if tp1 < entry + 3 * risk else tp1 + 1.5 * risk
        ev.update({"entry": entry, "stop": stop, "tp1": tp1, "tp2": tp2})

    signals = []
    if score is not None:
        signals.extend(tscore.get("reasons") or [])
    if stabilized_dip:
        signals.append("pokles sa stabilizuje (MACD histogram kladný, support drží)")
    if extended:
        signals.append(f"cena je o {above_ema20_pct:.1f}% nad EMA20; nákup môže byť oneskorený")
    if greed:
        signals.append(f"Fear & Greed {fg:.0f}: zvýšená opatrnosť pri nákupe")

    ev.update({
        "action": action,
        "trend_score": score,
        "trend_label": tscore.get("label"),
        "risk_pts": pts,
        "risk_level": risk_level,
        "risk_reasons": reasons,
        "signals": signals,
        "tiers": tiers,
        "rsi": rsi_v,
        "macd_hist": hist,
        "ema20": ema20, "ema50": ema50, "ema200": ema200,
        "support": metrics.get("support"),
        "resistance": metrics.get("resistance"),
        "volume_ratio": metrics.get("volume_ratio"),
        "support_broken": metrics["support_broken"],
        "cause_category": classify_cause(data, metrics, ctx, fund_coin),
    })
    ev["flip"] = flip_condition(ev)
    return ev


def flip_condition(ev):
    action = ev["action"]
    support = format_price(ev.get("support")) if ev.get("support") else "N/A"
    ema50 = format_price(ev.get("ema50")) if ev.get("ema50") else "EMA50"

    if action == "BUY NOW":
        return f"Prehodnotí sa, ak cena klesne pod stop {format_price(ev.get('stop'))} alebo sa zvýši riziko."
    if action == "BUY PULLBACK":
        return (
            f"Nákup sa potvrdí až pri dosiahnutí {format_price(ev.get('entry'))} so stabilizáciou; "
            f"zrušené, ak cena prelomí support {support}."
        )
    if action == "WAIT":
        return f"Prejde na nákup po stabilizácii nad supportom {support} a kladnom MACD histograme."
    if action == "HOLD":
        return (
            f"Prejde na REDUCE, ak cena prelomí support {support} a pribudnú ďalšie varovné signály; "
            f"nákup sa zváži pri trende ≥ {CONFIG['buy_now_min_score']}/10 a nízkom riziku."
        )
    if action in {"REDUCE", "SELL"}:
        return f"Zmierni sa po návrate nad {ema50} a poklese rizika pod {CONFIG['risk_elevated_pts']} bodov."
    return "—"


def evaluate_all(ctx, state, fund=None, state_for_peaks=None):
    """Spoločné vyhodnotenie pre hlavnú analýzu aj bezpečnostný monitor."""
    state_for_peaks = state if state_for_peaks is None else state_for_peaks

    metrics_map = {"BTC": coin_metrics("BTC", ctx["btc_data"], state_for_peaks)}
    for symbol, data in ctx["portfolio_data"].items():
        metrics_map[symbol] = coin_metrics(symbol, data, state_for_peaks)

    safety = market_safety_v2(ctx, metrics_map, state, fund)

    evals = {}
    for symbol, data in ctx["portfolio_data"].items():
        fund_coin = merge_fund_for_coin(fund, state, symbol)
        evals[symbol] = decide_coin(
            symbol, data, metrics_map[symbol], safety, ctx, state, fund_coin
        )

    return metrics_map, safety, evals



# ============================================================
# POMOCNÉ FORMÁTOVANIE
# ============================================================

def fmt_pct(value, digits=1):
    v = safe_float(value)
    return "N/A" if v is None else f"{v:+.{digits}f}%"


def fmt_big(value):
    v = safe_float(value)
    if v is None:
        return "N/A"
    if v >= 1e12:
        return f"${v / 1e12:.2f}T"
    if v >= 1e9:
        return f"${v / 1e9:.2f}B"
    if v >= 1e6:
        return f"${v / 1e6:.1f}M"
    return f"${v:,.0f}"


def local_stamp(iso_value):
    ts = parse_timestamp(iso_value)
    return ts.astimezone(TZ).strftime("%d.%m. %H:%M") if ts else "?"


# ============================================================
# ZBER TRHOVÝCH DÁT (spoločný pre analýzu aj monitor)
# ============================================================

def previous_coin_map(state):
    result = {}
    for coin in (state.get("last_analysis") or {}).get("coins", []):
        if isinstance(coin, dict) and coin.get("symbol"):
            result[coin["symbol"]] = {
                "price": safe_float(coin.get("current_price")),
                "market_cap": safe_float(coin.get("market_cap")),
                "volume_24h": safe_float(coin.get("volume_24h")),
            }
    return result


def gather_market_data(state):
    market_global = coingecko_get("global")
    fear = get_fear_greed()
    gdata = market_global.get("data", {}) if isinstance(market_global, dict) else {}

    total_cap = safe_float((gdata.get("total_market_cap") or {}).get("usd"))
    total_volume = safe_float((gdata.get("total_volume") or {}).get("usd"))
    dominance = safe_float((gdata.get("market_cap_percentage") or {}).get("btc"))
    global_change = safe_float(gdata.get("market_cap_change_percentage_24h_usd"))

    btc_data = collect_coin_data("BTC", "bitcoin")
    previous = previous_coin_map(state)

    portfolio_data = {}
    for symbol, coin_id in PORTFOLIO.items():
        try:
            data = collect_coin_data(symbol, coin_id)
            cap = safe_float(data.get("market_cap"), 0)
            data["market_share_pct"] = (
                cap / total_cap * 100 if total_cap else 0.0
            )

            prev = previous.get(symbol, {})
            data["change_since_last"] = (
                pct_change(prev.get("price"), data["price_usd"]) if prev.get("price") else 0.0
            )
            data["mcap_change_since_last"] = (
                pct_change(prev.get("market_cap"), cap) if prev.get("market_cap") else 0.0
            )
            data["vol_change_since_last"] = (
                pct_change(prev.get("volume_24h"), data.get("volume_24h"))
                if prev.get("volume_24h") else 0.0
            )
            portfolio_data[symbol] = data

        except Exception as exc:
            print(f"Portfolio data error {symbol}: {exc}")
            portfolio_data[symbol] = {
                "symbol": symbol, "error": str(exc), "market_cap": 0,
                "market_share_pct": 0, "change_since_last": 0.0,
                "mcap_change_since_last": 0.0, "vol_change_since_last": 0.0,
            }

    return {
        "market_global": market_global,
        "fear": fear,
        "total_market_cap": total_cap,
        "total_volume": total_volume,
        "btc_dominance": dominance,
        "global_change": global_change,
        "btc_data": btc_data,
        "btc_change_24h": safe_float(btc_data.get("change_24h")),
        "portfolio_data": portfolio_data,
    }


# ============================================================
# RSS SPRÁVY (teraz sa skutočne posielajú do analýzy)
# ============================================================

def get_rss_news():
    all_items = []
    headers = {
        "User-Agent": f"Mozilla/5.0 (compatible; CryptoAIBot/{VERSION})",
        "Accept": "application/rss+xml,application/xml,text/xml,*/*",
    }
    max_age = timedelta(hours=CONFIG["news_max_age_hours"])
    now_utc = datetime.now(timezone.utc)

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
                published = None
                for child in item:
                    tag = child.tag.lower()
                    if tag.endswith("title"):
                        entry["title"] = (child.text or "").strip()
                    elif tag.endswith("link"):
                        entry["link"] = (child.text or "").strip()
                    elif tag.endswith("pubdate"):
                        raw_date = (child.text or "").strip()
                        try:
                            published = parsedate_to_datetime(raw_date)
                            if published.tzinfo is None:
                                published = published.replace(tzinfo=timezone.utc)
                            entry["pub_date"] = published.astimezone(timezone.utc).isoformat()
                        except Exception:
                            entry["pub_date"] = raw_date

                if not entry["title"]:
                    continue
                if published is not None and now_utc - published > max_age:
                    continue

                title_l = entry["title"].lower() + " "
                entry["symbols"] = [
                    sym for sym, words in NEWS_KEYWORDS.items()
                    if any(w in title_l for w in words)
                ]
                all_items.append(entry)
                count += 1
                if count >= 15:
                    break

        except Exception as exc:
            print(f"RSS error {source}: {exc}")

    return all_items[:30]


# ============================================================
# GEMINI (jedno volanie, s vyhľadávaním alebo bez neho)
# ============================================================

def gemini_call(prompt, search=False, thinking_level="high", timeout=120):
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY nie je nastavený.")

    client = genai.Client(api_key=GEMINI_API_KEY)
    print(f"Gemini model: {GEMINI_MODEL} | search={search}")

    kwargs = {
        "model": GEMINI_MODEL,
        "input": prompt,
        "background": True,
        "generation_config": {"thinking_level": thinking_level},
        "store": True,
        "timeout": timeout,
    }
    if search:
        kwargs["tools"] = [{"type": "google_search"}]

    interaction = client.interactions.create(**kwargs)
    interaction_id = interaction.id
    started = time.time()

    while True:
        if time.time() - started > GEMINI_MAX_WAIT:
            raise TimeoutError("Gemini trvá dlhšie ako 10 minút.")

        interaction = client.interactions.get(id=interaction_id)
        status = interaction.status

        if status == "completed":
            if not interaction.output_text:
                raise RuntimeError("Gemini vrátil prázdny výstup.")
            return interaction.output_text

        if status in {"failed", "cancelled", "expired", "incomplete", "requires_action"}:
            raise RuntimeError(f"Gemini skončil so stavom: {status}")

        time.sleep(POLL_INTERVAL)


def gemini_json(prompt, search=False, thinking_level="high"):
    return parse_json_output(gemini_call(prompt, search=search, thinking_level=thinking_level))


# ============================================================
# FUNDAMENTÁLNA ANALÝZA (Google Search cez Gemini)
# Spúšťa sa IBA: ranná analýza 07:00 a alert pri prepade nad 10 %.
# ============================================================

IMPACTS = {"positive", "negative", "neutral"}


def research_prompt(symbols, include_market, moves, hours):
    names = "\n".join(f"- {s}: {COIN_NAMES.get(s, s)}" for s in symbols)
    market_block = (
        "A) TRH A MAKRO (vždy): regulácia (SEC, EÚ, USA), ETF a toky do ETF, úrokové sadzby, Fed, inflácia, "
        "akciové trhy, likvidácie, bezpečnostné incidenty búrz alebo protokolov, stablecoiny.\n"
        if include_market else
        "A) TRH A MAKRO: hľadaj iba udalosti, ktoré môžu vysvetľovať súčasný prepad.\n"
    )
    return f"""
Si výskumný analytik kryptomien. Použi vyhľadávanie na webe a zisti AKTUÁLNE informácie, ktoré majú vplyv
na ceny nižšie uvedených kryptomien. Dnešný dátum a čas: {iso_now()}.

MINCE:
{names}

POHYBY CIEN (z dát bota):
{chr(10).join(moves)}

{market_block}B) PRE KAŽDÚ MINCU: upgrady a vydania, partnerstvá, odomykanie tokenov (unlocky), bezpečnostné incidenty,
rozhodnutia regulátorov, listingy a delistingy, väčšie pohyby veľrýb, zmeny v tokenomike, správy konkurencie.
C) Pri minciach s výrazným pohybom skús nájsť PRÍČINU pohybu a napíš, či ju potvrdzuje zdroj.

PRAVIDLÁ:
- Hľadaj anglicky aj v iných jazykoch podľa potreby, výsledok napíš po slovensky.
- Iba informácie z posledných {hours} hodín, alebo plánované udalosti do 30 dní (unlocky, upgrady, rozhodnutia).
- Ku každému zisteniu uveď: nadpis, dátum zverejnenia (YYYY-MM-DD), presnú URL zdroja, dopad
  (pozitívny / negatívny / neutrálny), závažnosť 1 až 3 a 1 až 2 vety popisu.
- Ak URL alebo dátum nepoznáš, zistenie NEUVÁDZAJ.
- Ak pre mincu nenájdeš nič relevantné, napíš "NEZISTENÉ". Nič si nevymýšľaj ani nedomýšľaj.
- Nepíš investičné odporúčania, len fakty a zdroje.
""".strip()


def structure_prompt(text, symbols, include_market):
    categories = " | ".join(sorted(CAUSE_CATEGORIES))
    sym_template = ",\n".join(
        f'  "{s}": {{"findings": [], "cause_category": "", "cause_summary": ""}}' for s in symbols
    )
    return f"""
Z textu nižšie vytvor štruktúrovaný JSON. Použi VÝHRADNE informácie a URL, ktoré sa v texte nachádzajú.
Nič nedopĺňaj ani nevymýšľaj. Zistenie bez URL alebo bez dátumu vynechaj. Odpoveď iba validný JSON bez Markdown.

Štruktúra:
{{
 "market": {{"findings": [
   {{"headline": "", "summary": "", "category": "regulácia|makro|projekt|bezpečnosť|token unlock|ETF a toky|trh|iné",
     "impact": "positive|negative|neutral", "severity": 1, "date": "YYYY-MM-DD", "url": "https://..."}}
 ]}},
 "coins": {{
{sym_template}
 }}
}}

Každé zistenie v "findings" mince má rovnaké polia ako zistenie trhu.
"cause_category" musí byť PRESNE jedna z hodnôt: {categories}.
"Potvrdená správa alebo udalosť" použi iba ak existuje zdroj, ktorý sa časovo a vecne spája s pohybom.
"cause_summary": 1 až 2 vety, alebo prázdny reťazec.
{"" if include_market else 'Pole "market" nechaj s prázdnym zoznamom findings.'}

TEXT:
{text}
""".strip()


def clean_findings(items, max_items):
    cleaned = []
    now_utc = datetime.now(timezone.utc)
    max_age = timedelta(hours=CONFIG["fundamentals_max_age_hours"]) + timedelta(days=1)

    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue

        headline = str(item.get("headline", "")).strip()
        url = str(item.get("url", "")).strip()
        date_raw = str(item.get("date", "")).strip()[:10]

        if not headline or not url.startswith("http"):
            continue

        try:
            published = datetime.strptime(date_raw, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            continue

        if now_utc - published > max_age:
            continue                      # príliš stará správa
        if published - now_utc > timedelta(days=30):
            continue                      # príliš vzdialená udalosť

        impact = str(item.get("impact", "neutral")).strip().lower()
        if impact not in IMPACTS:
            impact = "neutral"

        severity = int(clamp(safe_float(item.get("severity"), 1) or 1, 1, 3))

        cleaned.append({
            "headline": headline[:160],
            "summary": str(item.get("summary", "")).strip()[:300],
            "category": str(item.get("category", "iné")).strip()[:30],
            "impact": impact,
            "severity": severity,
            "date": date_raw,
            "url": url,
        })

    cleaned.sort(key=lambda f: (f["severity"], f["date"]), reverse=True)
    return cleaned[:max_items]


def negative_risk_pts(findings):
    """Fundament môže riziko zvýšiť najviac o 1 bod."""
    return 1 if any(f["impact"] == "negative" and f["severity"] >= 2 for f in findings) else 0


def run_fundamental_research(symbols, include_market, ctx, evals, mode):
    result = {
        "generated_at": utc_now_iso(),
        "mode": mode,
        "status": "failed",
        "symbols": list(symbols),
        "market": {"findings": [], "risk_pts": 0},
        "coins": {},
    }

    try:
        moves = []
        for symbol in symbols:
            data = ctx["portfolio_data"].get(symbol) or {}
            moves.append(
                f"{symbol}: 24h {fmt_pct(data.get('change_24h'))}, "
                f"7d {fmt_pct((data.get('returns') or {}).get('7d'))}"
                + (f", pokles od maxima {evals[symbol]['drawdown_pct']:.1f}%" if symbol in evals else "")
            )

        print(f"Hlboké hľadanie ({mode}): {', '.join(symbols)}")
        text = gemini_call(
            research_prompt(symbols, include_market, moves, CONFIG["fundamentals_max_age_hours"]),
            search=True,
            thinking_level="high",
        )
        structured = gemini_json(
            structure_prompt(text, symbols, include_market),
            search=False,
            thinking_level="low",
        )

        if include_market:
            market_findings = clean_findings(
                (structured.get("market") or {}).get("findings"), 8
            )
            result["market"] = {
                "findings": market_findings,
                "risk_pts": negative_risk_pts(market_findings),
            }

        for symbol in symbols:
            block = (structured.get("coins") or {}).get(symbol)
            block = block if isinstance(block, dict) else {}

            findings = clean_findings(block.get("findings"), 6)
            category = str(block.get("cause_category", "")).strip()
            if category not in CAUSE_CATEGORIES:
                category = CAUSE_UNKNOWN
            # Bez overiteľného zdroja nie je možné tvrdiť, že príčina je potvrdená či pravdepodobná
            summary = str(block.get("cause_summary", "")).strip()[:300]
            if category in {CAUSE_CONFIRMED, CAUSE_PROBABLE} and not findings:
                category = CAUSE_UNKNOWN
            if not findings:
                summary = ""              # tvrdenie bez zdroja sa nezobrazuje

            result["coins"][symbol] = {
                "findings": findings,
                "risk_pts": negative_risk_pts(findings),
                "cause_category": category,
                "cause_summary": summary,
            }

        result["status"] = "ok"

    except Exception as exc:
        print(f"Fundamentálne hľadanie zlyhalo: {exc}")
        result["error"] = str(exc)[:200]

    return result


def get_usable_fundamentals(state):
    fund = state.get("fundamentals")
    if not isinstance(fund, dict) or fund.get("status") != "ok":
        return None

    generated = parse_timestamp(fund.get("generated_at"))
    if not generated:
        return None

    age_h = (datetime.now(timezone.utc) - generated).total_seconds() / 3600
    return fund if age_h <= CONFIG["fundamentals_reuse_hours"] else None


def merge_fund_for_coin(fund, state, symbol):
    """Preferuje novšie hľadanie pri prepade pred ranným fundamentom."""
    base = ((fund or {}).get("coins") or {}).get(symbol)
    base_ts = parse_timestamp((fund or {}).get("generated_at")) if fund else None

    alert = (state.get("alert_research") or {}).get(symbol) or {}
    alert_data = alert.get("data")
    alert_ts = parse_timestamp(alert.get("ts"))

    if isinstance(alert_data, dict) and alert_ts:
        age_h = (datetime.now(timezone.utc) - alert_ts).total_seconds() / 3600
        if age_h <= CONFIG["alert_research_reuse_hours"] and (
            not base or base_ts is None or alert_ts > base_ts
        ):
            return dict(alert_data, source_label=f"hľadanie pri prepade {local_stamp(alert.get('ts'))}")

    if isinstance(base, dict):
        return dict(base, source_label=f"stav z {local_stamp(fund.get('generated_at'))}")

    return None


def fund_status_text(fund, researched_now, failed=False):
    if researched_now:
        return "aktuálne hľadanie dokončené"
    if fund:
        return f"stav z {local_stamp(fund.get('generated_at'))} (hlboké hľadanie beží iba o 07:00)"
    if failed:
        return "ranné hľadanie zlyhalo; fundament nie je k dispozícii"
    return "fundamentálne podklady nie sú k dispozícii"


def fmt_finding(finding):
    icon = {"negative": "🔴", "positive": "🟢"}.get(finding["impact"], "⚪")
    return f"{icon} {finding['headline']} ({finding['date']}) {finding['url']}"



# ============================================================
# FÁZA TRHU, ZMENY OD POSLEDNEJ ANALÝZY
# ============================================================

def market_regime(ctx, evals):
    """Odraz / Konsolidácia / Potvrdený rast: určuje kód podľa dát."""
    valid = [e for e in evals.values() if e.get("trend_score") is not None]
    if not valid:
        return "Konsolidácia"

    avg_score = sum(e["trend_score"] for e in valid) / len(valid)
    above50 = sum(1 for e in valid if e.get("ema50") and e["price"] > e["ema50"]) / len(valid)

    btc_tech = (ctx.get("btc_data") or {}).get("technical_4h") or {}
    btc_up = btc_tech.get("above_ema50") is True

    changes = [
        safe_float(ctx["portfolio_data"][s].get("change_24h"))
        for s in evals if s in ctx["portfolio_data"]
    ]
    changes = [c for c in changes if c is not None]
    avg_change = sum(changes) / len(changes) if changes else 0.0

    if above50 >= 0.67 and avg_score >= 6.5 and btc_up:
        return "Potvrdený rast"
    if avg_change > 0.5 and (above50 < 0.67 or avg_score < 6.5):
        return "Odraz"
    return "Konsolidácia"


def collect_flags(ctx, evals, safety):
    def tech_flags(tech):
        return {
            "above_ema50": tech.get("above_ema50"),
            "above_ema200": tech.get("above_ema200"),
        }

    flags = {
        "safety": safety["state"],
        "dominance": ctx.get("btc_dominance"),
        "BTC": tech_flags((ctx.get("btc_data") or {}).get("technical_4h") or {}),
    }
    for symbol, data in ctx["portfolio_data"].items():
        item = tech_flags(data.get("technical_4h") or {})
        item["support_broken"] = evals[symbol].get("support_broken", False)
        item["action"] = evals[symbol]["action"]
        flags[symbol] = item
    return flags


def compute_changes(state, ctx, evals, safety):
    previous = state.get("prev_flags")
    if not isinstance(previous, dict):
        return ["Prvá analýza po spustení V10.3, nie je s čím porovnať."]

    changes = []

    if previous.get("safety") and previous["safety"] != safety["state"]:
        changes.append(f"Bezpečnostný stav trhu: {previous['safety']} → {safety['state']}.")

    dom_now = safe_float(ctx.get("btc_dominance"))
    dom_prev = safe_float(previous.get("dominance"))
    if dom_now is not None and dom_prev is not None and abs(dom_now - dom_prev) >= 0.5:
        changes.append(f"Dominancia Bitcoinu: {dom_prev:.1f}% → {dom_now:.1f}%.")

    current = collect_flags(ctx, evals, safety)
    for key in ["BTC"] + REQUIRED_SYMBOLS:
        before = previous.get(key) or {}
        now = current.get(key) or {}
        label = "Bitcoin" if key == "BTC" else key

        for flag, name in (("above_ema50", "EMA50"), ("above_ema200", "EMA200")):
            if before.get(flag) is True and now.get(flag) is False:
                changes.append(f"{label} sa dostal pod {name}.")
            elif before.get(flag) is False and now.get(flag) is True:
                changes.append(f"{label} sa vrátil nad {name}.")

        if key != "BTC":
            if now.get("support_broken") and not before.get("support_broken"):
                changes.append(f"{key} prelomil support {format_price(evals[key].get('support'))}.")
            if before.get("action") and before["action"] != now.get("action"):
                note = evals[key].get("action_note")
                changes.append(
                    f"{key}: signál {before['action']} → {now['action']}"
                    + (f" ({note})." if note else ".")
                )

    for symbol, data in ctx["portfolio_data"].items():
        move = safe_float(data.get("change_since_last"), 0.0)
        if abs(move) >= 5.0:
            changes.append(f"{symbol} {move:+.1f}% od poslednej analýzy.")

    return changes or ["Od poslednej analýzy sa nezmenilo nič podstatné."]


# ============================================================
# VYSVETLENIE OD GEMINI (nemení čísla ani signály)
# ============================================================

def build_explain_payload(ctx, safety, evals, news, changes, state, fund, fund_status):
    coins = []
    for symbol, ev in evals.items():
        data = ctx["portfolio_data"].get(symbol) or {}
        fund_coin = merge_fund_for_coin(fund, state, symbol)
        findings = [
            {k: f[k] for k in ("headline", "impact", "severity", "date", "url")}
            for f in (fund_coin or {}).get("findings", [])[:3]
        ]
        coins.append({
            "symbol": symbol,
            "price": ev["price"],
            "signal": ev["action"],
            "signal_status": ev["status"],
            "previous_signal": ev.get("previous_action"),
            "signal_note": ev.get("action_note"),
            "trend_score": ev.get("trend_score"),
            "risk_level": ev.get("risk_level"),
            "risk_points": ev.get("risk_pts"),
            "risk_reasons": ev.get("risk_reasons", []),
            "technical_signals": ev.get("signals", []),
            "drawdown_from_7d_high_pct": ev["drawdown_pct"],
            "rsi": ev.get("rsi"),
            "support": ev.get("support"),
            "resistance": ev.get("resistance"),
            "planned_buy_levels": ev.get("tiers"),
            "change_24h_pct": data.get("change_24h"),
            "change_since_last_analysis_pct": data.get("change_since_last"),
            "move_cause_category": ev.get("cause_category"),
            "fundamental_cause_summary": (fund_coin or {}).get("cause_summary"),
            "fundamental_findings": findings,
            "data_warnings": data.get("data_warnings", [])[:3],
        })

    market_findings = [
        {k: f[k] for k in ("headline", "impact", "severity", "date", "url")}
        for f in ((fund or {}).get("market") or {}).get("findings", [])[:5]
    ]
    headlines = [
        {"source": n["source"], "title": n["title"], "symbols": n.get("symbols", [])}
        for n in news[:20]
    ]

    return {
        "time_bratislava": iso_now(),
        "market": {
            "market_cap_change_24h_pct": ctx.get("global_change"),
            "btc_change_24h_pct": ctx.get("btc_change_24h"),
            "btc_dominance_pct": ctx.get("btc_dominance"),
            "fear_greed": (ctx.get("fear") or {}).get("value"),
            "regime_computed": market_regime(ctx, evals),
            "safety_state": safety["state"],
            "safety_score": safety["score"],
            "safety_reasons": safety["reasons"],
        },
        "fundamentals_status": fund_status,
        "market_fundamental_findings": market_findings,
        "rss_headlines": headlines,
        "changes_since_last_analysis": changes,
        "coins": coins,
    }


def explain_prompt(payload):
    return f"""
Si analytik kryptomien. Píš po slovensky, zrozumiteľne a s plne dokončenými vetami.
DÔLEŽITÉ: signály, skóre, hladiny, bezpečnostný stav a ceny už vypočítal program. Ty ich NESMIEŠ meniť, spochybniť
ani nahrádzať vlastnými. Tvojou úlohou je iba vysvetliť, prečo program dospel k týmto výsledkom, a prepojiť ich
s dostupnými správami.

PRAVIDLÁ:
- Čísla, sumy a percentá píš číslicami.
- Používaj iba údaje z DÁT nižšie. Nevymýšľaj správy, ceny ani príčiny. Ak príčina pohybu nie je v dátach doložená,
  napíš, že príčina nie je potvrdená.
- Rozlišuj potvrdené fakty (so zdrojom) od odhadov. Žiadne slová ako "jednoznačne" či "spoľahlivo".
- Ak je signal_status "podmienený", jasne napíš, že ide len o plánovanú nákupnú úroveň a nie o odporúčanie kúpiť
  hneď za aktuálnu cenu.
- Ak sa signál oproti previous_signal zmenil, vysvetli prečo (použi signal_note a changes_since_last_analysis).
- Ak sú údaje nedostatočné alebo si protirečia, napíš to.
- "reason": 2 až 3 vety pre mincu (technický stav, riziko, dôvod signálu).
- "cause_text": 1 až 2 vety o príčine pohybu, iba ak je move_cause_category vyplnená, inak prázdny reťazec.
  Kategóriu NEMEŇ, iba ju zdôvodni dostupnými údajmi.
- "market_summary": 3 až 4 vety o stave trhu, bezpečnostnom stave a dôvodoch.
- "conditions_to_watch": najviac 3 stručné položky.

DÁTA:
{json.dumps(payload, ensure_ascii=False)}

Vráť iba validný JSON bez Markdown:
{{
 "market_summary": "",
 "market_cause": "",
 "coins": [{{"symbol": "", "reason": "", "cause_text": ""}}],
 "conditions_to_watch": [""]
}}
""".strip()


def fallback_explanation(evals, safety, error):
    return {
        "market_summary": (
            f"Vysvetlenie od AI nie je dostupné ({str(error)[:80]}). "
            f"Bezpečnostný stav: {safety['state']}. Nižšie sú signály vypočítané programom."
        ),
        "market_cause": "",
        "coins": [
            {
                "symbol": s,
                "reason": "; ".join((ev.get("risk_reasons") or []) + (ev.get("signals") or [])[:3])
                or "Bez významných signálov.",
                "cause_text": "",
            }
            for s, ev in evals.items()
        ],
        "conditions_to_watch": [],
    }


# ============================================================
# SPRÁVY PRE TELEGRAM
# ============================================================

def format_coin_block(symbol, ev, data, ai_coin, fund_coin):
    action = ev["action"]
    emoji = ACTION_EMOJI.get(action, "⚪")
    status = ""
    if action == "BUY PULLBACK":
        status = " (PODMIENENÝ vstup, zatiaľ nepotvrdený)"
    elif action == "BUY NOW":
        status = " (potvrdený)"

    lines = [
        f"{emoji} {symbol} — {action}{status}",
        f"   Cena: {format_price(ev['price'])} | od poslednej analýzy {fmt_pct(data.get('change_since_last'), 2)} | 24h {fmt_pct(data.get('change_24h'), 2)}",
    ]

    if ev.get("trend_score") is None:
        lines.append("   Údaje sú nedostupné alebo neúplné.")
    else:
        rsi_txt = f"{ev['rsi']:.0f}" if ev.get("rsi") is not None else "N/A"
        lines.append(
            f"   Trend: {ev['trend_score']}/10 ({ev['trend_label']}) | Riziko: {ev['risk_level']} ({ev['risk_pts']} b.) | RSI {rsi_txt}"
        )
        lines.append(
            f"   Pokles od 7-dňového maxima: {ev['drawdown_pct']:.1f}% (podrobné posúdenie od {ev['review_thr']:.1f}%, hlboký prepad od {CONFIG['drawdown_deep_pct']:.0f}%)"
        )
        lines.append(
            f"   Support: {format_price(ev.get('support'))} | Rezistencia: {format_price(ev.get('resistance'))}"
        )

    lines.append(
        f"   Kapitalizácia: {fmt_big(data.get('market_cap'))} ({fmt_pct(data.get('mcap_change_since_last'), 2)} | podiel {safe_float(data.get('market_share_pct'), 0.0):.3f}%) | "
        f"Objem 24h: {fmt_big(data.get('volume_24h'))} ({fmt_pct(data.get('vol_change_since_last'), 2)})"
    )

    if action == "BUY NOW" and ev.get("entry"):
        rr1, rr2 = calculate_rr(ev["entry"], ev["stop"], ev["tp1"], ev["tp2"])
        rr_txt = f"R:R 1:{rr1}" if rr1 else "R:R N/A"
        if rr2:
            rr_txt += f" / 1:{rr2}"
        lines.append(
            f"   Vstup {format_price(ev['entry'])} | Stop {format_price(ev['stop'])} | "
            f"TP1 {format_price(ev['tp1'])} | TP2 {format_price(ev['tp2'])} ({rr_txt}, orientačne)"
        )
        lines.append("   Ciele sú iba orientačné; ich dosiahnutie nespúšťa automatický predaj.")

    if action in {"BUY PULLBACK", "WAIT"} and ev.get("tiers"):
        tiers = " | ".join(f"{i}) {format_price(v)}" for i, v in enumerate(ev["tiers"], 1))
        lines.append(f"   Plánované nákupné úrovne (NIE sú potvrdené, ide o možné zóny): {tiers}")
    if action == "BUY PULLBACK" and ev.get("entry"):
        lines.append(
            f"   Stop pod vstupom: {format_price(ev['stop'])} | TP1 {format_price(ev['tp1'])} (orientačne)"
        )

    if ev.get("cause_category"):
        cause_text = (ai_coin or {}).get("cause_text", "").strip()
        lines.append(f"   Príčina pohybu: {ev['cause_category']}" + (f" — {cause_text}" if cause_text else ""))

    reason = (ai_coin or {}).get("reason", "").strip()
    if reason:
        lines.append(f"   Analýza: {reason}")

    if ev.get("action_note"):
        lines.append(f"   ⚠️ Poznámka k signálu: {ev['action_note']}")

    findings = (fund_coin or {}).get("findings") or []
    if findings:
        lines.append(f"   Fundament ({fund_coin.get('source_label', '')}):")
        for finding in findings[:2]:
            lines.append(f"     • {fmt_finding(finding)}")

    lines.append(f"   Čo by zmenilo odporúčanie: {ev['flip']}")
    return lines


def format_main_message(slot_name, ctx, safety, evals, ai, changes, state, fund, fund_status):
    regime = market_regime(ctx, evals)
    fear = ctx.get("fear") or {}
    fg_txt = (
        f"{fear.get('value')} ({fear.get('classification')})"
        if fear.get("value") is not None else "N/A"
    )
    btc_price = safe_float((ctx.get("btc_data") or {}).get("price_usd"))

    dom_prev = safe_float((state.get("prev_flags") or {}).get("dominance"))
    dom_now = safe_float(ctx.get("btc_dominance"))
    dom_txt = f"{dom_now:.1f}%" if dom_now is not None else "N/A"
    if dom_now is not None and dom_prev is not None:
        dom_txt += f" ({dom_now - dom_prev:+.1f} p. b.)"

    lines = [
        f"📊 CRYPTO BOT V{VERSION} | analýza {slot_name}",
        f"🕒 {now_local().strftime('%d.%m. %H:%M')}",
        f"🌐 TRH: {regime} | {SAFETY_EMOJI[safety['state']]} Bezpečnostný stav: {safety['state']} (skóre {safety['score']})",
        "",
        "📈 SÚHRN TRHU",
        f"Kapitalizácia: {fmt_big(ctx.get('total_market_cap'))} ({fmt_pct(ctx.get('global_change'), 2)} za 24h) | Objem 24h: {fmt_big(ctx.get('total_volume'))}",
        f"Bitcoin: {format_price(btc_price)} ({fmt_pct(ctx.get('btc_change_24h'), 2)} za 24h) | Dominancia: {dom_txt} | Fear & Greed: {fg_txt}",
    ]

    summary = (ai.get("market_summary") or "").strip()
    if summary:
        lines.append(summary)
    market_cause = (ai.get("market_cause") or "").strip()
    if market_cause:
        lines.append(f"Príčina pohybu trhu: {market_cause}")

    if safety["reasons"]:
        lines.append("Dôvody bezpečnostného stavu: " + "; ".join(safety["reasons"][:4]) + ".")
    else:
        lines.append("Bezpečnostný stav: žiadne významné rizikové signály.")

    lines.append(f"🔎 Fundamentálna vrstva: {fund_status}")
    for finding in (((fund or {}).get("market") or {}).get("findings") or [])[:3]:
        lines.append(f"  • {fmt_finding(finding)}")

    lines.extend(["", "📌 MINCE"])
    ai_by_symbol = {
        str(c.get("symbol", "")).upper(): c
        for c in ai.get("coins", []) if isinstance(c, dict)
    }
    for symbol, ev in evals.items():
        lines.extend(format_coin_block(
            symbol, ev, ctx["portfolio_data"].get(symbol) or {},
            ai_by_symbol.get(symbol), merge_fund_for_coin(fund, state, symbol),
        ))
        lines.append("")

    lines.append("🔄 ZMENY OD POSLEDNEJ ANALÝZY")
    lines.extend(f"• {c}" for c in changes)

    watch = [str(x) for x in (ai.get("conditions_to_watch") or [])[:3] if str(x).strip()]
    if watch:
        lines.extend(["", "👀 Sledovať: " + " | ".join(watch)])

    lines.extend(["", "ℹ️ Analytická pomoc, nie finančné poradenstvo. Bot neobchoduje; rozhodnutie je na tebe."])
    return "\n".join(lines)


ACTION_SEVERITY = {
    "BUY NOW": 0, "BUY PULLBACK": 0, "HOLD": 0, "WAIT": 1, "REDUCE": 2, "SELL": 3,
}


def next_step_text(safety, ev):
    action = ev["action"]
    if action == "SELL":
        return "Zvážiť predaj; investičný scenár sa výrazne zhoršil."
    if action == "REDUCE":
        return "Zvážiť zníženie časti pozície alebo ochranu časti zisku."
    if ev["drawdown_pct"] >= CONFIG["drawdown_deep_pct"]:
        return f"Nedokupovať, sledovať support {format_price(ev.get('support'))}; posúdiť ochranný plán."
    return f"Držať a nedokupovať, sledovať support {format_price(ev.get('support'))}."


def format_safety_alert(kind, safety, ctx, coin_alerts, pump_alerts, evals, state, researched):
    titles = {
        "ESCALATION": f"{SAFETY_EMOJI[safety['state']]} BEZPEČNOSTNÝ ALERT: {safety['previous_state']} → {safety['state']}",
        "WORSENING": f"{SAFETY_EMOJI[safety['state']]} BEZPEČNOSTNÝ ALERT: zhoršenie v stave {safety['state']}",
        "EASING": f"🟢 UVOĽNENIE RIZIKA: {safety['previous_state']} → {safety['state']}",
        None: "⚠️ ALERT RIZIKA MINCE",
    }
    lines = [
        f"CRYPTO AI BOT V{VERSION} — {titles.get(kind, titles[None])}",
        f"🕒 {now_local().strftime('%d.%m. %H:%M')}",
        "",
        f"Trh: kapitalizácia {fmt_pct(ctx.get('global_change'), 2)} za 24h | Bitcoin {format_price((ctx['btc_data'] or {}).get('price_usd'))} "
        f"({fmt_pct(ctx.get('btc_change_24h'), 2)}) | Bezpečnostné skóre {safety['score']}",
    ]
    if safety["reasons"]:
        lines.append("Dôvody: " + "; ".join(safety["reasons"][:5]) + ".")

    if kind in {"ESCALATION", "WORSENING"}:
        if safety["state"] == "CRITICAL":
            lines.append("Odporúčaný ďalší krok: aktívne zvážiť ochranu kapitálu; každú pozíciu posúď samostatne, nepredávaj všetko naraz.")
        else:
            lines.append("Odporúčaný ďalší krok: nedokupovať, pripraviť ochranný plán a sledovať supporty.")

    for symbol, ev, level in coin_alerts:
        data = ctx["portfolio_data"].get(symbol) or {}
        tag = "🔻 HLBOKÝ PREPAD" if level == "DEEP" else "🔻 RIZIKO"
        lines.extend([
            "",
            f"{tag} {symbol}: {format_price(ev['price'])} | od 7-dňového maxima -{ev['drawdown_pct']:.1f}% | 24h {fmt_pct(data.get('change_24h'), 2)}",
            f"   Signál: {ev['action']} | Riziko: {ev['risk_level']} ({ev['risk_pts']} b.)",
            "   Dôvody: " + ("; ".join(ev.get("risk_reasons", [])[:5]) or "—"),
        ])
        if ev.get("cause_category"):
            lines.append(f"   Príčina pohybu: {ev['cause_category']}")
        fund_coin = merge_fund_for_coin(None, state, symbol) if symbol in researched else None
        if fund_coin:
            if fund_coin.get("cause_summary"):
                lines.append(f"   Výsledok hľadania: {fund_coin['cause_summary']}")
            for finding in (fund_coin.get("findings") or [])[:3]:
                lines.append(f"   • {fmt_finding(finding)}")
        elif level == "DEEP":
            lines.append("   Hľadanie príčin: nové hľadanie sa teraz nespustilo (platí predchádzajúce alebo cooldown).")
        lines.append(f"   Ďalší krok: {next_step_text(safety, ev)}")

    market_f = ((state.get("alert_research_market") or {}).get("findings") or []) if researched else []
    if market_f:
        lines.extend(["", "🔎 Trhové fundamenty:"])
        lines.extend(f"   • {fmt_finding(f)}" for f in market_f[:3])

    for item in pump_alerts:
        lines.extend([
            "",
            f"🚀 {item['symbol']}: výrazný rast {item['change_since_last']:+.2f}% od poslednej analýzy | cena {format_price(item['price'])}",
            "   Rast nespúšťa automatický predaj; sleduj, či nenarazí na rezistenciu a či rastie objem.",
        ])

    return "\n".join(lines)


# ============================================================
# BEZPEČNOSTNÝ MONITOR (medzi hlavnými analýzami)
# ============================================================

def run_safety_monitor():
    state = load_state()
    ctx = gather_market_data(state)
    fund = get_usable_fundamentals(state)
    metrics_map, safety, evals = evaluate_all(ctx, state, fund)

    now_utc = datetime.now(timezone.utc)
    store = state.setdefault("alerts", {})
    sstate = dict(state.get("safety") or {})
    last_state = sstate.get("last_alert_state", "NORMAL")
    last_score = safe_float(sstate.get("last_alert_score"), 0)

    # --- 1) bezpečnostný stav ---
    kind = None
    if SAFETY_RANK[safety["state"]] > SAFETY_RANK[last_state]:
        kind = "ESCALATION"
    elif (
        safety["state"] != "NORMAL" and safety["state"] == last_state
        and safety["score"] - last_score >= CONFIG["safety_alert_worsen_pts"]
    ):
        kind = "WORSENING"
    elif SAFETY_RANK[safety["state"]] < SAFETY_RANK[last_state]:
        kind = "EASING"

    # --- 2) alerty mincí ---
    level_rank = {"RISK": 1, "DEEP": 2}
    coin_alerts = []
    for symbol, ev in evals.items():
        if ev.get("risk_level") == "NEZNÁME":
            continue

        dd = ev["drawdown_pct"]
        level = None
        if dd >= CONFIG["drawdown_deep_pct"]:
            level = "DEEP"
        elif (
            (dd >= ev["review_thr"] and ev["risk_pts"] >= CONFIG["risk_elevated_pts"])
            or ev["action"] in {"REDUCE", "SELL"}
        ):
            level = "RISK"

        last = store.get(symbol) or {}

        if level is None:
            if dd < ev["review_thr"] * 0.6:
                store.pop(symbol, None)          # zotavenie -> pamäť alertov sa vynuluje
            continue

        last_rank = level_rank.get(last.get("level"), 0)
        last_dd = safe_float(last.get("drawdown"), 0.0)
        worse_action = (
            bool(last)
            and ACTION_SEVERITY.get(ev["action"], 0) > ACTION_SEVERITY.get(last.get("action"), 0)
        )
        if (
            level_rank[level] > last_rank
            or dd - last_dd >= CONFIG["alert_worsen_pp"]
            or worse_action
        ):
            coin_alerts.append((symbol, ev, level))

    # --- 3) upozornenie na výrazný rast ---
    pump_store = state.setdefault("coin_change_alerts", {})
    pump_alerts = []
    for symbol, data in ctx["portfolio_data"].items():
        if data.get("error"):
            continue
        move = safe_float(data.get("change_since_last"), 0.0)
        last_move = safe_float(pump_store.get(symbol), 0.0)
        if move >= CONFIG["pump_alert_pct"] and move - last_move >= CONFIG["pump_alert_step_pct"]:
            pump_alerts.append({
                "symbol": symbol, "change_since_last": move, "price": data.get("price_usd"),
            })
            pump_store[symbol] = move

    if not (kind or coin_alerts or pump_alerts):
        state["last_run"] = iso_now()
        save_state(state)
        print("Monitor: žiadny alert.")
        return

    # --- 4) hlboké hľadanie IBA pri prepade nad 10 % ---
    researched = []
    deep_symbols = [s for s, _, lvl in coin_alerts if lvl == "DEEP"]
    if deep_symbols:
        research_store = state.setdefault("alert_research", {})
        todo = []
        for symbol in deep_symbols:
            last = research_store.get(symbol) or {}
            ts = parse_timestamp(last.get("ts"))
            age_h = (now_utc - ts).total_seconds() / 3600 if ts else 1e9
            worsened = evals[symbol]["drawdown_pct"] - safe_float(last.get("drawdown"), 0.0) >= CONFIG["deep_search_worsen_pp"]
            if age_h >= CONFIG["deep_search_cooldown_hours"] or worsened:
                todo.append(symbol)

        if todo:
            include_market = len(todo) >= 2 or safety["state"] != "NORMAL"
            result = run_fundamental_research(todo, include_market, ctx, evals, "alert")
            if result["status"] == "ok":
                for symbol in todo:
                    research_store[symbol] = {
                        "ts": result["generated_at"],
                        "drawdown": evals[symbol]["drawdown_pct"],
                        "data": result["coins"].get(symbol),
                    }
                if include_market:
                    state["alert_research_market"] = {
                        "ts": result["generated_at"],
                        **(result.get("market") or {}),
                    }
                researched = todo
                # nový fundament môže zmeniť riziko mincí; prepočítame
                metrics_map, safety, evals = evaluate_all(ctx, state, fund)
                for idx, (symbol, _, level) in enumerate(coin_alerts):
                    coin_alerts[idx] = (symbol, evals[symbol], level)

    message = format_safety_alert(kind, safety, ctx, coin_alerts, pump_alerts, evals, state, researched)
    telegram_send_long(message)

    # --- 5) uloženie stavu ---
    for symbol, ev, level in coin_alerts:
        store[symbol] = {
            "level": level, "drawdown": ev["drawdown_pct"],
            "action": ev["action"], "ts": utc_now_iso(),
        }

    state["safety"] = {
        **sstate,
        "state": safety["state"], "score": safety["score"],
        "reasons": safety["reasons"], "ts": utc_now_iso(),
        "last_alert_state": safety["state"] if kind else last_state,
        "last_alert_score": safety["score"] if kind else last_score,
        "last_alert_ts": utc_now_iso() if kind else sstate.get("last_alert_ts"),
    }
    state["last_run"] = iso_now()
    save_state(state)
    print("Monitor: alert odoslaný.")


# ============================================================
# HLAVNÁ ANALÝZA
# ============================================================

def run_full_analysis(schedule_reason, schedule_slot=None):
    print(f"Starting full analysis V{VERSION}: {schedule_reason}")

    state = load_state()
    ctx = gather_market_data(state)
    news = get_rss_news()

    fund = None
    researched_now = False
    research_failed = False

    if deep_search_allowed(schedule_reason, schedule_slot):
        _, _, evals_pre = evaluate_all(ctx, state, None)
        result = run_fundamental_research(list(PORTFOLIO.keys()), True, ctx, evals_pre, "morning")
        if result["status"] == "ok":
            state["fundamentals"] = result
            fund = result
            researched_now = True
        else:
            research_failed = True

    if fund is None:
        fund = get_usable_fundamentals(state)

    metrics_map, safety, evals = evaluate_all(ctx, state, fund)
    fund_status = fund_status_text(fund, researched_now, research_failed)
    changes = compute_changes(state, ctx, evals, safety)

    payload = build_explain_payload(ctx, safety, evals, news, changes, state, fund, fund_status)
    try:
        ai = gemini_json(explain_prompt(payload), search=False, thinking_level="high")
    except Exception as exc:
        print(f"Gemini vysvetlenie zlyhalo: {exc}")
        ai = fallback_explanation(evals, safety, exc)

    slot_name = slot_label(schedule_slot) or "ručná"
    message = format_main_message(slot_name, ctx, safety, evals, ai, changes, state, fund, fund_status)
    telegram_send_long(message)

    # --- uloženie stavu (kompatibilné s predchádzajúcou štruktúrou last_analysis) ---
    state["last_analysis"] = {
        "market_regime": market_regime(ctx, evals),
        "coins": [
            {
                "symbol": s,
                "action": ev["action"],
                "current_price": ev["price"],
                "market_cap": (ctx["portfolio_data"].get(s) or {}).get("market_cap"),
                "volume_24h": (ctx["portfolio_data"].get(s) or {}).get("volume_24h"),
                "trend_score": ev.get("trend_score"),
                "risk_level": ev.get("risk_level"),
            }
            for s, ev in evals.items()
        ],
    }
    state["last_actions"] = {
        s: {"action": ev["action"], "ts": utc_now_iso(), "trend_score": ev.get("trend_score")}
        for s, ev in evals.items()
    }
    state["prev_flags"] = collect_flags(ctx, evals, safety)
    state["safety"] = {
        "state": safety["state"], "score": safety["score"],
        "reasons": safety["reasons"], "ts": utc_now_iso(),
        "last_alert_state": safety["state"],       # správa už obsahuje aktuálny stav
        "last_alert_score": safety["score"],
        "last_alert_ts": utc_now_iso(),
    }
    state["fear_greed"] = ctx.get("fear")
    state["coin_change_alerts"] = {}               # základ pre rast sa posúva s novou analýzou
    state["last_run"] = iso_now()
    state["last_full_analysis"] = iso_now()
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
