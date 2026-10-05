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

current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")

# 2. NAČÍTANIE PREDCHÁDZAJÚCEJ ANALÝZY (PAMÄŤ BOTA)
memory_file = "last_analysis.txt"
try:
    with open(memory_file, "r", encoding="utf-8") as f:
        previous_analysis = f.read()
except FileNotFoundError:
    previous_analysis = "Žiadna predchádzajúca analýza. Toto je prvý beh."

# 3. GLOBÁLNE MAKRO DÁTA A FEAR & GREED
try:
    global_url = "https://api.coingecko.com/api/v3/global"
    req = urllib.request.Request(global_url, headers={'User-Agent': 'Mozilla/5.0'})
    global_data = json.loads(urllib.request.urlopen(req, timeout=10).read().decode())['data']
    total_mcap = global_data['total_market_cap'].get('usd', 0)
    btc_dom = global_data['market_cap_percentage'].get('btc', 0)
    macro_context = f"Total Market Cap: ${total_mcap:,.0f} | BTC Dominance: {btc_dom:.2f}%"
except:
    macro_context = "Makro dáta nedostupné."

try:
    fng_url = "https://api.alternative.me/fng/"
    fng_data = json.loads(urllib.request.urlopen(fng_url, timeout=10).read().decode())['data'][0]
    fng_context = f"{fng_data['value']}/100 ({fng_data['value_classification']})"
except:
    fng_context = "UNKNOWN"

# 4. RSS SPRÁVY
news_items = []
try:
    rss_url = "https://cointelegraph.com/rss"
    root = ET.fromstring(urllib.request.urlopen(urllib.request.Request(rss_url, headers={'User-Agent': 'Mozilla/5.0'}), timeout=10).read())
    for item in root.findall('./channel/item')[:4]:
        title = item.find('title').text
        if title: news_items.append(title)
except: pass
news_context = " | ".join(news_items) if news_items else "DATA NOT AVAILABLE"

# 5. DETAILNÉ DÁTA O MINCIACH + SPARKLINE
coins_map = {"bitcoin": "BTC", "ethereum": "ETH", "solana": "SOL", "bittensor": "TAO", "fetch-ai": "FET", "aave": "AAVE", "render-token": "RENDER", "ondo-finance": "ONDO"}
coin_ids = ",".join(coins_map.keys())
cg_url = f"https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&ids={coin_ids}&order=market_cap_desc&price_change_percentage=24h,7d,30d&sparkline=true"

crypto_summary_lines = []
try:
    req = urllib.request.Request(cg_url, headers={'User-Agent': 'Mozilla/5.0'})
    market_data = json.loads(urllib.request.urlopen(req, timeout=15).read().decode())
    for coin in market_data:
        sym = coins_map.get(coin['id'], coin['symbol'].upper())
        p = coin.get('current_price', 0)
        c24 = coin.get('price_change_percentage_24h_in_currency', 0) or coin.get('price_change_percentage_24h', 0)
        c7d = coin.get('price_change_percentage_7d_in_currency', 0)
        c30d = coin.get('price_change_percentage_30d_in_currency', 0)
        vol = coin.get('total_volume', 0)
        ath_dist = coin.get('ath_change_percentage', 0)
        
        sparkline = coin.get('sparkline_in_7d', {}).get('price', [])
        if sparkline:
            downsampled = sparkline[::4]
            prices_str = ", ".join(f"{pr:.2f}" for pr in downsampled)
            trend_data = f"Vývoj ceny (4H interval, posledných 7 dní): [{prices_str}]"
        else:
            trend_data = "Historické ceny nedostupné."
            
        crypto_summary_lines.append(
            f"[{sym}] Cena: \({p} | 24h: {c24:+.2f}% | 7d: {c7d:+.2f}% | 30d: {c30d:+.2f}% | Vol:\){vol:,.0f} | Od ATH: {ath_dist:.1f}%\n   {trend_data}"
        )
except Exception as e:
    print(f"CoinGecko error: {e}")

market_context = "\n".join(crypto_summary_lines)

def send_telegram(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = urllib.parse.urlencode({"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "Markdown"}).encode("utf-8")
    try:
        req = urllib.request.Request(url, data=payload)
        with urllib.request.urlopen(req, timeout=10) as response:
            print(f"Telegram úspešne odoslaný, status: {response.status}")
    except Exception as e:
        print(f"CHYBA Telegram: {e}")

# 6. MASTER PROMPT S PAMÄŤOU A PORTFÓLIOM
prompt = f"""
ROLE: Si špičkový AI kvantitatívny analytik. GitHub funguje len ako zberač surových dát. Analyzuj dáta objektívne, bez halucinácií.

DÁTOVÝ BALÍČEK OD GITHUB (AS OF {current_time}):
GLOBÁLNE MAKRO: {macro_context}
FEAR & GREED: {fng_context}
RSS SPRÁVY: {news_context}

TRHOVÉ DÁTA A HISTÓRIA (Cenové pole zohľadni ako proxy pre EMA/RSI a hľadanie supportov/rezistencií):
{market_context}

PAMÄŤ BOTA (TVOJA POSLEDNÁ ANALÝZA SPRED 4 HODÍN):
{previous_analysis}

PORTFÓLIO KLIENTA:
Klient aktuálne aktívne drží na burzách eToro a Bybit: BTC, SOL, AAVE, FET, TAO.
Zvyšné mince (ETH, RENDER, ONDO) zatiaľ len sleduje. Zohľadni túto sektorovú koncentráciu a nepodporuj agresívne zväčšovanie pozícií bez extrémne jasného R:R.

INŠTRUKCIE PRE EXEKÚCIU A VÝSTUP:
1. Skontroluj svoju predošlú analýzu. Status meň, Iba ak sa štruktúra trhu alebo dáta za 4 hodiny zmenili.
2. Statusy: NEW BUY, HOLD, WAIT, REDUCE, TAKE PROFIT, EXIT, NO TRADE.
3. Výstup musí striktne oddeľovať Technické a Fundamentálne skóre.

VÝSTUP DO TELEGRAMU (Zachovaj presne tento markdown formát, buď stručný a dátový):

📊 **CRYPTO MARKET UPDATE (4H)**
🕐 {current_time}

🌍 **MAKRO & SENTIMENT**
- Trh: [Analýza trendu podľa BTC dom. a Total Cap]
- Správy: [Zhodnotenie RSS správ]

🔥 **PORTFÓLIO & WATCHLIST**
(Rozober všetkých 8 mincí: BTC, ETH, SOL, TAO, FET, AAVE, RENDER, ONDO)

- **[SYMBOL]** (${{Cena}}) | Bias: **[STATUS]** | Conf: [XX]%
  - Tech Skóre: [XX/100] | Fundament Skóre: [XX/100]
  - Analýza: [1 stručná veta kombinujúca cenovú štruktúru zo 7d poľa]
  - Exekúcia: [Napr. HOLD. Ak NEW BUY, definuj Entry X, TP X, Stop X. Ak WAIT, tak dokedy/na akú cenu].

🧠 **FINAL VERDICT**
- Najlepší Risk/Reward: [Symbol]
- Zmena oproti minulej analýze: [1 veta]
"""

try:
    genai.configure(api_key=GEMINI_API_KEY)
    # Použitie predvoleného modelu bez explicitného názvu verzie
    model = genai.GenerativeModel()
    response = model.generate_content(prompt)
    ai_analysis = response.text
except Exception as e:
    ai_analysis = f"⚠️ Chyba AI pri generovaní: {str(e)[:150]}"

if len(ai_analysis) > 4000:
    ai_analysis = ai_analysis[:3950] + "\n\n... (skrátené)"

send_telegram(ai_analysis)

# 7. ULOŽENIE AKTUÁLNEJ ANALÝZY DO PAMÄTE PRE ĎALŠÍ BEH
try:
    with open(memory_file, "w", encoding="utf-8") as f:
        f.write(ai_analysis)
    print("Analýza úspešne odoslaná a uložená do pamäte!")
except Exception as e:
    print(f"Chyba pri ukladaní pamäte: {e}")
