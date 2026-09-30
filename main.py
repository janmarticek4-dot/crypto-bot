import os
import json
import urllib.request
import urllib.parse

print("Dostupné premenné v systéme:", list(os.environ.keys()))

TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

print(f"TOKEN načítaný: {'ÁNO (dĺžka ' + str(len(TOKEN)) + ')' if TOKEN else 'NIE (je prázdny)'}")
print(f"CHAT_ID načítaný: {'ÁNO' if CHAT_ID else 'NIE (je prázdny)'}")

if TOKEN and CHAT_ID:
    url = "https://api.alternative.me/fng/"
    req = urllib.request.urlopen(url)
    data = json.loads(req.read().decode())['data'][0]
    message = f"🚨 Aktuálny Crypto Fear & Greed Index:\nHodnota: {data['value']} ({data['value_classification']})"

    telegram_url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = urllib.parse.urlencode({
        "chat_id": CHAT_ID,
        "text": message
    }).encode("utf-8")

    urllib.request.urlopen(telegram_url, data=payload)
    print("Notifikácia odoslaná!")
else:
    print("CHYBA: Token alebo Chat ID chýbajú v prostredí!")
