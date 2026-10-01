import os
import json
import urllib.request
import urllib.parse

# Načítanie všetkých kľúčov
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()

if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID or not GEMINI_API_KEY:
    print("CHYBA: Niektorý z kľúčov chýba v GitHub Secrets!")
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

# 2. Stiahnutie pokročilých dát z CoinGecko (trhová kapitalizácia, valuácia, ATH)
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
    response = urllib.request.urlopen(req)
    market_data = json.loads(response.read().decode())
except Exception as e:
    print(f"Chyba pri sťahovaní z CoinGecko: {e}")
    market_data = []

crypto_summary_lines = []
for coin in market_data:
    symbol = coins_map.get(coin['id'], coin['symbol'].upper())
    price = coin.get('current_price', 0)
    change_24h = coin.get('price_change_percentage_24h', 0)
    market_cap = coin.get('market_cap', 0)
    ath = coin.get('ath', 0)
    
    crypto_summary_lines.append(
        f"- {symbol}: Cena: \({price:,.2f}, 24h zmena: {change_24h:+.2f}%, Market Cap:\){market_cap:,.0f}, ATH: ${ath:,.2f}"
    )

market_context = "\n".join(crypto_summary_lines)

# 3. Pokročilý Prompt pre Gemini AI s požiadavkou na Twitter/X sentiment a vyhlásenia vplyvných osôb
prompt = f"""
Si špičkový kvantitatívny krypto analytik, portfólio manažér a expert na on-chain, fundamentálnu analýzu a sociálny sentiment (Twitter/X).
Tu sú aktuálne dáta z trhu:
- Trhový sentiment (Fear & Greed Index): {fng_value}/100 ({fng_class})
- Aktuálne dáta sledovaných mincí:
{market_context}

Tvojou úlohou je vykonať hĺbkový prieskum a pripraviť profesionálnu 6-hodinovú krypto analýzu pre môj Telegramový kanál.
Pri analýze bezpodmienečne zohľadni:
1. **Sociálny sentiment a Twitter (X) / správy**: Vyhľadaj si najnovšie vyhlásenia, tweety a statusy od vplyvných osôb (ako sú Elon Musk, Donald Trump, zakladatelia a kľúčoví vývojári spojení s týmito mincami: BTC, ETH, SOL, TAO, FET, AAVE, RENDER, ONDO) za posledné hodiny/dni a zohľadni ich vplyv na cenu.
2. **Fundamentálnu situáciu a valuáciu** (trhovú kapitalizáciu, pomer voči ATH).
3. **Konkrétne obchodné odporúčanie** pre každú mincu vrátane exaktného percenta aktuálnej pozície, ktoré sa má predať, dokúpiť alebo držať (napr. „Predať 15% pozície“, „Dokúpiť 10%“, „Držať 100%“).

Odpoveď naformátuj priamo pre Telegram (používaj emoji, tučné písmo cez markdown). Ak za posledné hodiny prebehol nejaký dôležitý tweet alebo vyhlásenie ovplyvňujúce tieto mince, výslovne ho v analýze spomeň. Začni priamo správou, žiadne úvody okolo toho.
"""

# Volanie Gemini API s povoleným nástrojom Google Search Grounding (na vyhľadávanie tweetov a aktuálnych správ)
gemini_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
payload_gemini = {
    "contents": [{
        "parts": [{"text": prompt}]
    }],
    "tools": [{"google_search": {}}]  # Toto umožní Gemini prehľadávať web a sociálne siete v reálnom čase
}

try:
    req = urllib.request.Request(
        gemini_url,
        data=json.dumps(payload_gemini).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    response = urllib.request.urlopen(req)
    gemini_response = json.loads(response.read().decode())
    ai_analysis = gemini_response['candidates'][0]['content']['parts'][0]['text']
except Exception as e:
    print(f"Chyba pri volaní Gemini API: {e}")
    ai_analysis = "⚠️ Chyba pri generovaní AI analýzy trhu."

# 4. Odoslanie výslednej analýzy do Telegramu
telegram_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
payload_telegram = urllib.parse.urlencode({
    "chat_id": TELEGRAM_CHAT_ID,
    "text": ai_analysis,
    "parse_mode": "Markdown"
}).encode("utf-8")

try:
    urllib.request.urlopen(telegram_url, data=payload_telegram)
    print("Pokročilá AI analýza so sentimentom z Twitteru úspešne odoslaná do Telegramu!")
except urllib.error.HTTPError as e:
    print(f"HTTP Chyba od Telegramu: {e.code} - {e.reason}")
    print(e.read().decode())
    raise e
