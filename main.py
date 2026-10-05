import os
import json
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime
import google.generativeai as genai

# 1. NAČÍTANIE KĽÚČOV
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()

if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID or not GEMINI_API_KEY:
    print("CHYBA: Kľúč chýba v GitHub Secrets!")
    exit(1)

# 2. Aktuálny čas
current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")

# 3. Stiahnutie Fear & Greed Indexu
try:
    fng_url = "https://api.alternative.me/fng/"
    req = urllib.request.urlopen(fng_url, timeout=10)
    fng_data = json.loads(req.read().decode())['data'][0]
    fng_value = fng_data['value']
    fng_class = fng_data['value_classification']
except Exception as e:
    fng_value = "UNKNOWN"
    fng_class = "UNKNOWN"

# 4. Sťahovanie aktuálnych správ z trhu (RSS)
news_context = "Žiadne overené správy."
try:
    rss_url = "https://cointelegraph.com/rss"
    req = urllib.request.Request(rss_url, headers={'User-Agent': 'Mozilla/5.0'})
    response = urllib.request.urlopen(req, timeout=10)
    root = ET.fromstring(response.read())
    news_items = []
    for item in root.findall('./channel/item')[:5]:
        title = item.find('title').text if item.find('title') is not None else ""
        if title:
            news_items.append(title)
    if news_items:
        news_context = " | ".join(news_items)
except Exception as e:
    print(f"Varovanie RSS: {e}")

# 5. Stiahnutie reálnych dát z CoinGecko
coins_map = {
    "bitcoin": "BTC",
    "ethereum": "ETH",
    "solana": "SOL",
    "bittensor": "TAO",
    "fetch-ai": "FET",
    "aave": "AAVE",
    "render-token": "RENDER",
    "ondo-finance": "ONDO"
}

coin_ids = ",".join(coins_map.keys())
cg_url = f"https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&ids={coin_ids}&order=market_cap_desc"

try:
    req = urllib.request.Request(cg_url, headers={'User-Agent': 'Mozilla/5.0'})
    response = urllib.request.urlopen(req, timeout=10)
    market_data = json.loads(response.read().decode())
except Exception as e:
    market_data = []

sudden_drops = []
crypto_summary_lines = []

for coin in market_data:
    symbol = coins_map.get(coin['id'], coin['symbol'].upper())
    price = coin.get('current_price', 0)
    change_24h = coin.get('price_change_percentage_24h', 0)
    market_cap = coin.get('market_cap', 0)
    ath = coin.get('ath', 0)
    
    crypto_summary_lines.append(f"- {symbol}: \({price:,.2f} (24h: {change_24h:+.2f}%, MC:\){market_cap:,.0f}, ATH: ${ath:,.2f})")
    
    if change_24h < -6.0:
        sudden_drops.append((symbol, change_24h, price))

market_context = "\n".join(crypto_summary_lines)

def send_telegram(text):
    telegram_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = urllib.parse.urlencode({"chat_id": TELEGRAM_CHAT_ID, "text": text}).encode("utf-8")
    try:
        urllib.request.urlopen(telegram_url, data=payload, timeout=10)
    except Exception as e:
        print(f"Chyba Telegram: {e}")

# 6. OKAMŽITÝ ALERT PRI POKLESE > 6%
if sudden_drops:
    for symbol, change, price in sudden_drops:
        alert_prompt = f"""
        Si prísny kvantitatívny AI analytik.
        🚨 KRITICKÝ POKLES: {symbol} padol o {change:.2f}% (${price:,.2f}).
        Napíš stručný výstražný alert pre Telegram podľa pravidiel dátovej prísnosti. 
        1. Fundamentálny dôvod poklesu (ak nemáš dáta, uveď UNKNOWN, nehalucinuj veľryby ani inštitúcie).
        2. Pokyn (držat/predat). Ak je R:R < 2:1 alebo chýbajú dáta, daj pokyn NO TRADE / HOLD.
        3. Support a predikcia zotavenia.
        """
        try:
            genai.configure(api_key=GEMINI_API_KEY)
            alert_res = genai.GenerativeModel('gemini-3.8-flash').generate_content(alert_prompt)
            send_telegram(f"🚨 **ALERT: {symbol}** 🚨\n\n{alert_res.text}")
        except Exception as e:
            print(f"Alert error: {e}")

# 7. HLAVNÝ KVANTITATÍVNY 4H PROMPT
prompt = f"""
ROLE: Si pokročilý AI analytik kryptomenového trhu. Tvojou úlohou nie je vytvárať optimistické predikcie, ale objektívne vyhodnocovať pravdepodobnosť rastu alebo poklesu a vytvárať obchodné rozhodnutia založené na dátach.
Používateľ preferuje agresívnejší rastový štýl, ale nechce realizovať zbytočné straty. Horizont je krátkodobý/strednodobý trading a držanie kvalitných altcoinov v bull markete.

HLAVNÉ PRAVIDLO: NIKDY nevymýšľaj dáta. Ak nemáš údaj, označ ho UNKNOWN. Nikdy nepoužívaj "inštitúcie nakupujú" alebo "whales akumulujú" bez tvrdých dát. 

DATA AS OF: {current_time}
SENTIMENT (F&G): {fng_value}/100 ({fng_class})
NEWS CONTEXT: {news_context}
MARKET DATA: 
{market_context}

APLIKUJ TIETO LOGICKÉ KROKY:
1. Vyhodnoť MACRO SCORE (0-100) a BTC MARKET REGIME.
2. ALTCOIN ROTATION: Zhodnoť kam reálne tečie kapitál z 8 sledovaných mincí (BTC, ETH, SOL, TAO, FET, AAVE, RENDER, ONDO).
3. SCORING MODEL (Macro 20%, BTC Regime 15%, Tech 25%, Fundament 20%, Onchain 10%, Tokenomics 5%, Sentiment 5%) pre každú mincu.
4. CONFIDENCE SCORE (0-100%). Zníž ju, ak si indikátory odporujú alebo chýbajú dáta.
5. SCENÁRE (Bull/Base/Bear % pravdepodobnosť).
6. RISK/REWARD: Entry, Stop, TP1, TP2, TP3. Ak R:R < 2:1, použi príkaz NO TRADE.
7. ANTI-HALLUCINATION CHECK: Zosúlaď matematiku. Predikcia sa musí logicky rovnať cieľovej cene. NIKDY nenavrhuj dokúpiť 20% bez dôvodu, zohľadni voľný kapitál používateľa.

VÝSTUP DO TELEGRAMU MUSÍ BYŤ STRUČNÝ, DÁTOVÝ A PRESNE V TOMTO FORMÁTE:

📊 CRYPTO MARKET UPDATE (4H)
🕐 Data: {current_time}

🌍 MACRO Score: [XX]/100 | Bias: [BULLISH/NEUTRAL/BEARISH] | Hotovosť: [Šetriť / Nasadiť]
₿ BTC Price: [Aktuálna cena] | Regime: [Režim] | Score: [XX]/100
Bull: [X-X] | Base: [X-X] | Bear: [X-X]
⚡ ROTÁCIA: [Leading sectors] | [Weak sectors]

🔥 PORTFÓLIO: 8 SLEDOVANÝCH MINCÍ
(Pre každú z mincí BTC, ETH, SOL, TAO, FET, AAVE, RENDER, ONDO v tomto formáte)

- **[SYMBOL]** ([Cena]) — [XX]/100 | Bias: [BUY / HOLD / REDUCE / NO TRADE] | Conf: [XX]%
  - Scenár: Bull [X%] Base [X%] Bear [X%]
  - Exekúcia: [Presný pokyn na držanie/nákup/predaj so 100% zosúladenými cenovými hladinami s tvojou predikciou. Ak nákup, uveď ENTRY X, STOP X, TP1 X. Ak sa to neoplatí, napíš NO TRADE a len držať do X].
  - R:R: [X:X] | Dôvod: [1 stručná dátová veta]

🧠 FINAL VERDICT
Market bias: [..] | Best opportunity: [..] | Biggest risk: [..]
"""

ai_analysis = ""
try:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-3.8-flash')
    response = model.generate_content(prompt)
    ai_analysis = response.text
except Exception as e:
    ai_analysis = f"⚠️ Chyba AI: {str(e)[:150]}"

if len(ai_analysis) > 4000:
    ai_analysis = ai_analysis[:3950] + "\n\n... (skrátené)"

send_telegram(ai_analysis)
print("Hotovo, kvantitatívna 4h analýza úspešne odoslaná!")
