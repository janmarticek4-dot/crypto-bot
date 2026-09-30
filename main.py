import os
import json
import urllib.request
import urllib.parse

TOKEN = os.environ.get("TELEGRAM_TOKEN", "").strip()
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()

print(f"Dĺžka tokenu: {len(TOKEN)}")
print(f"Chat ID: {CHAT_ID}")

if not TOKEN or not CHAT_ID:
    print("CHYBA: Token alebo Chat ID chýbajú!")
    exit(1)

url = "https://api.alternative.me/fng/"
req = urllib.request.urlopen(url)
data = json.loads(req.read().decode())['data'][0]
message = f"🚨 Aktuálny Crypto Fear & Greed Index:\nHodnota: {data['value']} ({data['value_classification']})"

telegram_url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
payload = urllib.parse.urlencode({
    "chat_id": CHAT_ID,
    "text": message
}).encode("utf-8")

try:
    urllib.request.urlopen(telegram_url, data=payload)
    print("Notifikácia úspešne odoslaná!")
except urllib.error.HTTPError as e:
    print(f"HTTP Chyba od Telegramu: {e.code} - {e.reason}")
    print(e.read().decode())
    raise e
