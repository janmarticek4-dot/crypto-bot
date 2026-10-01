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

# 3. Stiahnutie reálnych dát z CoinGecko (zodpovedá cenám na eToro)
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

crypto_summary_lines = []
for coin in market_data:
    symbol = coins_map.get(coin['id'], coin['symbol'].upper())
    price = coin.get('current_price', 0)
    change_24h = coin.get('price_change_percentage_24h', 0)
    market_cap = coin.get('market_cap', 0)
    ath = coin.get('ath', 0)
    crypto_summary_lines.append(f"- {symbol}: Aktuálna cena: \({price:,.2f} | 24h zmena: {change_24h:+.2f}% | Market Cap:\){market_cap:,.0f} | ATH: ${ath:,.2f}")

market_context = "\n".join(crypto_summary_lines)

# 4. Efektívny a presný prompt pre exekučné pokyny
prompt = f"""
Si špičkový krypto analytik a portfólio manažér.
Trhový sentiment: {fng_value}/100 ({fng_class})

Aktuálne trhové dáta mincí:
{market_context}

Priprav prehľadnú a údernú krypto analýzu pre Telegram. 
Pre každú mincu (BTC, ETH, SOL, TAO, FET, AAVE, RENDER, ONDO) uveď:
1. **Fundament / Stav:** Stručný dôvod.
2. **Exekúcia:** Presný príkaz:
   - **DOKÚPIŤ [X]% z investície** (uveď či Market za aktuálnu cenu, alebo Limitná objednávka na presnej cene $X)
   - **PREDAŤ [X]% z pozície** (uveď či Market, alebo Take-Profit / Stop-Loss na presnej cene $X)
   - **DRŽAŤ 100% pozície**

Píš prehľadne, s emoji a začni priamo správou.
"""

# 5. Volanie Gemini cez oficiálne SDK
ai_analysis = ""
try:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-3.8-flash')
    response = model.generate_content(prompt)
    ai_analysis = response.text
except Exception as e:
    error_str = str(e)
    ai_analysis = f"⚠️️ Chyba Gemini: {error_str[:150]}"

# Poistka proti prekročeniu dĺžky správy
if len(ai_analysis) > 4000:
    ai_analysis = ai_analysis[:3950] + "\n\n... (analýza bola skrátená)"

# 6. Odoslanie do Telegramu
telegram_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
payload_telegram = urllib.parse.urlencode({
    "chat_id": TELEGRAM_CHAT_ID,
    "text": ai_analysis
}).encode("utf-8")

try:
    urllib.request.urlopen(telegram_url, data=payload_telegram, timeout=10)
    print("Hotovo, správa úspešne odoslaná do Telegramu!")
except urllib.error.HTTPError as e:
    error_body = e.read().decode()
    print(f"Telegram HTTP Error: {e.code} - {error_body}")
    raise e
