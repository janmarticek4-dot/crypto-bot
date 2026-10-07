import os, json, math, time, urllib.request, urllib.parse, xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

# ============================================================
# CRYPTO AI BOT V5
# GitHub Actions -> CoinGecko/Alternative.me/RSS -> Gemini -> Telegram
# ============================================================
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()
COINGECKO_API_KEY = os.getenv("COINGECKO_API_KEY", "").strip()
MANUAL_ANALYSIS = os.getenv("MANUAL_ANALYSIS", "false").lower() == "true"

GEMINI_MODEL = "gemini-3.8-flash"
CG_BASE = "https://api.coingecko.com/api/v3"
LOCAL_TZ = ZoneInfo("Europe/Bratislava")
NY_TZ = ZoneInfo("America/New_York")
STATE_FILE = "bot_state.json"

PORTFOLIO = {
    "AAVE": "aave",
    "TAO": "bittensor",
    "FET": "fetch-ai",
    "SOL": "solana",
    "ONDO": "ondo-finance",
    "RENDER": "render-token",
}
MARKET = {"BTC": "bitcoin", "ETH": "ethereum"}


def http_get_json(url, headers=None, timeout=60):
    req = urllib.request.Request(url, headers=headers or {"User-Agent": "crypto-ai-bot/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def http_post_json(url, payload, headers=None, timeout=180):
    data = json.dumps(payload).encode("utf-8")
    h = {"Content-Type": "application/json", "User-Agent": "crypto-ai-bot/5.0"}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, data=data, headers=h, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def cg(path, params=None):
    url = CG_BASE + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    headers = {"User-Agent": "crypto-ai-bot/5.0"}
    if COINGECKO_API_KEY:
        headers["x-cg-demo-api-key"] = COINGECKO_API_KEY
    return http_get_json(url, headers=headers)


def market(ids, changes="1h,24h,7d,30d"):
    return cg("/coins/markets", {
        "vs_currency": "usd", "ids": ",".join(ids),
        "order": "market_cap_desc", "per_page": max(1, len(ids)), "page": 1,
        "sparkline": "false", "price_change_percentage": changes,
    })


def chart(coin_id, days):
    params = {"vs_currency": "usd", "days": str(days), "precision": "full"}
    if days <= 30:
        params["interval"] = "hourly"
    else:
        params["interval"] = "daily"
    return cg(f"/coins/{coin_id}/market_chart", params)


def fear_greed():
    try:
        x = http_get_json("https://api.alternative.me/fng/?limit=1")["data"][0]
        return {"value": int(x["value"]), "classification": x["value_classification"]}
    except Exception as e:
        return {"value": None, "classification": "UNKNOWN", "error": str(e)}


def rss_news(limit=8):
    try:
        req = urllib.request.Request("https://cointelegraph.com/rss", headers={"User-Agent": "crypto-ai-bot/5.0"})
        root = ET.fromstring(urllib.request.urlopen(req, timeout=30).read())
        out = []
        for item in root.findall(".//item")[:limit]:
            out.append({
                "title": (item.findtext("title") or "").strip(),
                "link": (item.findtext("link") or "").strip(),
                "published": (item.findtext("pubDate") or "").strip(),
            })
        return out
    except Exception as e:
        return [{"title": "RSS unavailable", "error": str(e)}]


def ema(v, n):
    if len(v) < n:
        return None
    k = 2 / (n + 1)
    x = sum(v[:n]) / n
    for y in v[n:]:
        x = y * k + x * (1 - k)
    return x


def rsi(v, n=14):
    if len(v) <= n:
        return None
    gains, losses = [], []
    for i in range(1, len(v)):
        d = v[i] - v[i - 1]
        gains.append(max(d, 0)); losses.append(max(-d, 0))
    ag = sum(gains[:n]) / n; al = sum(losses[:n]) / n
    for i in range(n, len(gains)):
        ag = (ag * (n - 1) + gains[i]) / n
        al = (al * (n - 1) + losses[i]) / n
    return 100.0 if al == 0 else 100 - 100 / (1 + ag / al)


def ema_series(v, n):
    if len(v) < n:
        return []
    k = 2 / (n + 1); x = sum(v[:n]) / n
    out = [None] * (n - 1) + [x]
    for y in v[n:]:
        x = y * k + x * (1 - k); out.append(x)
    return out


def macd(v):
    fast, slow, sig = ema_series(v, 12), ema_series(v, 26), 9
    line = [None if a is None or b is None else a - b for a, b in zip(fast, slow)]
    clean = [x for x in line if x is not None]
    if len(clean) < sig:
        return None, None, None
    s = ema(clean, sig); m = clean[-1]
    return m, s, (m - s if s is not None else None)


def aggregate_4h(prices, volumes):
    vols = {int(t): float(v) for t, v in volumes}
    b = {}
    for ts, price in prices:
        ts = int(ts); key = ts - ts % 14400; price = float(price)
        z = b.setdefault(key, {"open": None, "high": -math.inf, "low": math.inf, "close": None, "volume": 0.0})
        if z["open"] is None: z["open"] = price
        z["high"] = max(z["high"], price); z["low"] = min(z["low"], price); z["close"] = price
        z["volume"] += vols.get(ts, 0.0)
    return [{"ts": k, **z} for k, z in sorted(b.items())]


def daily_closes(prices):
    d = {}
    for ts, price in prices:
        d[int(ts) // 86400] = float(price)
    return [(k * 86400, v) for k, v in sorted(d.items())]


def series_change(points, hours):
    if len(points) < 2: return None
    target = points[-1][0] - hours * 3600
    old = min(points[:-1], key=lambda x: abs(x[0] - target))
    return (points[-1][1] / old[1] - 1) * 100


def tech(c30, c365):
    p4 = c30.get("prices", []); c4 = aggregate_4h(p4, c30.get("total_volumes", [])); x4 = [z["close"] for z in c4]
    pd = daily_closes(c365.get("prices", [])); xd = [z[1] for z in pd]
    m4, s4, h4 = macd(x4); md, sd, hd = macd(xd)
    e20, e50, e100 = ema(x4,20), ema(x4,50), ema(x4,100)
    de20, de50, de200 = ema(xd,20), ema(xd,50), ema(xd,200)
    sup = min(z["low"] for z in c4[-30:]) if len(c4) >= 5 else None
    res = max(z["high"] for z in c4[-30:]) if len(c4) >= 5 else None
    vp = None
    if len(c4) >= 21:
        av = sum(z["volume"] for z in c4[-21:-1]) / 20
        vp = c4[-1]["volume"] / av if av else None
    cur = x4[-1] if x4 else (xd[-1] if xd else None)
    trend4 = "UNKNOWN"
    if cur and e20 and e50:
        trend4 = "BULLISH" if cur > e20 > e50 else "BEARISH" if cur < e20 < e50 else "MIXED"
    trendd = "UNKNOWN"
    if cur and de20 and de50:
        trendd = "BULLISH" if cur > de20 > de50 else "BEARISH" if cur < de20 < de50 else "MIXED"
    return {
        "4h": {"bars": len(c4), "ema20": e20, "ema50": e50, "ema100": e100, "rsi14": rsi(x4),
               "macd": m4, "macd_signal": s4, "macd_histogram": h4, "support_30_4h": sup,
               "resistance_30_4h": res, "volume_pressure_proxy": vp, "trend": trend4},
        "1d": {"bars": len(xd), "ema20": de20, "ema50": de50, "ema200": de200, "rsi14": rsi(xd),
               "macd": md, "macd_signal": sd, "macd_histogram": hd, "trend": trendd},
        "series_change_24h": series_change(p4,24), "series_change_7d": series_change(p4,168), "last_price": cur
    }


def coin_packet(symbol, coin_id):
    m = market([coin_id])[0]
    t = tech(chart(coin_id,30), chart(coin_id,365))
    return {
        "symbol": symbol, "coin_id": coin_id, "price_usd": m.get("current_price"),
        "market_cap_usd": m.get("market_cap"), "volume_24h_usd": m.get("total_volume"),
        "market_cap_rank": m.get("market_cap_rank"),
        "change_1h_pct": m.get("price_change_percentage_1h_in_currency"),
        "change_24h_pct": m.get("price_change_percentage_24h_in_currency"),
        "change_7d_pct": m.get("price_change_percentage_7d_in_currency"),
        "change_30d_pct": m.get("price_change_percentage_30d_in_currency"),
        "ath": m.get("ath"), "ath_change_pct": m.get("ath_change_percentage"), "technical": t
    }


def safety():
    rows = market(list(MARKET.values()) + list(PORTFOLIO.values()), "24h")
    d = {x["id"]: x for x in rows}; btc = float(d["bitcoin"].get("price_change_percentage_24h_in_currency") or 0)
    vals = [float(d[c].get("price_change_percentage_24h_in_currency")) for c in PORTFOLIO.values() if d.get(c) and d[c].get("price_change_percentage_24h_in_currency") is not None]
    avg = sum(vals)/len(vals) if vals else 0; down5 = sum(x <= -5 for x in vals)
    state = "CRITICAL" if btc <= -5 or avg <= -6 or down5 >= 4 else "WARNING" if btc <= -3 or avg <= -3.5 or down5 >= 2 else "NORMAL"
    return {"state": state, "btc_24h_pct": btc, "portfolio_avg_24h_pct": avg, "coins_down_5pct_or_more": down5,
            "note": "CoinGecko volume is only a volume-pressure proxy, not true order flow."}


def schema():
    actions = ["BUY NOW","BUY LIMIT","WAIT","HOLD","REDUCE NOW","EXIT NOW","TAKE PROFIT NOW","NO TRADE"]
    coin = {"type":"object","properties":{
        "symbol":{"type":"string"},"action":{"type":"string","enum":actions},"decision_now":{"type":"string"},"decision_reason":{"type":"string"},
        "opportunity_score":{"type":"number"},"execution_score":{"type":"number"},"confidence":{"type":"number"},"technical_score":{"type":"number"},"fundamental_score":{"type":"number"},"fundamental_confidence":{"type":"number"},
        "current_price":{"type":"number"},"buy_zone_low":{"type":"number"},"buy_zone_high":{"type":"number"},"strong_buy_zone_low":{"type":"number"},"strong_buy_zone_high":{"type":"number"},"invalidation_price":{"type":"number"},"take_profit_1":{"type":"number"},"take_profit_2":{"type":"number"},"rr_at_buy_zone":{"type":"number"},
        "sell_now":{"type":"boolean"},"sell_reason":{"type":"string"},"reversal_probability_24_72h":{"type":"number"},"continuation_probability_24_72h":{"type":"number"},"reversal_probability_7_14d":{"type":"number"},"continuation_probability_7_14d":{"type":"number"},"turning_timeframe":{"type":"string"},"technical_reason":{"type":"string"},"fundamental_reason":{"type":"string"},"news_risk":{"type":"string"},"sources":{"type":"array","items":{"type":"string"}}
    },"required":["symbol","action","decision_now","decision_reason","opportunity_score","execution_score","confidence","technical_score","fundamental_score","fundamental_confidence","current_price","buy_zone_low","buy_zone_high","strong_buy_zone_low","strong_buy_zone_high","invalidation_price","take_profit_1","take_profit_2","rr_at_buy_zone","sell_now","sell_reason","reversal_probability_24_72h","continuation_probability_24_72h","reversal_probability_7_14d","continuation_probability_7_14d","turning_timeframe","technical_reason","fundamental_reason","news_risk","sources"]}
    return {"type":"object","properties":{
        "market_regime":{"type":"string"},"market_safety":{"type":"string","enum":["NORMAL","WARNING","CRITICAL"]},"btc_outlook":{"type":"string"},"market_action":{"type":"string"},
        "market_reversal_probability_24_72h":{"type":"number"},"market_continuation_probability_24_72h":{"type":"number"},"market_reversal_probability_7_14d":{"type":"number"},"market_continuation_probability_7_14d":{"type":"number"},"market_probability_reason":{"type":"string"},"summary":{"type":"string"},"coins":{"type":"array","items":coin},"new_coin":coin},
        "required":["market_regime","market_safety","btc_outlook","market_action","market_reversal_probability_24_72h","market_continuation_probability_24_72h","market_reversal_probability_7_14d","market_continuation_probability_7_14d","market_probability_reason","summary","coins","new_coin"]}


def gemini(prompt, sch):
    resp = http_post_json("https://generativelanguage.googleapis.com/v1beta/interactions", {
        "model": GEMINI_MODEL, "input": prompt, "tools":[{"type":"google_search"}],
        "response_format":{"type":"text","mime_type":"application/json","schema":sch}
    }, {"x-goog-api-key": GEMINI_API_KEY}, 180)
    candidates=[]
    def walk(x):
        if isinstance(x,str):
            s=x.strip()
            if (s.startswith("{") and s.endswith("}")) or (s.startswith("[") and s.endswith("]")): candidates.append(s)
        elif isinstance(x,dict):
            for v in x.values(): walk(v)
        elif isinstance(x,list):
            for v in x: walk(v)
    walk(resp)
    for s in candidates:
        try: return json.loads(s)
        except: pass
    raise ValueError("Gemini nevrátil platný JSON.")


def validate(c):
    try:
        p=float(c["current_price"]); lo=float(c["buy_zone_low"]); hi=float(c["buy_zone_high"]); inv=float(c["invalidation_price"]); tp=float(c["take_profit_1"])
        rr=(tp-((lo+hi)/2))/(((lo+hi)/2)-inv)
    except Exception:
        c["action"]="WAIT"; c["decision_now"]="WAIT – chýba platný risk plán."; return c
    c["rr_at_buy_zone"]=round(rr,2)
    if rr < 2 or inv >= (lo+hi)/2 or tp <= (lo+hi)/2:
        if c.get("action") in ("BUY NOW","BUY LIMIT"):
            c["action"]="WAIT"; c["decision_now"]="WAIT – vstup nespĺňa minimálne R:R 2:1."
    if c.get("action")=="BUY NOW" and not lo <= p <= hi:
        c["action"]="BUY LIMIT"; c["decision_now"]=f"BUY LIMIT – aktuálna cena je mimo BUY zóny {lo:.6g}–{hi:.6g}."
    return c


def prompt(data, fg, news, safe):
    return f'''Si profesionálny crypto portfolio analytik. Čas: {datetime.now(timezone.utc).astimezone(LOCAL_TZ).isoformat()}.
Použi Google Search na overenie aktuálnych fundamentálnych správ. Neuvádzaj neoverené tvrdenia.

HLAVNÁ ÚLOHA: používateľ chce jasnú akciu, nie všeobecný komentár.
Akcia musí byť jedna z: BUY NOW, BUY LIMIT, WAIT, HOLD, REDUCE NOW, TAKE PROFIT NOW, EXIT NOW, NO TRADE.
BUY NOW = kúpiť hneď na aktuálnej cene. BUY LIMIT = čakať na uvedenú BUY zónu. WAIT = zatiaľ nič nekupovať/predávať a uviesť podmienku, ktorá zmení rozhodnutie. HOLD = držať. REDUCE/TAKE PROFIT/EXIT = predaj podľa uvedeného rozhodnutia.

PRE KAŽDÝ COIN:
- opportunity_score = dlhší potenciál; execution_score = kvalita vstupu TERAZ.
- buy_zone a strong_buy_zone musia byť konkrétne cenové pásma.
- invalidation_price je hranica, pod ktorou je long setup neplatný.
- TP1/TP2 musia byť nad vstupom. Preferuj R:R >= 2:1.
- BUY NOW iba keď aktuálna cena je v BUY zóne a 4H podmienky podporujú vstup.
- Ak je coin kvalitný, ale stále padá, môže mať vysoký opportunity_score a nízky execution_score -> BUY LIMIT alebo WAIT.
- RSI pod 30 NIE JE samostatný buy signál.
- Pri poklese povedz, či je pravdepodobnejší OBRAT alebo POKRAČOVANIE poklesu.
- reversal_probability + continuation_probability musia byť 100 pre 24–72h aj 7–14d.
- turning_timeframe: napr. 24–72h, 3–7 dní, 1–2 týždne alebo "nie je potvrdený".
- Pravdepodobnosti sú odhady, nie istota.
- Rozlišuj skutočné 4H indikátory od 1D trendu.
- CoinGecko volume je iba volume-pressure proxy.
- sources: 1–4 reálne zdroje pre dôležité aktuálne fundamentálne tvrdenia.

MARKET SAFETY: {json.dumps(safe,ensure_ascii=False)}
FEAR & GREED: {json.dumps(fg,ensure_ascii=False)}
NEWS: {json.dumps(news,ensure_ascii=False)}
DATA: {json.dumps(data,ensure_ascii=False)}

PORTFÓLIO: AAVE, TAO, FET, SOL, ONDO, RENDER. BTC/ETH sú iba kontext.
Vyber maximálne jeden nový altcoin mimo portfólia. Ak nie je jasná výhoda, new_coin = NONE / NO TRADE. Nevyberaj BTC/ETH.

Ak MARKET SAFETY = CRITICAL, nové BUY/BUY LIMIT neodporúčaj.
Vráť iba JSON podľa schémy.'''


def choose_new_candidate(candidates):
    # Keep this deterministic: Gemini gets a shortlist and current market data.
    # It returns one symbol; technical confirmation happens in the main analysis.
    s = "Vyber maximálne 3 najzaujímavejšie altcoiny z tohto zoznamu. Ak nič, [] . Vráť iba JSON pole symbolov.\n" + json.dumps(candidates,ensure_ascii=False)
    try:
        x=gemini(s,{"type":"array","items":{"type":"string"}})
        return [str(v).upper() for v in x[:3] if isinstance(v,str)]
    except Exception:
        return []


def tg(text):
    return http_post_json(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", {"chat_id":TELEGRAM_CHAT_ID,"text":text,"disable_web_page_preview":True}, timeout=30)


def price(x):
    if x is None:return "—"
    x=float(x)
    if x>=1000:return f"${x:,.0f}"
    if x>=1:return f"${x:,.2f}"
    if x>=.1:return f"${x:.4f}"
    return f"${x:.6f}"


def pct(x): return "—" if x is None else f"{float(x):.0f}%"


def coin_text(c):
    return "\n".join([
        f"🪙 {c.get('symbol','?')} — {c.get('action','WAIT')}",
        f"👉 TERAZ: {c.get('decision_now','—')}",
        f"💰 Cena: {price(c.get('current_price'))}",
        f"🟢 BUY ZÓNA: {price(c.get('buy_zone_low'))} – {price(c.get('buy_zone_high'))}",
        f"🔥 STRONG BUY: {price(c.get('strong_buy_zone_low'))} – {price(c.get('strong_buy_zone_high'))}",
        f"🛑 INVALIDÁCIA: {price(c.get('invalidation_price'))}",
        f"🎯 TP1: {price(c.get('take_profit_1'))} | TP2: {price(c.get('take_profit_2'))} | R:R {float(c.get('rr_at_buy_zone',0)):.1f}:1",
        f"📊 Potenciál {c.get('opportunity_score',0):.0f}/100 | Vstup {c.get('execution_score',0):.0f}/100 | Istota {c.get('confidence',0):.0f}/100",
        f"🔄 24–72h: OBRAT {pct(c.get('reversal_probability_24_72h'))} | POKRAČOVANIE {pct(c.get('continuation_probability_24_72h'))}",
        f"🔄 7–14d: OBRAT {pct(c.get('reversal_probability_7_14d'))} | POKRAČOVANIE {pct(c.get('continuation_probability_7_14d'))}",
        f"⏱️ Očakávaný obrat: {c.get('turning_timeframe','—')}",
        f"📈 Technika: {c.get('technical_reason','—')}",
        f"🧠 Fundament: {c.get('fundamental_reason','—')}",
        f"⚠️ Riziko: {c.get('news_risk','—')}",
        ("🔴 Predaj: "+c.get('sell_reason','')) if c.get('sell_reason') else "",
        ("🔎 Zdroje: "+" | ".join(c.get('sources',[])[:4])) if c.get('sources') else ""
    ]).strip()


def report_text(r,s):
    now=datetime.now(timezone.utc).astimezone(LOCAL_TZ)
    out=["📊 CRYPTO AI — ROZHODOVACIA ANALÝZA",now.strftime("%d.%m.%Y %H:%M"),"",f"🌐 REŽIM: {r.get('market_regime','—')}",f"🛡️ MARKET SAFETY: {r.get('market_safety',s['state'])}",f"🧭 TRH: {r.get('market_action','—')}","", "BTC VÝHĽAD:",r.get('btc_outlook','—'),"",f"🔄 24–72h: OBRAT {pct(r.get('market_reversal_probability_24_72h'))} | POKRAČOVANIE {pct(r.get('market_continuation_probability_24_72h'))}",f"🔄 7–14d: OBRAT {pct(r.get('market_reversal_probability_7_14d'))} | POKRAČOVANIE {pct(r.get('market_continuation_probability_7_14d'))}",f"🧠 {r.get('market_probability_reason','—')}","", "🎯 HLAVNÝ ZÁVER:",r.get('summary','—'),""]
    for c in r.get('coins',[]): out += [coin_text(c),""]
    out += ["🆕 NOVÝ COIN",coin_text(r.get('new_coin',{'symbol':'NONE','action':'NO TRADE','decision_now':'Žiadny nový obchod.'}))]
    text="\n".join(out)
    if len(text)<=3900:return [text]
    chunks=[]; cur=""
    for p in text.split("\n\n"):
        if len(cur)+len(p)+2>3900: chunks.append(cur); cur=p
        else: cur += ("\n\n" if cur else "")+p
    if cur:chunks.append(cur)
    return chunks


def load_state():
    try:
        with open(STATE_FILE,encoding="utf-8") as f:return json.load(f)
    except:return {}


def save_state(s):
    with open(STATE_FILE,"w",encoding="utf-8") as f:json.dump(s,f,ensure_ascii=False,indent=2)


def slot(now):
    if MANUAL_ANALYSIS:return "MANUAL"
    candidates=[]
    # 07:00 and 20:00 Bratislava
    for h in (7,20):
        t=now.replace(hour=h,minute=0,second=0,microsecond=0)
        if 0 <= (now-t).total_seconds() < 900:candidates.append((t,f"LOCAL_{t:%Y-%m-%d}_{h:02d}"))
    # 15 minutes before US cash market open, DST-safe.
    ny=now.astimezone(NY_TZ)
    open_ny=ny.replace(hour=9,minute=30,second=0,microsecond=0)
    pre=open_ny-timedelta(minutes=15)
    if 0 <= (ny-pre).total_seconds() < 900:
        candidates.append((now,f"USOPEN_{ny:%Y-%m-%d}"))
    return candidates[0][1] if candidates else None


def main_analysis():
    safe=safety(); fg=fear_greed(); news=rss_news()
    data=[]
    for symbol,cid in {**MARKET,**PORTFOLIO}.items():
        data.append(coin_packet(symbol,cid)); time.sleep(.25)

    top=cg("/coins/markets",{"vs_currency":"usd","order":"market_cap_desc","per_page":100,"page":1,"sparkline":"false","price_change_percentage":"24h,7d"})
    held=set(PORTFOLIO.values())|set(MARKET.values())
    candidates=[{"id":x["id"],"symbol":x["symbol"].upper(),"name":x["name"],"price":x.get("current_price"),"market_cap":x.get("market_cap"),"volume_24h":x.get("total_volume"),"change_24h":x.get("price_change_percentage_24h_in_currency"),"change_7d":x.get("price_change_percentage_7d_in_currency")} for x in top if x["id"] not in held]
    candidates=sorted(candidates,key=lambda x:float(x.get("volume_24h") or 0),reverse=True)[:20]
    selected=choose_new_candidate(candidates)
    chosen=[x for x in candidates if x["symbol"] in selected][:2]
    new_packets=[]
    for x in chosen:
        try:new_packets.append(coin_packet(x["symbol"],x["id"]))
        except:pass
    payload={"market_context":data[:2],"portfolio":data[2:],"new_coin_candidates":new_packets}
    r=gemini(prompt(payload,fg,news,safe),schema())
    r["market_safety"]=safe["state"]
    for c in r.get("coins",[]):validate(c)
    validate(r.get("new_coin",{}))
    if safe["state"]=="CRITICAL":
        for c in r.get("coins",[]):
            if c.get("action") in ("BUY NOW","BUY LIMIT"):c["action"]="WAIT";c["decision_now"]="WAIT – MARKET SAFETY MODE (CRITICAL)."
        n=r.get("new_coin",{})
        if n.get("action") in ("BUY NOW","BUY LIMIT"):n["action"]="NO TRADE";n["decision_now"]="NO TRADE – MARKET SAFETY MODE (CRITICAL)."
    for m in report_text(r,safe):tg(m);time.sleep(.4)


def safety_monitor():
    s=safety(); st=load_state(); old=st.get("safety_state","NORMAL"); st["safety_state"]=s["state"]; save_state(st)
    rank={"NORMAL":0,"WARNING":1,"CRITICAL":2}
    if rank[s["state"]]>rank.get(old,0):
        tg(f"🚨 CRYPTO SAFETY ALERT — {s['state']}\nBTC 24h: {s['btc_24h_pct']:.2f}%\nPriemer portfólia 24h: {s['portfolio_avg_24h_pct']:.2f}%\nCoiny pod -5%: {s['coins_down_5pct_or_more']}\n⚠️ {s['note']}\n{'⛔ MARKET SAFETY MODE: žiadne nové BUY.' if s['state']=='CRITICAL' else '⚠️ Nové vstupy sprísniť.'}")


def run():
    if not GEMINI_API_KEY or not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:raise RuntimeError("Chýba GEMINI_API_KEY, TELEGRAM_TOKEN alebo TELEGRAM_CHAT_ID.")
    now=datetime.now(timezone.utc).astimezone(LOCAL_TZ); st=load_state(); sl=slot(now)
    if sl and st.get("main_analysis_slot")!=sl:
        main_analysis(); st["main_analysis_slot"]=sl; save_state(st)
    else:safety_monitor()

if __name__=="__main__":run()
