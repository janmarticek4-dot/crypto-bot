import os
import json
import math
import time
import urllib.request
import urllib.parse
import urllib.error
import xml.etree.ElementTree as ET

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


# ============================================================
# KONFIGURÁCIA
# ============================================================

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
COINGECKO_API_KEY = os.environ.get("COINGECKO_API_KEY", "")

GEMINI_MODEL = "gemini-3.8-flash"

LOCAL_TZ = ZoneInfo("Europe/Bratislava")
US_TZ = ZoneInfo("America/New_York")

STATE_FILE = "bot_state.json"

# Tvoje kryptomeny
HELD_COINS = {
    "AAVE": "aave",
    "TAO": "bittensor",
    "FET": "fetch-ai",
    "SOL": "solana",
    "ONDO": "ondo-finance",
    "RENDER": "render-token",
}

# Trhový kontext
MARKET_COINS = {
    "BTC": "bitcoin",
    "ETH": "ethereum",
}

# CoinTelegraph RSS
NEWS_RSS = "https://cointelegraph.com/rss"

# Koľko coinov z top trhu chceme preskúmať
NEW_COIN_LIMIT = 100


# ============================================================
# ZÁKLADNÉ FUNKCIE
# ============================================================

def http_get_json(url, headers=None, timeout=30):
    req = urllib.request.Request(
        url,
        headers=headers or {
            "User-Agent": "Crypto-AI-Bot/1.0"
        }
    )

    with urllib.request.urlopen(req, timeout=timeout) as response:
        data = response.read().decode("utf-8")

    return json.loads(data)


def http_post_json(url, payload, headers=None, timeout=120):
    body = json.dumps(payload).encode("utf-8")

    final_headers = {
        "Content-Type": "application/json",
        "User-Agent": "Crypto-AI-Bot/1.0",
    }

    if headers:
        final_headers.update(headers)

    req = urllib.request.Request(
        url,
        data=body,
        headers=final_headers,
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            data = response.read().decode("utf-8")

        return json.loads(data)

    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="ignore")
        print("HTTP ERROR:", e.code)
        print(error_body[:10000])
        raise


def now_local():
    return datetime.now(LOCAL_TZ)


def safe_float(value, default=None):
    try:
        return float(value)
    except Exception:
        return default


def pct(a, b):
    if a is None or b in (None, 0):
        return None
    return ((a - b) / b) * 100


# ============================================================
# ENVIRONMENT CHECK
# ============================================================

def check_environment():
    missing = []

    if not GEMINI_API_KEY:
        missing.append("GEMINI_API_KEY")

    if not TELEGRAM_TOKEN:
        missing.append("TELEGRAM_TOKEN")

    if not TELEGRAM_CHAT_ID:
        missing.append("TELEGRAM_CHAT_ID")

    if missing:
        raise RuntimeError(
            "Chýbajú GitHub Secrets: " + ", ".join(missing)
        )


# ============================================================
# TELEGRAM
# ============================================================

def send_telegram(message):
    url = (
        f"https://api.telegram.org/bot"
        f"{TELEGRAM_TOKEN}/sendMessage"
    )

    # Telegram má limit 4096 znakov.
    chunks = []

    while len(message) > 3900:
        cut = message.rfind("\n", 0, 3900)

        if cut < 1000:
            cut = 3900

        chunks.append(message[:cut])
        message = message[cut:].lstrip()

    chunks.append(message)

    for chunk in chunks:
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": chunk,
        }

        response = http_post_json(
            url,
            payload,
            timeout=30,
        )

        if not response.get("ok"):
            raise RuntimeError(
                f"Telegram chyba: {response}"
            )

        time.sleep(0.3)


# ============================================================
# COINGECKO
# ============================================================

def cg_headers():
    headers = {
        "User-Agent": "Crypto-AI-Bot/1.0"
    }

    if COINGECKO_API_KEY:
        headers["x-cg-demo-api-key"] = COINGECKO_API_KEY

    return headers


def coingecko_markets(ids):
    ids_string = ",".join(ids)

    url = (
        "https://api.coingecko.com/api/v3/coins/markets"
        "?vs_currency=usd"
        f"&ids={urllib.parse.quote(ids_string)}"
        "&order=market_cap_desc"
        "&per_page=250"
        "&page=1"
        "&sparkline=false"
        "&price_change_percentage=1h,24h,7d"
    )

    return http_get_json(
        url,
        headers=cg_headers(),
        timeout=40,
    )


def coingecko_market_chart(coin_id, days=30):
    url = (
        f"https://api.coingecko.com/api/v3/coins/"
        f"{urllib.parse.quote(coin_id)}/market_chart"
        f"?vs_currency=usd&days={days}"
    )

    return http_get_json(
        url,
        headers=cg_headers(),
        timeout=40,
    )


def coingecko_top_markets():
    url = (
        "https://api.coingecko.com/api/v3/coins/markets"
        "?vs_currency=usd"
        "&order=market_cap_desc"
        f"&per_page={NEW_COIN_LIMIT}"
        "&page=1"
        "&sparkline=false"
        "&price_change_percentage=24h,7d"
    )

    return http_get_json(
        url,
        headers=cg_headers(),
        timeout=40,
    )


# ============================================================
# FEAR & GREED
# ============================================================

def get_fear_greed():
    url = "https://api.alternative.me/fng/?limit=1"

    try:
        data = http_get_json(url, timeout=30)

        item = data["data"][0]

        return {
            "value": int(item["value"]),
            "classification": item["value_classification"],
        }

    except Exception as e:
        print("Fear & Greed chyba:", e)

        return {
            "value": None,
            "classification": "UNKNOWN",
        }


# ============================================================
# COINTELEGRAPH NEWS
# ============================================================

def get_news():
    try:
        req = urllib.request.Request(
            NEWS_RSS,
            headers={
                "User-Agent": "Mozilla/5.0 Crypto-AI-Bot"
            }
        )

        with urllib.request.urlopen(req, timeout=30) as response:
            xml_data = response.read()

        root = ET.fromstring(xml_data)

        articles = []

        for item in root.findall(".//item")[:15]:

            title = item.findtext("title") or ""
            link = item.findtext("link") or ""
            pub_date = item.findtext("pubDate") or ""

            if title:
                articles.append({
                    "title": title.strip(),
                    "url": link.strip(),
                    "date": pub_date.strip(),
                })

        return articles

    except Exception as e:
        print("RSS chyba:", e)
        return []


# ============================================================
# TECHNICKÉ INDIKÁTORY
# ============================================================

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
    if len(values) <= period:
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
            (avg_gain * (period - 1) + gains[i])
            / period
        )

        avg_loss = (
            (avg_loss * (period - 1) + losses[i])
            / period
        )

        if avg_loss == 0:
            current_rsi = 100.0
        else:
            rs = avg_gain / avg_loss
            current_rsi = 100 - (100 / (1 + rs))

    return current_rsi


def macd(values):
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

    signal_valid = ema(valid, 9)

    signal = [None] * (
        len(macd_values) - len(signal_valid)
    )

    signal.extend(signal_valid)

    histogram = []

    for m, s in zip(macd_values, signal):

        if m is None or s is None:
            histogram.append(None)
        else:
            histogram.append(m - s)

    return macd_values, signal, histogram


def atr_proxy(values, period=14):
    if len(values) < period + 1:
        return None

    changes = []

    for i in range(1, len(values)):
        changes.append(
            abs(values[i] - values[i - 1])
        )

    return sum(changes[-period:]) / period


def calculate_technicals(chart):
    prices = [
        safe_float(x[1])
        for x in chart.get("prices", [])
    ]

    volumes = [
        safe_float(x[1])
        for x in chart.get("total_volumes", [])
    ]

    prices = [
        x for x in prices
        if x is not None
    ]

    volumes = [
        x for x in volumes
        if x is not None
    ]

    if len(prices) < 30:
        return {}

    current = prices[-1]

    ema20_values = ema(prices, 20)
    ema50_values = ema(prices, 50)
    ema200_values = ema(prices, 200)

    ema20 = ema20_values[-1]
    ema50 = ema50_values[-1]
    ema200 = ema200_values[-1]

    current_rsi = rsi(prices, 14)

    macd_values, signal_values, histogram = macd(prices)

    current_macd = next(
        (x for x in reversed(macd_values)
         if x is not None),
        None
    )

    current_signal = next(
        (x for x in reversed(signal_values)
         if x is not None),
        None
    )

    current_hist = next(
        (x for x in reversed(histogram)
         if x is not None),
        None
    )

    atr = atr_proxy(prices)

    # Support / resistance približne z posledných 30 dní
    recent_prices = prices[-30:]

    support = min(recent_prices)
    resistance = max(recent_prices)

    # Volume pressure proxy
    volume_pressure = "UNKNOWN"

    if len(volumes) >= 10:
        recent_volume = sum(volumes[-3:]) / 3
        previous_volume = sum(volumes[-10:-3]) / 7

        price_change_3 = pct(
            prices[-1],
            prices[-4]
        )

        if (
            price_change_3 is not None
            and price_change_3 < -2
            and recent_volume > previous_volume * 1.4
        ):
            volume_pressure = "VERY_HIGH_SELL_PRESSURE"

        elif (
            price_change_3 is not None
            and price_change_3 < -1
            and recent_volume > previous_volume * 1.2
        ):
            volume_pressure = "HIGH_SELL_PRESSURE"

        elif (
            price_change_3 is not None
            and price_change_3 < 0
            and recent_volume > previous_volume
        ):
            volume_pressure = "ELEVATED_SELL_PRESSURE"

        elif (
            price_change_3 is not None
            and price_change_3 > 1
            and recent_volume > previous_volume * 1.2
        ):
            volume_pressure = "BUYING_PRESSURE"

        else:
            volume_pressure = "NORMAL"

    trend = "NEUTRAL"

    if ema20 and ema50:

        if current > ema20 > ema50:
            trend = "BULLISH"

        elif current < ema20 < ema50:
            trend = "BEARISH"

        else:
            trend = "MIXED"

    rsi_state = "NEUTRAL"

    if current_rsi is not None:

        if current_rsi >= 70:
            rsi_state = "OVERBOUGHT"

        elif current_rsi >= 55:
            rsi_state = "BULLISH"

        elif current_rsi <= 30:
            rsi_state = "OVERSOLD"

        elif current_rsi <= 45:
            rsi_state = "BEARISH"

    macd_state = "NEUTRAL"

    if (
        current_macd is not None
        and current_signal is not None
    ):

        if (
            current_macd > current_signal
            and current_hist is not None
            and current_hist > 0
        ):
            macd_state = "BULLISH"

        elif (
            current_macd < current_signal
            and current_hist is not None
            and current_hist < 0
        ):
            macd_state = "BEARISH"

        else:
            macd_state = "MIXED"

    return {
        "price": current,
        "ema20": ema20,
        "ema50": ema50,
        "ema200": ema200,
        "rsi14": current_rsi,
        "macd": current_macd,
        "macd_signal": current_signal,
        "macd_histogram": current_hist,
        "atr_proxy": atr,
        "support_30d": support,
        "resistance_30d": resistance,
        "trend": trend,
        "rsi_state": rsi_state,
        "macd_state": macd_state,
        "volume_pressure": volume_pressure,
        "change_24h": pct(
            prices[-1],
            prices[-2]
        ),
        "change_7d": pct(
            prices[-1],
            prices[-min(8, len(prices))]
        ),
    }


# ============================================================
# SAFETY MONITOR
# ============================================================

def safety_score(market_rows):
    """
    Toto NIE JE skutočný order-flow.
    Je to proxy založené na:
    - poklese ceny
    - objeme
    - strate supportu
    - volatilite
    """

    alerts = []

    critical_count = 0
    warning_count = 0

    for symbol, row in market_rows.items():

        change_24h = safe_float(
            row.get("price_change_percentage_24h")
        )

        change_1h = safe_float(
            row.get("price_change_percentage_1h_in_currency")
        )

        volume = safe_float(
            row.get("total_volume")
        )

        market_cap = safe_float(
            row.get("market_cap")
        )

        pressure = "NORMAL"
        reasons = []

        if change_24h is not None:

            if change_24h <= -8:
                pressure = "CRITICAL"
                reasons.append("24h pokles > 8%")

            elif change_24h <= -5:
                pressure = "HIGH"
                reasons.append("24h pokles > 5%")

            elif change_24h <= -3:
                pressure = "ELEVATED"
                reasons.append("24h pokles > 3%")

        if (
            change_1h is not None
            and change_1h <= -3
        ):
            reasons.append("prudký 1h pokles")

            if pressure == "NORMAL":
                pressure = "ELEVATED"

        volume_ratio = None

        if (
            volume is not None
            and market_cap is not None
            and market_cap > 0
        ):
            volume_ratio = volume / market_cap

        if (
            volume_ratio is not None
            and change_24h is not None
            and change_24h < -3
            and volume_ratio > 0.08
        ):
            reasons.append(
                "zvýšený objem pri poklese"
            )

            if pressure == "ELEVATED":
                pressure = "HIGH"

        if pressure == "CRITICAL":
            critical_count += 1

        elif pressure in ("HIGH", "ELEVATED"):
            warning_count += 1

        alerts.append({
            "symbol": symbol,
            "pressure": pressure,
            "change_24h": change_24h,
            "change_1h": change_1h,
            "reasons": reasons,
        })

    if critical_count >= 2:
        state = "CRITICAL"

    elif critical_count >= 1:
        state = "WARNING"

    elif warning_count >= 3:
        state = "WARNING"

    else:
        state = "NORMAL"

    return state, alerts


def load_state():
    if not os.path.exists(STATE_FILE):
        return {
            "safety_state": "NORMAL",
            "last_alert": "",
            "market_safety_mode": False,
        }

    try:
        with open(
            STATE_FILE,
            "r",
            encoding="utf-8"
        ) as f:
            return json.load(f)

    except Exception:
        return {
            "safety_state": "NORMAL",
            "last_alert": "",
            "market_safety_mode": False,
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
            indent=2,
        )


def run_safety_monitor():

    print("Spúšťam SAFETY MONITOR...")

    ids = list(HELD_COINS.values())
    ids.append("bitcoin")

    rows = coingecko_markets(ids)

    market_rows = {}

    for row in rows:

        symbol = row.get(
            "symbol",
            ""
        ).upper()

        market_rows[symbol] = row

    state, alerts = safety_score(
        market_rows
    )

    previous = load_state()

    print("Safety state:", state)

    # Ak sa situácia zhorší, upozorni Telegram
    should_alert = False

    if state == "CRITICAL":
        if previous.get("safety_state") != "CRITICAL":
            should_alert = True

    elif state == "WARNING":
        if previous.get("safety_state") == "NORMAL":
            should_alert = True

    if should_alert:

        lines = [
            "🚨 CRYPTO SAFETY ALERT",
            "",
            f"Stav: {state}",
            "",
        ]

        for item in alerts:

            if item["pressure"] != "NORMAL":

                reasons = ", ".join(
                    item["reasons"]
                )

                change = item["change_24h"]

                if change is None:
                    change_text = "N/A"
                else:
                    change_text = f"{change:.2f}%"

                lines.append(
                    f"• {item['symbol']}: "
                    f"{item['pressure']} "
                    f"({change_text})"
                )

                if reasons:
                    lines.append(
                        f"  {reasons}"
                    )

        if state == "CRITICAL":

            lines.extend([
                "",
                "🛑 MARKET SAFETY MODE",
                "Nové BUY/ADD signály sú dočasne blokované.",
                "Najprv sa musí zlepšiť stav trhu."
            ])

            previous["market_safety_mode"] = True

        send_telegram(
            "\n".join(lines)
        )

    # Ak sa trh vráti do normálu
    if (
        state == "NORMAL"
        and previous.get("market_safety_mode")
    ):

        send_telegram(
            "🟢 MARKET SAFETY MODE OFF\n\n"
            "Predajný tlak sa zmiernil. "
            "Nové BUY/ADD signály sú opäť povolené."
        )

        previous["market_safety_mode"] = False

    previous["safety_state"] = state
    previous["last_check"] = now_local().isoformat()

    save_state(previous)


# ============================================================
# GEMINI JSON SCHEMA
# ============================================================

def gemini_schema():

    coin_schema = {
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
                    "NO TRADE"
                ]
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
                "type": "number"
            },

            "stop": {
                "type": "number"
            },

            "tp1": {
                "type": "number"
            },

            "tp2": {
                "type": "number"
            },

            "risk_reward": {
                "type": "number"
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
            }
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
            "risk_reward",
            "thesis",
            "fundamental_facts",
            "sources"
        ]
    }

    return {
        "type": "object",

        "properties": {

            "market_regime": {
                "type": "string"
            },

            "market_safety": {
                "type": "string"
            },

            "btc_outlook": {
                "type": "string"
            },

            "summary": {
                "type": "string"
            },

            "portfolio": {
                "type": "array",
                "items": coin_schema
            },

            "new_coin": coin_schema
        },

        "required": [
            "market_regime",
            "market_safety",
            "btc_outlook",
            "summary",
            "portfolio",
            "new_coin"
        ]
    }


# ============================================================
# GEMINI
# ============================================================

def gemini_generate(prompt):

    url = (
        "https://generativelanguage.googleapis.com/"
        "v1beta/interactions"
    )

    payload = {

        "model": GEMINI_MODEL,

        "input": prompt,

        "tools": [
            {
                "type": "google_search"
            }
        ],

        "response_format": {
            "type": "text",
            "mime_type": "application/json",
            "schema": gemini_schema()
        }
    }

    response = http_post_json(
        url,
        payload,
        headers={
            "x-goog-api-key": GEMINI_API_KEY,
        },
        timeout=180,
    )

    try:

        output_text = response.get(
            "output_text"
        )

        if output_text:
            return json.loads(output_text)

        # Záložné získanie textu
        for step in response.get(
            "steps",
            []
        ):

            if step.get("type") == "model_output":

                for content in step.get(
                    "content",
                    []
                ):

                    if content.get("type") == "text":

                        text = content.get(
                            "text",
                            ""
                        )

                        if text:
                            return json.loads(text)

    except Exception as e:

        print(
            "Gemini parsing chyba:",
            e
        )

    print(
        "Gemini raw response:"
    )

    print(
        json.dumps(
            response,
            ensure_ascii=False,
            indent=2
        )[:15000]
    )

    raise RuntimeError(
        "Gemini nevrátil platný JSON."
    )


# ============================================================
# PRÍPRAVA DÁT
# ============================================================

def collect_analysis_data():

    print("Získavam trhové dáta...")

    all_ids = list(
        HELD_COINS.values()
    ) + list(
        MARKET_COINS.values()
    )

    market_rows = coingecko_markets(
        list(dict.fromkeys(all_ids))
    )

    market_by_id = {
        row["id"]: row
        for row in market_rows
    }

    technicals = {}

    # Technické dáta len pre držané coiny + BTC + ETH
    for symbol, coin_id in {
        **HELD_COINS,
        **MARKET_COINS,
    }.items():

        try:

            chart = coingecko_market_chart(
                coin_id,
                days=30
            )

            technicals[symbol] = calculate_technicals(
                chart
            )

            time.sleep(0.4)

        except Exception as e:

            print(
                f"Technická analýza {symbol} chyba:",
                e
            )

            technicals[symbol] = {}

    fear_greed = get_fear_greed()

    news = get_news()

    # Top 100 pre hľadanie nového coinu
    top_market = []

    try:
        top_market = coingecko_top_markets()
    except Exception as e:
        print(
            "Top market chyba:",
            e
        )

    return {
        "market": market_by_id,
        "technicals": technicals,
        "fear_greed": fear_greed,
        "news": news,
        "top_market": top_market,
    }


# ============================================================
# PROMPT PRE GEMINI
# ============================================================

def build_prompt(data):

    current_time = now_local()

    state = load_state()

    market_safety_mode = state.get(
        "market_safety_mode",
        False
    )

    prompt = f"""
Si hlavný analytický mozog môjho crypto trading bota.

AKTUÁLNY ČAS:
{current_time.isoformat()}

TIMEZONE:
Europe/Bratislava

MARKET SAFETY MODE:
{market_safety_mode}

DÔLEŽITÉ:
Nechcem nútené obchody.
Ak nie je kvalitná príležitosť, použi WAIT alebo NO TRADE.

MOJE PORTFÓLIO:
AAVE, TAO, FET, SOL, ONDO, RENDER

BTC a ETH používaj ako trhový kontext.

==================================================
TVOJA ÚLOHA
==================================================

1. Zhodnoť celkový stav crypto trhu.

2. Zhodnoť BTC:
   - trend
   - momentum
   - riziko poklesu
   - support/resistance
   - vplyv na altcoiny

3. Zhodnoť každý coin v mojom portfóliu.

4. Hľadaj aj JEDEN nový coin mimo môjho portfólia.

5. Nový coin odporuč iba vtedy, ak má skutočne lepší
   potenciál ako moje existujúce coiny.

6. Ak žiadny nový coin nie je dostatočne kvalitný:
   nastav new_coin.status = "NO TRADE".

==================================================
STATUSY
==================================================

Použi iba:

NEW BUY
ADD
HOLD
WAIT
REDUCE
TAKE PROFIT
EXIT
NO TRADE

==================================================
TECHNICKÁ ANALÝZA
==================================================

Použi:

- EMA20
- EMA50
- EMA200, ak sú dostupné
- RSI14
- MACD
- ATR proxy
- support
- resistance
- 24h zmenu
- 7d zmenu
- volume pressure proxy

Neber jeden indikátor ako rozhodujúci.

==================================================
FUNDAMENTÁLNA ANALÝZA
==================================================

Použi Google Search na overenie AKTUÁLNYCH informácií.

Hľadaj najmä:

- nové partnerstvá
- adopciu
- vývoj siete
- token unlocks
- reguláciu
- ETF / staking / RWA / DeFi
- TVL
- vývoj ekosystému
- hacky
- bezpečnostné problémy
- konkurenciu
- tokenomics
- vývoj tímu
- dôležité správy za posledné dni

Nekopíruj slepo titulky.

Rozlišuj:
FAKT
vs.
ŠPEKULÁCIA

==================================================
OBCHODNÉ NASTAVENIE
==================================================

Pri BUY alebo ADD musíš určiť:

entry
stop
tp1
tp2
risk_reward

R:R počítaj podľa:

risk = abs(entry - stop)

reward = abs(tp1 - entry)

R:R = reward / risk

Ak je R:R < 2.0:
NEODPORÚČAJ BUY ani ADD.

Použi WAIT alebo NO TRADE.

==================================================
OPPORTUNITY vs EXECUTION
==================================================

OPPORTUNITY SCORE:

Ako veľmi je coin atraktívny z pohľadu
potenciálneho rastu.

EXECUTION SCORE:

Ako dobre vyzerá vstup práve teraz.

Príklad:

Opportunity 90
Execution 45

znamená:

"Coin je veľmi zaujímavý,
ale TERAZ ho nekupovať."

==================================================
SELL PRESSURE
==================================================

Volume pressure proxy znamená iba:

pokles ceny + zvýšený objem.

NEVOLAJ TO SKUTOČNÝM ORDER FLOW.

Ak je možnosť silného predajného tlaku,
zohľadni to v Execution Score.

==================================================
MARKET SAFETY MODE
==================================================

Ak je MARKET SAFETY MODE = true:

- žiadne nové BUY
- žiadne nové ADD
- preferuj HOLD / WAIT / REDUCE
- upozorni na riziko

==================================================
SKÓRE
==================================================

Použi 0-100:

technical_score
fundamental_score
fundamental_confidence
opportunity_score
execution_score
confidence

==================================================
ZDROJE
==================================================

Pri fundamentálnych tvrdeniach používaj aktuálne
a dôveryhodné zdroje.

Do sources uveď URL alebo názov zdroja.

Ak niečo nevieš overiť, napíš to.

==================================================
DÁTA Z COINGECKO
==================================================

{json.dumps(data, ensure_ascii=False)}

==================================================
VÝSTUP
==================================================

Vráť iba JSON podľa zadanej schémy.

Žiadny markdown.
Žiadne vysvetľovanie mimo JSON.
"""


    return prompt


# ============================================================
# VALIDÁCIA OBCHODOV
# ============================================================

def validate_coin(coin):

    status = coin.get(
        "status",
        "NO TRADE"
    )

    entry = safe_float(
        coin.get("entry")
    )

    stop = safe_float(
        coin.get("stop")
    )

    tp1 = safe_float(
        coin.get("tp1")
    )

    if status in ("NEW BUY", "ADD"):

        valid = (
            entry is not None
            and stop is not None
            and tp1 is not None
            and stop < entry
            and tp1 > entry
        )

        if not valid:

            coin["status"] = "WAIT"
            coin["risk_reward"] = 0

            return coin

        risk = abs(
            entry - stop
        )

        reward = abs(
            tp1 - entry
        )

        if risk <= 0:

            coin["status"] = "WAIT"
            coin["risk_reward"] = 0

            return coin

        rr = reward / risk

        coin["risk_reward"] = round(
            rr,
            2
        )

        if rr < 2.0:

            coin["status"] = "WAIT"

    return coin


def validate_report(report):

    portfolio = report.get(
        "portfolio",
        []
    )

    validated = []

    for coin in portfolio:

        validated.append(
            validate_coin(coin)
        )

    report["portfolio"] = validated

    report["new_coin"] = validate_coin(
        report.get(
            "new_coin",
            {
                "symbol": "NONE",
                "status": "NO TRADE"
            }
        )
    )

    return report


# ============================================================
# FORMÁTOVANIE TELEGRAM SPRÁVY
# ============================================================

def fmt_number(value):

    if value is None:
        return "N/A"

    try:
        value = float(value)

        if abs(value) >= 1000:
            return f"${value:,.0f}"

        if abs(value) >= 1:
            return f"${value:.2f}"

        return f"${value:.4f}"

    except Exception:
        return str(value)


def format_coin(coin):

    symbol = coin.get(
        "symbol",
        "?"
    )

    status = coin.get(
        "status",
        "NO TRADE"
    )

    opportunity = coin.get(
        "opportunity_score",
        0
    )

    execution = coin.get(
        "execution_score",
        0
    )

    confidence = coin.get(
        "confidence",
        0
    )

    technical = coin.get(
        "technical_score",
        0
    )

    fundamental = coin.get(
        "fundamental_score",
        0
    )

    entry = fmt_number(
        coin.get("entry")
    )

    stop = fmt_number(
        coin.get("stop")
    )

    tp1 = fmt_number(
        coin.get("tp1")
    )

    tp2 = fmt_number(
        coin.get("tp2")
    )

    rr = coin.get(
        "risk_reward",
        0
    )

    thesis = coin.get(
        "thesis",
        ""
    )

    lines = [
        f"🪙 {symbol} — {status}",
        f"Opportunity: {opportunity}/100",
        f"Execution: {execution}/100",
        f"Confidence: {confidence}%",
        f"Technical: {technical}/100",
        f"Fundamental: {fundamental}/100",
    ]

    if status in (
        "NEW BUY",
        "ADD",
        "WAIT"
    ):

        lines.extend([
            "",
            f"Entry: {entry}",
            f"Stop: {stop}",
            f"TP1: {tp1}",
            f"TP2: {tp2}",
            f"R:R: {rr}",
        ])

    lines.extend([
        "",
        f"💡 {thesis}",
    ])

    return "\n".join(lines)


def format_report(report):

    lines = [
        "📊 CRYPTO AI — 4H ANALÝZA",
        "",
        f"Market regime: {report.get('market_regime', 'N/A')}",
        f"Market safety: {report.get('market_safety', 'N/A')}",
        f"BTC outlook: {report.get('btc_outlook', 'N/A')}",
        "",
        f"🧠 {report.get('summary', '')}",
        "",
        "━━━━━━━━━━━━━━━━",
        "💼 PORTFÓLIO",
        "━━━━━━━━━━━━━━━━",
        "",
    ]

    for coin in report.get(
        "portfolio",
        []
    ):

        lines.append(
            format_coin(coin)
        )

        lines.append(
            "\n━━━━━━━━━━━━━━━━\n"
        )

    new_coin = report.get(
        "new_coin"
    )

    lines.extend([
        "🆕 NOVÁ PRÍLEŽITOSŤ",
        "",
        format_coin(new_coin),
        "",
        "⚠️ Toto je analytický signál, nie automatický nákup."
    ])

    return "\n".join(lines)


# ============================================================
# HLAVNÁ ANALÝZA
# ============================================================

def run_analysis():

    print(
        "======================================"
    )

    print(
        "SPÚŠŤAM HLAVNÚ CRYPTO ANALÝZU"
    )

    print(
        "Čas:",
        now_local().strftime(
            "%Y-%m-%d %H:%M:%S %Z"
        )
    )

    data = collect_analysis_data()

    prompt = build_prompt(
        data
    )

    print(
        "Posielam dáta Gemini..."
    )

    report = gemini_generate(
        prompt
    )

    report = validate_report(
        report
    )

    message = format_report(
        report
    )

    send_telegram(
        message
    )

    print(
        "Analýza odoslaná do Telegramu."
    )


# ============================================================
# URČENIE TYPU SPUSTENIA
# ============================================================

def us_market_open_local():

    """
    NYSE/Nasdaq open = 09:30 New York time.
    Prepočítame na Bratislavu.
    """

    current_local = now_local()

    ny_date = current_local.astimezone(
        US_TZ
    ).date()

    ny_open = datetime(
        ny_date.year,
        ny_date.month,
        ny_date.day,
        9,
        30,
        tzinfo=US_TZ,
    )

    return ny_open.astimezone(
        LOCAL_TZ
    )


def should_run_analysis():

    current = now_local()

    # Analýza 07:00
    if current.hour == 7 and current.minute < 5:
        return True

    # Analýza 20:00
    if current.hour == 20 and current.minute < 5:
        return True

    # 15 minút pred otvorením USA
    us_open = us_market_open_local()

    analysis_time = us_open - timedelta(
        minutes=15
    )

    difference = abs(
        (
            current - analysis_time
        ).total_seconds()
    )

    if difference <= 180:
        return True

    return False


# ============================================================
# MAIN
# ============================================================

def main():

    check_environment()

    current = now_local()

    print(
        "Crypto AI Bot"
    )

    print(
        "Bratislava:",
        current.strftime(
            "%Y-%m-%d %H:%M:%S %Z"
        )
    )

    print(
        "USA open:",
        us_market_open_local().strftime(
            "%H:%M %Z"
        )
    )

    # Manuálne spustenie workflow môžeš použiť
    # na okamžitú hlavnú analýzu.
    manual_run = os.environ.get(
        "MANUAL_ANALYSIS",
        "false"
    ).lower() == "true"

    if manual_run:

        print(
            "MANUAL_ANALYSIS=true"
        )

        run_analysis()
        return

    if should_run_analysis():

        run_analysis()

    else:

        run_safety_monitor()


if __name__ == "__main__":
    main()
