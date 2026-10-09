import os
import json
import time
import re
import urllib.request
import urllib.parse
import urllib.error
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from google import genai

# ============================================================
# CRYPTO AI BOT V7.0
# - pravidlá pre BUY NOW / BUY PULLBACK / HOLD / REDUCE / SELL
# - technické skóre vypočítané z dát, nie vymyslené Gemini
# - fundamentálne skóre s povinným odôvodnením a istotou
# - nadväznosť na predchádzajúce odporúčania
# - kontrola starších 24h predpovedí
# - konzervatívna ochrana pred panickým predajom
# ============================================================

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()
COINGECKO_API_KEY = os.getenv("COINGECKO_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash").strip()

REQUEST_TIMEOUT = 60
GEMINI_MAX_WAIT = 600
POLL_INTERVAL = 5
STATE_FILE = "bot_state.json"
TZ = ZoneInfo("Europe/Bratislava")
US_TZ = ZoneInfo("America/New_York")

PORTFOLIO = {
    "AAVE": "aave", "TAO": "bittensor", "FET": "fetch-ai",
    "SOL": "solana", "ONDO": "ondo-finance", "RENDER": "render-token",
}
CANDIDATES = [
    "sui", "chainlink", "compound-governance-token", "avalanche-2",
    "hyperliquid", "near", "injective-protocol", "uniswap",
    "arbitrum", "optimism", "maker", "mantle",
]
RSS_FEEDS = [
    ("CoinTelegraph", "https://cointelegraph.com/rss"),
    ("CoinDesk", "https://www.coindesk.com/arc/outboundfeeds/rss/"),
]
VALID_ACTIONS = {"BUY NOW", "BUY PULLBACK", "HOLD", "REDUCE", "SELL", "NO TRADE"}


# ----------------------------- Utilities -----------------------------

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


def clamp(value, low, high):
    return max(low, min(high, value))


def pct_change(old, new):
    if old in (None, 0) or new is None:
        return None
    return (new - old) / old * 100.0


def manual_analysis_requested():
    return os.getenv("MANUAL_ANALYSIS", "").strip().lower() in {"true", "1", "yes", "y", "on"}


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


# ----------------------------- Schedule -----------------------------

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


# ----------------------------- HTTP / CoinGecko -----------------------------

def http_request(req, timeout=REQUEST_TIMEOUT, retries=4):
    last_error = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            last_error = exc
            if exc.code in {400, 401, 403, 404}:
                raise
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as exc:
            last_error = exc
        if attempt < retries - 1:
            time.sleep(2 ** attempt)
    raise last_error or RuntimeError("HTTP požiadavka zlyhala.")


def http_json(url, headers=None, timeout=REQUEST_TIMEOUT, retries=4):
    req = urllib.request.Request(url, headers=headers or {}, method="GET")
    raw = http_request(req, timeout, retries)
    return json.loads(raw.decode("utf-8"))


def coingecko_headers():
    headers = {"Accept": "application/json", "User-Agent": "CryptoAIBot/7.0"}
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
        "ids": ",".join(ids), "vs_currencies": "usd",
        "include_market_cap": "true", "include_24hr_vol": "true",
        "include_24hr_change": "true", "include_last_updated_at": "true",
    })


def coingecko_markets(ids):
    if not ids:
        return []
    return coingecko_get("coins/markets", {
        "vs_currency": "usd", "ids": ",".join(ids),
        "order": "market_cap_desc", "per_page": len(ids), "page": 1,
        "sparkline": "false", "price_change_percentage": "24h,7d",
    })


def coingecko_chart(coin_id, days=90):
    return coingecko_get(f"coins/{coin_id}/market_chart", {
        "vs_currency": "usd", "days": days, "interval": "hourly",
    })


# ----------------------------- Technical indicators -----------------------------

def closes_from_chart(chart):
    return [{"timestamp": p[0], "price": safe_float(p[1])}
            for p in chart.get("prices", []) if len(p) >= 2 and safe_float(p[1]) is not None]


def aggregate_candles(prices, hours=4):
    buckets = {}
    width = hours * 60 * 60 * 1000
    for point in prices:
        ts, price = int(point["timestamp"]), point["price"]
        bucket = (ts // width) * width
        if bucket not in buckets:
            buckets[bucket] = {"timestamp": bucket, "open": price, "high": price, "low": price, "close": price}
        else:
            buckets[bucket]["high"] = max(buckets[bucket]["high"], price)
            buckets[bucket]["low"] = min(buckets[bucket]["low"], price)
            buckets[bucket]["close"] = price
    return [buckets[k] for k in sorted(buckets)]


def ema(values, period):
    if len(values) < period:
        return [None] * len(values)
    out = [None] * len(values)
    previous = sum(values[:period]) / period
    out[period - 1] = previous
    mult = 2 / (period + 1)
    for i in range(period, len(values)):
        previous = (values[i] - previous) * mult + previous
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
    changes = [values[i] - values[i - 1] for i in range(1, len(values))]
    gains, losses = [max(x, 0) for x in changes], [max(-x, 0) for x in changes]
    avg_gain, avg_loss = sum(gains[:period]) / period, sum(losses[:period]) / period
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - 100 / (1 + rs)


def macd(values):
    if len(values) < 35:
        return {"macd": None, "signal": None, "histogram": None}
    e12, e26 = ema(values, 12), ema(values, 26)
    series = [a - b if a is not None and b is not None else None for a, b in zip(e12, e26)]
    valid = [x for x in series if x is not None]
    signal = last_valid(ema(valid, 9))
    current = valid[-1]
    return {"macd": current, "signal": signal, "histogram": current - signal if signal is not None else None}


def atr(candles, period=14):
    if len(candles) < period + 1:
        return None
    ranges = []
    for i in range(1, len(candles)):
        c, prev = candles[i], candles[i - 1]
        ranges.append(max(c["high"] - c["low"], abs(c["high"] - prev["close"]), abs(c["low"] - prev["close"])))
    return sum(ranges[-period:]) / period if ranges else None


def recent_support_resistance(candles, lookback=30):
    recent = candles[-lookback:]
    if not recent:
        return {"support": None, "resistance": None}
    return {"support": min(c["low"] for c in recent), "resistance": max(c["high"] for c in recent)}


def technical_summary(candles):
    if not candles:
        return {}
    closes = [c["close"] for c in candles]
    price = closes[-1]
    averages = {f"ema{n}": last_valid(ema(closes, n)) for n in (20, 50, 100, 200)}
    sr = recent_support_resistance(candles)
    current_atr = atr(candles)
    above = {f"above_ema{n}": price > averages[f"ema{n}"] if averages[f"ema{n}"] is not None else None for n in (20, 50, 100, 200)}
    return {
        "price": price, **averages, **above, "rsi14": rsi(closes), "macd": macd(closes),
        "atr14": current_atr, "atr_percent": current_atr / price * 100 if current_atr and price else None,
        "support_30_candles": sr["support"], "resistance_30_candles": sr["resistance"],
        "candles_4h_available": len(candles),
    }


def recent_returns(closes):
    result = {}
    for name, bars in {"24h": 6, "7d": 42, "30d": 180}.items():
        if len(closes) > bars:
            result[name] = pct_change(closes[-bars - 1], closes[-1])
    return result


def calculate_technical_score(tech):
    """Deterministické skóre 0–10: trend, priemery, RSI, MACD. Nie je predikcia ceny."""
    if not tech or safe_float(tech.get("price")) is None:
        return {"score": None, "label": "nedostatok dát", "reasons": []}
    score = 5.0
    reasons = []
    for key, weight, label in [
        ("above_ema20", 0.45, "EMA20"), ("above_ema50", 0.8, "EMA50"),
        ("above_ema100", 0.65, "EMA100"), ("above_ema200", 1.0, "EMA200"),
    ]:
        value = tech.get(key)
        if value is True:
            score += weight
            reasons.append(f"cena nad {label}")
        elif value is False:
            score -= weight
            reasons.append(f"cena pod {label}")
    r = safe_float(tech.get("rsi14"))
    if r is not None:
        if 50 <= r <= 65:
            score += 0.8; reasons.append(f"RSI {r:.1f}: pozitívne momentum")
        elif r > 65:
            score += 0.3; reasons.append(f"RSI {r:.1f}: silné, ale môže byť prekúpené")
        elif 40 <= r < 50:
            score -= 0.2; reasons.append(f"RSI {r:.1f}: neutrálne až slabšie")
        elif 30 <= r < 40:
            score -= 0.6; reasons.append(f"RSI {r:.1f}: slabé momentum")
        elif r < 30:
            score -= 0.3; reasons.append(f"RSI {r:.1f}: prepredané, možný odraz aj pokračovanie poklesu")
    hist = safe_float((tech.get("macd") or {}).get("histogram"))
    if hist is not None:
        if hist > 0:
            score += 0.6; reasons.append("MACD histogram kladný")
        elif hist < 0:
            score -= 0.6; reasons.append("MACD histogram záporný")
    return {"score": round(clamp(score, 0, 10), 1), "label": "silná" if score >= 7 else "slabá" if score <= 3 else "zmiešaná", "reasons": reasons}


def collect_coin_data(symbol, coin_id, days=90):
    print(f"Collecting: {symbol}")
    simple = coingecko_simple_price([coin_id])
    current = simple.get(coin_id, {})
    chart = coingecko_chart(coin_id, days=days)
    candles = aggregate_candles(closes_from_chart(chart))
    tech = technical_summary(candles)
    return {
        "symbol": symbol, "coin_id": coin_id, "price_usd": current.get("usd"),
        "market_cap": current.get("usd_market_cap"), "volume_24h": current.get("usd_24h_vol"),
        "change_24h": current.get("usd_24h_change"), "last_updated": current.get("last_updated_at"),
        "technical_4h": tech, "technical_score_calc": calculate_technical_score(tech),
        "returns": recent_returns([c["close"] for c in candles]),
    }


def shortlist_candidates():
    print("Shortlisting candidate coins...")
    markets = coingecko_markets(CANDIDATES)
    if not markets:
        return CANDIDATES[:3]
    portfolio_ids = set(PORTFOLIO.values())
    filtered = [x for x in markets if x.get("id") not in portfolio_ids and safe_float(x.get("market_cap"), 0) > 100_000_000]
    filtered.sort(key=lambda x: (safe_float(x.get("total_volume"), 0), safe_float(x.get("market_cap"), 0)), reverse=True)
    return [x["id"] for x in filtered[:3]]


# ----------------------------- Market safety -----------------------------

def get_fear_greed():
    try:
        item = http_json("https://api.alternative.me/fng/?limit=1", headers={"User-Agent": "CryptoAIBot/7.0"})["data"][0]
        return {"value": int(item["value"]), "classification": item["value_classification"], "timestamp": item.get("timestamp")}
    except Exception as exc:
        print(f"Fear & Greed error: {exc}")
        return {"value": None, "classification": "UNKNOWN", "timestamp": None}


def market_safety(global_data, simple_prices, btc_data=None):
    score, reasons = 0, []
    global_change = safe_float(global_data.get("data", {}).get("market_cap_change_percentage_24h_usd"))
    btc_change = safe_float(simple_prices.get("bitcoin", {}).get("usd_24h_change"))
    if global_change is not None:
        if global_change <= -5: score += 3; reasons.append("celková kapitalizácia prudko klesá")
        elif global_change <= -3.5: score += 2; reasons.append("celková kapitalizácia výrazne klesá")
        elif global_change <= -2: score += 1; reasons.append("celková kapitalizácia klesá")
    if btc_change is not None:
        if btc_change <= -7: score += 4; reasons.append("BTC prudko klesá")
        elif btc_change <= -5: score += 3; reasons.append("BTC výrazne klesá")
        elif btc_change <= -3: score += 2; reasons.append("BTC klesá výrazne")
        elif btc_change <= -1.5: score += 1; reasons.append("BTC klesá")
    tech = btc_data.get("technical_4h", {}) if isinstance(btc_data, dict) else {}
    price, e50, e200, rsi_value = [safe_float(tech.get(k)) for k in ("price", "ema50", "ema200", "rsi14")]
    if price is not None and e50 is not None and price < e50:
        score += 1; reasons.append("BTC je pod 4H EMA50")
    if price is not None and e200 is not None and price < e200:
        score += 2; reasons.append("BTC je pod 4H EMA200")
    if rsi_value is not None and rsi_value < 35:
        score += 2; reasons.append("BTC 4H RSI je pod 35")
    elif rsi_value is not None and rsi_value < 40:
        score += 1; reasons.append("BTC 4H RSI je pod 40")
    if global_change is not None and btc_change is not None and global_change <= -2 and btc_change <= -1.5:
        score += 1; reasons.append("BTC aj celý kryptotrh klesajú súčasne")
    state = "CRITICAL" if score >= 6 else "WARNING" if score >= 3 else "NORMAL"
    return {"state": state, "score": score, "reasons": reasons, "market_cap_change_24h": global_change,
            "btc_change_24h": btc_change, "btc_price": price, "btc_ema50": e50, "btc_ema200": e200, "btc_rsi14": rsi_value}


def should_send_safety_alert(current, state):
    level, score = current.get("state", "NORMAL"), safe_float(current.get("score"), 0)
    prev_level, prev_score = state.get("last_safety_state", "NORMAL"), safe_float(state.get("last_safety_score"), 0)
    if level == "NORMAL": return False, "NORMAL"
    if prev_level == "NORMAL": return True, "STATE_CHANGE"
    if prev_level == "WARNING" and level == "CRITICAL": return True, "STATE_ESCALATION"
    if score >= prev_score + 2: return True, "SCORE_WORSENING"
    return False, "NO_NEW_ALERT"


# ----------------------------- Telegram -----------------------------

def telegram_send(text):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        raise RuntimeError("Chýba TELEGRAM_TOKEN alebo TELEGRAM_CHAT_ID.")
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "disable_web_page_preview": True}
    req = urllib.request.Request(url, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=30) as response:
        result = json.loads(response.read().decode("utf-8"))
    if not result.get("ok"):
        raise RuntimeError(f"Telegram odmietol správu: {result}")
    print("Telegram message sent.")
    return True


def telegram_send_long(text):
    chunks, current = [], ""
    for line in text.splitlines():
        if len(current) + len(line) + 1 > 3900:
            if current: chunks.append(current)
            current = line
        else:
            current += ("\n" if current else "") + line
    if current: chunks.append(current)
    for chunk in chunks:
        telegram_send(chunk)
        time.sleep(1)


# ----------------------------- News / Gemini -----------------------------

def get_rss_news():
    all_items = []
    headers = {"User-Agent": "Mozilla/5.0 (compatible; CryptoAIBot/7.0)", "Accept": "application/rss+xml,application/xml,text/xml,*/*"}
    for source, url in RSS_FEEDS:
        try:
            raw = http_request(urllib.request.Request(url, headers=headers), timeout=30, retries=2)
            root = ET.fromstring(raw)
            count = 0
            for item in root.iter():
                if not item.tag.lower().endswith("item"): continue
                entry = {"source": source, "title": "", "link": "", "pub_date": ""}
                for child in item:
                    tag = child.tag.lower()
                    if tag.endswith("title"): entry["title"] = (child.text or "").strip()
                    elif tag.endswith("link"): entry["link"] = (child.text or "").strip()
                    elif tag.endswith("pubdate"): entry["pub_date"] = (child.text or "").strip()
                if entry["title"]:
                    all_items.append(entry); count += 1
                if count >= 10: break
        except Exception as exc:
            print(f"RSS error {source}: {exc}")
    return all_items[:20]


def parse_json_output(text):
    if not text: raise RuntimeError("Gemini neposlal výstup.")
    text = re.sub(r"^```json\s*", "", text.strip(), flags=re.I)
    text = re.sub(r"\s*```$", "", text)
    try: return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start: return json.loads(text[start:end + 1])
        raise RuntimeError("Gemini neposlal validný JSON.")


def gemini_analyze(prompt):
    if not GEMINI_API_KEY: raise RuntimeError("GEMINI_API_KEY nie je nastavený.")
    client = genai.Client(api_key=GEMINI_API_KEY)
    interaction = client.interactions.create(
        model=GEMINI_MODEL, input=prompt, background=True,
        tools=[{"type": "google_search"}],
        generation_config={"thinking_level": "high"}, store=True, timeout=120,
    )
    interaction_id, started = interaction.id, time.time()
    while True:
        if time.time() - started > GEMINI_MAX_WAIT:
            raise TimeoutError("Gemini analýza trvá dlhšie ako 10 minút.")
        interaction = client.interactions.get(id=interaction_id)
        status = interaction.status
        if status == "completed":
            if not interaction.output_text: raise RuntimeError("Gemini vrátil prázdny výstup.")
            return parse_json_output(interaction.output_text)
        if status in {"failed", "cancelled", "expired", "incomplete", "requires_action"}:
            raise RuntimeError(f"Gemini analýza skončila: {status}")
        time.sleep(POLL_INTERVAL)


def build_prompt(market_global, fear_greed, safety, news, portfolio_data, candidate_data, btc_data, state):
    previous = state.get("last_analysis", {})
    previous_coins = previous.get("coins", []) if isinstance(previous, dict) else []
    prior_summary = []
    for c in previous_coins:
        if isinstance(c, dict):
            prior_summary.append({
                "symbol": c.get("symbol"), "action": c.get("action"),
                "price": c.get("current_price"), "outlook_direction": c.get("outlook_direction"),
                "outlook_pct": c.get("outlook_pct"), "technical_score": c.get("technical_score"),
                "fundamental_score": c.get("fundamental_score"), "reason": c.get("reason"),
            })
    return f"""
Si disciplinovaný analytik kryptomien a správca rizika. Píš po slovensky.
Čas Bratislava: {iso_now()}
Portfólio: AAVE, TAO, FET, SOL, ONDO, RENDER. APT nikdy neodporúčaj.

CIEĽ: odporúčanie musí pomôcť rozhodnúť, čo urobiť teraz s už držanou pozíciou a čo urobiť s NOVÝMI PENIAZMI.
Tieto dve rozhodnutia rozlišuj. HOLD na držanú mincu neznamená, že sa nemá čakať na nákupnú príležitosť.
Pre každú mincu vyber jednu akciu: BUY NOW, BUY PULLBACK, HOLD, REDUCE, SELL, NO TRADE.
- BUY NOW: technika a trhový kontext dávajú dostatočne potvrdený vstup teraz; uveď vstup, invalidáciu a ciele.
- BUY PULLBACK: projekt je atraktívny, ale nákup až v uvedenej zóne a po potvrdení odrazu; nepíš, že vstup je potvrdený, ak nie je.
- HOLD: existujúcu pozíciu držať; zatiaľ nekupovať ani nepredávať. Vysvetli, na čo čakáme.
- REDUCE: zmenšiť časť pozície len pri konkrétnom zhoršení trendu/rizika. Uveď dôkaz a čo by zmenilo názor.
- SELL: úplný odchod len pri silnom dôvode, nie na základe jedného indikátora.
- NO TRADE: vstup nemá výhodný pomer rizika a výnosu alebo dáta nestačia.

SKÓRE:
Technické skóre bude dodané skriptom a musíš ho použiť, nie si ho vymýšľať. Znamená trend/indikátory, nie pravdepodobnosť zisku.
Fundamentálne skóre 0–10 hodnotí využitie, adopciu, príjmy/poplatky, tokenomiku/odomykanie, konkurenciu, vývoj a aktuálne overiteľné správy. Vysvetli skóre aj istotu podkladov. Ak chýbajú dáta, zníž istotu; nevymýšľaj fakty.
Skóre nie je samo osebe signál na nákup/predaj. Vysoký fundament + slabá technika často znamená sledovať BUY PULLBACK; vysoká technika + zlý pomer výnos/riziko nemusí znamenať BUY NOW.
Pri REDUCE/SELL nestačí samotné RSI pod 30/40 ani samotná cena pod EMA200. Hľadaj súlad viacerých signálov, potvrdenie uzavretím sviečky, prerazenie podpory, negatívne momentum a širší trh. RSI pod 30 môže znamenať aj prepredanie a odraz.
Nepovažuj vzdialenosť k podpore za predpoveď poklesu. Uveď samostatne krátkodobý výhľad a úrovne invalidácie.
Nedávaj BUY len preto, aby nebol všade HOLD. Ak nie je výhoda, HOLD/NO TRADE je správne.
Predchádzajúca analýza je kontext: napíš, či sa scenár napĺňa, čo sa zmenilo a či akcia zostáva rovnaká. Nezachovávaj starý názor len zo zotrvačnosti.
Pravdepodobnosti musia byť konzervatívne, súčet bull/bear = 100, žiadne predstieranie presnosti. 24h predikcia je odhad.
Novú mincu odporuč iba vtedy, ak je lepšia než držané alternatívy po zohľadnení rizika; inak NO TRADE.

MARKET GLOBAL: {json.dumps(market_global, ensure_ascii=False)}
FEAR & GREED: {json.dumps(fear_greed, ensure_ascii=False)}
SAFETY: {json.dumps(safety, ensure_ascii=False)}
BTC DATA: {json.dumps(btc_data, ensure_ascii=False)}
PORTFOLIO DATA: {json.dumps(portfolio_data, ensure_ascii=False)}
CANDIDATES: {json.dumps(candidate_data, ensure_ascii=False)}
RSS NEWS (titulky nie sú automaticky overené fakty): {json.dumps(news, ensure_ascii=False)}
PREVIOUS ANALYSIS: {json.dumps(prior_summary, ensure_ascii=False)}

Vráť iba validný JSON:
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
   "current_price":0,
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
   "fundamental_evidence":"konkrétne dôvody a limity dát",
   "reason":"rozhodnutie a čo robiť s existujúcou pozíciou",
   "new_money_plan":"čo robiť s novými peniazmi",
   "bear_case":"medvedí scenár",
   "bull_case":"býčí scenár",
   "confirmation_needed":"čo presne musí nastať",
   "previous_comparison":"čo sa zmenilo oproti poslednej analýze"
  }}
 ],
 "best_opportunity":"string",
 "avoid":"string",
 "conditions_to_watch":["string"]
}}
V poli coins uveď presne AAVE, TAO, FET, SOL, ONDO, RENDER, každú raz. Bez Markdownu mimo JSON.
"""


# ----------------------------- Validation and recommendation continuity -----------------------------

def price_number(value):
    if value is None: return None
    text = str(value).replace("–", "-").replace("—", "-").replace("−", "-")
    matches = re.findall(r"(?<![A-Za-z])(?:\d+(?:[.,]\d+)?|\.\d+)", text.replace(",", "."))
    try: return float(matches[0]) if matches else None
    except (ValueError, TypeError): return None


def price_range(value):
    if value is None: return None
    text = str(value).replace("–", "-").replace("—", "-").replace("−", "-")
    vals = re.findall(r"(?<![A-Za-z])(?:\d+(?:\.\d+)?|\.\d+)", text.replace(",", "."))
    try:
        nums = [float(v) for v in vals]
        return (min(nums[:2]), max(nums[:2])) if nums else None
    except ValueError:
        return None


def calculate_rr(buy_zone, invalidation, tp1, tp2):
    zone, inv, t1, t2 = price_range(buy_zone), price_number(invalidation), price_number(tp1), price_number(tp2)
    if not zone or inv is None or t1 is None or t2 is None: return None
    entry = sum(zone) / 2
    risk = entry - inv
    if risk <= 0 or t1 <= entry or t2 <= entry: return None
    return {"rr_tp1": (t1 - entry) / risk, "rr_tp2": (t2 - entry) / risk}


def validate_and_correct_analysis(analysis, safety, portfolio_data, previous_analysis):
    if not isinstance(analysis, dict) or not isinstance(analysis.get("coins"), list):
        raise RuntimeError("Gemini neposlal analýzu v očakávanom JSON formáte.")
    previous = {str(c.get("symbol", "")).upper(): c for c in previous_analysis.get("coins", []) if isinstance(c, dict)}
    by_symbol = {str(c.get("symbol", "")).upper(): c for c in analysis["coins"] if isinstance(c, dict)}
    validated = []

    for symbol, coin_id in PORTFOLIO.items():
        coin = by_symbol.get(symbol, {"symbol": symbol, "action": "HOLD", "reason": "Gemini neposkytol kompletné odporúčanie; bezpečný náhradný stav HOLD."})
        coin["symbol"] = symbol
        data = portfolio_data.get(symbol, {})
        actual_price = safe_float(data.get("price_usd"))
        tech = data.get("technical_4h", {})
        calc = data.get("technical_score_calc", {})
        if actual_price is not None: coin["current_price"] = actual_price

        # Skóre techniky sa počíta z indikátorov v Pythone; Gemini ho nemôže svojvoľne meniť.
        coin["technical_score"] = calc.get("score")
        coin["technical_score_label"] = calc.get("label", "nedostatok dát")
        coin["technical_score_reasons"] = calc.get("reasons", [])
        coin["fundamental_score"] = round(clamp(safe_float(coin.get("fundamental_score"), 5) or 5, 0, 10), 1)
        coin["fundamental_confidence"] = str(coin.get("fundamental_confidence", "nízka"))
        coin["fundamental_evidence"] = str(coin.get("fundamental_evidence", "Gemini neuviedol dostatočné dôkazy."))

        action = str(coin.get("action", "HOLD")).upper().strip()
        if action not in VALID_ACTIONS: action = "HOLD"

        # Brzda: predaj musí mať viac než jeden signál. Nezakazujeme ho navždy,
        # ale RSI alebo EMA200 samostatne nestačia.
        price, e50, e100, e200 = [safe_float(tech.get(k)) for k in ("price", "ema50", "ema100", "ema200")]
        rsi_value = safe_float(tech.get("rsi14"))
        hist = safe_float((tech.get("macd") or {}).get("histogram"))
        support = safe_float(tech.get("support_30_candles"))
        below_50_200 = price is not None and e50 is not None and e200 is not None and price < e50 and price < e200
        momentum_negative = hist is not None and hist < 0
        support_broken = price is not None and support is not None and price < support * 0.995
        bearish_signals = sum([bool(below_50_200), bool(momentum_negative), bool(support_broken)])
        if action in {"SELL", "REDUCE"} and bearish_signals < 2:
            coin["action_guard_note"] = (
                f"Gemini navrhol {action}, ale dáta nepotvrdzujú aspoň 2 nezávislé signály zhoršenia trendu; "
                "akcia upravená na HOLD, kým sa pokles nepotvrdí."
            )
            action = "HOLD"
        elif action == "SELL" and rsi_value is not None and rsi_value < 30 and bearish_signals < 3:
            coin["action_guard_note"] = "SELL zmenené na HOLD: RSI je výrazne prepredané a pokles nie je potvrdený viacerými signálmi."
            action = "HOLD"

        # Safety ovplyvňuje veľkosť rizika a istotu, nie mechanický predaj.
        if safety.get("state") == "CRITICAL" and action == "BUY NOW":
            coin["action_guard_note"] = (coin.get("action_guard_note", "") + " Safety CRITICAL: BUY NOW zmenené na BUY PULLBACK, počkaj na potvrdenie.").strip()
            action = "BUY PULLBACK"
        coin["action"] = action

        bull = safe_float(coin.get("bull_probability"), 50)
        bull = 50 if bull is None else bull
        if 0 < bull <= 1: bull *= 100
        bull = clamp(bull, 0, 100)
        if safety.get("state") == "WARNING": bull = min(bull, 65)
        elif safety.get("state") == "CRITICAL": bull = min(bull, 55)
        coin["bull_probability"] = round(bull)
        coin["bear_probability"] = round(100 - bull)
        coin["outlook_probability"] = round(clamp(safe_float(coin.get("outlook_probability"), 50) or 50, 5, 95))
        coin["outlook_pct"] = round(clamp(safe_float(coin.get("outlook_pct"), 0) or 0, -30, 30), 2)

        old = previous.get(symbol, {})
        old_action = str(old.get("action", "")).upper()
        if old:
            coin["action_change"] = f"{old_action} → {action}" if old_action and old_action != action else "Akcia bez zmeny"
            coin["previous_price"] = old.get("current_price")
            coin["previous_action"] = old_action
            if not coin.get("previous_comparison"):
                coin["previous_comparison"] = "Porovnaj cenu, indikátory, pôvodný scenár a zmenu skóre s poslednou analýzou."
        else:
            coin["action_change"] = "Prvá uložená analýza pre túto mincu"
            coin["previous_comparison"] = "Zatiaľ nie je staršia analýza na porovnanie."

        rr = calculate_rr(coin.get("buy_zone_1"), coin.get("invalidation"), coin.get("tp1"), coin.get("tp2"))
        coin["risk_reward"] = f"1:{rr['rr_tp1']:.1f} / 1:{rr['rr_tp2']:.1f}" if rr else "N/A"
        validated.append(coin)

    analysis["coins"] = validated
    analysis["action"] = "INDIVIDUAL COIN ACTIONS"
    return analysis


def evaluate_previous_forecasts(previous_analysis, current_data):
    """Vyhodnoť len predpovede, ktoré majú aspoň približne 24 hodín."""
    forecasts = previous_analysis.get("forecast_history", [])
    now = datetime.now(timezone.utc)
    results = []
    for f in forecasts[-40:]:
        try:
            created = datetime.fromisoformat(f["timestamp"].replace("Z", "+00:00"))
            if (now - created).total_seconds() < 23 * 3600:
                continue
            symbol = f["symbol"]
            price_now = safe_float(current_data.get(symbol, {}).get("price_usd"))
            price_then = safe_float(f.get("price"))
            if not price_now or not price_then:
                continue
            actual_pct = pct_change(price_then, price_now)
            predicted_pct = safe_float(f.get("outlook_pct"), 0) or 0
            predicted_dir = str(f.get("outlook_direction", "")).lower()
            actual_dir = "rast" if actual_pct > 0.5 else "pokles" if actual_pct < -0.5 else "do strany"
            hit = (predicted_dir == actual_dir)
            results.append({"symbol": symbol, "predicted_pct": predicted_pct, "actual_pct": round(actual_pct, 2),
                            "predicted_direction": predicted_dir, "actual_direction": actual_dir, "direction_hit": hit})
        except Exception:
            continue
    return results


# ----------------------------- Message formatting -----------------------------

def format_price(value):
    value = safe_float(value)
    if value is None: return "N/A"
    if value >= 1000: return f"${value:,.0f}"
    if value >= 100: return f"${value:,.2f}"
    if value >= 1: return f"${value:,.3f}"
    if value >= 0.01: return f"${value:,.4f}"
    return f"${value:.8f}"


def format_safety_alert(safety, fear_greed, portfolio_analysis=None):
    critical = safety.get("state") == "CRITICAL"
    lines = [
        "🚨 CRYPTO AI BOT — KRÍZOVÝ ALERT" if critical else "⚠️ CRYPTO AI BOT — BEZPEČNOSTNÝ ALERT",
        "", f"🛡 Safety: {safety.get('state')} ({safety.get('score', 0)})",
        "Toto je upozornenie na riziko, nie automatický pokyn na predaj.",
    ]
    for key, label in [("btc_change_24h", "BTC 24h"), ("market_cap_change_24h", "Market cap 24h")]:
        if safety.get(key) is not None: lines.append(f"{label}: {safety[key]:+.2f}%")
    for key, label in [("btc_ema50", "BTC 4H EMA50"), ("btc_ema200", "BTC 4H EMA200")]:
        if safety.get(key) is not None: lines.append(f"{label}: {format_price(safety[key])}")
    if safety.get("btc_rsi14") is not None: lines.append(f"BTC 4H RSI: {safety['btc_rsi14']:.1f}")
    if fear_greed.get("value") is not None:
        lines.append(f"Fear & Greed: {fear_greed['value']}/100 ({fear_greed.get('classification', '')})")
    if safety.get("reasons"): lines.extend(["", "Dôvody:", *[f"• {x}" for x in safety["reasons"][:6]]])
    if portfolio_analysis:
        lines.extend(["", "📊 PORTFÓLIO — KONTEXT:"])
        for item in portfolio_analysis:
            lines.append(f"• {item['symbol']} {format_price(item.get('price'))}: posledná akcia {item.get('action', 'N/A')}; RSI {item.get('rsi', 'N/A')}; technika {item.get('technical_score', 'N/A')}/10")
            lines.append(f"  {item.get('interpretation', '')}")
    lines.extend(["", "Samotné RSI, EMA200 ani vzdialenosť k podpore nepotvrdzujú budúci prepad.",
                  "Sleduj uzatvorenie 4H sviečok, potvrdenie podpory, MACD a širší trh."])
    return "\n".join(lines)


def coin_priority(coin):
    action = str(coin.get("action", "")).upper()
    return {"SELL": 0, "REDUCE": 1, "BUY NOW": 2, "BUY PULLBACK": 3, "HOLD": 4, "NO TRADE": 5}.get(action, 6)


def format_bot_message(analysis, safety, fear_greed, forecast_results=None):
    coins = sorted(analysis.get("coins", []), key=coin_priority)
    lines = ["📊 CRYPTO AI BOT — 4H ANALÝZA", f"🕒 {iso_now()}",
             f"🌐 Trh: {analysis.get('market_regime', 'N/A')}",
             f"🛡 Safety: {safety.get('state', 'N/A')} ({safety.get('score', 0)})"]
    lines.extend(f"• {r}" for r in safety.get("reasons", []))
    if fear_greed.get("value") is not None:
        lines.append(f"😱 Fear & Greed: {fear_greed['value']}/100 ({fear_greed.get('classification', '')})")
    lines.extend(["", "⚡ RÝCHLY AKČNÝ PLÁN:"])
    for c in coins:
        action = c.get("action", "HOLD")
        emoji = "🔴" if action in {"SELL", "REDUCE"} else "🟢" if "BUY" in action else "🟡"
        lines.append(f"{emoji} {c.get('symbol')}: {action}")
    lines.extend(["", "🧠 Makro:", str(analysis.get("market_summary", ""))])
    for c in coins:
        action, symbol = c.get("action", "HOLD"), c.get("symbol", "?")
        emoji = "🔴" if action in {"SELL", "REDUCE"} else "🟢" if "BUY" in action else "🟡"
        lines.extend(["", f"━━ {emoji} {symbol} ━━", f"Akcia: {action}", f"Cena: {format_price(c.get('current_price'))}"])
        direction = str(c.get("outlook_direction", "do strany"))
        move = safe_float(c.get("outlook_pct"), 0) or 0
        prob = safe_float(c.get("outlook_probability"), 50) or 50
        de = "📈" if "rast" in direction.lower() else "📉" if "pokles" in direction.lower() else "↔️"
        lines.append(f"Predikcia 24h: {de} {direction}, {move:+.1f}% (odhad {prob:.0f}%)")
        lines.append(f"🐂 Bull: {c.get('bull_probability', 'N/A')}% | 🐻 Bear: {c.get('bear_probability', 'N/A')}%")
        lines.append(f"Technika: {c.get('technical_score', 'N/A')}/10 ({c.get('technical_score_label', 'N/A')})")
        if c.get("technical_score_reasons"): lines.append("Technické signály: " + "; ".join(c["technical_score_reasons"][:5]))
        lines.append(f"Fundament: {c.get('fundamental_score', 'N/A')}/10 | istota: {c.get('fundamental_confidence', 'N/A')}")
        if c.get("fundamental_evidence"): lines.append(f"Fundament – dôvody: {c['fundamental_evidence']}")
        if "BUY" in action:
            for label, key in [("Nákupná zóna 1", "buy_zone_1"), ("Nákupná zóna 2", "buy_zone_2"),
                               ("Invalidácia", "invalidation"), ("TP1", "tp1"), ("TP2", "tp2"), ("R:R", "risk_reward")]:
                lines.append(f"{label}: {c.get(key, 'N/A')}")
        lines.append(f"Zmena akcie: {c.get('action_change', 'N/A')}")
        if c.get("action_guard_note"): lines.append("🛡 Ochranné pravidlo: " + c["action_guard_note"])
        if c.get("previous_comparison"): lines.append("Oproti minule: " + str(c["previous_comparison"]))
        if c.get("new_money_plan"): lines.append("Nové peniaze: " + str(c["new_money_plan"]))
        if c.get("confirmation_needed"): lines.append("Potvrdenie: " + str(c["confirmation_needed"]))
        if c.get("bear_case"): lines.append("Medvedí scenár: " + str(c["bear_case"]))
        if c.get("bull_case"): lines.append("Býčí scenár: " + str(c["bull_case"]))
        if c.get("reason"): lines.append("Záver: " + str(c["reason"]))
    lines.extend(["", "🚀 Najlepšia príležitosť:", str(analysis.get("best_opportunity", "N/A")),
                  "", f"🆕 Nová kryptomena: {analysis.get('new_coin', 'NO TRADE')}",
                  f"Akcia: {analysis.get('new_coin_action', 'NO TRADE')}",
                  f"Dôvod: {analysis.get('new_coin_reason', '')}",
                  "", f"⚠️ Vyhnúť sa: {analysis.get('avoid', '')}"])
    if analysis.get("conditions_to_watch"):
        lines.extend(["", "👀 Sledovať:", *[f"• {x}" for x in analysis["conditions_to_watch"][:6]]])
    if forecast_results:
        lines.extend(["", "📉 KONTROLA PREDCHÁDZAJÚCICH 24H PREDPOVEDÍ:"])
        for r in forecast_results[-12:]:
            lines.append(f"• {r['symbol']}: predikcia {r['predicted_direction']} {r['predicted_pct']:+.1f}%, skutočnosť {r['actual_direction']} {r['actual_pct']:+.2f}% — {'zhoda' if r['direction_hit'] else 'nezhoda'}")
    lines.extend(["", "Poznámka: skóre a pravdepodobnosti sú odhady, nie záruky. Nie je to finančné poradenstvo."])
    return "\n".join(lines)


# ----------------------------- Safety monitor -----------------------------

def run_safety_monitor():
    market_global = coingecko_get("global")
    simple = coingecko_simple_price(["bitcoin"])
    fear = get_fear_greed()
    btc = {}
    try: btc = collect_coin_data("BTC", "bitcoin", days=35)
    except Exception as exc: print(f"BTC technical data error: {exc}")
    safety = market_safety(market_global, simple, btc)
    state = load_state()
    previous = state.get("last_analysis", {})
    prev_coins = {str(c.get("symbol", "")).upper(): c for c in previous.get("coins", []) if isinstance(c, dict)}
    portfolio_context = []
    for symbol, coin_id in PORTFOLIO.items():
        try:
            data = collect_coin_data(symbol, coin_id, days=35)
            tech = data.get("technical_4h", {})
            price = safe_float(data.get("price_usd"))
            rsi_value = safe_float(tech.get("rsi14"))
            prev = prev_coins.get(symbol, {})
            if rsi_value is not None and rsi_value < 30:
                interpretation = "Prepredané; možný odraz aj pokračovanie poklesu. Nie je to samostatný signál na predaj."
            elif tech.get("above_ema200") is False:
                interpretation = "Zvýšené riziko, ale samotná EMA200 nepotvrdzuje predaj."
            else:
                interpretation = "Indikátory samy osebe nepotvrdzujú nútený predaj."
            portfolio_context.append({"symbol": symbol, "price": price, "rsi": round(rsi_value, 1) if rsi_value is not None else None,
                                      "technical_score": data.get("technical_score_calc", {}).get("score"),
                                      "action": prev.get("action", "N/A"), "interpretation": interpretation})
        except Exception as exc:
            print(f"Safety monitor error for {symbol}: {exc}")
    should_alert, reason = should_send_safety_alert(safety, state)
    if should_alert:
        telegram_send_long(format_safety_alert(safety, fear, portfolio_context))
        state["last_safety_alert"] = iso_now()
        state["last_safety_alert_reason"] = reason
    state["last_safety_state"] = safety.get("state", "NORMAL")
    state["last_safety_score"] = safety.get("score", 0)
    state["last_safety_check"] = iso_now()
    state["market_safety"] = safety
    state["fear_greed"] = fear
    save_state(state)
    return safety


# ----------------------------- Main analysis -----------------------------

def run_full_analysis(schedule_reason, schedule_slot=None):
    market_global = coingecko_get("global")
    fear = get_fear_greed()
    all_ids = list(dict.fromkeys(list(PORTFOLIO.values()) + CANDIDATES + ["bitcoin"]))
    simple = coingecko_simple_price(all_ids)
    news = get_rss_news()
    btc_data = collect_coin_data("BTC", "bitcoin")
    safety = market_safety(market_global, simple, btc_data)

    portfolio_data = {}
    for symbol, coin_id in PORTFOLIO.items():
        try: portfolio_data[symbol] = collect_coin_data(symbol, coin_id)
        except Exception as exc: portfolio_data[symbol] = {"symbol": symbol, "coin_id": coin_id, "error": str(exc), "technical_4h": {}, "technical_score_calc": {"score": None, "label": "nedostatok dát", "reasons": []}}
    candidate_data = {}
    for coin_id in shortlist_candidates():
        try: candidate_data[coin_id.upper()] = collect_coin_data(coin_id.upper(), coin_id)
        except Exception as exc: candidate_data[coin_id.upper()] = {"coin_id": coin_id, "error": str(exc)}

    state = load_state()
    previous_analysis = state.get("last_analysis", {})
    prompt = build_prompt(market_global, fear, safety, news, portfolio_data, candidate_data, btc_data, state)
    analysis = gemini_analyze(prompt)
    analysis = validate_and_correct_analysis(analysis, safety, portfolio_data, previous_analysis)

    # vyhodnoť staršie predpovede pred pridaním nových
    forecast_results = evaluate_previous_forecasts(state, portfolio_data)
    message = format_bot_message(analysis, safety, fear, forecast_results)

    # Uloženie histórie predpovedí. Nevymažeme staršie záznamy pri každom behu.
    history = state.get("forecast_history", [])
    now_utc = datetime.now(timezone.utc).isoformat()
    for coin in analysis.get("coins", []):
        history.append({
            "timestamp": now_utc, "symbol": coin["symbol"],
            "price": safe_float(coin.get("current_price")),
            "outlook_direction": str(coin.get("outlook_direction", "do strany")).lower(),
            "outlook_pct": safe_float(coin.get("outlook_pct"), 0),
        })
    state["forecast_history"] = history[-240:]

    # Doručenie musí prebehnúť pred označením časového slotu za vybavený.
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
    if schedule_slot and schedule_reason != "MANUAL":
        state["last_main_slot"] = schedule_slot
    save_state(state)
    print("Hlavná analýza bola odoslaná a uložená.")


def main():
    if not GEMINI_API_KEY: raise RuntimeError("Chýba GEMINI_API_KEY.")
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID: raise RuntimeError("Chýba TELEGRAM_TOKEN alebo TELEGRAM_CHAT_ID.")
    run_main, reason = is_main_analysis_time()
    slot = get_main_analysis_slot() if run_main and reason != "MANUAL" else None
    if run_main:
        run_full_analysis(reason, slot)
    else:
        run_safety_monitor()


if __name__ == "__main__":
    main()
