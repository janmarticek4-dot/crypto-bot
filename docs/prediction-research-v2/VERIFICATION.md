# Kontrola integrácie — 28.10.2026

- Najnovšia prevzatá main pred integráciou: `bb99ccb` (novší produkčný stav
  než pôvodná `944a9bc`, bezpečne prevzatý fast-forwardom).
- Záloha na GitHube: `backup/main-before-prediction-v2-20261028-bb99ccb`.
- 215 offline testov prešlo so zakázaným nemockovaným sieťovým prístupom.
  Zahŕňajú kauzalitu príznakov aj režimov, dozretie tréningových labelov,
  zmrazenie tolerancie/výberu voči zmenám budúceho testu, presnú reprodukciu V1
  vrátane volatility pri šoku, PIT revízie, spoločné tréningové riadky ablácií,
  neprekrývajúce sa testové horizonty, JSON exporty, nemennosť paper prognóz,
  súkromné polia, poškodený denník a chýbajúce presné endpointy.
- YAML výskumného workflow bol načítaný a overený: predvolene contents:read,
  zápis iba na explicitný manuálny checkbox alebo schválenú verziu paper režimu.
- Živý lokálny shadow zber a historické porovnanie prebehli úspešne. Presný čas,
  rozsahy a verzie sú v input-manifest.json; zdroje v source-diagnostics.json.
- Číselné podklady pre mincu/horizont/model/režim a neistotu sú v diagnostics.json
  a all-models.csv. Celé verejné historické vstupy a jednotlivé originy sú súčasťou
  nového Artifactu pri behu na GitHube.
- 12 chránených súborov vrátane main.py, bot_state.json, Telegram denníka,
  run.yml, strategy.py, analyst.py, fundamentov, V1 a produkčných doručovacích
  skriptov sa pred integráciou byte-po-byte zhodovalo s aktuálnou main.
- Žiadne produkčné aktivovanie, Telegram test, prístup k súkromnému repozitáru,
  zmena Secrets/Variables, portfólia ani obchodných pravidiel.
- GitHub-hosted nový test spustí až normálny push výskumných zmien. Jeho výsledok
  sa nepovažuje za známy v čase tohto lokálneho záznamu; nezávislé budúce
  predikčné výsledky sú zatiaľ N/A.

## Následná GitHub kontrola po pushi

- V11.1 Analytical Release Review, run 40705360101: **SUCCESS**.
- Prediction Research Shadow, run 40705360099: **SUCCESS**, Artifact vytvorený.
- Verejná auditná anotácia: 15 aktuálnych zdrojov / 33 pokusov, produkčné
  aktivovanie false, nezávislé potvrdenie false, dozreté paper výsledky 0.
- Podklady: GITHUB_VERIFICATION.json. Toto overuje čistý runner a zber;
  neznamená preukázanú presnosť predikcií. Cenové tabuľky v tomto adresári
  pochádzajú z explicitne datovaného lokálneho výskumu, nie z neprečítaného ZIPu.
