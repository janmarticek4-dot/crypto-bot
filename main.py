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
    print("CHYBA: Niektorý kľúč chýba v GitHub Secrets!")
    exit(1)

# 2. Stiahnutie Fear & Greed Indexu
try:
    fng_url = "https://api.alternative.me/fng/"
    req = urllib.request.urlopen(fng_url, timeout=10)
    fng_data = json.loads(req.read().decode())['data'][0]
    fng_value = fng_data['value']
    fng_class = fng_data['value_classification']
except Exception as e:
    print(f"Varovanie FNG: {e}")
    fng_value = "74"
    fng_class = "Greed"

# 3. Sťahovanie aktuálnych správy a oznámení z trhu (RSS)
news_context = "Žiadne aktuálne správy k dispozícii."
try:
    rss_url = "https://cointelegraph.com/rss"
    req = urllib.request.Request(rss_url, headers={'User-Agent': 'Mozilla/5.0'})
    response = urllib.request.urlopen(req, timeout=10)
    xml_data = response.read()
    
    root = ET.fromstring(xml_data)
    news_items = []
    for item in root.findall('./channel/item')[:8]: # Top 8 najnovších správ
        title = item.find('title').text if item.find('title') is not None else ""
        if title:
            news_items.append(f"- {title}")
    if news_items:
        news_context = "\n".join(news_items)
except Exception as e:
    print(f"Varovanie pri sťahovaní správ: {e}")

# 4. Stiahnutie dát z CoinGecko
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
    print(f"Varovanie CoinGecko: {e}")
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

# 5. Pokročilý prompt zahŕňajúci fundamenty a živé správy
prompt = f"""
Si špičkový kvantitatívny krypto analytik, portfólio manažér a makroekonóm.
Trhový sentiment (Fear & Greed Index): {fng_value}/100 ({fng_class})

Najnovšie správy, udalosti a vyhlásenia z krypto trhu:
{news_context}

Aktuálne kvantitatívne dáta sledovaných mincí (vrátane Market Capu a vzťahu k ATH):
{market_context}

Priprav profesionálnu a hĺbkovú krypto analýzu pre môj Telegramový kanál. 
Požiadavky na analýzu:
1. Zohľadni nielen aktuálne cenové pohyby a sentiment, ale predovšetkým **silné fundamenty každého projektu** (BTC, ETH, SOL, TAO, FET, AAVE, RENDER, ONDO) – ich technologický pokrok, ekosystém, reálne využitie, tokenomiku a vplyv najnovších správ z trhu.
2. Pre každú mincu vecne prepoj fundamentálnu hodnotu s aktuálnou trhovou situáciou.
3. Uveď jasné investičné odporúčanie a **konkrétne odporúčané percento aktuálnej pozície, ktoré sa má predať, dokúpiť alebo držať** (napr. „Predať 15% pozície“, „Dokúpiť 10%“, „Držať 100%“).
4. Naformátuj to prehľadne pre Telegram (použi emoji a štruktúrovaný text). Začni priamo správou.
"""

# 6. Volanie Gemini cez oficiálne SDK
ai_analysis = ""
try:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-3.8-flash')
    response = model.generate_content(prompt)
    ai_analysis = response.text
except Exception as e:
    error_str = str(e)
    print(f"Chyba Gemini: {error_str}")
    ai_analysis = f"⚠️️ Chyba Gemini: {error_str[:150]}"

# 7. Odoslanie do Telegramu
telegram_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
payload_telegram = urllib.parse.urlencode({
    "chat_id": TELEGRAM_CHAT_ID,
    "text": ai_analysis
}).encode("utf-8")

try:
    urllib.request.urlopen(telegram_url, data=payload_telegram, timeout=10)
    print("Hotovo, správa s fundamentmi a správami úspešne odoslaná do Telegramu!")
except urllib.error.HTTPError as e:
    error_body = e.read().decode()
    print(f"Telegram HTTP Error: {e.code} - {error_body}")
    raise e
