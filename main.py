# 6. STRUČNÁ A KOMPAKTNÁ HLAVNÁ ANALÝZA PRE VŠETKY MINCE
prompt = f"""
Si špičkový krypto portfólio manažér. Priprav STRUČNÚ a prehľadnú 6-hodinovú analýzu pre Telegram. Žiadne dlhé texty, píš vecne v bodoch.
Cieľ: Maximalizovať zisky v bull markete, realizovať zisky na vrchoch a dokupovať LEN NA SKUTOČNÝCH DNÁCH.

Sentiment: {fng_value}/100 ({fng_class}) | Správy: {news_context}
Dáta trhu:
{market_context}

Požiadavky na štruktúru:
1. **Makro & Rotácia:** 2 vety o fáze trhu a kam smeruje kapitál.
2. **Pre KAŽDÚ z 8 mincí (BTC, ETH, SOL, TAO, FET, AAVE, RENDER, ONDO)** použi tento ultrakrátky formát:
   - **[SYMBOL]** | Prognóza: [rast +X% / pokles -X% / range X%]
     - **Fundament/Tech:** [1 stručná veta]
     - **Exekúcia:** [Buď čisté **DRŽAŤ 100% pozície** (ak sa teraz neoplatí nič robiť), ALEBO ak je vhodná príležitosť, uveď konkrétne **DOKÚPIŤ [X]% za Market / Limitku na \(X** resp. **PREDAŤ [X]% na Take-Profit\)X**, pričom uveď aj následnú limitku na odkúpenie]. 
     *DÔLEŽITÉ:* Ak sa nákup/predaj neoplatí, nevymýšľaj ho a napíš iba **DRŽAŤ** s cieľovou hodnotou!

Začni priamo správou, dodrž stručnosť a pokry všetkých 8 mincí!
"""
