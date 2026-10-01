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

# 3. Sťahovanie aktuálnych správ a vyhlásení z trhu (RSS)
news_context = "Žiadne aktuálne správy k dispozícii."
try:
    rss_url = "https://cointelegraph.com/rss"
    req = urllib.request.Request(rss_url, headers={'User-Agent': 'Mozilla/5.0'})
    response = urllib.request.urlopen(req, timeout=10)
    xml_data = response.read()
    
    root = ET.fromstring(xml_data)
    news_items = []
    for item in root.findall('./channel/item')[:6]:
        title = item.find('title').text if item.find('title') is not None else ""
        if title:
            news_items.append(f"- {title}")
    if news_items:
        news_context = "\n".join(news_items)
except Exception as e:
    print(f"Varovanie pri sťahovaní správ: {e}")

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

# Kontrola okamžitých alertov (pokles > 6% za 24h)
sudden_drops = []
crypto_summary_lines = []

for coin in market_data:
    symbol = coins_map.get(coin['id'], coin['symbol'].upper())
    price = coin.get('current_price', 0)
    change_24h = coin.get('price_change_percentage_24h', 0)
    market_cap = coin.get('market_cap', 0)
    ath = coin.get('ath', 0)
    
    crypto_summary_lines.append(f"- {symbol}: Cena: \({price:,.2f} | 24h zmena: {change_24h:+.2f}% | Market Cap:\){market_cap:,.0f} | ATH: ${ath:,.2f}")
    
    if change_24h < -6.0:
        sudden_drops.append((symbol, change_24h, price))

market_context = "\n".join(crypto_summary_lines)

def send_telegram(text):
    telegram_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = urllib.parse.urlencode({"chat_id": TELEGRAM_CHAT_ID, "text": text}).encode("utf-8")
    try:
        urllib.request.urlopen(telegram_url, data=payload, timeout=10)
    except Exception as e:
        print(f"Chyba pri odosielaní do Telegramu: {e}")

# 5. AK EXISTUJE NÁHLY POKLES > 6%, POŠLI OKAMŽITÝ ALERT
if sudden_drops:
    for symbol, change, price in sudden_drops:
        alert_prompt = f"""
        🚨 KRITICKÝ POKLES: Minca {symbol} zaznamenala za posledných 24 hodín prepad o {change:.2f}% (Aktuálna cena: ${price:,.2f}).
        Trhový sentiment: {fng_value}/100 ({fng_class})
        Správy z trhu: {news_context}

        Priprav okamžitý varovný alert pre Telegram:
        1. **Fundamentálna analýza dôvodu** tohto prudkého poklesu.
        2. **Konkrétny pokyn:** Či držať alebo predávať (celú pozíciu alebo len časť).
        3. **Predikcia:** Pravdepodobnosť ďalšieho poklesu, cieľová hodnota (support), kde sa pokles zastaví a odkedy sa očakáva obnovenie rastu.
        Píš stručne, dôrazne a s emoji.
        """
        try:
            genai.configure(api_key=GEMINI_API_KEY)
            alert_model = genai.GenerativeModel('gemini-3.8-flash')
            alert_res = alert_model.generate_content(alert_prompt)
            send_telegram(f"🚨 **MOMENTÁLNY ALERT PRE TRH** 🚨\n\n{alert_res.text}")
        except Exception as e:
            print(f"Chyba pri generovaní alertu: {e}")

# 6. HLAVNÁ KOMPLEXNÁ ANALÝZA PODĽA STRATÉGIE CYKLU A ROTÁCIE
prompt = f"""
Si špičkový kvantitatívny krypto analytik, portfólio manažér a makroekonóm.
INVESTIČNÁ STRATÉGIA: 
- Maximalizovať rast v bull markete. Realizovať zisky na vrchoch pred lokálnymi korekciami a lacno dokupovať na dnách. 
- Pri prechode do bear marketu obchody úplne ukončiť na ochranu kapitálu.
- Sledovať rotáciu kapitálu (altcoiny <-> BTC <-> iné kryptomeny alebo prechod do hotovosti/mimo krypto).

Trhový sentiment: {fng_value}/100 ({fng_class})
Najnovšie správy z trhu: {news_context}
Trhové dáta mincí: {market_context}

Priprav profesionálnu krypto analýzu pre Telegram v tejto štruktúre:
1. **Makro výhľad, Fáza cyklu & Rotácia kapitálu:** Zhodnoť, či sme v silnom bull markete alebo hrozí korekcia/bear market. Sleduj prelievanie kapitálu (altcoiny vs BTC). Ak kapitál odlieta inam, uveď presne, do ktorej konkrétnej kryptomeny ho preinvestovať, prípadne odporuč neinvestovať do krypto a držať hotovosť.
2. **Hĺbková analýza a exekúcia pre každú mincu (BTC, ETH, SOL, TAO, FET, AAVE, RENDER, ONDO):**
   - **Očakávanie v %:** Odhadovaný pohyb v najbližšom období (napr. rast +10%, pokles -4%, konsolidácia/range).
   - **Fundament & Technika:** Prepojenie reálneho fundamentu projektu s technickým kontextom.
   - **Presný exekučný pokyn:**
     - **PREDAŤ [X]% z pozície** (pri realizácii ziskov na vrchole – uveď či Market, alebo Take-Profit na cene \(X) + **Následná limitka na odkúpenie** na spodnej hladine\)X (alebo uveď, že po predaji nedokupujeme).
     - **DOKÚPIŤ [X]% z investície** (pri lokálnom dne – uveď či Market, alebo Limitná objednávka na cene $X).
     - **DRŽAŤ 100% pozície** (v zdravej fáze bull marketu).
     - **Ukončiť obchod / Predať 100%** (pri nástupe bear marketu).

Píš prehľadne, odborne, s emoji a začni priamo správom.
"""

ai_analysis = ""
try:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-3.8-flash')
    response = model.generate_content(prompt)
    ai_analysis = response.text
except Exception as e:
    error_str = str(e)
    ai_analysis = f"⚠️ Chyba Gemini: {error_str[:150]}"

# Poistka proti prekročeniu dĺžky správy pre Telegram (max 4096 znakov)
if len(ai_analysis) > 4000:
    ai_analysis = ai_analysis[:3950] + "\n\n... (analýza bola skrátená pre limit správy)"

# 7. Odoslanie hlavnej analýzy do Telegramu
send_telegram(ai_analysis)
print("Hotovo, analýza bola úspešne spracovaná a odoslaná!")
