import os
import json
import urllib.request
import urllib.parse

# Načítanie tokenov
TOKEN = os.environ.get("TELEGRAM_TOKEN", "").strip()
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()

if not TOKEN or not CHAT_ID:
    print("CHYBA: Token alebo Chat ID chýbajú!")
    exit(1)

# 1. Stiahnutie Crypto Fear & Greed Indexu
try:
    fng_url = "https://api.alternative.me/fng/"
    req = urllib.request.urlopen(fng_url)
    fng_data = json.loads(req.read().decode())['data'][0]
    fng_value = fng_data['value']
    fng_class = fng_data['value_classification']
except Exception as e:
    fng_value = "N/D"
    fng_class = "N/D"

# 2. Stiahnutie dát z CoinGecko pre naše mince
coins = [
    ("bitcoin", "BTC"),
    ("ethereum", "ETH"),
    ("solana", "SOL"),
    ("bittensor", "TAO"),
    ("fetch-ai", "FET"),
    ("aave", "AAVE"),
    ("render-token", "RENDER"),
    ("ondo-finance", "ONDO")
]

coin_ids = ",".join([c[0] for c in coins])
cg_url = f"https://api.coingecko.com/api/v3/simple/price?ids={coin_ids}&vs_currencies=usd&include_24hr_change=true"

try:
    req = urllib.request.Request(cg_url, headers={'User-Agent': 'Mozilla/5.0'})
    response = urllib.request.urlopen(req)
    cg_data = json.loads(response.read().decode())
except Exception as e:
    print(f"Chyba pri sťahovaní z CoinGecko: {e}")
    cg_data = {}

# 3. Vybudovanie komplexnej správy a analýzy
message_lines = [
    "📊 **KOMPLEXNÁ KRYPTO ANALÝZA**",
    f"🧠 **Trhový Sentiment (F&G):** {fng_value} / 100 ({fng_class})",
    "-----------------------------------"
]

for coin_id, symbol in coins:
    if coin_id in cg_data:
        price = cg_data[coin_id].get('usd', 0)
        change_24h = cg_data[coin_id].get('usd_24h_change', 0)
        
        # Jednoduchá analytická logika pre odporúčanie
        if change_24h > 5.0:
            action = "🟢 SILNÝ RAST (Zvážiť čiastočný výber ziskov / Držať)"
        elif change_24h > 0:
            action = "🔵 RAST / STABILNÉ (Držať)"
        elif change_24h > -5.0:
            action = "🟡 MIERNY POKLES (Sledovať / Možný nákup v zľave)"
        else:
            action = "🔴 VÝRAZNÝ POKLES (Príležitosť na DCA nákup / Držať)"
            
        emoji_change = "📈" if change_24h >= 0 else "📉"
        line = f"*{symbol}*: ${price:,.2f} | {emoji_change} {change_24h:+.2f}%\n   💡 *Signál:* {action}"
        message_lines.append(line)
    else:
        message_lines.append(f"*{symbol}*: Dáta nedostupné")

message_lines.append("-----------------------------------")
message_lines.append("🤖 *AI Agent:* Pravidelná 6-hodinová analýza trhu.")

full_message = "\n".join(message_lines)

# 4. Odoslanie správy do Telegramu
telegram_url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
payload = urllib.parse.urlencode({
    "chat_id": CHAT_ID,
    "text": full_message,
    "parse_mode": "Markdown"
}).encode("utf-8")

try:
    urllib.request.urlopen(telegram_url, data=payload)
    print("Komplexná analýza úspešne odoslaná do Telegramu!")
except urllib.error.HTTPError as e:
    print(f"HTTP Chyba od Telegramu: {e.code} - {e.reason}")
    print(e.read().decode())
    raise e
