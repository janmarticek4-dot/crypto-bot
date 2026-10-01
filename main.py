import os
import json
import urllib.request
import urllib.parse
import google.generativeai as genai

# 1. NAČÍTANIE KĽÚČOV
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()

if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID or not GEMINI_API_KEY:
    print("CHYBA: Niektorý kľúč chýba v GitHub Secrets!")
    exit(1)

# 2. Stiahnutie Fear & Greed Indexu
try:
    fng_url = "https://api.alternative.me/fng/"
    req = urllib.request.urlopen(fng_url)
    fng_data = json.loads(req.read().decode())['data'][0]
    fng_value = fng_data['value']
    fng_class = fng_data['value_classification']
except Exception as e:
    fng_value = "74"
    fng_class = "Greed"

# 3. Stiahnutie dát z CoinGecko
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
    response = urllib.request.urlopen(req)
    market_data = json.loads(response.read().decode())
except Exception as e:
    market_data = []

crypto_summary_lines = []
for coin in market_data:
    symbol = coins_map.get(coin['id'], coin['symbol'].upper())
    price = coin.get('current_price', 0)
    change_24h = coin.get('price_change_percentage_24h', 0)
    market_cap = coin.get('market_cap', 0)
    ath = coin.get('ath', 0)
    crypto_summary_lines.append(f"- {symbol}: Cena: \({price:,.2f}, 24h zmena: {change_24h:+.2f}%, Market Cap:\){market_cap:,.0f}, ATH: ${ath:,.2f}")

market_context = "\n".join(crypto_summary_lines)

# 4. Prompt pre Gemini
prompt = f"""
Si špičkový kvantitatívny krypto analytik a portfólio manažér.
Trhový sentiment (Fear & Greed Index): {fng_value}/100 ({fng_class})
Aktuálne dáta mincí (vrátane Market Capu a vzťahu k ATH):
{market_context}

Priprav profesionálnu 6-hodinovú krypto analýzu pre môj Telegramový kanál. 
Zohľadni fundamenty a valuáciu pre každú mincu (BTC, ETH, SOL, TAO, FET, AAVE, RENDER, ONDO).
Uveď jasné odporúčanie a **konkrétne odporúčané percento aktuálnej pozície, ktoré sa má predať, dokúpiť alebo držať** (napr. „Predať 15% pozície“, „Dokúpiť 10%“, „Držať 100%“).
Naformátuj to pre Telegram (emoji, tučné písmo). Začni priamo správou.
"""

# 5. Volanie Gemini cez oficiálnu knižnicu (model gemini-2.0-flash)
ai_analysis = ""
try:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-2.0-flash')
    response = model.generate_content(prompt)
    ai_analysis = response.text
except Exception as e:
    print(f"Chyba pri generovaní cez Gemini SDK: {e}")
    ai_analysis = f"⚠️ Chyba Gemini SDK: {str(e)}"

# 6. Odoslanie do Telegramu
telegram_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
payload_telegram = urllib.parse.urlencode({
    "chat_id": TELEGRAM_CHAT_ID,
    "text": ai_analysis,
    "parse_mode": "Markdown"
}).encode("utf-8")

urllib.request.urlopen(telegram_url, data=payload_telegram)
print("Hotovo, správa odoslaná do Telegramu!")
