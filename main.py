import os
import json
import urllib.request
import urllib.parse

# .strip() odstrihne prípadné neviditeľné medzery alebo nové riadky na začiatku/konci
TOKEN = os.environ.get("TELEGRAM_TOKEN", "").strip()
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()

print(f"Dĺžka tokenu po očistení: {len(TOKEN)}")
print(f"Chat ID po očistení: {CHAT_ID}")

if not TOKEN or not CHAT_ID:
    raise ValueError("CHYBA: Token alebo Chat ID sú prázdne!")

# Stiahnutie dát z API
url = "https://api.alternative.me/fng/"
req = urllib.request.urlopen(url)
data = json.loads(req.read().decode())['data'][0]
message = f"🚨 Aktuálny Crypto Fear & Greed Index:\nHodnota: {data['value']} ({data['value_classification']})"

# Odoslanie do Telegramu
telegram_url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
payload = urllib.parse.urlencode({
    "chat_id": CHAT_ID,
    "text": message
}).encode("utf-8")

try:
    urllib.request.urlopen(telegram_url, data=payload)
    print("Notifikácia úspešne odoslaná do Telegramu!")
except urllib.error.HTTPError as e:
    print(f"HTTP Chyba od Telegramu: {e.code} - {e.reason}")
    print(e.read().decode())
    raise e
