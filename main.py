
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
# CRYPTO AI BOT V8.0
# Opatrnejšie odporúčania, kontrola dát a meranie presnosti
#
# Zachováva:
# - CoinGecko, Gemini, Telegram, RSS a Fear & Greed
# - AAVE, TAO, FET, SOL, ONDO, RENDER
# - pravidelné analýzy a bezpečnostný monitor
# - predchádzajúce analýzy a históriu predpovedí
#
# UPOZORNENIE:
# - bot nevykonáva obchody na burze
# - BUY/SELL sú analytické odporúčania, nie príkazy
# - cenové predpovede nie sú štatisticky overené,
#   kým sa nevyhodnotia na dostatočnej vzorke
# ============================================================

VERSION = "8.0"

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()
COINGECKO_API_KEY = os.getenv("COINGECKO_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash").strip()

REQUEST_TIMEOUT = 45
GEMINI_MAX_WAIT = 600
POLL_INTERVAL = 5
STATE_FILE = "bot_state.json"

TZ = ZoneInfo("Europe/Bratislava")
US_TZ = ZoneInfo("America/New_York")

PORTFOLIO = {
    "AAVE": "aave",
    "TAO": "bittensor",
    "FET": "fetch-ai",
    "SOL": "solana",
    "ONDO": "ondo-finance",
    "RENDER": "render-token",
}

CANDIDATES = [
    "sui", "chainlink", "compound-governance-token",
    "avalanche-2", "hyperliquid", "near",
    "injective-protocol", "uniswap", "arbitrum",
    "optimism", "maker", "mantle",
]

RSS_FEEDS = [
    ("CoinTelegraph", "https://cointelegraph.com/rss"),
    ("CoinDesk", "https://www.coindesk.com/arc/outboundfeeds/rss/"),
]

VALID_ACTIONS = {
    "BUY NOW", "BUY PULLBACK", "HOLD",
    "REDUCE", "SELL", "NO TRADE"
}


# ============================================================
# ZÁKLADNÉ POMOCNÉ FUNKCIE
# ============================================================

def now_local():
    return datetime.now(TZ)


def iso_now():
    return now_local().isoformat()


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
    if old in (None, 0) or new is None:
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


def unix_to_iso(value):
    try:
        return datetime.fromtimestamp(
            float(value), timezone.utc
        ).isoformat()
    except (ValueError, TypeError, OSError):
        return None


# ============================================================
# ČASOVÝ PLÁN
# ============================================================

def get_main_analysis_slot(now=None):
    now = now or now_local()

    if now.hour == 7 and now.minute < 30:
        return f"BRATISLAVA_{now.date().isoformat()}_07:00"

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
            if exc.code in {400, 401, 403, 404}:
                raise

        except (urllib.error.URLError, TimeoutError,
                ConnectionError, OSError) as exc:
            last_error = exc

        if attempt < retries - 1:
            time.sleep(2 ** attempt)

    raise last_error or RuntimeError("HTTP požiadavka zlyhala.")


def http_json(url, headers=None, timeout=REQUEST_TIMEOUT, retries=3):
    req = urllib.request.Request(
        url, headers=headers or {}, method="GET"
    )
    raw = http_request(req, timeout, retries)
    return json.loads(raw.decode("utf-8"))


def coingecko_headers():
    headers = {
        "Accept": "application/json",
        "User-Agent": f"CryptoAIBot/{VERSION}"
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
        "per_page": len(ids),
        "page": 1,
        "sparkline": "false",
        "price_change_percentage": "24h,7d",
    })


def coingecko_chart(coin_id, days=90):
    # Nevnucujeme hourly interval: dostupná granularita závisí
    # od plánu a pravidiel CoinGecko.
    return coingecko_get(
        f"coins/{coin_id}/market_chart",
        {"vs_currency": "usd", "days": days}
    )


# ============================================================
# TECHNICKÉ UKAZOVATELE
# ============================================================

def closes_from_chart(chart):
    return [
        {"timestamp": int(p[0]), "price": safe_float(p[1])}
        for p in chart.get("prices", [])
        if len(p) >= 2 and safe_float(p[1]) is not None
    ]


def aggregate_candles(prices, hours=4):
    buckets = {}
    width = hours * 60 * 60 * 1000

    for point in prices:
        ts, price = int(point["timestamp"]), point["price"]
        bucket = (ts // width) * width

        if bucket not in buckets:
            buckets[bucket] = {
                "timestamp": bucket,
                "open": price, "high": price,
                "low": price, "close": price
            }
        else:
            buckets[bucket]["high"] = max(
                buckets[bucket]["high"], price
            )
            buckets[bucket]["low"] = min(
                buckets[bucket]["low"], price
            )
            buckets[bucket]["close"] = price

    return [buckets[k] for k in sorted(buckets)]


def ema(values, period):
    if len(values) < period:
        return [None] * len(values)

    out = [None] * len(values)
    previous = sum(values[:period]) / period
    out[period - 1] = previous
    multiplier = 2 / (period + 1)

    for i in range(period, len(values)):
        previous += (values[i] - previous) * multiplier
        out[i] = previous

    return out


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

    gains = [max(x, 0) for x in changes]
    losses = [max(-x, 0) for x in changes]

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
            "macd": None, "signal": None, "histogram": None
        }

    e12 = ema(values, 12)
    e26 = ema(values, 26)

    series = [
        a - b if a is not None and b is not None else None
        for a, b in zip(e12, e26)
    ]

    valid = [x for x in series if x is not None]
    signal = last_valid(ema(valid, 9))
    current = valid[-1]

    return {
        "macd": current,
        "signal": signal,
        "histogram": current - signal if signal is not None else None
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
            abs(current["low"] - previous["close"])
        ))

    return sum(ranges[-period:]) / period if ranges else None


def recent_support_resistance(candles, lookback=30):
    recent = candles[-lookback:]

    if not recent:
        return {"support": None, "resistance": None}

    return {
        "support": min(c["low"] for c in recent),
        "resistance": max(c["high"] for c in recent)
    }


def technical_summary(candles, live_price=None):
    if not candles:
        return {}

    closes = [c["close"] for c in candles]
    chart_price = closes[-1]
    price = safe_float(live_price, chart_price)

    averages = {
        f"ema{n}": last_valid(ema(closes, n))
        for n in (20, 50, 100, 200)
    }

    sr = recent_support_resistance(candles)
    current_atr = atr(candles)

    above = {
        f"above_ema{n}": (
            price > averages[f"ema{n}"]
            if averages[f"ema{n}"] is not None else None
        )
        for n in (20, 50, 100, 200)
    }

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
            if current_atr and price else None
        ),
        "support_30_candles": sr["support"],
        "resistance_30_candles": sr["resistance"],
        "candles_4h_available": len(candles),
        "last_chart_timestamp": candles[-1]["timestamp"],
    }


def recent_returns(closes):
    result = {}

    for name, bars in {
        "24h": 6, "7d": 42, "30d": 180
    }.items():
        if len(closes) > bars:
            result[name] = round(
                pct_change(closes[-bars - 1], closes[-1]), 3
            )

    return result


def calculate_technical_score(tech):
    """Skóre trendu 0–10; nie je pravdepodobnosť zisku."""

    if not tech or safe_float(tech.get("price")) is None:
        return {
            "score": None,
            "label": "nedostatok dát",
            "reasons": []
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

    r = safe_float(tech.get("rsi14"))

    if r is not None:
        if 50 <= r <= 65:
            score += 0.8
            reasons.append(f"RSI {r:.1f}: pozitívne momentum")
        elif r > 65:
            score += 0.3
            reasons.append(f"RSI {r:.1f}: silné, možná prekúpenosť")
        elif 40 <= r < 50:
            score -= 0.2
            reasons.append(f"RSI {r:.1f}: neutrálne až slabšie")
        elif 30 <= r < 40:
            score -= 0.6
            reasons.append(f"RSI {r:.1f}: slabé momentum")
        else:
            score -= 0.3
            reasons.append(
                f"RSI {r:.1f}: extrémna zóna, možný odraz aj pokles"
            )

    hist = safe_float((tech.get("macd") or {}).get("histogram"))

    if hist is not None:
        if hist > 0:
            score += 0.6
            reasons.append("MACD histogram kladný")
        elif hist < 0:
            score -= 0.6
            reasons.append("MACD histogram záporný")

    if known_emas < 4:
        reasons.append("chýbajú niektoré EMA; skóre má nižšiu istotu")

    score = round(clamp(score, 0, 10), 1)

    return {
        "score": score,
        "label": (
            "silná" if score >= 7
            else "slabá" if score <= 3
            else "zmiešaná"
        ),
        "reasons": reasons,
        "known_emas": known_emas
    }


# ============================================================
# ZBER DÁT A KONTROLA ICH KVALITY
# ============================================================

def collect_coin_data(symbol, coin_id, days=90):
    print(f"Collecting: {symbol}")

    simple = coingecko_simple_price([coin_id])
    current = simple.get(coin_id, {})
    live_price = safe_float(current.get("usd"))

    if live_price is None or live_price <= 0:
        raise RuntimeError(
            f"CoinGecko neposkytol platnú cenu pre {symbol}."
        )

    chart = coingecko_chart(coin_id, days=days)
    candles = aggregate_candles(closes_from_chart(chart))
    tech = technical_summary(candles, live_price)

    if not tech:
        raise RuntimeError(f"Nedostatočné technické dáta: {symbol}")

    last_updated = safe_float(current.get("last_updated_at"))
    data_age_seconds = (
        max(0, time.time() - last_updated)
        if last_updated else None
    )

    warnings = []

    if len(candles) < 200:
        warnings.append(
            f"len {len(candles)} agregovaných sviečok; EMA200 môže chýbať"
        )

    if data_age_seconds is None:
        warnings.append("chýba čas aktualizácie ceny")
    elif data_age_seconds > 900:
        warnings.append("cena môže byť zastaraná")

    chart_price = safe_float(tech.get("chart_last_close"))

    if chart_price and abs(live_price / chart_price - 1) > 0.05:
        warnings.append(
            "živá cena sa výrazne líši od posledného uzavretia grafu"
        )

    score = calculate_technical_score(tech)

    return {
        "symbol": symbol,
        "coin_id": coin_id,
        "price_usd": live_price,
        "market_cap": safe_float(current.get("usd_market_cap")),
        "volume_24h": safe_float(current.get("usd_24h_vol")),
        "change_24h": safe_float(current.get("usd_24h_change")),
        "last_updated": last_updated,
        "data_age_seconds": (
            round(data_age_seconds) if data_age_seconds is not None else None
        ),
        "data_warnings": warnings,
        "technical_4h": tech,
        "technical_score_calc": score,
        "returns": recent_returns([c["close"] for c in candles]),
    }


def shortlist_candidates():
    print("Shortlisting candidate coins...")

    markets = coingecko_markets(CANDIDATES)
    if not markets:
        return CANDIDATES[:3]

    portfolio_ids = set(PORTFOLIO.values())

    filtered = [
        x for x in markets
        if x.get("id") not in portfolio_ids
        and safe_float(x.get("market_cap"), 0) > 100_000_000
        and safe_float(x.get("total_volume"), 0) > 5_000_000
    ]

    filtered.sort(
        key=lambda x: safe_float(x.get("total_volume"), 0),
        reverse=True
    )

    return [x["id"] for x in filtered[:3]]


# ============================================================
# FEAR & GREED A BEZPEČNOSŤ TRHU
# ============================================================

def get_fear_greed():
    try:
        item = http_json(
            "https://api.alternative.me/fng/?limit=1",
            headers={"User-Agent": f"CryptoAIBot/{VERSION}"}
        )["data"][0]

        return {
            "value": int(item["value"]),
            "classification": item["value_classification"],
            "timestamp": item.get("timestamp"),
            "source": "Alternative.me"
        }

    except Exception as exc:
        print(f"Fear & Greed error: {exc}")
        return {
            "value": None,
            "classification": "UNKNOWN",
            "timestamp": None,
            "source": "Alternative.me",
            "error": str(exc)
        }


def market_safety(global_data, simple_prices, btc_data=None):
    """
    Rizikové skóre:
    NORMAL 0–2
    WARNING 3–6
    CRITICAL 7+
    Skóre je orientačný interný indikátor, nie pravdepodobnosť krachu.
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
    macd_hist = safe_float(
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
            reasons.append("BTC RSI pod 30: extrémna slabosť alebo prepredanie")
        elif rsi_value < 35:
            score += 2
            reasons.append("BTC RSI pod 35")
        elif rsi_value < 40:
            score += 1
            reasons.append("BTC RSI pod 40")

    if macd_hist is not None and macd_hist < 0:
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
        "btc_macd_histogram": macd_hist,
        "data_warnings": (
            btc_data.get("data_warnings", [])
            if isinstance(btc_data, dict) else ["BTC technické dáta chýbajú"]
        )
    }


def should_send_safety_alert(current, state):
    level = current.get("state", "NORMAL")
    score = safe_float(current.get("score"), 0)
    previous_level = state.get("last_safety_state", "NORMAL")
    previous_score = safe_float(state.get("last_safety_score"), 0)

    if level == "NORMAL":
        return False, "NORMAL"

    if level != previous_level:
        return True, "STATE_CHANGE"

    if score >= previous_score + 2:
        return True, "SCORE_WORSENING"

    return False, "NO_NEW_ALERT"


# ============================================================
# TELEGRAM
# ============================================================

def telegram_send(text):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        raise RuntimeError("Chýba TELEGRAM_TOKEN alebo TELEGRAM_CHAT_ID.")

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"

    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "disable_web_page_preview": True
    }

    req = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    with urllib.request.urlopen(req, timeout=30) as response:
        result = json.loads(response.read().decode("utf-8"))

    if not result.get("ok"):
        raise RuntimeError(f"Telegram odmietol správu: {result}")

    print("Telegram message sent.")
    return True


def telegram_send_long(text):
    # Telegram má limit 4096 znakov na jednu textovú správu.
    # Rezerva znižuje riziko odmietnutia správy.
    chunks = []
    current = ""

    for line in text.splitlines():
        if len(current) + len(line) + 1 > 3800:
            if current:
                chunks.append(current)
            current = line
        else:
            current += ("\n" if current else "") + line

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
        "User-Agent": "Mozilla/5.0 (compatible; CryptoAIBot/8.0)",
        "Accept": "application/rss+xml,application/xml,text/xml,*/*"
    }

    for source, url in RSS_FEEDS:
        try:
            raw = http_request(
                urllib.request.Request(url, headers=headers),
                timeout=25,
                retries=2
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
                    "pub_date": ""
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

    text = re.sub(r"^```json\s*", "", text.strip(), flags=re.I)
    text = re.sub(r"\s*```$", "", text)

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")

        if start >= 0 and end > start:
            return json.loads(text[start:end + 1])

        raise RuntimeError("Gemini neposlal validný JSON.")


def gemini_analyze(prompt):
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY nie je nastavený.")

    client = genai.Client(api_key=GEMINI_API_KEY)

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

        if status in {
            "failed", "cancelled", "expired",
            "incomplete", "requires_action"
        }:
            raise RuntimeError(f"Gemini analýza skončila: {status}")

        time.sleep(POLL_INTERVAL)


def build_prompt(
    market_global, fear_greed, safety, news,
    portfolio_data, candidate_data, btc_data, state
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

    return f"""
Si disciplinovaný analytik kryptomien a správca rizika.
Píš po slovensky, zrozumiteľne a bez zbytočného žargónu.

Čas Bratislava: {iso_now()}
Portfólio: AAVE, TAO, FET, SOL, ONDO, RENDER.
APT nikdy neodporúčaj.

PRAVIDLÁ DÁT:
- Najprv vyhodnoť dodané údaje a ich kvalitu.
- Google Search použi na overenie aktuálnych správ, nie na
  nahrádzanie dodaných trhových dát vymyslenými cenami.
- Rozlišuj potvrdený fakt, odhad a nepotvrdenú správu.
- Nepíš, že ETF majú odlevy, ak nemáš aktuálny overiteľný zdroj.
- Ak chýbajú dáta, výslovne to uveď a zníž istotu.
- Nekombinuj ceny z rôznych časov bez upozornenia.
- Technické skóre musí zostať presne také, aké vypočítal Python.

ODPORÚČANIA:
Vyber pre každú mincu jednu akciu:
BUY NOW, BUY PULLBACK, HOLD, REDUCE, SELL, NO TRADE.

BUY NOW:
Len pri dostatočnom potvrdení trendu, primeranom riziku
a rozumnom pomere možného zisku k strate.

BUY PULLBACK:
Nákup až v určenej zóne po potvrdení obratu.
Samotné dosiahnutie ceny nepotvrdzuje odraz.

HOLD:
Držať existujúcu pozíciu. Nové nákupy posúď samostatne.
HOLD neznamená ignorovať ďalšie zhoršenie.

REDUCE:
Zmenšiť pozíciu len pri konkrétnom a potvrdenom zhoršení.
Uveď dôvod, podmienku a čo by zmenilo názor.

SELL:
Úplný odchod vyžaduje silný dôvod. Jedno RSI alebo EMA nestačí.
Zohľadni širší trend, potvrdenie podpory, momentum a fundament.

NO TRADE:
Nie je dostatočná výhoda alebo nie sú kvalitné dáta.

TECHNICKÁ ANALÝZA:
- RSI pod 30 môže znamenať prepredanie aj ďalší pokles.
- Cena pod EMA200 nie je sama osebe pokynom na predaj.
- Rozlišuj živú cenu, poslednú uzavretú 4H cenu a EMA.
- Nepíš, že cena testuje podporu, ak je od nej výrazne vzdialená.
- Rozlišuj podporu z nedávneho cenového rozsahu od potvrdenej
  historickej podpory.
- Ak je podpora prelomená len na základe jednej živej ceny,
  počkaj na uzavretie sviečky a potvrdenie.
- Nevymýšľaj objemové signály, likvidácie ani on-chain dáta.
- Technické skóre je indikátor, nie pravdepodobnosť zisku.

FUNDAMENT:
Skóre 0–10 vysvetli na základe využitia, adopcie, príjmov,
tokenomiky, odomykania tokenov, konkurencie a overených správ.
Vysoká kvalita projektu automaticky neznamená lacný token.
Ak nemáš dôkazy, zníž istotu a nevymýšľaj príjmy ani partnerstvá.

PRAVDEPODOBNOSTI:
Bull a bear musia spolu dať 100.
Ide o subjektívny odhad, nie štatisticky overenú pravdepodobnosť.
Nedávaj 55 % len preto, že sa očakáva mierny rast.
Ak chýbajú dáta alebo je situácia nejasná, približ sa k 50/50.

PREDCHÁDZAJÚCA ANALÝZA:
Porovnaj aktuálnu cenu, techniku a scenár s minulým reportom.
Nedrž staré odporúčanie len zo zotrvačnosti.
Vysvetli, čo sa zmenilo a čo by vyvrátilo aktuálny scenár.

NOVÉ PENIAZE:
Nedávaj BUY len preto, aby bolo odporúčanie aktívne.
Ak nie je potvrdená výhoda, drž hotovosť.
Nová minca musí byť lepšia než existujúce alternatívy
po zohľadnení rizika a korelácie s portfóliom.

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

RSS NEWS (titulky nie sú automaticky overené fakty):
{json.dumps(news, ensure_ascii=False)}

PREVIOUS ANALYSIS:
{json.dumps(prior_summary, ensure_ascii=False)}

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
    matches = re.findall(
        r"(?<![A-Za-z])(?:\d+(?:[.,]\d+)?|\.\d+)",
        text.replace(",", ".")
    )

    try:
        return float(matches[0]) if matches else None
    except (ValueError, TypeError):
        return None


def price_range(value):
    if value is None:
        return None

    text = str(value).replace("–", "-").replace("—", "-").replace("−", "-")
    vals = re.findall(
        r"(?<![A-Za-z])(?:\d+(?:\.\d+)?|\.\d+)",
        text.replace(",", ".")
    )

    try:
        nums = [float(v) for v in vals]
        return (min(nums[:2]), max(nums[:2])) if nums else None
    except ValueError:
        return None


def calculate_rr(buy_zone, invalidation, tp1, tp2):
    zone = price_range(buy_zone)
    inv = price_number(invalidation)
    t1 = price_number(tp1)
    t2 = price_number(tp2)

    if not zone or inv is None or t1 is None or t2 is None:
        return None

    entry = sum(zone) / 2
    risk = entry - inv

    if risk <= 0 or t1 <= entry or t2 <= entry:
        return None

    return {
        "rr_tp1": (t1 - entry) / risk,
        "rr_tp2": (t2 - entry) / risk
    }


def validate_and_correct_analysis(
    analysis, safety, portfolio_data, previous_analysis
):
    if not isinstance(analysis, dict) or not isinstance(
        analysis.get("coins"), list
    ):
        raise RuntimeError("Gemini neposlal očakávaný JSON.")

    previous = {
        str(c.get("symbol", "")).upper(): c
        for c in previous_analysis.get("coins", [])
        if isinstance(c, dict)
    }

    by_symbol = {
        str(c.get("symbol", "")).upper(): c
        for c in analysis["coins"]
        if isinstance(c, dict)
    }

    validated = []

    for symbol, coin_id in PORTFOLIO.items():
        coin = by_symbol.get(symbol)

        if coin is None:
            coin = {
                "symbol": symbol,
                "action": "HOLD",
                "reason": "Chýba platné odporúčanie; bezpečný náhradný stav HOLD.",
                "fundamental_evidence": "Analýza nebola dodaná."
            }

        coin["symbol"] = symbol
        data = portfolio_data.get(symbol, {})
        actual_price = safe_float(data.get("price_usd"))
        tech = data.get("technical_4h", {})
        calc = data.get("technical_score_calc", {})

        if actual_price is not None:
            coin["current_price"] = actual_price

        coin["technical_score"] = calc.get("score")
        coin["technical_score_label"] = calc.get("label", "nedostatok dát")
        coin["technical_score_reasons"] = calc.get("reasons", [])
        coin["data_warnings"] = data.get("data_warnings", [])

        if data.get("error") or actual_price is None:
            coin["action"] = "NO TRADE"
            coin["action_guard_note"] = (
                "Nedostatočné aktuálne dáta. Automatické odporúčanie "
                "nákupu alebo predaja sa nepovažuje za spoľahlivé."
            )

        coin["fundamental_score"] = round(clamp(
            safe_float(coin.get("fundamental_score"), 5) or 5, 0, 10
        ), 1)

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

        price = safe_float(tech.get("price"))
        e50 = safe_float(tech.get("ema50"))
        e100 = safe_float(tech.get("ema100"))
        e200 = safe_float(tech.get("ema200"))
        rsi_value = safe_float(tech.get("rsi14"))
        hist = safe_float((tech.get("macd") or {}).get("histogram"))
        support = safe_float(tech.get("support_30_candles"))

        below_50_200 = (
            price is not None and e50 is not None and e200 is not None
            and price < e50 and price < e200
        )

        momentum_negative = hist is not None and hist < 0

        support_broken = (
            price is not None and support is not None
            and price < support * 0.995
        )

        bearish_signals = sum([
            bool(below_50_200),
            bool(momentum_negative),
            bool(support_broken)
        ])

        # Predaj vyžaduje aspoň dva nezávislé signály.
        if action in {"SELL", "REDUCE"} and bearish_signals < 2:
            coin["action_guard_note"] = (
                "Predaj upravený na HOLD: Python nenašiel aspoň "
                "dva nezávislé signály zhoršenia."
            )
            action = "HOLD"

        # Pri prepredaní sa SELL neblokuje navždy, ale musí byť
        # podporený všetkými tromi signálmi.
        elif (
            action == "SELL"
            and rsi_value is not None
            and rsi_value < 30
            and bearish_signals < 3
        ):
            coin["action_guard_note"] = (
                "SELL upravený na HOLD: RSI je pod 30 a "
                "pokles nie je potvrdený všetkými tromi signálmi."
            )
            action = "HOLD"

        if safety.get("state") == "CRITICAL" and action == "BUY NOW":
            coin["action_guard_note"] = (
                str(coin.get("action_guard_note", "")) +
                " Safety CRITICAL: BUY NOW upravené na BUY PULLBACK."
            ).strip()
            action = "BUY PULLBACK"

        # Pri chýbajúcich technických dátach neodporúčaj nákup.
        if calc.get("score") is None and action in {"BUY NOW", "BUY PULLBACK"}:
            action = "NO TRADE"
            coin["action_guard_note"] = (
                "Nákup zablokovaný: chýbajú technické dáta."
            )

        coin["action"] = action

        bull = safe_float(coin.get("bull_probability"), 50)
        bull = 50 if bull is None else bull

        if 0 < bull <= 1:
            bull *= 100

        bull = clamp(bull, 0, 100)

        if safety.get("state") == "WARNING":
            bull = min(bull, 65)
        elif safety.get("state") == "CRITICAL":
            bull = min(bull, 55)

        coin["bull_probability"] = round(bull)
        coin["bear_probability"] = round(100 - bull)

        outlook_prob = safe_float(coin.get("outlook_probability"), 50)
        coin["outlook_probability"] = round(
            clamp(50 if outlook_prob is None else outlook_prob, 5, 95)
        )

        outlook_pct = safe_float(coin.get("outlook_pct"), 0)
        coin["outlook_pct"] = round(
            clamp(0 if outlook_pct is None else outlook_pct, -30, 30), 2
        )

        direction = str(coin.get("outlook_direction", "do strany")).lower()

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

            if not coin.get("previous_comparison"):
                coin["previous_comparison"] = (
                    "Porovnaj aktuálne dáta s predchádzajúcou analýzou."
                )
        else:
            coin["action_change"] = "Prvá uložená analýza"
            coin["previous_comparison"] = (
                "Zatiaľ nie je staršia analýza na porovnanie."
            )

        rr = calculate_rr(
            coin.get("buy_zone_1"),
            coin.get("invalidation"),
            coin.get("tp1"),
            coin.get("tp2")
        )

        coin["risk_reward"] = (
            f"1:{rr['rr_tp1']:.1f} / 1:{rr['rr_tp2']:.1f}"
            if rr else "N/A"
        )

        validated.append(coin)

    analysis["coins"] = validated
    analysis["action"] = "INDIVIDUAL COIN ACTIONS"

    return analysis


# ============================================================
# KONTROLA PREDCHÁDZAJÚCICH PREDPOVEDÍ
# ============================================================

def evaluate_previous_forecasts(state, current_data):
    """
    Vyhodnocuje predpovede staré aspoň 23 hodín.
    Meria smer aj rozdiel medzi odhadovaným a skutočným pohybom.
    Jedna predpoveď nie je dôkazom dlhodobej presnosti.
    """

    forecasts = state.get("forecast_history", [])
    now = datetime.now(timezone.utc)
    results = []

    for forecast in forecasts[-240:]:
        try:
            created = datetime.fromisoformat(
                forecast["timestamp"].replace("Z", "+00:00")
            )

            age_hours = (now - created).total_seconds() / 3600

            if age_hours < 23:
                continue

            symbol = forecast["symbol"]
            price_now = safe_float(
                current_data.get(symbol, {}).get("price_usd")
            )
            price_then = safe_float(forecast.get("price"))

            if not price_now or not price_then:
                continue

            actual_pct = pct_change(price_then, price_now)
            predicted_pct = safe_float(forecast.get("outlook_pct"), 0) or 0

            predicted_dir = str(
                forecast.get("outlook_direction", "do strany")
            ).lower()

            actual_dir = (
                "rast" if actual_pct > 0.5
                else "pokles" if actual_pct < -0.5
                else "do strany"
            )

            results.append({
                "symbol": symbol,
                "predicted_pct": predicted_pct,
                "actual_pct": round(actual_pct, 2),
                "predicted_direction": predicted_dir,
                "actual_direction": actual_dir,
                "direction_hit": predicted_dir == actual_dir,
                "absolute_error_pct": round(
                    abs(predicted_pct - actual_pct), 2
                ),
                "age_hours": round(age_hours, 1)
            })

        except Exception as exc:
            print(f"Forecast evaluation error: {exc}")
            continue

    return results


def forecast_accuracy_summary(state):
    """
    Zhrnutie historickej úspešnosti podľa dostupných záznamov.
    Nejde o nezávislý backtest ani záruku budúcich výsledkov.
    """

    history = state.get("forecast_evaluations", [])
    usable = [
        x for x in history
        if isinstance(x, dict) and "direction_hit" in x
    ]

    if not usable:
        return {
            "sample_size": 0,
            "direction_accuracy_pct": None,
            "mean_absolute_error_pct": None
        }

    hits = sum(bool(x["direction_hit"]) for x in usable)
    errors = [
        safe_float(x.get("absolute_error_pct"))
        for x in usable
        if safe_float(x.get("absolute_error_pct")) is not None
    ]

    return {
        "sample_size": len(usable),
        "direction_accuracy_pct": round(
            hits / len(usable) * 100, 1
        ),
        "mean_absolute_error_pct": (
            round(sum(errors) / len(errors), 2) if errors else None
        )
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
        "🚨 CRYPTO AI BOT — KRÍZOVÝ ALERT"
        if critical else "⚠️ CRYPTO AI BOT — BEZPEČNOSTNÝ ALERT",
        "",
        f"🛡 Safety: {safety.get('state')} ({safety.get('score', 0)})",
        "Upozornenie na riziko, nie automatický pokyn na predaj."
    ]

    for key, label in [
        ("btc_change_24h", "BTC 24h"),
        ("market_cap_change_24h", "Market cap 24h")
    ]:
        if safety.get(key) is not None:
            lines.append(f"{label}: {safety[key]:+.2f}%")

    for key, label in [
        ("btc_ema20", "BTC 4H EMA20"),
        ("btc_ema50", "BTC 4H EMA50"),
        ("btc_ema100", "BTC 4H EMA100"),
        ("btc_ema200", "BTC 4H EMA200")
    ]:
        if safety.get(key) is not None:
            lines.append(f"{label}: {format_price(safety[key])}")

    if safety.get("btc_rsi14") is not None:
        lines.append(f"BTC 4H RSI: {safety['btc_rsi14']:.1f}")

    if fear_greed.get("value") is not None:
        lines.append(
            f"Fear & Greed: {fear_greed['value']}/100 "
            f"({fear_greed.get('classification', '')})"
        )

    if safety.get("reasons"):
        lines.extend([
            "", "Dôvody:",
            *[f"• {x}" for x in safety["reasons"][:8]]
        ])

    if safety.get("data_warnings"):
        lines.extend([
            "", "Upozornenia na dáta:",
            *[f"• {x}" for x in safety["data_warnings"][:4]]
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
        "Sleduj uzavretie 4H sviečok, podporu, MACD a širší trh."
    ])

    return "\n".join(lines)


def coin_priority(coin):
    action = str(coin.get("action", "")).upper()

    return {
        "SELL": 0, "REDUCE": 1, "BUY NOW": 2,
        "BUY PULLBACK": 3, "HOLD": 4, "NO TRADE": 5
    }.get(action, 6)


def format_bot_message(
    analysis, safety, fear_greed, forecast_results=None,
    accuracy=None
):
    coins = sorted(
        analysis.get("coins", []),
        key=coin_priority
    )

    lines = [
        f"📊 CRYPTO AI BOT V{VERSION} — 4H ANALÝZA",
        f"🕒 {iso_now()}",
        f"🌐 Trh: {analysis.get('market_regime', 'N/A')}",
        f"🛡 Safety: {safety.get('state', 'N/A')} "
        f"({safety.get('score', 0)})"
    ]

    lines.extend(f"• {r}" for r in safety.get("reasons", []))

    if fear_greed.get("value") is not None:
        lines.append(
            f"😱 Fear & Greed: {fear_greed['value']}/100 "
            f"({fear_greed.get('classification', '')})"
        )

    if accuracy and accuracy.get("sample_size", 0) > 0:
        lines.extend([
            "",
            "📐 HISTORICKÁ KONTROLA PREDIKCIÍ",
            f"Vzorka: {accuracy['sample_size']} vyhodnotených predpovedí",
            f"Správny smer: {accuracy['direction_accuracy_pct']}%",
            f"Priemerná absolútna chyba pohybu: "
            f"{accuracy['mean_absolute_error_pct']}%"
        ])
    else:
        lines.extend([
            "",
            "📐 Historická presnosť: zatiaľ nedostatok vyhodnotených dát."
        ])

    lines.extend(["", "⚡ RÝCHLY AKČNÝ PLÁN:"])

    for coin in coins:
        action = coin.get("action", "HOLD")
        emoji = (
            "🔴" if action in {"SELL", "REDUCE"}
            else "🟢" if "BUY" in action
            else "🟡"
        )
        lines.append(f"{emoji} {coin.get('symbol')}: {action}")

    lines.extend([
        "", "🧠 Makro:",
        str(analysis.get("market_summary", ""))
    ])

    for coin in coins:
        action = coin.get("action", "HOLD")
        symbol = coin.get("symbol", "?")
        emoji = (
            "🔴" if action in {"SELL", "REDUCE"}
            else "🟢" if "BUY" in action
            else "🟡"
        )

        lines.extend([
            "", f"━━ {emoji} {symbol} ━━",
            f"Akcia: {action}",
            f"Cena: {format_price(coin.get('current_price'))}",
            f"Predikcia 24h: {coin.get('outlook_direction', 'do strany')}, "
            f"{safe_float(coin.get('outlook_pct'), 0):+.1f}% "
            f"(odhad {coin.get('outlook_probability', 50)}%)",
            f"🐂 Bull: {coin.get('bull_probability', 50)}% | "
            f"🐻 Bear: {coin.get('bear_probability', 50)}%",
            f"Technika: {coin.get('technical_score', 'N/A')}/10 "
            f"({coin.get('technical_score_label', 'N/A')})"
        ])

        if coin.get("technical_score_reasons"):
            lines.append(
                "Technické signály: " +
                "; ".join(coin["technical_score_reasons"][:6])
            )

        lines.append(
            f"Fundament: {coin.get('fundamental_score', 'N/A')}/10 "
            f"| istota: {coin.get('fundamental_confidence', 'N/A')}"
        )

        if coin.get("fundamental_evidence"):
            lines.append(
                f"Fundament – dôvody: {coin['fundamental_evidence']}"
            )

        if coin.get("data_warnings"):
            lines.append(
                "⚠️ Dáta: " + "; ".join(coin["data_warnings"][:3])
            )

        if "BUY" in action:
            for label, key in [
                ("Nákupná zóna 1", "buy_zone_1"),
                ("Nákupná zóna 2", "buy_zone_2"),
                ("Invalidácia", "invalidation"),
                ("TP1", "tp1"), ("TP2", "tp2"),
                ("R:R", "risk_reward")
            ]:
                lines.append(f"{label}: {coin.get(key, 'N/A')}")

        lines.append(f"Zmena akcie: {coin.get('action_change', 'N/A')}")

        if coin.get("action_guard_note"):
            lines.append("🛡 Ochrana: " + coin["action_guard_note"])

        if coin.get("previous_comparison"):
            lines.append(
                "Oproti minule: " + str(coin["previous_comparison"])
            )

        if coin.get("new_money_plan"):
            lines.append("Nové peniaze: " + str(coin["new_money_plan"]))

        if coin.get("confirmation_needed"):
            lines.append("Potvrdenie: " + str(coin["confirmation_needed"]))

        if coin.get("bear_case"):
            lines.append("Medvedí scenár: " + str(coin["bear_case"]))

        if coin.get("bull_case"):
            lines.append("Býčí scenár: " + str(coin["bull_case"]))

        if coin.get("reason"):
            lines.append("Záver: " + str(coin["reason"]))

    lines.extend([
        "", "🚀 Najlepšia príležitosť:",
        str(analysis.get("best_opportunity", "N/A")),
        "", f"🆕 Nová kryptomena: {analysis.get('new_coin', 'NO TRADE')}",
        f"Akcia: {analysis.get('new_coin_action', 'NO TRADE')}",
        f"Dôvod: {analysis.get('new_coin_reason', '')}",
        "", f"⚠️ Vyhnúť sa: {analysis.get('avoid', '')}"
    ])

    if analysis.get("conditions_to_watch"):
        lines.extend([
            "", "👀 Sledovať:",
            *[
                f"• {x}"
                for x in analysis["conditions_to_watch"][:8]
            ]
        ])

    if forecast_results:
        lines.extend([
            "", "📉 KONTROLA PREDCHÁDZAJÚCICH PREDPOVEDÍ:"
        ])

        for result in forecast_results[-12:]:
            lines.append(
                f"• {result['symbol']}: smer "
                f"{result['predicted_direction']} "
                f"{result['predicted_pct']:+.1f}%, "
                f"skutočnosť {result['actual_direction']} "
                f"{result['actual_pct']:+.2f}% — "
                f"{'zhoda' if result['direction_hit'] else 'nezhoda'}; "
                f"chyba odhadu {result['absolute_error_pct']:.2f} p. b."
            )

    lines.extend([
        "",
        "Poznámka: skóre a predikcie sú odhady, nie záruky.",
        "Bot nevykonáva obchody. Nie je to finančné poradenstvo."
    ])

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
        btc = {}

    safety = market_safety(market_global, simple, btc)
    state = load_state()
    previous = state.get("last_analysis", {})

    prev_coins = {
        str(c.get("symbol", "")).upper(): c
        for c in previous.get("coins", [])
        if isinstance(c, dict)
    }

    portfolio_context = []

    for symbol, coin_id in PORTFOLIO.items():
        try:
            data = collect_coin_data(symbol, coin_id, days=35)
            tech = data.get("technical_4h", {})
            price = safe_float(data.get("price_usd"))
            rsi_value = safe_float(tech.get("rsi14"))
            prev = prev_coins.get(symbol, {})

            if rsi_value is not None and rsi_value < 30:
                interpretation = (
                    "Prepredané; možný odraz aj pokračovanie poklesu. "
                    "Nie je to samostatný signál na predaj."
                )
            elif tech.get("above_ema200") is False:
                interpretation = (
                    "Zvýšené riziko, ale samotná EMA200 nepotvrdzuje predaj."
                )
            else:
                interpretation = (
                    "Indikátory samy osebe nepotvrdzujú nútený predaj."
                )

            portfolio_context.append({
                "symbol": symbol,
                "price": price,
                "rsi": round(rsi_value, 1) if rsi_value is not None else None,
                "technical_score": data.get(
                    "technical_score_calc", {}
                ).get("score"),
                "action": prev.get("action", "N/A"),
                "interpretation": interpretation
            })

        except Exception as exc:
            print(f"Safety monitor error for {symbol}: {exc}")

    should_alert, reason = should_send_safety_alert(safety, state)

    if should_alert:
        telegram_send_long(
            format_safety_alert(safety, fear, portfolio_context)
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
        list(PORTFOLIO.values()) + CANDIDATES + ["bitcoin"]
    ))

    simple = coingecko_simple_price(all_ids)
    news = get_rss_news()

    btc_data = collect_coin_data("BTC", "bitcoin")
    safety = market_safety(market_global, simple, btc_data)

    portfolio_data = {}

    for symbol, coin_id in PORTFOLIO.items():
        try:
            portfolio_data[symbol] = collect_coin_data(symbol, coin_id)
        except Exception as exc:
            print(f"Portfolio data error {symbol}: {exc}")
            portfolio_data[symbol] = {
                "symbol": symbol,
                "coin_id": coin_id,
                "error": str(exc),
                "data_warnings": ["Zber dát zlyhal"],
                "technical_4h": {},
                "technical_score_calc": {
                    "score": None,
                    "label": "nedostatok dát",
                    "reasons": []
                }
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
                "error": str(exc)
            }

    state = load_state()
    previous_analysis = state.get("last_analysis", {})

    prompt = build_prompt(
        market_global, fear, safety, news,
        portfolio_data, candidate_data, btc_data, state
    )

    analysis = gemini_analyze(prompt)

    analysis = validate_and_correct_analysis(
        analysis, safety, portfolio_data, previous_analysis
    )

    forecast_results = evaluate_previous_forecasts(
        state, portfolio_data
    )

    # Uložíme vyhodnotenia iba raz, podľa časovej značky a symbolu.
    evaluations = state.get("forecast_evaluations", [])
    existing_keys = {
        (x.get("timestamp"), x.get("symbol"))
        for x in evaluations
        if isinstance(x, dict)
    }

    for result in forecast_results:
        # Identifikátor vyhodnotenia je vytvorený z pôvodnej predpovede
        # v histórii; rovnaký výsledok sa nepridá opakovane.
        key = (result.get("forecast_timestamp"), result["symbol"])
        if key not in existing_keys:
            evaluations.append({
                **result,
                "evaluated_at": datetime.now(timezone.utc).isoformat()
            })
            existing_keys.add(key)

    state["forecast_evaluations"] = evaluations[-500:]
    accuracy = forecast_accuracy_summary(state)

    message = format_bot_message(
        analysis, safety, fear, forecast_results, accuracy
    )

    # Pridaj nové predpovede až po vyhodnotení predchádzajúcich.
    history = state.get("forecast_history", [])
    now_utc = datetime.now(timezone.utc).isoformat()

    for coin in analysis.get("coins", []):
        history.append({
            "timestamp": now_utc,
            "symbol": coin["symbol"],
            "price": safe_float(coin.get("current_price")),
            "outlook_direction": str(
                coin.get("outlook_direction", "do strany")
            ).lower(),
            "outlook_pct": safe_float(coin.get("outlook_pct"), 0),
        })

    state["forecast_history"] = history[-500:]

    # Správa musí byť doručená pred označením slotu za dokončený.
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
