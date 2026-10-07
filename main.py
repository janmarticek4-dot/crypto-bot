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
# CRYPTO AI BOT V5.5 (Chat API + Gemini 3.8 Flash)
# ============================================================

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()
COINGECKO_API_KEY = os.getenv("COINGECKO_API_KEY", "").strip()

GEMINI_MODEL = "gemini-3.8-flash"

REQUEST_TIMEOUT = 120
STATE_FILE = "bot_state.json"
TZ = ZoneInfo("Europe/Bratislava")


# ============================================================
# PORTFOLIO & CANDIDATES
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
# HELPERS
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

def http_request(req, timeout=REQUEST_TIMEOUT, retries=4):
    last_error = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                return response.read()
        except urllib.error.HTTPError as e:
            last_error = e
            print(f"HTTP {e.code} (pokus {attempt + 1}/{retries}): {e.reason}")
            if e.code in {400, 401, 403, 404}:
                raise
            if attempt < retries - 1:
                wait = 2 ** attempt
                time.sleep(wait)
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
            last_error = e
            if attempt < retries - 1:
                wait = 2 ** attempt
                time.sleep(wait)
    if last_error:
        raise last_error
    raise RuntimeError("HTTP request zlyhal.")


def http_json(url, headers=None, timeout=REQUEST_TIMEOUT, retries=4):
    if headers is None:
        headers = {}
    req = urllib.request.Request(url, headers=headers, method="GET")
    raw = http_request(req, timeout=timeout, retries=retries)
    return json.loads(raw.decode("utf-8"))


# ============================================================
# COINGECKO
# ============================================================

def coingecko_headers():
    headers = {"Accept": "application/json", "User-Agent": "CryptoAIBot/5.5"}
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
# TECHNICAL ANALYSIS
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


def technical_summary(candles):
    if not candles:
        return {}
    closes = [c["close"] for c in candles if c.get("close") is not None]
    if len(closes) < 20:
        return {"price": closes[-1] if closes else None}
    ema20 = ema(closes, 20)
    ema50 = ema(closes, 50)
    ema100 = ema(closes, 100)
    ema200 = ema(closes, 200)
    current = closes[-1]
    e20 = last_valid(ema20)
    e50 = last_valid(ema50)
    e100 = last_valid(ema100)
    e200 = last_valid(ema200)
    return {
        "price": current,
        "ema20": e20,
        "ema50": e50,
        "ema100": e100,
        "ema200": e200,
        "rsi14": rsi(closes, 14),
        "macd": macd(closes),
        "above_ema20": current > e20 if e20 is not None else None,
        "above_ema50": current > e50 if e50 is not None else None,
        "above_ema200": current > e200 if e200 is not None else None,
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


def collect_coin_data(symbol, coin_id):
    print(f"Collecting: {symbol}")
    simple = coingecko_simple_price([coin_id])
    current = simple.get(coin_id, {})
    chart = coingecko_chart(coin_id, days=90)
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
    filtered = [x for x in market_data if x.get("id") not in portfolio_ids and safe_float(x.get("market_cap"), 0) > 100_000_000]
    filtered.sort(key=lambda x: (safe_float(x.get("total_volume"), 0), safe_float(x.get("market_cap"), 0)), reverse=True)
    selected = filtered[:3]
    return [x["id"] for x in selected]


# ============================================================
# MARKET & RSS
# ============================================================

def get_market_global():
    return coingecko_get("global")


def get_fear_greed():
    try:
        data = http_json("https://api.alternative.me/fng/?limit=1", headers={"User-Agent": "CryptoAIBot/5.5"})
        item = data["data"][0]
        return {"value": int(item["value"]), "classification": item["value_classification"], "timestamp": item.get("timestamp")}
    except Exception as e:
        print(f"Fear & Greed error: {e}")
        return {"value": None, "classification": "UNKNOWN", "timestamp": None}


def market_safety(global_data, simple_prices):
    score = 0
    reasons = []
    try:
        change = global_data["data"].get("market_cap_change_percentage_24h_usd")
        if change is not None:
            if change < -5:
                score += 2
                reasons.append("celková kapitalizácia prudko klesá")
            elif change < -2:
                score += 1
                reasons.append("celková kapitalizácia klesá")
    except Exception:
        pass

    try:
        btc = simple_prices.get("bitcoin", {})
        btc_change = btc.get("usd_24h_change")
        if btc_change is not None:
            if btc_change < -7:
                score += 3
                reasons.append("BTC výrazne klesá")
            elif btc_change < -3:
                score += 2
                reasons.append("BTC prudko klesá")
            elif btc_change < -1.5:
                score += 1
                reasons.append("BTC klesá")
    except Exception:
        pass

    state = "CRITICAL" if score >= 5 else ("WARNING" if score >= 2 else "NORMAL")
    return {"state": state, "score": score, "reasons": reasons}


def get_rss_news():
    headers = {"User-Agent": "Mozilla/5.0 (compatible; CryptoAIBot/5.5)"}
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


# ============================================================
# GEMINI JSON PARSER & CHAT API
# ============================================================

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
        candidate = text[start:end + 1]
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass

    raise RuntimeError("Gemini output nie je validný JSON:\n" + text[:5000])


def gemini_analyze(prompt):
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY nie je nastavený.")

    print("Spúšťam Gemini analýzu (Chat API) cez official google-genai SDK...")
    client = genai.Client(api_key=GEMINI_API_KEY)

    # Použitie Chat prístupu kvôli integrácii Google Search nástroja,
    # ako priamo odporúča Google v chybovej hláške "AFC in Chat.send_message"
    chat = client.chats.create(
        model=GEMINI_MODEL,
        config={
            "tools": [{"google_search": {}}],
            "response_mime_type": "application/json",
            "temperature": 0.2,
        }
    )

    response = chat.send_message(prompt)

    output_text = response.text
    if not output_text:
        raise RuntimeError("Gemini vrátil prázdnu textovú odpoveď.")

    return parse_json_output(output_text)


# ============================================================
# PROMPT
# ============================================================

def build_prompt(market_global, fear_greed, safety, news, portfolio_data, candidate_data):
    return f"""
You are the main investment intelligence engine of a crypto trading bot.

CURRENT TIME:
{iso_now()}

Use current information from Google Search whenever current fundamental information is relevant.
Do NOT rely on old knowledge for regulation, ETFs, institutional adoption, partnerships, token unlocks, tokenomics, ecosystem activity, or current news.

The user wants practical investment decisions.
INVESTMENT HORIZON: now through approximately April 2027.
User prefers buying pullbacks. User does NOT want additional APT exposure. User already owns the portfolio coins below.
A missed trade is better than a bad trade. If there is no attractive setup, say NO TRADE.

GLOBAL MARKET:
{json.dumps(market_global, ensure_ascii=False, indent=2)}

FEAR & GREED:
{json.dumps(fear_greed, ensure_ascii=False, indent=2)}

MARKET SAFETY:
{json.dumps(safety, ensure_ascii=False, indent=2)}

RECENT NEWS:
{json.dumps(news, ensure_ascii=False, indent=2)}

USER PORTFOLIO:
{json.dumps(portfolio_data, ensure_ascii=False, indent=2)}

NEW COIN CANDIDATES:
{json.dumps(candidate_data, ensure_ascii=False, indent=2)}

TASK:
Analyze: AAVE, TAO, FET, SOL, ONDO, RENDER.
For every portfolio coin determine action (BUY NOW, BUY PULLBACK, HOLD, REDUCE, SELL, NO TRADE), current_price, buy_zone_1, buy_zone_2, invalidation, tp1, tp2, risk_reward, bull_probability, bear_probability, technical_score (0-10), fundamental_score (0-10), reason.

Analyze shortlisted new coins. Choose AT MOST ONE new coin, or set new_coin = "NO TRADE". Do NOT recommend APT.

Return ONLY a valid JSON object matching this structure:
{{
  "market_regime": "bullish|neutral|corrective|bearish|capitulation",
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
      "risk_reward": "string",
      "bull_probability": 0.0,
      "bear_probability": 0.0,
      "technical_score": 0.0,
      "fundamental_score": 0.0,
      "reason": "string"
    }}
  ],
  "best_opportunity": "string",
  "avoid": "string",
  "conditions_to_watch": ["string"]
}}
"""


# ============================================================
# TELEGRAM & STATE
# ============================================================

def telegram_send(text):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    try:
        http_request(req, timeout=30, retries=3)
    except Exception as e:
        print(f"Telegram error: {e}")


def clean_html(text):
    if text is None:
        return ""
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


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
        "<b>📊 CRYPTO AI BOT — 4H ANALÝZA</b>",
        f"🕒 {clean_html(iso_now())}",
        "",
        f"<b>🌐 Trh:</b> {clean_html(analysis.get('market_regime', 'N/A'))}",
        f"<b>🛡 Safety:</b> {clean_html(safety.get('state', 'N/A'))} ({safety.get('score', 0)})",
    ]
    for reason in safety.get("reasons", []):
        lines.append("• " + clean_html(reason))

    fg = fear_greed.get("value")
    if fg is not None:
        lines.append(f"<b>😱 Fear & Greed:</b> {fg}/100 ({clean_html(fear_greed.get('classification', ''))})")

    lines.extend(["", "<b>🧠 Makro:</b>", clean_html(analysis.get('market_summary', '')) , ""])

    for coin in analysis.get("coins", []):
        symbol = coin.get("symbol", "?")
        lines.extend([
            f"<b>━━ {clean_html(symbol)} ━━</b>",
            f"<b>Akcia:</b> {clean_html(coin.get('action', 'N/A'))}",
            f"<b>Cena:</b> {format_price(coin.get('current_price'))}",
            f"<b>BUY 1:</b> {clean_html(coin.get('buy_zone_1', 'N/A'))}",
            f"<b>BUY 2:</b> {clean_html(coin.get('buy_zone_2', 'N/A'))}",
            f"<b>Invalidácia:</b> {clean_html(coin.get('invalidation', 'N/A'))}",
            f"<b>TP1:</b> {clean_html(coin.get('tp1', 'N/A'))} | <b>TP2:</b> {clean_html(coin.get('tp2', 'N/A'))}",
            f"<b>R:R:</b> {clean_html(coin.get('risk_reward', 'N/A'))} | <b>Technika:</b> {coin.get('technical_score', 'N/A')}/10 | <b>Fundament:</b> {coin.get('fundamental_score', 'N/A')}/10",
            f"<i>{clean_html(coin.get('reason', ''))}</i>",
            ""
        ])

    lines.extend([
        f"<b>🚀 Najlepšia príležitosť:</b> {clean_html(analysis.get('best_opportunity', 'N/A'))}",
        f"<b>🆕 Nová kryptomena:</b> {clean_html(analysis.get('new_coin', 'NO TRADE'))} ({clean_html(analysis.get('new_coin_action', 'NO TRADE'))})",
        f"<b>Dôvod:</b> {clean_html(analysis.get('new_coin_reason', ''))}",
        f"<b>⚠️ Vyhnúť sa:</b> {clean_html(analysis.get('avoid', ''))}",
        ""
    ])

    conditions = analysis.get("conditions_to_watch", [])
    if conditions:
        lines.append("<b>👀 Sledovať:</b>")
        for cond in conditions[:6]:
            lines.append("• " + clean_html(cond))
        lines.append("")

    lines.append("<i>Nie je to finančné poradenstvo.</i>")
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
    except Exception as e:
        print(f"State load error: {e}")
        return {}


def save_state(state):
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"State save error: {e}")


# ============================================================
# MAIN
# ============================================================

def main():
    print("Crypto bot V5.5:", iso_now())
    if not GEMINI_API_KEY:
        raise RuntimeError("Chýba GEMINI_API_KEY.")

    print("Collecting global market...")
    market_global = get_market_global()

    print("Collecting Fear & Greed...")
    fear_greed = get_fear_greed()

    all_ids = list(dict.fromkeys(list(PORTFOLIO.values()) + CANDIDATES + ["bitcoin"]))
    simple_prices = coingecko_simple_price(all_ids)

    safety = market_safety(market_global, simple_prices)
    print("MARKET SAFETY:", safety)

    news = get_rss_news()

    portfolio_data = {}
    for symbol, coin_id in PORTFOLIO.items():
        try:
            portfolio_data[symbol] = collect_coin_data(symbol, coin_id)
        except Exception as e:
            print(f"ERROR collecting {symbol}: {e}")
            portfolio_data[symbol] = {"symbol": symbol, "coin_id": coin_id, "error": str(e)}

    shortlist = shortlist_candidates()
    candidate_data = {}
    for coin_id in shortlist:
        symbol = coin_id.upper()
        try:
            candidate_data[symbol] = collect_coin_data(symbol, coin_id)
        except Exception as e:
            print(f"ERROR collecting candidate {coin_id}: {e}")
            candidate_data[symbol] = {"coin_id": coin_id, "error": str(e)}

    prompt = build_prompt(market_global, fear_greed, safety, news, portfolio_data, candidate_data)

    print("Sending data to Gemini...")
    analysis = gemini_analyze(prompt)
    print("Gemini analysis completed.")

    state = load_state()
    state["last_run"] = iso_now()
    state["market_safety"] = safety
    state["fear_greed"] = fear_greed
    state["last_analysis"] = analysis
    save_state(state)

    messages = format_bot_message(analysis, safety, fear_greed)
    for message in messages:
        telegram_send(message)
        time.sleep(1)

    print("Crypto bot V5.5 finished successfully.")


if __name__ == "__main__":
    main()
