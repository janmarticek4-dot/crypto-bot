import os
import json
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime
from zoneinfo import ZoneInfo
import google.generativeai as genai

# 1. NAČÍTANIE KĽÚČOV
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()

if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID or not GEMINI_API_KEY:
    print("CHYBA: Niektorý kľúč chýba v GitHub Secrets!")
    exit(1)

# 2. KONTROLA ČASU A NOČNÉHO KLUDU (23:00 - 08:00)
local_now = datetime.now(ZoneInfo("Europe/Bratislava"))
local_hour = local_now.hour

if 23 <= local_hour or local_hour < 8:
    print(f"Aktuálna lokálna hodina je {local_hour}:00. V čase nočného kľudu (23:00 - 08:00) sa správy neposielajú.")
    exit(0)

# 3. Stiahnutie Fear & Greed Indexu
try:
    fng_url = "https://api.alternative.me/fng/"
    req = urllib.request.urlopen(fng_url, timeout=10)
    fng_data = json.loads(req.read().decode())['data'][0]
    fng_value = fng_data['value']
    fng_class = fng_data['value_classification']
except Exception as e:
    fng_value = "74"
    fng_class = "Greed"

# 4. Sťahovanie aktuálnych správ a vyhlásení z trhu (RSS)
news_context = "Žiadne aktuálne správy k dispozícii."
try:
    rss_url = "https://cointelegraph.com/rss"
    req = urllib.request.Request(rss_url, headers={'User-Agent': 'Mozilla/5.0'})
    response = urllib.request.urlopen(req, timeout=10)
    xml_data = response.read()
    
    root = ET.fromstring(xml_data)
    news_items = []
    for item in root.findall('./channel/item')[:5]:
        title = item.find('title').text if item.find('title') is not None else ""
        if title:
            news_items.append(f"- {title}")
    if news_items:
        news_context = "\n".join(news_items)
except Exception as e:
    print(f"Varovanie pri sťahovaní správ: {e}")

# 5. Stiahnutie dát z CoinGecko
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

# 6. KONTROLA NÚDZOVÉHO POKLESU (> 6% za 24h u ktorejkoľvek mince)
emergency_coins = []
for coin in market_data:
    change_24h = coin.get('price_change_percentage_24h', 0)
    if change_24h < -6.0:
        emergency_coins.append(coin)

ai_message = ""

if emergency_coins:
    # Generovanie núdzového alertu
    emergency_context = "\n".join([f"- {coins_map.get(c['id'], c['symbol'].upper())}: Cena \({c.get('current_price', 0):,.2f}, 24h zmena: {c.get('price_change_percentage_24h', 0):+.2f}% (ATH:\){c.get('ath', 0):,.2f})" for c in emergency_coins])
    
    prompt = f"""
    🚨 KRITICKÝ POKLES KRYPTOMENY! 🚨
    Nasledujúce aktíva zaznamenali za posledných 24 hodín prudký prepad o viac ako 6%:
    {emergency_context}

    Najnovšie správy z trhu:
    {news_context}

    Priprav okamžitú núdzovú alert správu pre môj Telegramový kanál. 
    Požiadavky:
    1. Jasne uveď, ktorá kryptomena prudko klesá a aký je jej aktuálny 24h prepad.
    2. Vysvetli dôvod, prečo klesá (na základe správ a trhových fundamentov).
    3. Odhadni, aký ďalší pokles sa u nej očakáva.
    4. Daj okamžitý exekučný pokyn: či držať, alebo ihneď predať, a presne koľko percent z pozície (alebo celú pozíciu).
    
    Píš stručne, urgentne, s emoji a začni priamo správou.
    """
else:
    # Kontrola, či je čas na pravidelnú 4-hodinovú analýzu (8:00, 12:00, 16:00, 20:00)
    if local_hour not in [8, 12, 16, 20]:
        print(f"Hodina {local_hour}:00 nie je časom pre pravidelnú analýzu (beh každé 4 hodiny od 08:00) a nenastal ani núdzový pokles. Končíme.")
        exit(0)

    crypto_summary_lines = []
    for coin in market_data:
        symbol = coins_map.get(coin['id'], coin['symbol'].upper())
        price = coin.get('current_price', 0)
        change_24h = coin.get('price_change_percentage_24h', 0)
        market_cap = coin.get('market_cap', 0)
        ath = coin.get('ath', 0)
        crypto_summary_lines.append(f"- {symbol}: Aktuálna cena: \({price:,.2f} | 24h zmena: {change_24h:+.2f}% | Market Cap:\){market_cap:,.0f} | ATH: ${ath:,.2f}")

    market_context = "\n".join(crypto_summary_lines)

    # Pravidelný pokročilý prompt
    prompt = f"""
    Si špičkový kvantitatívny krypto analytik, portfólio manažér a makroekonóm.
    Investičná stratégia: Maximalizovať rast v bull markete, realizovať zisky na vrchoch pred blížiacimi sa korekciami, lacno dokupovať na lokálnych dnách, prípadne ukončiť obchody pri prechode do bear marketu. Sleduje sa rotácia kapitálu (altcoiny <-> BTC <-> externé aktíva).

    Trhový sentiment (Fear & Greed Index): {fng_value}/100 ({fng_class})

    Kľúčové správy a vyhlásenia z trhu:
    {news_context}

    Aktuálne trhové dáta mincí:
    {market_context}

    Priprav profesionálnu 4-hodinovú krypto analýzu pre Telegram s touto štruktúrou:
    1. **Makro výhľad & Rotácia kapitálu:** Zhodnotenie trhovej fázy (bull market vs. riziko korekcie/bear marketu). Sleduj prelievanie kapitálu (altcoiny vs BTC) a ak hrozí odliv inam, uveď presne, kam a do ktorých kryptomien presunúť kapitál.
    2. **Exekučné pokyny pre každú mincu (BTC, ETH, SOL, TAO, FET, AAVE, RENDER, ONDO):**
       - **Analýza & Fundament:** Vplyv správ a stavu trhu.
       - **Exekúcia:** 
         - Ak realizujeme zisk na vrchole (Take-Profit): **PREDAŤ [X]% z pozície** (Market / Take-Profit na cene $X). **Zároveň uveď reálnu limitnú cenu na silnom blízkom supporte pre spätný odkup po korekcii.**
         - Ak využívame lokálne dno/dip na nákup: **DOKÚPIŤ [X]% z investície** (Market / Limitná objednávka na reálnej a dosiahnutej hladine $X).
         - Ak držíme v bull markete: **DRŽAŤ 100% pozície**.
         - Ak sa končí cyklus / bear market: **Ukončiť obchod / Predať 100%**.

    Píš vecne, úderne, s emoji a začni priamo správou.
    """

# 7. Volanie Gemini cez oficiálne SDK
try:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-3.8-flash')
    response = model.generate_content(prompt)
    ai_message = response.text
except Exception as e:
    error_str = str(e)
    ai_message = f"⚠️ Chyba Gemini: {error_str[:150]}"

# Poistka proti prekročeniu dĺžky správy pre Telegram
if len(ai_message) > 4000:
    ai_message = ai_message[:3950] + "\n\n... (správa bola skrátená)"

# 8. Odoslanie do Telegramu
telegram_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
payload_telegram = urllib.parse.urlencode({
    "chat_id": TELEGRAM_CHAT_ID,
    "text": ai_message
}).encode("utf-8")

try:
    urllib.request.urlopen(telegram_url, data=payload_telegram, timeout=10)
    print("Hotovo, správa úspešne odoslaná do Telegramu!")
except urllib.error.HTTPError as e:
    error_body = e.read().decode()
    print(f"Telegram HTTP Error: {e.code} - {error_body}")
    raise e
