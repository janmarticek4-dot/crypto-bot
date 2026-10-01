import os
import json
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
import google.generativeai as genai

# 1. NAČÍTANIE KĽÚČOV
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()

if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID or not GEMINI_API_KEY:
    print("CHYBA: Kľúč chýba v GitHub Secrets!")
    exit(1)

# 2. Stiahnutie Fear & Greed Indexu
try:
    fng_url = "https://api.alternative.me/fng/"
    req = urllib.request.urlopen(fng_url, timeout=10)
    fng_data = json.loads(req.read().decode())['data'][0]
    fng_value = fng_data['value']
    fng_class = fng_data['value_classification']
except Exception as e:
    fng_value = "74"
    fng_class = "Greed"

# 3. Sťahovanie aktuálnych správ z trhu (RSS)
news_context = "Žiadne správy."
try:
    rss_url = "https://cointelegraph.com/rss"
    req = urllib.request.Request(rss_url, headers={'User-Agent': 'Mozilla/5.0'})
    response = urllib.request.urlopen(req, timeout=10)
    root = ET.fromstring(response.read())
    news_items = [item.find('text').text if item.find('text') is not None else item.find('title').text for item in root.findall('./channel/item')[:4]]
    news_context = " | ".join([n for n in news_items if n])
except Exception as e:
    print(f"Varovanie RSS: {e}")

# 4. Stiahnutie reálnych dát z CoinGecko
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

# 5. OKAMŽITÝ ALERT PRI POKLESE > 6%
if sudden_drops:
    for symbol, change, price in sudden_drops:
        alert_prompt = f"""
        🚨 KRITICKÝ POKLES: {symbol} padol o {change:.2f}% (${price:,.2f}).
        Sentiment: {fng_value}/100. Správy: {news_context}
        Napíš stručný výstražný alert pre Telegram: 1. Fundamentálny dôvod poklesu. 2. Pokyn (držat/predat celok alebo časť). 3. Predikcia dna a návratu rastu.
        """
        try:
            genai.configure(api_key=GEMINI_API_KEY)
            alert_res = genai.GenerativeModel('gemini-3.8-flash').generate_content(alert_prompt)
            send_telegram(f"🚨 **ALERT: {symbol}** 🚨\n\n{alert_res.text}")
        except Exception as e:
            print(f"Alert error: {e}")

# 6. STRUČNÁ A KOMPAKTNÁ HLAVNÁ ANALÝZA PRE VŠETKY MINCE
prompt = f"""
Si špičkový krypto portfólio manažér. Priprav STRUČNÚ a prehľadnú 6-hodinovú analýzu pre Telegram. Žiadne dlhé texty, píš vecně v bodoch.
Cieľ: Maximalizovať zisky v bull markete, realizovať zisky na vrchoch a dokupovať na dnách, sledovať rotáciu kapitálu.

Sentiment: {fng_value}/100 ({fng_class}) | Správy: {news_context}
Dáta trhu:
{market_context}

Požiadavky na štruktúru:
1. **Makro & Rotácia:** 2 vety o fáze trhu a kam smeruje kapitál (altcoiny vs BTC vs iné/hotovosť).
2. **Pre KAŽDÚ z 8 mincí (BTC, ETH, SOL, TAO, FET, AAVE, RENDER, ONDO)** použi tento ultrakrátky formát:
   - **[SYMBOL]** | Prognóza: [rast +X% / pokles -X% / range X%]
     - **Fundament/Tech:** [1 stručná veta]
     - **Exekúcia:** [DRŽAŤ do \(X / DOKÚPIŤ [X]% za Market alebo Limitku na\)X / PREDAŤ [X]% na Take-Profit \(X, potom limitka na odkúpenie na\)X (alebo nedokupovať)].

Začni priamo správou, dodrž stručnosť a pokry všetkých 8 mincí!
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
print("Hotovo!")
