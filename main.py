import urllib.request
import json

url = "https://api.alternative.me/fng/"
req = urllib.request.urlopen(url)
data = json.loads(req.read().decode())['data'][0]

print(f"Aktuálny Fear & Greed Index: {data['value']} ({data['value_classification']})")
