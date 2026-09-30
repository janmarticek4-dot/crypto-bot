import os
import json
import urllib.request
import urllib.parse

url = "https://api.alternative.me/fng/"
req = urllib.request.urlopen(url)
data = json.loads(req.read().decode())['data'][0]
message = f"🚨 Aktuálny Crypto Fear & Greed Index:\nHodnota: {data['value']} ({data['value_classification']})"

TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

telegram_url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
payload = urllib.parse.urlencode({
    "chat_id": CHAT_ID,
    "text": message
}).encode("utf-8")

urllib.request.urlopen(telegram_url, data=payload)
print("Notifikácia odoslaná!")
