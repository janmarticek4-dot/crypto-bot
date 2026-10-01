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

# 3. Sťahovanie správ z viacerých svetových zdrojov (vrátane politiky a Trumpových vyhlásení)
news_items = []
rss_urls = [
    "https://cointelegraph.com/rss",
    "https://www.coindesk.com/arc/outboundfeeds/rss/"
]

for rss_url in rss_urls:
    try:
        req = urllib.request.Request(rss_url, headers={'User-Agent': 'Mozilla/5.0'})
        response = urllib.request.urlopen(req, timeout=8)
        root = ET.fromstring(response.read())
        for item in root.findall('./channel/item')[:3]:
            title = item.find('title').text if item.find('title') is not None else ""
            if title:
                news_items.append(title)
    except Exception as e:
        print(f"Varovanie RSS ({rss_url}): {e}")

news_context = " | ".join(news_items) if news_items else "Žiadne čerstvé správy."

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
    
    crypto_summary_lines.append(f"- {symbol} (Aktuálna cena: \({price:,.2f}): 24h zmena: {change_24h:+.2f}%, MC:\){market_cap:,.0f}, ATH: ${ath:,.2f}")
    
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
        Sentiment: {fng_value}/100. Aktuálne správy a vyhlásenia z trhu/politiky: {news_context}
        Napíš stručný výstražný alert pre Telegram: 1. Fundamentálny/politický dôvod poklesu. 2. Pokyn (držat/predat celok alebo časť). 3. Predikcia dna a návratu rastu.
        """
        try:
            genai.configure(api_key=GEMINI_API_KEY)
            alert_res = genai.GenerativeModel('gemini-3.8-flash').generate_content(alert_prompt)
            send_telegram(f"🚨 **ALERT: {symbol}** 🚨\n\n{alert_res.text}")
        except Exception as e:
            print(f"Alert error: {e}")

# 6. 4H ANALÝZA ZAHŔŇAJÚCA POLITICKÉ VPLYVY (TRUMP/MAKRO), AKTUÁLNE CENY A POKYNY
prompt = f"""
Si špičkový krypto portfólio manažér a makroekonóm. Priprav STRUČNÚ a prehľadnú **4-hodinovú analýzu** pre Telegram. Píš vecne v bodoch.
Cieľ: Maximalizovať zisky v bull markete, realizovať zisky na vrchoch a dokupovať na dnách. Sleduj politické vplyvy, vyhlásenia (napr. Donald Trump) a makro správy.

Sentiment: {fng_value}/100 ({fng_class}) | Čerstvé správy, vyhlásenia a makro/politické pozadia:
{news_context}

Dáta trhu (vrátane reálnych cien):
{market_context}

Požiadavky na štruktúru:
1. **Makro & Rotácia:** 2 vety o fáze trhu, vplyve aktuálnych politických/makro vyhlásení (napr. Trump/regulácie) a kam smeruje kapitál (v nadpise použi explicitne 4H analýza).
2. **Pre KAŽDÚ z 8 mincí (BTC, ETH, SOL, TAO, FET, AAVE, RENDER, ONDO)** dodrž tento presný formát:
   - **[SYMBOL] (Aktuálna cena: $X)** | Prognóza: [rast +X% / pokles -X% / range X%] (Časový horizont: napr. *najbližších 24-48 hodín*)
     - **Fundament/Tech:** [1 stručná veta s prihliadnutím na aktuálne správy/politiku]
     - **Exekúcia:** 
       - Ak je pokyn **DRŽAŤ**: Uveď **DRŽAŤ 100% pozície do cieľovej ceny $X** a definuj, čo spraviť po jej dosiahnutí (napr. *PREDAŤ [Y]%* alebo držať ďalej).
       - Ak je pokyn na predaj: Uveď **PREDAŤ [X]% na Take-Profit \(X** + následná limitka na odkúpenie na\)Y.
       - Ak je pokyn na nákup: Uveď **DOKÚPIŤ [X]% na Limitku $Y**.

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
print("Hotovo, 4h analýza s makro/politickým kontextom úspešne odoslaná!")
