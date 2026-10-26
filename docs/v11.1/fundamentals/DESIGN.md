# Fundamentálna vrstva – vývojový návrh

Produkčná main, stratégie, monitoring, Telegram a privátny stav sa týmto nemenia.

## Zistené príčiny

Pôvodná šablóna zobrazovala technické číselné údaje pred fundamentmi, titulok s URL nahrádzal analýzu a oznámenia zo softvérových/governance repozitárov boli takmer jediným projektovým podkladom pre viaceré mince. Úspešný HTTP/RSS parser neznamená, že obsahuje aktuálnu relevantnú správu. Nedostupný zdroj neznamená neutrálny fundament.

## Implementácia

- `v11/fundamental_analysis.py`: oddelenie doloženého oznámenia od nepotvrdenej realizácie; významnosť, podmienený mechanizmus, dotknuté mince, chýbajúce potvrdenie, publikovanie a zber; žiadne pravdepodobnosti ani obchodné rozhodnutia.
- Titulok je citácia zdroja, nie overenie obsahu článku. Primárne dokumenty a realizáciu väčšiny oznámení zatiaľ neoverujeme automaticky. Preto neprezentujeme kategorický rastový/poklesový verdikt.
- GitHub release/commit, návrh governance a partnerstvo nemajú automaticky pozitívny ekonomický dopad. Softvérové/governance záznamy nie sú významnou správou v úvodnom súhrne.
- Prísna aktuálnosť (správa najviac 72 h, zber 24 h, bez budúcich dát), normalizované titulky pri deduplikácii. Rozdielne titulky tej istej udalosti ešte môžu vyžadovať manuálne spojenie.
- Denné výnosy majú zmenu v bázických bodoch medzi poslednými dostupnými dátumami. Pri jedinom bode sa zmena nevymýšľa.
- CPI/PCE/UNRATE/PAYEMS: posledná a predchádzajúca **revidovaná** hodnota, merané obdobie oddelené od času publikovania; prvý výsledok a konsenzus zostávajú N/A. Nemožno z toho spätne rekonštruovať prekvapenie pri zverejnení.
- `v11/project_metrics.py`: tri bezkľúčové adaptéry DeFiLlama pre poplatky Aave, príjmy Aave a poplatky siete Solana. Iba uzavreté UTC denné agregáty, zdrojová URL, zber a merané obdobie; chýbajúci publikovací čas N/A. Príjmy protokolu nie sú automaticky príjmom tokenu. Kompatibilita živého API sa musí potvrdiť z runnera, lokálne je host blokovaný.
- TVL zostáva dostupné pre Aave, Solana a Ondo len pri čerstvých pozorovaniach. Zmena TVL nie je čistý tok peňazí.
- Úvod reportu: trh a neistota príčiny, významné udalosti, stále pozorované faktory, podmienený výhľad; každá minca má vlastný fundamentálny blok. Podrobné indikátory sa presúvajú do prílohy.
- `fundamental_evidence.json` zachováva štruktúrované vyhodnotenie a maticu tematického pokrytia. Je zaradený do explicitného zoznamu povolených shadow artefaktov.

## Zdroje a náklady

| Oblasť | Zdroje | Bezplatnosť a obmedzenia |
|---|---|---|
| Fed/FOMC | federalreserve.gov RSS, kalendár | verejné oficiálne dáta; kalendár nemusí obsahovať overený presný čas |
| CPI/zamestnanosť | BLS RSS/ICS; FRED časové rady | bez plateného API; FRED posledné revidované údaje, nie prvý release |
| PCE/HDP | BEA RSS; FRED PCEPI | verejné; konsenzus a prekvapenie nepokryté |
| ECB | oficiálne RSS, záložný blog | blog nie je rozhodnutie banky |
| Regulácia | SEC/CFTC RSS | obsah nie je úplný ETF/súdny kalendár |
| Výnosy | Treasury XML, záloha FRED CSV | denné pozorovania, nie živé kotácie |
| Projektové oznámenia | Aave governance, Ondo blog; GitHub vydania SOL/TAO/FET, RENDER governance | oznámenia nie sú dôkaz adopcie; sekundárna záloha nemení dôveryhodnosť na primárnu |
| Správy/geopolitika | CoinDesk/Cointelegraph verejné RSS | iba sekundárne publikované tvrdenia, neúplné globálne pokrytie |
| Ekonomika protokolov | DeFiLlama verejné TVL/fees/revenue | agregátor, nie auditované účtovníctvo; rešpektovať limity API |

Žiadne obchádzanie paywallu, žiadne platené vyhľadávanie. Existujúca cache fundamentov 15 minút, makro výnosov hodina. Limity poskytovateľa môžu zmeniť dostupnosť.

## AI

Groq zostáva existujúcim voliteľným poskytovateľom. `rank_evidence()` môže vrátiť iba maximálne tri ID existujúcich významných podkladov, nie nový text/fakty. Neplatné ID, dodatočný text, výnimka a HTTP 429 vedú na deterministické poradie. Obsahová cache 12 h, limit pokusu raz za 2 h v dodanom stave; bez okamžitého retry. V jednorazovom shadow procese je cache iba v pamäti; nejde o globálny limit medzi nezávislými behmi. Shadow používa Groq len pri výslovnom `--use-groq`, bez kľúča ani raz.

Bezplatné tarify nie sú garantované: aktuálne podmienky overovať na https://console.groq.com/docs/rate-limits . Gemini má tiež bezplatné limity pre vybrané modely (https://ai.google.dev/gemini-api/docs/rate-limits), ale ďalší poskytovateľ nie je zapojený: nepriniesol by nové overené podklady a vyžadoval by ďalší kľúč. AI nedokáže nahradiť nedostupný zdroj. Súčasná verzia používa konzervatívne pravidlá interpretácie; nejde o autonómnu faktografickú analýzu celých dokumentov.

## Otvorené medzery

Overený úrokový konsenzus/FedWatch, prvé makro releases a vintages/revízne rozdiely, ETF/burzové čisté toky, DXY/likvidita, primárne geopolitické potvrdenia, úplné token unlocky/emisie a aktivity/príjmy TAO/FET/ONDO/RENDER zatiaľ nie sú spoľahlivo pokryté. Ongoing faktory staršie než 72 h sa automaticky neudržujú ako potvrdené naratívy; treba registry s overiteľnou platnosťou a následné vyhodnotenie účinnosti. Žiadny údaj o percentuálnom pokrytí všetkých významných udalostí nie je obhájiteľný. Uvádzame len dostupnosť endpointov a počet čiastočne pozorovaných tematických okruhov.

## Bezpečné overenie

`python scripts/test_offline.py` blokuje všetku nezamockovanú sieť. Živé preview: `BOT_DISABLE_TELEGRAM=1 BOT_DATA_MODE=shadow python scripts/v111_shadow.py --phase preview --output shadow-output/fundamentals-review`.

Z GitHub-hosted runnera: existujúci manuálny workflow v `crypto-bot` → Actions → registrovaný `run.yml` → Run workflow → vetva `feature/v11-1-review`, task `shadow`, phase `preview`. Na tejto vetve nemá produkčné úlohy. Artifacts obsahujú `morning.txt`, `evening.txt`, `fundamental_evidence.json`, `fundamentals.json`, `source_availability.json` a `summary.json`. Toto sú dve šablóny z jedného zberu, nie skutočný ranný/večerný test. Žiadne produkčné Secrets ani súkromné portfólio sa do shadow nenačítavajú.

## Chyby odhalené pri regresnom overení

Čas snapshotu vzniká pred zberom RSS. Použitie tohto skoršieho času na kontrolu `retrieved_at` nesprávne vyradilo správy získané o pár sekúnd neskôr ako „budúce“. Report teraz vyhodnocuje fundamenty voči skutočnému času zostavenia; čas ceny zostáva pôvodný. Regresný test kontroluje explicitný 30-sekundový rozdiel.

Geopolitický vzor musí používať hranice slova `war`; inak `warns`/`software` vytvárajú falošné geopolitické udalosti. Táto chyba je opravená a pokrytá testom. Deduplikácia rovnakých titulkov naprieč vydavateľmi nevytvára dve nezávislé potvrdenia.
