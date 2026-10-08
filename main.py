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
# CRYPTO AI BOT V5.7 (Opravená syntax a krízový monitoring)
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
# CONFIG PORTFOLIO & CANDIDATES
# ============================================================

PORTFOLIO = {
    "AAVE": "aave",
    "TAO": "bittensor",
    "FET": "fetch-ai",
    "SOL": "solana",
    "ONDO": "ondo-finance",
    "RENDER": "render-token",
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
            value = value.replace("$", "").replace(",", "").strip()
        return float(value)
    except Exception:
        return default


def pct_change(old, new):
    if old in (None, 0) or new is None:
        return None
    return ((new - old) / old) * 100.0


def clamp(value, minimum, maximum):
    return max(minimum, min(maximum, value))


def manual_analysis_requested():
    value = os.getenv("MANUAL_ANALYSIS", "").strip().lower()
    return value in {"true", "1", "yes", "y", "on"}


# ============================================================
# SCHEDULING (30-minútové okno kvôli meškaniu GitHub Actions)
# ============================================================

def get_main_analysis_slot(now=None):
    if now is None:
        now = datetime.now(TZ)

    if now.hour == 7 and now.minute < 30:
        return f"BRATISLAVA_{now.date().isoformat()}_07:00"

    if now.hour == 20 and now.minute < 30:
        return f"BRATISLAVA_{now.date().isoformat()}_20:00"

    us_now = now.astimezone(US_TZ)
    if us_now.hour == 9 and 15 <= us_now.minute < 45:
        return f"US_PREOPEN_{us_now.date().isoformat()}"

    return None


def is_main_analysis_time(now=None):
    if now is None:
        now = datetime.now(TZ)

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
# HTTP & COINGECKO
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
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
            last_error = e
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
    if last_error:
        raise last_error
    raise RuntimeError("HTTP request zlyhal.")


def http_json(url, headers=None, timeout=REQUEST_TIMEOUT, retries=4):
    if headers is None:
        headers = {}
    req = urllib.request.Request(url, headers=headers, method="GET")
    raw = http_request(req, timeout=timeout, retries=retries)
    return json.loads(raw.decode("utf-8"))


def coingecko_headers():
    headers = {"Accept": "application/json", "User-Agent": "CryptoAIBot/5.7"}
    if COINGECKO_API_KEY:
        headers["x-cg-demo-api-key"] = COINGECKO_API_KEY
    return headers


def coingecko_get(endpoint, params=None):
    base = "https://api.coingecko.com/api/v3"
    if params:
        query = urllib.parse.urlencode(params)
        url = f"{base}/{endpoint}?{query}"
    else:
        url = f"{base}/{endpoint}"
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
    return coingecko_get(f"coins/{coin_id}/market_chart", {
        "vs_currency": "usd",
        "days": days,
        "interval": "hourly",
    })


# ============================================================
# TECHNICAL ANALYSIS HELPERS
# ============================================================

def closes_from_chart(chart):
    prices = chart.get("prices", [])
    return [{"timestamp": p[0], "price": safe_float(p[1])} for p in prices if len(p) >= 2 and safe_float(p[1]) is not None]


def aggregate_candles(prices, hours=4):
    if not prices:
        return []
    buckets = {}
    bucket_ms = hours * 60 * 60 * 1000
    for p in prices:
        timestamp = int(p["timestamp"])
        price = p["price"]
        bucket = (timestamp // bucket_ms) * bucket_ms
        if bucket not in buckets:
            buckets[bucket] = {"timestamp": bucket, "open": price, "high": price, "low": price, "close": price}
        else:
            buckets[bucket]["high"] = max(buckets[bucket]["high"], price)
            buckets[bucket]["low"] = min(buckets[bucket]["low"], price)
            buckets[bucket]["close"] = price
    return [buckets[key] for key in sorted(buckets.keys())]


def ema(values, period):
    if not values or len(values) < period:
        return [None] * len(values)
    result = [None] * len(values)
    sma = sum(values[:period]) / period
    result[period - 1] = sma
    multiplier = 2 / (period + 1)
    previous = sma
    for i in range(period, len(values)):
        current = (values[i] - previous) * multiplier + previous
        result[i] = current
        previous = current
    return result


def rsi(values, period=14):
    if len(values) < period + 1:
        return None
    gains, losses = [], []
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
        avg_gain = ((avg_gain * (period - 1)) + gains[i]) / period
        avg_loss = ((avg_loss * (period - 1)) + losses[i]) / period
        if avg_loss == 0:
            current_rsi = 100.0
        else:
            rs = avg_gain / avg_loss
            current_rsi = 100 - (100 / (1 + rs))
    return current_rsi


def macd(values):
    if len(values) < 35:
        return {"macd": None, "signal": None, "histogram": None}
    ema12 = ema(values, 12)
    ema26 = ema(values, 26)
    macd_values = [a - b if a is not None and b is not None else None for a, b in zip(ema12, ema26)]
    valid = [x for x in macd_values if x is not None]
    signal_values = ema(valid, 9)
    if not signal_values:
        return {"macd": None, "signal": None, "histogram": None}
    current_macd = valid[-1]
    current_signal = signal_values[-1]
    histogram = current_macd - current_signal if current_signal is not None else None
    return {"macd": current_macd, "signal": current_signal, "histogram": histogram}


def last_valid(values):
    for value in reversed(values):
        if value is not None:
            return value
    return None


def atr(candles, period=14):
    if len(candles) < period + 1:
        return None
    true_ranges = []
    for i in range(1, len(candles)):
        current, previous = candles[i], candles[i - 1]
        high, low, prev_close = current["high"], current["low"], previous["close"]
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        true_ranges.append(tr)
    if len(true_ranges) < period:
        return None
    return sum(true_ranges[-period:]) / period


def recent_support_resistance(candles, lookback=30):
    if not candles:
        return {"support": None, "resistance": None}
    recent = candles[-lookback:]
    lows = [c["low"] for c in recent if c.get("low") is not None]
    highs = [c["high"] for c in recent if c.get("high") is not None]
    return {"support": min(lows) if lows else None, "resistance": max(highs) if highs else None}


def technical_summary(candles):
    if not candles:
        return {}
    closes = [c["close"] for c in candles if c.get("close") is not None]
    if not closes:
        return {}
    current = closes[-1]
    e20 = last_valid(ema(closes, 20))
    e50 = last_valid(ema(closes, 50))
    e100 = last_valid(ema(closes, 100))
    e200 = last_valid(ema(closes, 200))
    sr = recent_support_resistance(candles, 30)
    current_atr = atr(candles, 14)
    current_rsi = rsi(closes, 14)
    current_macd = macd(closes)
    return {
        "price": current,
        "ema20": e20,
        "ema50": e50,
        "ema100": e100,
        "ema200": e200,
        "rsi14": current_rsi,
        "macd": current_macd,
        "atr14": current_atr,
        "atr_percent": (current_atr / current * 100 if current_atr and current else None),
        "support_30_candles": sr["support"],
        "resistance_30_candles": sr["resistance"],
        "above_ema20": (current > e20 if e20 is not None else None),
        "above_ema50": (current > e50 if e50 is not None else None),
        "above_ema100": (current > e100 if e100 is not None else None),
        "above_ema200": (current > e200 if e200 is not None else None),
    }


def recent_returns(closes):
    if not closes:
        return {}
    current = closes[-1]
    periods = {"24h": 6, "7d": 42, "30d": 180}
    result = {}
    for name, bars in periods.items():
        if len(closes) > bars:
            old = closes[-bars - 1]
            result[name] = pct_change(old, current)
    return result


def collect_coin_data(symbol, coin_id, days=90):
    print(f"Collecting: {symbol}")
    simple = coingecko_simple_price([coin_id])
    current = simple.get(coin_id, {})
    chart = coingecko_chart(coin_id, days=days)
    prices = closes_from_chart(chart)
    candles = aggregate_candles(prices, hours=4)
    technical = technical_summary(candles)
    closes = [x["close"] for x in candles]
    return {
        "symbol": symbol,
        "coin_id": coin_id,
        "price_usd": current.get("usd"),
        "market_cap": current.get("usd_market_cap"),
        "volume_24h": current.get("usd_24h_vol"),
        "change_24h": current.get("usd_24h_change"),
        "last_updated": current.get("last_updated_at"),
        "technical_4h": technical,
        "returns": recent_returns(closes),
    }


def shortlist_candidates():
    print("Shortlisting candidate coins...")
    market_data = coingecko_markets(CANDIDATES)
    if not market_data:
        return CANDIDATES[:3]
    portfolio_ids = set(PORTFOLIO.values())
    filtered = [x for x in market_data if x.get("id") not in portfolio_ids]
    filtered = [x for x in filtered if safe_float(x.get("market_cap"), 0) > 100_000_000]
    filtered.sort(key=lambda x: (safe_float(x.get("total_volume"), 0), safe_float(x.get("market_cap"), 0)), reverse=True)
    selected = filtered[:3]
    return [x["id"] for x in selected]


def get_market_global():
    return coingecko_get("global")


def get_fear_greed():
    try:
        data = http_json("https://api.alternative.me/fng/?limit=1", headers={"User-Agent": "CryptoAIBot/5.7"})
        item = data["data"][0]
        return {"value": int(item["value"]), "classification": item["value_classification"], "timestamp": item.get("timestamp")}
    except Exception as e:
        print(f"Fear & Greed error: {e}")
        return {"value": None, "classification": "UNKNOWN", "timestamp": None}


def market_safety(global_data, simple_prices, btc_data=None):
    score = 0
    reasons = []
    global_change, btc_change = None, None

    try:
        global_change = safe_float(global_data["data"].get("market_cap_change_percentage_24h_usd"))
        if global_change is not None:
            if global_change <= -5:
                score += 3
                reasons.append("celková kapitalizácia prudko klesá")
            elif global_change <= -3.5:
                score += 2
                reasons.append("celková kapitalizácia klesá výrazne")
            elif global_change <= -2:
                score += 1
                reasons.append("celková kapitalizácia klesá")
    except Exception:
        pass

    try:
        btc = simple_prices.get("bitcoin", {})
        btc_change = safe_float(btc.get("usd_24h_change"))
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
    except Exception:
        pass

    btc_tech = {}
    if isinstance(btc_data, dict):
        btc_tech = btc_data.get("technical_4h", {}) or {}

    btc_price = safe_float(btc_tech.get("price"))
    btc_ema50 = safe_float(btc_tech.get("ema50"))
    btc_ema200 = safe_float(btc_tech.get("ema200"))
    btc_rsi = safe_float(btc_tech.get("rsi14"))

    if btc_price is not None and btc_ema50 is not None and btc_price < btc_ema50:
        score += 1
        reasons.append("BTC je pod 4H EMA50")

    if btc_price is not None and btc_ema200 is not None and btc_price < btc_ema200:
        score += 2
        reasons.append("BTC je pod 4H EMA200")

    if btc_rsi is not None:
        if btc_rsi < 35:
            score += 2
            reasons.append("BTC 4H RSI je pod 35")
        elif btc_rsi < 40:
            score += 1
            reasons.append("BTC 4H RSI je pod 40")

    if global_change is not None and btc_change is not None and global_change <= -2 and btc_change <= -1.5:
        score += 1
        reasons.append("BTC aj celý kryptotrh klesajú súčasne")

    if score >= 6:
        state = "CRITICAL"
    elif score >= 3:
        state = "WARNING"
    else:
        state = "NORMAL"

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
    current_score = safe_float(current_safety.get("score", 0), 0)
    previous_state = state.get("last_safety_state", "NORMAL")
    previous_score = safe_float(state.get("last_safety_score", 0), 0)

    if current_state == "NORMAL":
        return False, "NORMAL"

    if previous_state == "NORMAL" and current_state in {"WARNING", "CRITICAL"}:
        return True, "STATE_CHANGE"

    if previous_state == "WARNING" and current_state == "CRITICAL":
        return True, "STATE_ESCALATION"

    if current_score >= previous_score + 2:
        return True, "SCORE_WORSENING"

    if previous_state == "NORMAL" and current_state == "CRITICAL":
        return True, "CRITICAL"

    return False, "NO_NEW_ALERT"


def format_safety_alert(safety, fear_greed, portfolio_analysis=None):
    state = safety.get("state", "NORMAL")
    score = safety.get("score", 0)
    btc_change = safety.get("btc_change_24h")
    market_change = safety.get("market_cap_change_24h")

    if state == "CRITICAL":
        title = "🚨 CRYPTO AI BOT — KRÍZOVÝ ALERT"
        message = "Hrozí výraznejší prepad alebo pokračovanie korekcie."
    else:
        title = "⚠️ CRYPTO AI BOT — BEZPEČNOSTNÝ ALERT"
        message = "Trh sa zhoršuje a rastie riziko väčšej korekcie."

    lines = [title, "", f"🛡 Safety: {state} ({score})", message, ""]
    if btc_change is not None:
        lines.append(f"₿ BTC 24h: {btc_change:+.2f}%")
    if market_change is not None:
        lines.append(f"🌐 Market cap 24h: {market_change:+.2f}%")

    btc_ema50 = safety.get("btc_ema50")
    btc_ema200 = safety.get("btc_ema200")
    btc_rsi = safety.get("btc_rsi14")

    if btc_ema50 is not None:
        lines.append(f"₿ BTC 4H EMA50: {format_price(btc_ema50)}")
    if btc_ema200 is not None:
        lines.append(f"₿ BTC 4H EMA200: {format_price(btc_ema200)}")
    if btc_rsi is not None:
        lines.append(f"₿ BTC 4H RSI: {btc_rsi:.1f}")

    fg = fear_greed.get("value")
    if fg is not None:
        lines.append(f"😱 Fear & Greed: {fg}/100 ({fear_greed.get('classification', '')})")

    reasons = safety.get("reasons", [])
    if reasons:
        lines.append("")
        lines.append("Dôvod:")
        for reason in reasons[:5]:
            lines.append(f"• {reason}")

    if portfolio_analysis:
        lines.extend(["", "📊 ANALÝZA PORTFÓLIA V OHROZENÍ:"])
        for item in portfolio_analysis:
            sym = item["symbol"]
            cur = format_price(item["price"])
            drop = item["expected_drop"]
            dur = item["duration"]
            bear = item["bear_prob"]
            act = item["action"]
            
            lines.extend([
                f"━━ {sym} ({cur}) ━━",
                f"• Predpokladaný prepad: do -{drop:.1f}%",
                f"• Horizont/Trvanie: {dur}",
                f"• Bear pravdepodobnosť: {bear}%",
                f"• Odporúčanie: **{act}**",
            ])

    lines.extend([
        "",
        "➡️ Pravidlá ochrany: Prepad >7% + Bear ≥60% + Breakdown = SELL PARTIAL. Prepad >10% + Bear ≥70% = SELL."
    ])
    return "\n".join(lines)


# ============================================================
# RSS & GEMINI
# ============================================================

def get_rss_news():
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; CryptoAIBot/5.7)",
        "Accept": "application/rss+xml,application/xml,text/xml,*/*",
    }
    all_items = []
    for source_name, url in RSS_FEEDS:
        try:
            req = urllib.request.Request(url, headers=headers, method="GET")
            raw = http_request(req, timeout=30, retries=2)
            root = ET.fromstring(raw)
            count = 0
            for item in root.iter():
                if not item.tag.lower().endswith("item"):
                    continue
                title, link, pub_date = "", "", ""
                for child in item:
                    tag = child.tag.lower()
                    if tag.endswith("title"):
                        title = (child.text or "").strip()
                    elif tag.endswith("link"):
                        link = (child.text or "").strip()
                    elif tag.endswith("pubdate"):
                        pub_date = (child.text or "").strip()
                if title:
                    all_items.append({"source": source_name, "title": title, "link": link, "pub_date": pub_date})
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
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            pass
    raise RuntimeError("Gemini output nie je validný JSON:\n" + text[:5000])


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
        elapsed = time.time() - started
        if elapsed > GEMINI_MAX_WAIT:
            raise TimeoutError("Gemini background analysis trvá dlhšie ako 10 minút.")
        interaction = client.interactions.get(id=interaction_id)
        status = interaction.status
        if status == "completed":
            output_text = interaction.output_text
            if not output_text:
                raise RuntimeError("Gemini completed, ale output_text je prázdny.")
            return parse_json_output(output_text)
        if status in {"failed", "cancelled", "expired", "incomplete"}:
            raise RuntimeError(f"Gemini interaction skončila stavom {status}.")
        if status == "requires_action":
            raise RuntimeError("Gemini vyžaduje ďalšiu akciu.")
        time.sleep(POLL_INTERVAL)


def build_prompt(market_global, fear_greed, safety, news, portfolio_data, candidate_data, btc_data):
    return f"""
You are the main investment intelligence engine of a crypto trading bot.
All descriptive output MUST be in Slovak.
Current time Bratislava: {iso_now()}

PORTFOLIO: AAVE, TAO, FET, SOL, ONDO, RENDER. Do NOT recommend APT.

GLOBAL MARKET: {json.dumps(market_global, ensure_ascii=False, indent=2)}
FEAR & GREED: {json.dumps(fear_greed, ensure_ascii=False, indent=2)}
SAFETY: {json.dumps(safety, ensure_ascii=False, indent=2)}
BTC TECH: {json.dumps(btc_data, ensure_ascii=False, indent=2)}
NEWS: {json.dumps(news, ensure_ascii=False, indent=2)}
PORTFOLIO DATA: {json.dumps(portfolio_data, ensure_ascii=False, indent=2)}
CANDIDATES: {json.dumps(candidate_data, ensure_ascii=False, indent=2)}

Analyze AAVE, TAO, FET, SOL, ONDO, RENDER. Choose BUY NOW, BUY PULLBACK, HOLD, REDUCE, SELL, NO TRADE.
Return ONLY valid JSON with structure:
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
  "conditions_to_watch": ["string"]
}}
No markdown. No explanations outside JSON.
"""


def extract_numbers(value):
    if value is None:
        return []
    text = str(value).replace("–", "-").replace("—", "-").replace("−", "-")
    matches = re.findall(r"(?<!\d)(?:\d+(?:[.,]\d+)?|\.\d+)(?!\d)", text)
    result = []
    for item in matches:
        try:
            result.append(float(item.replace(",", ".")))
        except Exception:
            pass
    return result


def parse_price_level(value):
    nums = extract_numbers(value)
    return nums[0] if nums else None


def parse_price_range(value):
    nums = extract_numbers(value)
    if not nums:
        return None
    if len(nums) == 1:
        return (nums[0], nums[0])
    return (min(nums[0], nums[1]), max(nums[0], nums[1]))


def calculate_rr(buy_zone, invalidation, tp1, tp2):
    zone = parse_price_range(buy_zone)
    inv = parse_price_level(invalidation)
    t1 = parse_price_level(tp1)
    t2 = parse_price_level(tp2)
    if zone is None or inv is None or t1 is None or t2 is None:
        return None
    entry = (zone[0] + zone[1]) / 2
    risk = entry - inv
    reward1, reward2 = t1 - entry, t2 - entry
    if risk <= 0 or reward1 <= 0 or reward2 <= 0:
        return None
    return {"rr_tp1": reward1 / risk, "rr_tp2": reward2 / risk}


def format_rr(rr):
    if not rr:
        return "N/A"
    return f"1:{rr['rr_tp1']:.1f} / 1:{rr['rr_tp2']:.1f}"


def validate_and_correct_analysis(analysis, safety, portfolio_data):
    if not isinstance(analysis, dict):
        raise RuntimeError("Gemini analysis nie je objekt.")
    coins = analysis.get("coins", [])
    safety_state = safety.get("state", "NORMAL")

    for coin in coins:
        symbol = str(coin.get("symbol", "")).upper()
        if symbol in portfolio_data:
            actual_price = safe_float(portfolio_data[symbol].get("price_usd"))
            if actual_price is not None:
                coin["current_price"] = actual_price

        bull = safe_float(coin.get("bull_probability", 50))
        if 0 < bull <= 1:
            bull *= 100
        bull = clamp(bull, 0, 100)
        if safety_state == "WARNING":
            bull = min(bull, 65)
        elif safety_state == "CRITICAL":
            bull = min(bull, 55)

        coin["bull_probability"] = round(bull)
        coin["bear_probability"] = round(100 - bull)

        tech = safe_float(coin.get("technical_score"))
        fund = safe_float(coin.get("fundamental_score"))
        if tech is not None:
            coin["technical_score"] = round(clamp(tech, 0, 10), 1)
        if fund is not None:
            coin["fundamental_score"] = round(clamp(fund, 0, 10), 1)

        rr = calculate_rr(coin.get("buy_zone_1"), coin.get("invalidation"), coin.get("tp1"), coin.get("tp2"))
        coin["risk_reward"] = format_rr(rr)
    return analysis


def telegram_send(text):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "disable_web_page_preview": True}
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    try:
        urllib.request.urlopen(req, timeout=30)
    except Exception as e:
        print(f"Telegram error: {e}")


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


def format_bot_message(analysis, safety, fear_greed):
    lines = [
        "📊 CRYPTO AI BOT — 4H ANALÝZA",
        f"🕒 {iso_now()}",
        "",
        f"🌐 Trh: {analysis.get('market_regime', 'N/A')}",
        f"🛡 Safety: {safety.get('state', 'N/A')} ({safety.get('score', 0)})",
    ]
    for reason in safety.get("reasons", []):
        lines.append(f" • {reason}")
    fg = fear_greed.get("value")
    if fg is not None:
        lines.append(f"😱 Fear & Greed: {fg}/100 ({fear_greed.get('classification', '')})")

    lines.extend(["", "🧠 Makro:", str(analysis.get("market_summary", "")), ""])

    for coin in analysis.get("coins", []):
        symbol = coin.get("symbol", "?")
        lines.extend([
            f"━━ {symbol} ━━",
            f"Akcia: {coin.get('action', 'N/A')}",
            f"Cena: {format_price(coin.get('current_price'))}",
            f"BUY 1: {coin.get('buy_zone_1', 'N/A')}",
            f"BUY 2: {coin.get('buy_zone_2', 'N/A')}",
            f"Invalidácia: {coin.get('invalidation', 'N/A')}",
            f"TP1: {coin.get('tp1', 'N/A')}",
            f"TP2: {coin.get('tp2', 'N/A')}",
            f"R:R: {coin.get('risk_reward', 'N/A')}",
            f"🐂 Bull: {coin.get('bull_probability', 50)}% | 🐻 Bear: {coin.get('bear_probability', 50)}%",
            f"Technika: {coin.get('technical_score', 'N/A')}/10",
            f"Fundament: {coin.get('fundamental_score', 'N/A')}/10",
            str(coin.get("reason", "")),
            "",
        ])

    lines.extend([
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
        for condition in conditions[:6]:
            lines.append(f"• {condition}")

    lines.extend(["", "Nie je to finančné poradenstvo."])
    message = "\n".join(lines)
    if len(message) <= 4000:
        return [message]

    chunks, current = [], ""
    for line in lines:
        if len(current) + len(line) + 1 > 3900:
            chunks.append(current)
            current = line
        else:
            current += ("\n" if current else "") + line
    if current:
        chunks.append(current)
    return chunks


def load_state():
    if not os.path.exists(STATE_FILE):
        return {}
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_state(state):
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


# ============================================================
# SAFETY MONITOR S ANALÝZOU PORTFÓLIA A PRAVIDLAMI PREDAJA
# ============================================================

def run_safety_monitor():
    market_global = get_market_global()
    simple_prices = coingecko_simple_price(["bitcoin"])
    fear_greed = get_fear_greed()
    
    btc_data = {}
    try:
        btc_data = collect_coin_data("BTC", "bitcoin", days=35)
    except Exception:
        pass

    safety = market_safety(market_global, simple_prices, btc_data)

    portfolio_analysis = []
    safety_score = safety.get("score", 0)

    for symbol, coin_id in PORTFOLIO.items():
        try:
            cdata = collect_coin_data(symbol, coin_id, days=35)
            tech = cdata.get("technical_4h", {})
            cur_price = safe_float(cdata.get("price_usd"))
            support = safe_float(tech.get("support_30_candles"))
            rsi_val = safe_float(tech.get("rsi14", 50))
            above_200 = tech.get("above_ema200", True)

            expected_drop = 5.0
            if cur_price and support and support < cur_price:
                expected_drop = ((cur_price - support) / cur_price) * 100
            else:
                expected_drop = 6.5 + (safety_score * 0.5)

            bear_prob = int(clamp(50 + (safety_score * 3) + (14 if not above_200 else 0), 10, 95))

            if rsi_val < 35:
                duration = "Krátkodobý výplach (24–48 hodín)"
            elif not above_200:
                duration = "3–5 dňová korekcia / Týždenný tlak"
            else:
                duration = "Krátkodobá korekcia (1–3 dni)"

            tech_breakdown = not above_200 or rsi_val < 40

            if expected_drop > 10 and bear_prob >= 70:
                action = "SELL (Predať 100% pozície)"
            elif expected_drop > 7 and bear_prob >= 60 and tech_breakdown:
                action = "SELL PARTIAL (Predať 30–50% pozície)"
            else:
                action = "HOLD (Držať / Bežný výplach)"

            portfolio_analysis.append({
                "symbol": symbol,
                "price": cur_price,
                "expected_drop": expected_drop,
                "duration": duration,
                "bear_prob": bear_prob,
                "action": action
            })
        except Exception as e:
            print(f"Chyba pri analýze {symbol} pre safety alert: {e}")

    state = load_state()
    should_alert, reason = should_send_safety_alert(safety, state)

    if should_alert:
        alert = format_safety_alert(safety, fear_greed, portfolio_analysis)
        telegram_send(alert)
        state["last_safety_alert"] = iso_now()
        state["last_safety_alert_reason"] = reason

    state["last_safety_state"] = safety.get("state", "NORMAL")
    state["last_safety_score"] = safety.get("score", 0)
    state["last_safety_check"] = iso_now()
    state["market_safety"] = safety
    state["fear_greed"] = fear_greed
    save_state(state)
    return safety


# ============================================================
# FULL MAIN ANALYSIS
# ============================================================

def run_full_analysis(schedule_reason, schedule_slot=None):
    market_global = get_market_global()
    fear_greed = get_fear_greed()
    all_ids = list(dict.fromkeys(list(PORTFOLIO.values()) + CANDIDATES + ["bitcoin"]))
    simple_prices = coingecko_simple_price(all_ids)
    news = get_rss_news()
    btc_data = collect_coin_data("BTC", "bitcoin")
    safety = market_safety(market_global, simple_prices, btc_data)

    portfolio_data = {}
    for symbol, coin_id in PORTFOLIO.items():
        try:
            portfolio_data[symbol] = collect_coin_data(symbol, coin_id)
        except Exception as e:
            portfolio_data[symbol] = {"symbol": symbol, "coin_id": coin_id, "error": str(e)}

    shortlist = shortlist_candidates()
    candidate_data = {}
    for coin_id in shortlist:
        symbol = coin_id.upper()
        try:
            candidate_data[symbol] = collect_coin_data(symbol, coin_id)
        except Exception as e:
            candidate_data[symbol] = {"coin_id": coin_id, "error": str(e)}

    prompt = build_prompt(market_global, fear_greed, safety, news, portfolio_data, candidate_data, btc_data)
    analysis = gemini_analyze(prompt)
    analysis = validate_and_correct_analysis(analysis, safety, portfolio_data)

    state = load_state()
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

    messages = format_bot_message(analysis, safety, fear_greed)
    for message in messages:
        telegram_send(message)
        time.sleep(1)


# ============================================================
# MAIN
# ============================================================

def main():
    if not GEMINI_API_KEY:
        raise RuntimeError("Chýba GEMINI_API_KEY.")

    should_run, reason = is_main_analysis_time()
    scheduled_slot = None
    if should_run and reason != "MANUAL":
        scheduled_slot = get_main_analysis_slot()

    if should_run:
        run_full_analysis(reason, scheduled_slot)
        return

    run_safety_monitor()


if __name__ == "__main__":
    main()
