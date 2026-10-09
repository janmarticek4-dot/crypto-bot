
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
# CRYPTO AI BOT V6.0
# Ochrana pred predčasným predajom, bezpečnejšie alerty,
# kontrola doručenia Telegram správ a porovnanie odporúčaní.
# ============================================================

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()
COINGECKO_API_KEY = os.getenv("COINGECKO_API_KEY", "").strip()

GEMINI_MODEL = "gemini-3.8-flash"

REQUEST_TIMEOUT = 60
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


# ============================================================
# ZÁKLADNÉ FUNKCIE
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
            value = value.replace("$", "").replace(",", "").strip()
        return float(value)
    except (ValueError, TypeError):
        return default


def pct_change(old, new):
    if old in (None, 0) or new is None:
        return None
    return (new - old) / old * 100.0


def clamp(value, minimum, maximum):
    return max(minimum, min(maximum, value))


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
    except Exception as e:
        print(f"State read error: {e}")
        return {}


def save_state(state):
    temporary = STATE_FILE + ".tmp"
    try:
        with open(temporary, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        os.replace(temporary, STATE_FILE)
    except Exception as e:
        print(f"State save error: {e}")
        raise


# ============================================================
# PLÁNOVANIE
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

    state = load_state()
    if state.get("last_main_slot") == slot:
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

def http_request(req, timeout=REQUEST_TIMEOUT, retries=4):
    last_error = None

    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                return response.read()

        except urllib.error.HTTPError as e:
            last_error = e
            if e.code in {400, 401, 403, 404}:
                raise
            if attempt < retries - 1:
                time.sleep(2 ** attempt)

        except (urllib.error.URLError, TimeoutError,
                ConnectionError, OSError) as e:
            last_error = e
            if attempt < retries - 1:
                time.sleep(2 ** attempt)

    raise last_error or RuntimeError("HTTP požiadavka zlyhala.")


def http_json(url, headers=None, timeout=REQUEST_TIMEOUT, retries=4):
    req = urllib.request.Request(
        url, headers=headers or {}, method="GET"
    )
    raw = http_request(req, timeout, retries)
    return json.loads(raw.decode("utf-8"))


def coingecko_headers():
    headers = {
        "Accept": "application/json",
        "User-Agent": "CryptoAIBot/6.0",
    }
    if COINGECKO_API_KEY:
        headers["x-cg-demo-api-key"] = COINGECKO_API_KEY
    return headers


def coingecko_get(endpoint, params=None):
    base = "https://api.coingecko.com/api/v3"
    url = f"{base}/{endpoint}"
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
    return coingecko_get(
        f"coins/{coin_id}/market_chart",
        {
            "vs_currency": "usd",
            "days": days,
            "interval": "hourly",
        },
    )


# ============================================================
# TECHNICKÁ ANALÝZA
# ============================================================

def closes_from_chart(chart):
    return [
        {"timestamp": p[0], "price": safe_float(p[1])}
        for p in chart.get("prices", [])
        if len(p) >= 2 and safe_float(p[1]) is not None
    ]


def aggregate_candles(prices, hours=4):
    buckets = {}
    bucket_ms = hours * 60 * 60 * 1000

    for p in prices:
        timestamp = int(p["timestamp"])
        price = p["price"]
        bucket = (timestamp // bucket_ms) * bucket_ms

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

    return [buckets[k] for k in sorted(buckets)]


def ema(values, period):
    if len(values) < period:
        return [None] * len(values)

    result = [None] * len(values)
    previous = sum(values[:period]) / period
    result[period - 1] = previous
    multiplier = 2 / (period + 1)

    for i in range(period, len(values)):
        previous = (
            (values[i] - previous) * multiplier + previous
        )
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
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def macd(values):
    if len(values) < 35:
        return {"macd": None, "signal": None, "histogram": None}

    e12 = ema(values, 12)
    e26 = ema(values, 26)
    values_macd = [
        a - b if a is not None and b is not None else None
        for a, b in zip(e12, e26)
    ]

    valid = [x for x in values_macd if x is not None]
    signal_values = ema(valid, 9)
    current = valid[-1]
    signal = signal_values[-1]

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
        return {"support": None, "resistance": None}

    return {
        "support": min(c["low"] for c in recent),
        "resistance": max(c["high"] for c in recent),
    }


def technical_summary(candles):
    if not candles:
        return {}

    closes = [c["close"] for c in candles]
    current = closes[-1]
    e20 = last_valid(ema(closes, 20))
    e50 = last_valid(ema(closes, 50))
    e100 = last_valid(ema(closes, 100))
    e200 = last_valid(ema(closes, 200))
    sr = recent_support_resistance(candles)
    current_atr = atr(candles)

    return {
        "price": current,
        "ema20": e20,
        "ema50": e50,
        "ema100": e100,
        "ema200": e200,
        "rsi14": rsi(closes),
        "macd": macd(closes),
        "atr14": current_atr,
        "atr_percent": (
            current_atr / current * 100
            if current_atr and current else None
        ),
        "support_30_candles": sr["support"],
        "resistance_30_candles": sr["resistance"],
        "above_ema20": current > e20 if e20 is not None else None,
        "above_ema50": current > e50 if e50 is not None else None,
        "above_ema100": current > e100 if e100 is not None else None,
        "above_ema200": current > e200 if e200 is not None else None,
    }


def recent_returns(closes):
    if not closes:
        return {}

    result = {}
    for name, bars in {"24h": 6, "7d": 42, "30d": 180}.items():
        if len(closes) > bars:
            result[name] = pct_change(closes[-bars - 1], closes[-1])
    return result


def collect_coin_data(symbol, coin_id, days=90):
    print(f"Collecting: {symbol}")

    simple = coingecko_simple_price([coin_id])
    current = simple.get(coin_id, {})
    chart = coingecko_chart(coin_id, days=days)
    prices = closes_from_chart(chart)
    candles = aggregate_candles(prices)
    technical = technical_summary(candles)

    return {
        "symbol": symbol,
        "coin_id": coin_id,
        "price_usd": current.get("usd"),
        "market_cap": current.get("usd_market_cap"),
        "volume_24h": current.get("usd_24h_vol"),
        "change_24h": current.get("usd_24h_change"),
        "last_updated": current.get("last_updated_at"),
        "technical_4h": technical,
        "returns": recent_returns([c["close"] for c in candles]),
    }


def shortlist_candidates():
    print("Shortlisting candidate coins...")
    market_data = coingecko_markets(CANDIDATES)
    if not market_data:
        return CANDIDATES[:3]

    portfolio_ids = set(PORTFOLIO.values())
    filtered = [
        x for x in market_data
        if x.get("id") not in portfolio_ids
        and safe_float(x.get("market_cap"), 0) > 100_000_000
    ]
    filtered.sort(
        key=lambda x: (
            safe_float(x.get("total_volume"), 0),
            safe_float(x.get("market_cap"), 0),
        ),
        reverse=True,
    )
    return [x["id"] for x in filtered[:3]]


# ============================================================
# TRHOVÉ RIZIKO
# ============================================================

def get_market_global():
    return coingecko_get("global")


def get_fear_greed():
    try:
        data = http_json(
            "https://api.alternative.me/fng/?limit=1",
            headers={"User-Agent": "CryptoAIBot/6.0"},
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


def market_safety(global_data, simple_prices, btc_data=None):
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
            score += 4
            reasons.append("BTC prudko klesá")
        elif btc_change <= -5:
            score += 3
            reasons.append("BTC výrazne klesá")
        elif btc_change <= -3:
            score += 2
            reasons.append("BTC klesá výrazne")
        elif btc_change <= -1.5:
            score += 1
            reasons.append("BTC klesá")

    btc_tech = (
        btc_data.get("technical_4h", {})
        if isinstance(btc_data, dict) else {}
    )

    btc_price = safe_float(btc_tech.get("price"))
    btc_ema50 = safe_float(btc_tech.get("ema50"))
    btc_ema200 = safe_float(btc_tech.get("ema200"))
    btc_rsi = safe_float(btc_tech.get("rsi14"))

    if btc_price is not None and btc_ema50 is not None:
        if btc_price < btc_ema50:
            score += 1
            reasons.append("BTC je pod 4H EMA50")

    if btc_price is not None and btc_ema200 is not None:
        if btc_price < btc_ema200:
            score += 2
            reasons.append("BTC je pod 4H EMA200")

    if btc_rsi is not None:
        if btc_rsi < 35:
            score += 2
            reasons.append("BTC 4H RSI je pod 35")
        elif btc_rsi < 40:
            score += 1
            reasons.append("BTC 4H RSI je pod 40")

    if (
        global_change is not None and btc_change is not None
        and global_change <= -2 and btc_change <= -1.5
    ):
        score += 1
        reasons.append("BTC aj celý kryptotrh klesajú súčasne")

    state = "CRITICAL" if score >= 6 else (
        "WARNING" if score >= 3 else "NORMAL"
    )

    return {
        "state": state,
        "score": score,
        "reasons": reasons,
        "market_cap_change_24h": global_change,
        "btc_change_24h": btc_change,
        "btc_price": btc_price,
        "btc_ema50": btc_ema50,
        "btc_ema200": btc_ema200,
        "btc_rsi14": btc_rsi,
    }


def should_send_safety_alert(current_safety, state):
    current_state = current_safety.get("state", "NORMAL")
    current_score = safe_float(current_safety.get("score"), 0)
    previous_state = state.get("last_safety_state", "NORMAL")
    previous_score = safe_float(state.get("last_safety_score"), 0)

    if current_state == "NORMAL":
        return False, "NORMAL"

    if previous_state == "NORMAL":
        return True, "STATE_CHANGE"

    if previous_state == "WARNING" and current_state == "CRITICAL":
        return True, "STATE_ESCALATION"

    if current_score >= previous_score + 2:
        return True, "SCORE_WORSENING"

    return False, "NO_NEW_ALERT"


# ============================================================
# TELEGRAM
# ============================================================

def telegram_send(text):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        raise RuntimeError(
            "Chýba TELEGRAM_TOKEN alebo TELEGRAM_CHAT_ID."
        )

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "disable_web_page_preview": True,
    }
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with urllib.request.urlopen(req, timeout=30) as response:
        result = json.loads(response.read().decode("utf-8"))

    if not result.get("ok"):
        raise RuntimeError(f"Telegram odmietol správu: {result}")

    print("Telegram message sent.")
    return True


def telegram_send_long(text):
    # Telegram má limit približne 4096 znakov na správu.
    chunks = []
    current = ""

    for line in text.splitlines():
        if len(current) + len(line) + 1 > 3900:
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
# RSS A GEMINI
# ============================================================

def get_rss_news():
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; CryptoAIBot/6.0)",
        "Accept": "application/rss+xml,application/xml,text/xml,*/*",
    }
    all_items = []

    for source_name, url in RSS_FEEDS:
        try:
            req = urllib.request.Request(
                url, headers=headers, method="GET"
            )
            raw = http_request(req, timeout=30, retries=2)
            root = ET.fromstring(raw)
            count = 0

            for item in root.iter():
                if not item.tag.lower().endswith("item"):
                    continue

                entry = {
                    "source": source_name,
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

        except Exception as e:
            print(f"RSS error {source_name}: {e}")

    return all_items[:20]


def parse_json_output(text):
    if not text:
        raise RuntimeError("Gemini neposlal výstup.")

    text = text.strip()
    text = re.sub(r"^```json\s*", "", text, flags=re.IGNORECASE)
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

        if status in {"failed", "cancelled", "expired", "incomplete"}:
            raise RuntimeError(f"Gemini analýza skončila: {status}")

        if status == "requires_action":
            raise RuntimeError("Gemini vyžaduje ďalšiu akciu.")

        time.sleep(POLL_INTERVAL)


def build_prompt(market_global, fear_greed, safety, news,
                 portfolio_data, candidate_data, btc_data):
    return f"""
Si analytik kryptomien a riadiš riziko portfólia.
Všetok opisný výstup musí byť v slovenčine.
Aktuálny čas Bratislava: {iso_now()}

PORTFÓLIO: AAVE, TAO, FET, SOL, ONDO, RENDER.
APT neodporúčaj.

DÔLEŽITÉ PRAVIDLÁ:
1. Nerad automaticky predaj len preto, že cena prudko klesla,
   RSI je pod 30/40 alebo cena je pod EMA200.
2. Prudký pokles môže pokračovať, ale môže prísť aj odraz.
   Uveď oba scenáre a čo by ich potvrdilo.
3. Rozlišuj medzi potvrdeným prerazením podpory a obyčajným
   dotykom alebo krátkym prepichnutím úrovne.
4. Pri predaji uveď konkrétny dôvod, mieru neistoty a podmienku,
   pri ktorej by si odporúčanie zmenil.
5. Pri nejednoznačných signáloch preferuj HOLD pred panickým
   predajom. HOLD však neznamená, že riziko neexistuje.
6. Nezamieňaj vzdialenosť k podpore s predpoveďou prepadu.
7. Neuvádzaj vymyslené aktuálne ceny ani správy.
8. 24-hodinový výhľad je odhad, nie istota. Pravdepodobnosti
   musia byť primerané neistote a nesmú predstierať presnosť.
9. BUY PULLBACK neznamená automaticky nákup za každú cenu.
10. Ak sú dáta neúplné alebo si odporujú, výslovne to uveď.
11. Pri REDUCE/SELL rozlišuj medzi potvrdeným trendovým
    zhoršením a prepredaním, po ktorom môže nasledovať odraz.
12. Zohľadni trhový kontext BTC, kapitalizáciu, objem, techniku,
    fundamenty a relevantné správy.

TRH:
{json.dumps(market_global, ensure_ascii=False)}

FEAR & GREED:
{json.dumps(fear_greed, ensure_ascii=False)}

SAFETY:
{json.dumps(safety, ensure_ascii=False)}

BTC TECHNIKA:
{json.dumps(btc_data, ensure_ascii=False)}

SPRÁVY:
{json.dumps(news, ensure_ascii=False)}

PORTFÓLIO DÁTA:
{json.dumps(portfolio_data, ensure_ascii=False)}

KANDIDÁTI:
{json.dumps(candidate_data, ensure_ascii=False)}

Analyzuj AAVE, TAO, FET, SOL, ONDO a RENDER.
Pre každú mincu vyber jednu akciu:
BUY NOW, BUY PULLBACK, HOLD, REDUCE, SELL, NO TRADE.

Vráť iba validný JSON v tomto formáte:
{{
  "market_regime": "string",
  "market_summary": "string",
  "action": "string",
  "new_coin": "string",
  "new_coin_action": "string",
  "new_coin_reason": "string",
  "coins": [
    {{
      "symbol": "string",
      "action": "HOLD",
      "current_price": 0.0,
      "buy_zone_1": "string",
      "buy_zone_2": "string",
      "invalidation": "string",
      "tp1": "string",
      "tp2": "string",
      "risk_reward": "will be calculated",
      "bull_probability": 50,
      "bear_probability": 50,
      "outlook_direction": "pokles alebo rast alebo do strany",
      "outlook_pct": 0.0,
      "outlook_probability": 50,
      "technical_score": 0,
      "fundamental_score": 0,
      "reason": "string",
      "bear_case": "string",
      "bull_case": "string",
      "confirmation_needed": "string"
    }}
  ],
  "best_opportunity": "string",
  "avoid": "string",
  "conditions_to_watch": ["string"]
}}

Pri SELL/REDUCE vysvetli, čo konkrétne potvrdzuje pokračovanie
poklesu a prečo nestačí vysvetlenie samotným RSI alebo EMA.
Žiadny Markdown ani text mimo JSON.
"""


# ============================================================
# KONTROLA A OPRAVA VÝSTUPU GEMINI
# ============================================================

def extract_numbers(value):
    if value is None:
        return []
    text = str(value).replace("–", "-").replace("—", "-").replace("−", "-")
    found = re.findall(
        r"(?<!\d)(?:\d+(?:[.,]\d+)?|\.\d+)(?!\d)", text
    )
    result = []
    for item in found:
        try:
            result.append(float(item.replace(",", ".")))
        except ValueError:
            pass
    return result


def parse_price_level(value):
    numbers = extract_numbers(value)
    return numbers[0] if numbers else None


def parse_price_range(value):
    numbers = extract_numbers(value)
    if not numbers:
        return None
    if len(numbers) == 1:
        return numbers[0], numbers[0]
    return min(numbers[:2]), max(numbers[:2])


def calculate_rr(buy_zone, invalidation, tp1, tp2):
    zone = parse_price_range(buy_zone)
    inv = parse_price_level(invalidation)
    t1 = parse_price_level(tp1)
    t2 = parse_price_level(tp2)

    if zone is None or inv is None or t1 is None or t2 is None:
        return None

    entry = sum(zone) / 2
    risk = entry - inv
    reward1 = t1 - entry
    reward2 = t2 - entry

    if risk <= 0 or reward1 <= 0 or reward2 <= 0:
        return None

    return {
        "rr_tp1": reward1 / risk,
        "rr_tp2": reward2 / risk,
    }


def format_rr(rr):
    if not rr:
        return "N/A"
    return f"1:{rr['rr_tp1']:.1f} / 1:{rr['rr_tp2']:.1f}"


def validate_and_correct_analysis(analysis, safety, portfolio_data):
    if not isinstance(analysis, dict):
        raise RuntimeError("Gemini analýza nie je JSON objekt.")

    coins = analysis.get("coins", [])
    if not isinstance(coins, list):
        raise RuntimeError("Gemini pole coins nie je zoznam.")

    safety_state = safety.get("state", "NORMAL")
    valid_actions = {
        "BUY NOW", "BUY PULLBACK", "HOLD",
        "REDUCE", "SELL", "NO TRADE",
    }

    for coin in coins:
        if not isinstance(coin, dict):
            continue

        symbol = str(coin.get("symbol", "")).upper()
        if symbol not in PORTFOLIO:
            continue

        actual_price = safe_float(
            portfolio_data.get(symbol, {}).get("price_usd")
        )
        if actual_price is not None:
            coin["current_price"] = actual_price

        action = str(coin.get("action", "HOLD")).upper()
        if action not in valid_actions:
            coin["action"] = "HOLD"
            action = "HOLD"

        bull = safe_float(coin.get("bull_probability"), 50)
        if bull is None:
            bull = 50
        if 0 < bull <= 1:
            bull *= 100

        bull = clamp(bull, 0, 100)

        # Safety upravuje maximálnu býčiu pravdepodobnosť,
        # ale samo osebe nevynucuje SELL/REDUCE.
        if safety_state == "WARNING":
            bull = min(bull, 65)
        elif safety_state == "CRITICAL":
            bull = min(bull, 55)

        coin["bull_probability"] = round(bull)
        coin["bear_probability"] = round(100 - bull)

        for field in ("technical_score", "fundamental_score"):
            value = safe_float(coin.get(field))
            if value is not None:
                coin[field] = round(clamp(value, 0, 10), 1)

        outlook_probability = safe_float(
            coin.get("outlook_probability"), 50
        )
        coin["outlook_probability"] = round(
            clamp(outlook_probability or 50, 5, 95)
        )

        outlook_pct = safe_float(coin.get("outlook_pct"), 0)
        coin["outlook_pct"] = round(
            clamp(outlook_pct or 0, -30, 30), 2
        )

        rr = calculate_rr(
            coin.get("buy_zone_1"),
            coin.get("invalidation"),
            coin.get("tp1"),
            coin.get("tp2"),
        )
        coin["risk_reward"] = format_rr(rr)

    return analysis


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
    state = safety.get("state", "NORMAL")
    score = safety.get("score", 0)

    if state == "CRITICAL":
        title = "🚨 CRYPTO AI BOT — KRÍZOVÝ ALERT"
        message = (
            "Riziko na trhu je vysoké. Alert nie je automatickým "
            "pokynom na predaj."
        )
    else:
        title = "⚠️ CRYPTO AI BOT — BEZPEČNOSTNÝ ALERT"
        message = (
            "Trh sa zhoršuje. Sleduj potvrdenie pohybu, "
            "nie iba jeden indikátor."
        )

    lines = [
        title, "",
        f"🛡 Safety: {state} ({score})",
        message, "",
    ]

    if safety.get("btc_change_24h") is not None:
        lines.append(f"₿ BTC 24h: {safety['btc_change_24h']:+.2f}%")
    if safety.get("market_cap_change_24h") is not None:
        lines.append(
            f"🌐 Market cap 24h: "
            f"{safety['market_cap_change_24h']:+.2f}%"
        )
    if safety.get("btc_ema50") is not None:
        lines.append(
            f"₿ BTC 4H EMA50: {format_price(safety['btc_ema50'])}"
        )
    if safety.get("btc_ema200") is not None:
        lines.append(
            f"₿ BTC 4H EMA200: {format_price(safety['btc_ema200'])}"
        )
    if safety.get("btc_rsi14") is not None:
        lines.append(f"₿ BTC 4H RSI: {safety['btc_rsi14']:.1f}")

    fg = fear_greed.get("value")
    if fg is not None:
        lines.append(
            f"😱 Fear & Greed: {fg}/100 "
            f"({fear_greed.get('classification', '')})"
        )

    if safety.get("reasons"):
        lines.extend(["", "Dôvody:"])
        lines.extend(f"• {x}" for x in safety["reasons"][:6])

    if portfolio_analysis:
        lines.extend(["", "📊 PORTFÓLIO — RIZIKO:"])

        for item in portfolio_analysis:
            lines.extend([
                f"━━ {item['symbol']} ({format_price(item['price'])}) ━━",
                f"• Odporúčanie z hlavnej analýzy: {item['action']}",
            ])

            if item.get("rsi") is not None:
                lines.append(f"• RSI 4H: {item['rsi']:.1f}")

            if item.get("support_distance") is not None:
                lines.append(
                    f"• Podpora je približne "
                    f"{item['support_distance']:.1f}% pod cenou"
                )

            if item.get("reasons"):
                lines.extend(f"• {x}" for x in item["reasons"])

            lines.append(f"• {item['interpretation']}")

    lines.extend([
        "",
        "⚠️ RSI pod 30 môže znamenať prepredanie, ale aj možný odraz.",
        "Samotné RSI, EMA200 ani vzdialenosť k podpore nepotvrdzujú "
        "budúci prepad.",
        "Pred rozhodnutím sleduj uzatvorenie sviečky, podporu, BTC "
        "a širší trh. Predikcie nie sú zárukou výsledku.",
    ])

    return "\n".join(lines)


def coin_sort_priority(coin):
    action = str(coin.get("action", "")).upper()
    if action == "SELL":
        return 0
    if action == "REDUCE":
        return 1
    if action == "HOLD":
        return 2
    if "BUY" in action:
        return 3
    return 4


def format_bot_message(analysis, safety, fear_greed):
    coins = sorted(
        analysis.get("coins", []),
        key=coin_sort_priority,
    )

    lines = [
        "📊 CRYPTO AI BOT — 4H ANALÝZA",
        f"🕒 {iso_now()}",
        "",
        f"🌐 Trh: {analysis.get('market_regime', 'N/A')}",
        f"🛡 Safety: {safety.get('state', 'N/A')} "
        f"({safety.get('score', 0)})",
    ]

    for reason in safety.get("reasons", []):
        lines.append(f"• {reason}")

    fg = fear_greed.get("value")
    if fg is not None:
        lines.append(
            f"😱 Fear & Greed: {fg}/100 "
            f"({fear_greed.get('classification', '')})"
        )

    lines.extend(["", "⚡ RÝCHLY AKČNÝ PLÁN:"])

    for coin in coins:
        symbol = coin.get("symbol", "?")
        action = str(coin.get("action", "HOLD")).upper()
        emoji = (
            "🔴" if action in {"SELL", "REDUCE"}
            else "🟢" if "BUY" in action
            else "🟡"
        )
        lines.append(f"{emoji} {symbol}: {action}")

    lines.extend([
        "",
        "🧠 Makro:",
        str(analysis.get("market_summary", "")),
    ])

    for coin in coins:
        symbol = coin.get("symbol", "?")
        action = str(coin.get("action", "HOLD")).upper()
        emoji = (
            "🔴" if action in {"SELL", "REDUCE"}
            else "🟢" if "BUY" in action
            else "🟡"
        )

        lines.extend([
            "",
            f"━━ {emoji} {symbol} ━━",
            f"Akcia: {action}",
            f"Cena: {format_price(coin.get('current_price'))}",
        ])

        direction = str(
            coin.get("outlook_direction", "do strany")
        )
        pct = safe_float(coin.get("outlook_pct"), 0) or 0
        probability = safe_float(
            coin.get("outlook_probability"), 50
        ) or 50

        dir_emoji = (
            "📉" if "pokles" in direction.lower()
            else "📈" if "rast" in direction.lower()
            else "↔️"
        )
        lines.append(
            f"Predikcia 24h: {dir_emoji} {direction}, "
            f"{pct:+.1f}% (odhadovaná pravdepodobnosť "
            f"{probability:.0f}%)"
        )

        if "BUY" in action:
            lines.extend([
                f"BUY 1: {coin.get('buy_zone_1', 'N/A')}",
                f"BUY 2: {coin.get('buy_zone_2', 'N/A')}",
                f"Invalidácia: {coin.get('invalidation', 'N/A')}",
                f"TP1: {coin.get('tp1', 'N/A')}",
                f"TP2: {coin.get('tp2', 'N/A')}",
                f"R:R: {coin.get('risk_reward', 'N/A')}",
            ])

        lines.append(
            f"🐂 Bull: {coin.get('bull_probability', 'N/A')}% | "
            f"🐻 Bear: {coin.get('bear_probability', 'N/A')}%"
        )
        lines.append(
            f"Technika: {coin.get('technical_score', 'N/A')}/10"
        )
        lines.append(
            f"Fundament: {coin.get('fundamental_score', 'N/A')}/10"
        )

        if coin.get("action_change"):
            lines.append(f"Zmena: {coin['action_change']}")
        if coin.get("confirmation_needed"):
            lines.append(
                f"Potvrdenie: {coin['confirmation_needed']}"
            )
        if coin.get("bear_case"):
            lines.append(f"Medvedí scenár: {coin['bear_case']}")
        if coin.get("bull_case"):
            lines.append(f"Býčí scenár: {coin['bull_case']}")

        lines.append(str(coin.get("reason", "")))

    lines.extend([
        "",
        "🚀 Najlepšia príležitosť:",
        str(analysis.get("best_opportunity", "N/A")),
        "",
        f"🆕 Nová kryptomena: {analysis.get('new_coin', 'NO TRADE')}",
        f"Akcia: {analysis.get('new_coin_action', 'NO TRADE')}",
        f"Dôvod: {analysis.get('new_coin_reason', '')}",
        "",
        f"⚠️ Vyhnúť sa: {analysis.get('avoid', '')}",
    ])

    conditions = analysis.get("conditions_to_watch", [])
    if conditions:
        lines.extend(["", "👀 Sledovať:"])
        lines.extend(f"• {x}" for x in conditions[:6])

    lines.extend([
        "",
        "Poznámka: Pravdepodobnosti a cenové výhľady sú odhady, "
        "nie záruky. Nie je to finančné poradenstvo.",
    ])

    return "\n".join(lines)


# ============================================================
# SAFETY MONITOR
# ============================================================

def run_safety_monitor():
    market_global = get_market_global()
    simple_prices = coingecko_simple_price(["bitcoin"])
    fear_greed = get_fear_greed()

    btc_data = {}
    try:
        btc_data = collect_coin_data("BTC", "bitcoin", days=35)
    except Exception as e:
        print(f"BTC technical data error: {e}")

    safety = market_safety(market_global, simple_prices, btc_data)
    state = load_state()

    previous_analysis = state.get("last_analysis", {})
    previous_coins = {
        str(c.get("symbol", "")).upper(): c
        for c in previous_analysis.get("coins", [])
        if isinstance(c, dict)
    }

    portfolio_analysis = []

    for symbol, coin_id in PORTFOLIO.items():
        try:
            data = collect_coin_data(symbol, coin_id, days=35)
            tech = data.get("technical_4h", {})
            price = safe_float(data.get("price_usd"))
            support = safe_float(tech.get("support_30_candles"))
            rsi_value = safe_float(tech.get("rsi14"))
            above_200 = tech.get("above_ema200")

            support_distance = None
            if price and support and support < price:
                support_distance = (price - support) / price * 100

            previous = previous_coins.get(symbol, {})
            previous_action = str(
                previous.get("action", "N/A")
            ).upper()

            reasons = []
            if above_200 is False:
                reasons.append("cena je pod 4H EMA200")
            if rsi_value is not None and rsi_value < 30:
                reasons.append(
                    "RSI pod 30: silný tlak, ale aj možnosť odrazu"
                )
            elif rsi_value is not None and rsi_value < 40:
                reasons.append("RSI pod 40: slabé momentum")

            if support_distance is not None:
                reasons.append(
                    f"podpora približne {support_distance:.1f}% pod cenou"
                )

            if rsi_value is not None and rsi_value < 30:
                interpretation = (
                    "Možné prepredanie. Nepredávať automaticky; "
                    "sledovať potvrdenie alebo odraz."
                )
            elif above_200 is False:
                interpretation = (
                    "Zvýšené riziko, ale samotná EMA200 "
                    "nie je potvrdením na predaj."
                )
            else:
                interpretation = (
                    "Tieto indikátory samy nepotvrdzujú nútený predaj."
                )

            portfolio_analysis.append({
                "symbol": symbol,
                "price": price,
                "support_distance": support_distance,
                "rsi": rsi_value,
                "action": previous_action,
                "reasons": reasons,
                "interpretation": interpretation,
            })

        except Exception as e:
            print(f"Safety monitor error for {symbol}: {e}")

    should_alert, alert_reason = should_send_safety_alert(
        safety, state
    )

    if should_alert:
        alert = format_safety_alert(
            safety, fear_greed, portfolio_analysis
        )
        telegram_send_long(alert)
        state["last_safety_alert"] = iso_now()
        state["last_safety_alert_reason"] = alert_reason

    state["last_safety_state"] = safety.get("state", "NORMAL")
    state["last_safety_score"] = safety.get("score", 0)
    state["last_safety_check"] = iso_now()
    state["market_safety"] = safety
    state["fear_greed"] = fear_greed
    save_state(state)

    return safety


# ============================================================
# HLAVNÁ ANALÝZA
# ============================================================

def run_full_analysis(schedule_reason, schedule_slot=None):
    market_global = get_market_global()
    fear_greed = get_fear_greed()

    all_ids = list(dict.fromkeys(
        list(PORTFOLIO.values()) + CANDIDATES + ["bitcoin"]
    ))
    simple_prices = coingecko_simple_price(all_ids)
    news = get_rss_news()
    btc_data = collect_coin_data("BTC", "bitcoin")
    safety = market_safety(market_global, simple_prices, btc_data)

    portfolio_data = {}
    for symbol, coin_id in PORTFOLIO.items():
        try:
            portfolio_data[symbol] = collect_coin_data(symbol, coin_id)
        except Exception as e:
            portfolio_data[symbol] = {
                "symbol": symbol,
                "coin_id": coin_id,
                "error": str(e),
            }

    shortlist = shortlist_candidates()
    candidate_data = {}

    for coin_id in shortlist:
        symbol = coin_id.upper()
        try:
            candidate_data[symbol] = collect_coin_data(symbol, coin_id)
        except Exception as e:
            candidate_data[symbol] = {
                "coin_id": coin_id,
                "error": str(e),
            }

    prompt = build_prompt(
        market_global, fear_greed, safety, news,
        portfolio_data, candidate_data, btc_data,
    )

    analysis = gemini_analyze(prompt)
    analysis = validate_and_correct_analysis(
        analysis, safety, portfolio_data
    )

    state = load_state()
    previous_analysis = state.get("last_analysis", {})
    previous_actions = {
        str(c.get("symbol", "")).upper():
            str(c.get("action", "N/A")).upper()
        for c in previous_analysis.get("coins", [])
        if isinstance(c, dict)
    }

    for coin in analysis.get("coins", []):
        symbol = str(coin.get("symbol", "")).upper()
        old_action = previous_actions.get(symbol)
        new_action = str(coin.get("action", "N/A")).upper()

        if old_action and old_action != new_action:
            coin["action_change"] = (
                f"{old_action} → {new_action}"
            )
        else:
            coin["action_change"] = "Bez zmeny oproti poslednej analýze"

    message = format_bot_message(analysis, safety, fear_greed)

    # Najprv doruč správu. Až potom označ slot za dokončený.
    telegram_send_long(message)

    state["last_run"] = iso_now()
    state["last_full_analysis"] = iso_now()
    state["last_analysis_reason"] = schedule_reason
    state["market_safety"] = safety
    state["fear_greed"] = fear_greed
    state["btc_data"] = btc_data
    state["last_analysis"] = analysis
    state["last_main_schedule"] = schedule_reason

    if schedule_slot and schedule_reason != "MANUAL":
        state["last_main_slot"] = schedule_slot

    state["last_safety_state"] = safety.get("state", "NORMAL")
    state["last_safety_score"] = safety.get("score", 0)
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

    should_run, reason = is_main_analysis_time()
    scheduled_slot = None

    if should_run and reason != "MANUAL":
        scheduled_slot = get_main_analysis_slot()

    if should_run:
        run_full_analysis(reason, scheduled_slot)
    else:
        run_safety_monitor()


if __name__ == "__main__":
    main()
