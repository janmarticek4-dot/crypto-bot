import os
import json
import time
import urllib.request
import urllib.parse
import urllib.error
import xml.etree.ElementTree as ET
from datetime import datetime, timezone


# ============================================================
# CRYPTO AI BOT V2
# GitHub = zber dát
# Gemini = analytický mozog
# Telegram = výstup
# ============================================================


# ============================================================
# 1. KONFIGURÁCIA
# ============================================================

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()

# Aktuálny model podľa Gemini API dokumentácie
GEMINI_MODEL = "gemini-3.8-flash"

MEMORY_FILE = "last_analysis.txt"

# CoinGecko mince
COINS = {
    "bitcoin": "BTC",
    "ethereum": "ETH",
    "solana": "SOL",
    "bittensor": "TAO",
    "fetch-ai": "FET",
    "aave": "AAVE",
    "render-token": "RENDER",
    "ondo-finance": "ONDO"
}

# Reálne držané pozície
HELD_COINS = {
    "BTC",
    "SOL",
    "AAVE",
    "FET",
    "TAO"
}

# Watchlist
WATCHLIST_COINS = {
    "ETH",
    "RENDER",
    "ONDO"
}


# ============================================================
# 2. ZÁKLADNÉ KONTROLY
# ============================================================

if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID or not GEMINI_API_KEY:
    print("CHYBA: Chýba TELEGRAM_TOKEN, TELEGRAM_CHAT_ID alebo GEMINI_API_KEY v GitHub Secrets.")
    exit(1)


# Explicitný UTC čas
current_time = datetime.now(timezone.utc)
current_time_str = current_time.strftime("%Y-%m-%d %H:%M:%S UTC")


# ============================================================
# 3. HTTP HELPER
# ============================================================

def http_get(url, timeout=15, retries=3):
    """
    GET request s retry logikou.
    """

    last_error = None

    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "Crypto-AI-Bot-V2/1.0",
                    "Accept": "application/json, application/xml, text/xml, */*"
                }
            )

            with urllib.request.urlopen(req, timeout=timeout) as response:
                return response.read()

        except urllib.error.HTTPError as e:
            last_error = e

            # Rate limit / server errors
            if e.code in [429, 500, 502, 503, 504]:
                wait_time = 2 ** attempt
                print(f"HTTP {e.code}. Retry za {wait_time}s...")
                time.sleep(wait_time)
                continue

            raise

        except Exception as e:
            last_error = e

            if attempt < retries - 1:
                wait_time = 2 ** attempt
                print(f"HTTP chyba: {e}. Retry za {wait_time}s...")
                time.sleep(wait_time)

    raise last_error


# ============================================================
# 4. NAČÍTANIE PREDCHÁDZAJÚCEJ ANALÝZY
# ============================================================

try:
    with open(MEMORY_FILE, "r", encoding="utf-8") as f:
        previous_analysis = f.read().strip()

    if not previous_analysis:
        previous_analysis = "Žiadna použiteľná predchádzajúca analýza."

except FileNotFoundError:
    previous_analysis = "Žiadna predchádzajúca analýza. Toto je prvý beh."

except Exception as e:
    previous_analysis = f"Pamäť nedostupná: {e}"


# Ochrana proti nekonečne veľkej pamäti
MAX_MEMORY_CHARS = 12000

if len(previous_analysis) > MAX_MEMORY_CHARS:
    previous_analysis = previous_analysis[-MAX_MEMORY_CHARS:]


# ============================================================
# 5. COINGECKO – GLOBAL MARKET
# ============================================================

macro_context = "Makro dáta nedostupné."

try:

    global_url = "https://api.coingecko.com/api/v3/global"

    global_raw = http_get(global_url, timeout=15)
    global_data = json.loads(global_raw.decode("utf-8"))["data"]

    total_mcap = global_data.get("total_market_cap", {}).get("usd", 0)
    btc_dom = global_data.get("market_cap_percentage", {}).get("btc", 0)

    mcap_change_24h = global_data.get(
        "market_cap_change_percentage_24h_usd",
        0
    )

    active_cryptos = global_data.get("active_cryptocurrencies", 0)

    macro_context = (
        f"Total Market Cap: ${total_mcap:,.0f} | "
        f"BTC Dominance: {btc_dom:.2f}% | "
        f"Market Cap 24H: {mcap_change_24h:+.2f}% | "
        f"Active Cryptos: {active_cryptos:,}"
    )

except Exception as e:
    print(f"CoinGecko Global error: {e}")


# ============================================================
# 6. FEAR & GREED
# ============================================================

fng_context = "UNKNOWN"

try:

    fng_url = "https://api.alternative.me/fng/"

    fng_raw = http_get(fng_url, timeout=15)
    fng_data = json.loads(fng_raw.decode("utf-8"))["data"][0]

    fng_value = fng_data.get("value", "UNKNOWN")
    fng_classification = fng_data.get(
        "value_classification",
        "UNKNOWN"
    )

    fng_context = (
        f"{fng_value}/100 ({fng_classification})"
    )

except Exception as e:
    print(f"Fear & Greed error: {e}")


# ============================================================
# 7. RSS SPRÁVY
# ============================================================

news_items = []

try:

    rss_url = "https://cointelegraph.com/rss"

    rss_raw = http_get(rss_url, timeout=15)

    root = ET.fromstring(rss_raw)

    items = root.findall("./channel/item")

    for item in items[:12]:

        title_element = item.find("title")
        date_element = item.find("pubDate")
        link_element = item.find("link")

        title = (
            title_element.text.strip()
            if title_element is not None and title_element.text
            else ""
        )

        pub_date = (
            date_element.text.strip()
            if date_element is not None and date_element.text
            else "unknown time"
        )

        link = (
            link_element.text.strip()
            if link_element is not None and link_element.text
            else ""
        )

        if title:
            news_items.append(
                f"- {title} | {pub_date} | {link}"
            )

except Exception as e:
    print(f"RSS error: {e}")


if news_items:
    news_context = "\n".join(news_items)
else:
    news_context = "RSS DATA NOT AVAILABLE."


# ============================================================
# 8. COINGECKO – MARKET DATA
# ============================================================

coin_ids = ",".join(COINS.keys())

cg_url = (
    "https://api.coingecko.com/api/v3/coins/markets"
    "?vs_currency=usd"
    f"&ids={coin_ids}"
    "&order=market_cap_desc"
    "&price_change_percentage=24h,7d,30d"
    "&sparkline=true"
)

crypto_summary_lines = []

try:

    market_raw = http_get(cg_url, timeout=20)

    market_data = json.loads(
        market_raw.decode("utf-8")
    )

    for coin in market_data:

        coin_id = coin.get("id", "")
        sym = COINS.get(
            coin_id,
            coin.get("symbol", "").upper()
        )

        price = coin.get("current_price", 0) or 0

        change_24h = (
            coin.get("price_change_percentage_24h_in_currency")
            or coin.get("price_change_percentage_24h")
            or 0
        )

        change_7d = (
            coin.get("price_change_percentage_7d_in_currency")
            or 0
        )

        change_30d = (
            coin.get("price_change_percentage_30d_in_currency")
            or 0
        )

        volume = coin.get("total_volume", 0) or 0

        market_cap = coin.get("market_cap", 0) or 0

        ath = coin.get("ath", 0) or 0

        ath_change = (
            coin.get("ath_change_percentage", 0)
            or 0
        )

        market_cap_rank = (
            coin.get("market_cap_rank", "N/A")
        )

        # ----------------------------------------------------
        # 7D SPARKLINE
        # CoinGecko 7d sparkline = približne hodinové dáta.
        # [::4] => približne 4H interval.
        # ----------------------------------------------------

        sparkline = (
            coin.get("sparkline_in_7d", {})
            .get("price", [])
        )

        if sparkline:

            downsampled = sparkline[::4]

            prices_str = ", ".join(
                f"{p:.6g}"
                for p in downsampled
            )

            trend_data = (
                "4H proxy z 7D hodinovej histórie: "
                f"[{prices_str}]"
            )

        else:

            trend_data = (
                "7D historická cenová séria nedostupná."
            )

        # ----------------------------------------------------
        # Coin summary
        # ----------------------------------------------------

        position_type = (
            "HELD"
            if sym in HELD_COINS
            else "WATCHLIST"
        )

        crypto_summary_lines.append(
            f"""
[{sym}] [{position_type}]
Cena: ${price:,.6f}
24H: {change_24h:+.2f}%
7D: {change_7d:+.2f}%
30D: {change_30d:+.2f}%
Volume 24H: ${volume:,.0f}
Market Cap: ${market_cap:,.0f}
Market Cap Rank: #{market_cap_rank}
ATH: ${ath:,.6f}
Od ATH: {ath_change:.1f}%
{trend_data}
""".strip()
        )

except Exception as e:

    print(f"CoinGecko market error: {e}")


market_context = "\n\n".join(
    crypto_summary_lines
)


# ============================================================
# 9. GEMINI PROMPT
# ============================================================

prompt = f"""
ROLE:
Si profesionálny AI krypto analytik a risk manager.
Tvojou úlohou nie je vytvárať čo najviac obchodov.
Tvojou úlohou je nájsť iba obchody s dostatočne dobrým Risk/Reward.

GitHub je iba zberač dát.
Ty si hlavný analytický mozog.
Máš k dispozícii aj Google Search grounding a MUSÍŠ ho použiť pri
aktuálnych správach, makro udalostiach, regulácii, ETF/inštitucionálnych
udalostiach, token unlockoch, fundamentálnych zmenách a ďalších
časovo citlivých informáciách.

AKTUÁLNY ČAS:
{current_time_str}


============================================================
DÁTA Z GITHUB
============================================================

GLOBÁLNE MAKRO:
{macro_context}


FEAR & GREED:
{fng_context}


RSS SPRÁVY:
{news_context}


TRHOVÉ DÁTA:
{market_context}


============================================================
PORTFÓLIO
============================================================

AKTUÁLNE DRŽANÉ:
BTC, SOL, AAVE, FET, TAO

WATCHLIST:
ETH, RENDER, ONDO

Pri rozhodovaní rozlišuj medzi:
- existujúcou pozíciou
- novým vstupom
- watchlistom


============================================================
PREDCHÁDZAJÚCA ANALÝZA
============================================================

{previous_analysis}


============================================================
DÔLEŽITÉ ANALYTICKÉ PRAVIDLÁ
============================================================

1. ŽIADNE HALUCINÁCIE

Nikdy si nevymýšľaj:
- cenu
- fundament
- partnerstvo
- ETF
- token unlock
- on-chain údaj
- volume
- whale activity
- funding rate
- open interest
- makro udalosť
- správu

Ak údaj nemáš, povedz:
"N/A – dáta nedostupné."

Google Search použi na overenie aktuálnych informácií.


2. TECHNICKÉ SKÓRE

Technické skóre 0–100 určuj podľa dostupných dát.

Zohľadni najmä:
- trend
- momentum
- 24H / 7D / 30D
- cenovú štruktúru
- supporty
- rezistencie
- breakout / breakdown
- volume
- vzdialenosť od ATH
- BTC režim
- relatívnu silu voči trhu

7D cenové pole používaj ako cenovú históriu a proxy pre
market structure.

NEPREDSTIERAJ, že z neho priamo poznáš presné RSI alebo EMA.
Ak presné RSI/EMA nemáš, neuvádzaj ich ako presné čísla.


3. FUNDAMENTÁLNE SKÓRE

Fundamentálne skóre 0–100.

Zohľadni:
- adopciu
- vývoj projektu
- token utility
- konkurenciu
- ekosystém
- revenue / fees, ak sú dostupné
- tokenomics
- unlocky
- reguláciu
- významné partnerstvá
- aktuálne fundamentálne správy

Fundamentálne tvrdenia MUSIA byť založené na dostupných dátach
alebo overenom Google Search.

Ak je fundamentálnych dát málo:
zniž confidence.
Nevymýšľaj skóre.


4. GOOGLE SEARCH

Google Search použi najmä na:

- posledné významné správy
- makro udalosti
- Fed / ECB
- reguláciu
- ETF
- veľké partnerstvá
- hacky
- token unlocky
- veľké technologické aktualizácie
- významné on-chain / DeFi udalosti
- inštitucionálne správy

Nehľadaj zbytočnosti.
Použi Search iba tam, kde môže zmeniť investičný záver.


5. BTC JE HLAVNÝ FILTER

Pred analýzou altcoinov urč:

BTC REGIME:

- BULLISH
- NEUTRAL
- BEARISH

Ak je BTC bearish:
zníž agresivitu pri altcoinoch.

Ak je BTC bullish:
altcoin long setupy môžu dostať vyššiu prioritu.


6. STATUSY

Povolené statusy:

NEW BUY
ADD
HOLD
WAIT
REDUCE
TAKE PROFIT
EXIT
NO TRADE

Význam:

NEW BUY = nový vstup pre coin, ktorý klient aktuálne nedrží.

ADD = klient coin drží a existuje dobrý setup na dokúpenie.

HOLD = držať existujúcu pozíciu.

WAIT = zatiaľ nevstupovať / nedokupovať, čakať na konkrétnu cenu alebo potvrdenie.

REDUCE = znížiť časť pozície.

TAKE PROFIT = realizovať časť zisku.

EXIT = opustiť pozíciu.

NO TRADE = setup nemá dostatočnú kvalitu.


7. ANTI-OVERTRADING

Nezmeň status iba preto, že cena sa za posledné 4 hodiny
pohla o malé percento.

Status zmeň iba vtedy, ak sa zmenilo niečo významné:

- market structure
- support/resistance
- breakout/breakdown
- BTC regime
- fundament
- významná správa
- volume
- risk/reward
- trend


8. RISK / REWARD

Pri NEW BUY alebo ADD vždy definuj:

ENTRY
STOP
TP1
TP2

Minimálny preferovaný R:R = 2:1.

Ak R:R < 2:
preferuj WAIT alebo NO TRADE.

Nepoužívaj náhodné čísla.
Entry, Stop a TP musia vychádzať zo supportov,
rezistencií, volatility a aktuálnej štruktúry trhu.


9. CONFIDENCE

Confidence 0–100%.

Confidence nesmie byť iba priemer skóre.

Zohľadni:
- kvalitu dát
- zhodu techniky a fundamentu
- jasnosť market structure
- BTC regime
- kvalitu setupu
- aktuálne správy


10. SCENÁRE

Pri dôležitých rozhodnutiach interne zváž:

BULL CASE
BASE CASE
BEAR CASE

Do Telegramu však neposielaj dlhý text.
Použi iba najdôležitejší záver.


11. EXISTUJÚCE POZÍCIE

Pri BTC, SOL, AAVE, FET a TAO nepovažuj každý pokles
automaticky za dôvod na dokúpenie.

Najprv posúď:
- či sa zlepšil R:R
- či je support potvrdený
- či sa nezhoršil fundament
- či už pozícia nie je príliš veľká
- koreláciu s ostatnými pozíciami


12. PORTFÓLIO RIZIKO

Klient už drží:
BTC + SOL + AAVE + FET + TAO.

Zohľadni vysokú koreláciu kryptomien.

Nepodporuj agresívne zväčšovanie všetkých pozícií naraz.

Ak je celý trh rizikový:
uprednostni WAIT / HOLD / REDUCE.


13. WATCHLIST

ETH, RENDER a ONDO klient momentálne nedrží.

NEW BUY navrhni iba vtedy, keď setup má jasnú výhodu
oproti dokúpeniu existujúcej pozície.

Neodporúčaj nový coin iba preto, že rastie.


14. RELATÍVNA SILA

Porovnaj mince navzájom.

Ak napríklad:
SOL má lepší trend než ETH,
TAO má lepší R:R než FET,
alebo RENDER má lepší setup než ONDO,

zohľadni to v FINAL VERDICT.


15. SCORE

Výsledné skóre nie je mechanický priemer.

Použi orientačne:

Macro / BTC regime: 20%
Technical: 25%
Fundamental: 20%
Market structure / momentum: 15%
Risk/Reward: 10%
News / sentiment: 10%

Výsledné skóre používaj ako pomocný nástroj,
nie ako automatický signál.


============================================================
VÝSTUP
============================================================

Vráť iba nasledujúci formát.

ŽIADNE DLOUHÉ VYSVETĽOVANIE.
ŽIADNE ÚVODNÉ POZNÁMKY.
ŽIADNY DISCLAIMER.
ŽIADNE TABUĽKY.

📊 **CRYPTO MARKET UPDATE (4H)**
🕐 {current_time_str}

🌍 **MAKRO & SENTIMENT**
- BTC Regime: **[BULLISH / NEUTRAL / BEARISH]**
- Trh: [1 stručná veta]
- Fear & Greed: [hodnota + interpretácia]
- Správy: [1–2 najdôležitejšie aktuálne správy a ich dopad]

🔥 **PORTFÓLIO & WATCHLIST**

Rozober VŠETKÝCH 8 mincí v tomto poradí:

BTC
ETH
SOL
TAO
FET
AAVE
RENDER
ONDO

Pre každú:

- **[SYMBOL]** ($[PRICE]) | Bias: **[STATUS]** | Conf: [XX]%
  - Tech Skóre: [XX/100] | Fundament Skóre: [XX/100]
  - Analýza: [max 1 stručná veta]
  - Exekúcia: [konkrétna akcia]

Pri NEW BUY alebo ADD musí byť:

Entry: $X
Stop: $X
TP1: $X
TP2: $X
R:R: X.X

Pri WAIT:

Wait for: $X alebo [konkrétna podmienka]

Pri HOLD:

HOLD – [stručný dôvod]

Pri REDUCE / TAKE PROFIT / EXIT:

[stručná konkrétna akcia]


🧠 **FINAL VERDICT**

- Najlepší Risk/Reward: **[SYMBOL]**
- Najslabší setup: **[SYMBOL]**
- BTC režim: **[BULLISH / NEUTRAL / BEARISH]**
- Zmena oproti minulej analýze: [max 1 veta]

Ak sa oproti minulej analýze nič významné nezmenilo,
napíš:
"Bez významnej zmeny – trhová štruktúra zostáva rovnaká."


============================================================
KONEČNÉ PRAVIDLO
============================================================

Radšej daj WAIT alebo NO TRADE ako nekvalitný obchod.

Tvoj cieľ nie je predpovedať každý pohyb.
Tvoj cieľ je identifikovať asymetrické príležitosti
s dobrým R:R a zároveň chrániť existujúci kapitál.
"""


# ============================================================
# 10. GEMINI API
# ============================================================

def call_gemini(prompt_text):

    gemini_url = (
        f"https://generativelanguage.googleapis.com/"
        f"v1beta/models/{GEMINI_MODEL}:generateContent"
    )

    payload = {
        "contents": [
            {
                "parts": [
                    {
                        "text": prompt_text
                    }
                ]
            }
        ],

        # AKTUÁLNE GOOGLE SEARCH GROUNDING
        "tools": [
            {
                "google_search": {}
            }
        ],

        "generationConfig": {
            "temperature": 0.25,
            "topP": 0.90,
            "maxOutputTokens": 5000
        }
    }

    data = json.dumps(payload).encode("utf-8")

    request = urllib.request.Request(
        gemini_url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": GEMINI_API_KEY
        },
        method="POST"
    )

    with urllib.request.urlopen(
        request,
        timeout=120
    ) as response:

        result = json.loads(
            response.read().decode("utf-8")
        )

    # --------------------------------------------------------
    # Bezpečné vybratie odpovede
    # --------------------------------------------------------

    candidates = result.get("candidates", [])

    if not candidates:
        raise RuntimeError(
            "Gemini nevrátil žiadne candidates."
        )

    content = candidates[0].get("content", {})

    parts = content.get("parts", [])

    text_parts = []

    for part in parts:

        if "text" in part:
            text_parts.append(
                part["text"]
            )

    final_text = "\n".join(text_parts).strip()

    if not final_text:
        raise RuntimeError(
            "Gemini vrátil prázdnu textovú odpoveď."
        )

    return final_text


# ============================================================
# 11. SPUSTENIE GEMINI
# ============================================================

ai_analysis = ""

try:

    print(
        f"Spúšťam Gemini {GEMINI_MODEL}..."
    )

    ai_analysis = call_gemini(prompt)

    print(
        "Gemini analýza úspešne vytvorená."
    )

except urllib.error.HTTPError as e:

    error_body = ""

    try:
        error_body = e.read().decode("utf-8")[:1000]
    except Exception:
        pass

    ai_analysis = (
        f"⚠️ CHYBA GEMINI API\n"
        f"HTTP {e.code}\n"
        f"{error_body}"
    )

except Exception as e:

    ai_analysis = (
        f"⚠️ CHYBA AI PRI GENEROVANÍ\n"
        f"{str(e)[:1000]}"
    )


# ============================================================
# 12. OCHRANA PROTI PRÍLIŠ DLHEJ TELEGRAM SPRÁVE
# ============================================================

MAX_TELEGRAM_LENGTH = 3900


def split_message(text, max_length=MAX_TELEGRAM_LENGTH):

    if len(text) <= max_length:
        return [text]

    messages = []

    current = ""

    for line in text.split("\n"):

        if len(current) + len(line) + 1 <= max_length:

            current += line + "\n"

        else:

            if current.strip():
                messages.append(
                    current.strip()
                )

            current = line + "\n"

    if current.strip():
        messages.append(
            current.strip()
        )

    return messages


# ============================================================
# 13. TELEGRAM
# ============================================================

def send_telegram(text):

    messages = split_message(text)

    for index, message in enumerate(messages):

        url = (
            f"https://api.telegram.org/"
            f"bot{TELEGRAM_TOKEN}/sendMessage"
        )

        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "Markdown"
        }

        encoded_payload = urllib.parse.urlencode(
            payload
        ).encode("utf-8")

        try:

            req = urllib.request.Request(
                url,
                data=encoded_payload,
                method="POST"
            )

            with urllib.request.urlopen(
                req,
                timeout=15
            ) as response:

                print(
                    f"Telegram OK: "
                    f"{response.status} "
                    f"(časť {index + 1}/{len(messages)})"
                )

        except Exception as e:

            print(
                f"Telegram Markdown chyba: {e}"
            )

            # ------------------------------------------------
            # FALLBACK:
            # Skús poslať správu bez Markdown.
            # ------------------------------------------------

            try:

                fallback_payload = {
                    "chat_id": TELEGRAM_CHAT_ID,
                    "text": message
                }

                fallback_data = urllib.parse.urlencode(
                    fallback_payload
                ).encode("utf-8")

                fallback_req = urllib.request.Request(
                    url,
                    data=fallback_data,
                    method="POST"
                )

                with urllib.request.urlopen(
                    fallback_req,
                    timeout=15
                ) as response:

                    print(
                        f"Telegram fallback OK: "
                        f"{response.status}"
                    )

            except Exception as fallback_error:

                print(
                    f"TELEGRAM ERROR: "
                    f"{fallback_error}"
                )

        # malé oneskorenie medzi správami
        if index < len(messages) - 1:
            time.sleep(1)


# ============================================================
# 14. ODOSLANIE ANALÝZY
# ============================================================

send_telegram(ai_analysis)


# ============================================================
# 15. ULOŽENIE PAMÄTE
# ============================================================

try:

    with open(
        MEMORY_FILE,
        "w",
        encoding="utf-8"
    ) as f:

        f.write(ai_analysis)

    print(
        "Analýza úspešne uložená do "
        f"{MEMORY_FILE}"
    )

except Exception as e:

    print(
        f"CHYBA PRI UKLADANÍ PAMÄTE: {e}"
    )


# ============================================================
# 16. KONIEC
# ============================================================

print(
    "=================================================="
)

print(
    "CRYPTO AI BOT V2 – RUN COMPLETE"
)

print(
    f"Time: {current_time_str}"
)

print(
    f"Model: {GEMINI_MODEL}"
)

print(
    "Google Search: ENABLED"
)

print(
    "=================================================="
)
