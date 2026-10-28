# Izolované spustenie a budúce overovanie

Produkčný runtime, main.py, run.yml, obchodné rozhodovanie, Telegram a portfólio
sa nemenia. Žiadne nové produkčné nastavenie sa neaktivuje. V1 zostáva v repozitári.
Nové moduly sa nepoužívajú v hlavnom reporte; neexistuje prepínač na ich nasadenie.

## Jednorazový shadow test

Actions → **Prediction Research Shadow** → Run workflow → branch **main**.
Bez zaškrtnutia `persist_public_research_journal` sa vykonajú iba verejné GET
zbery, offline testy a výskum. Žiadne Secrets/Groq/Telegram nie sú sprístupnené.
Artifact `prediction-research-<run_id>` obsahuje:

- REPORT.md, preview.txt — výsledok a reálny náhľad šiestich mincí;
- diagnostics.json — všetky modely, validácia/test, intervaly, režimy, ablácie;
- <COIN>-origins.json — jednotlivé časové body pre reprodukovateľné prepočty;
- historical-inputs.json, current-public-inputs.json, input-manifest.json —
  verejné vstupy, presné časové rozsahy, hashe a verzie závislostí;
- source-diagnostics.json — rozdiel HTTP/sieť/schema/aktuálnosť/relevancia;
- public-predictions.json, paper-results.json — samostatná evidencia, budúce
  výsledky iba po dozretí; žiadne hypotetické obchody ani skutočné pozície.

Úprava výskumných súborov v main spúšťa rovnaký **read-only** test na GitHub
runneri. Push nikdy nepovoľuje zápis denníka. Má samostatnú concurrency skupinu.

## Verejný paper archív — samostatné výslovné zapnutie

Manuálny checkbox `persist_public_research_journal` uloží iba verejnú výskumnú
štruktúru do `public-analytics/prediction-shadow.json`. Súbor je oddelený od
produkčného stavu a doručovacieho denníka. Migruje iba jeho pôvodný verejný
zoznam do obálky V2; súkromný stav sa nemigruje. Zápis prejde validáciou polí,
credential/privacy kontrolou, hashom predošlého obsahu a GitHub blob-SHA CAS.
Konflikt zápisu zlyhá; nevynucuje sa prepísanie. Rovnaký GitHub run ID ponechá
prvú prognózu, nový úmyselný run má vlastné ID. Výsledky sa nikdy spätne neprepisujú.

Denný plán o 10:25 UTC je pripravený, ale job je preskočený, kým nie sú súčasne
nastavené `PREDICTION_PAPER_ENABLED=true` a
`PREDICTION_PAPER_APPROVED_VERSION=research-v2-20261028`. Tieto Variables sme
**nemenili ani nevytvárali**. Plán je výhradne výskumný, bez Telegramu, odlišný
od nezmenených produkčných slotov 07:00/15:00/20:00 Bratislava a monitoringu.
Čas GitHub cron nie je garantovaný. Denná frekvencia obmedzuje prekrývanie a
kapacitu denníka; 14-dňové výsledky zostávajú štatisticky závislé aj pri dennom zbere.

600 predikcií a 10000 vstupných vintage záznamov je pevný limit. Pri naplnení
kapacity nevyhodnotenými prognózami sa zápis odmietne, nevyhodnotené sa nevymažú.
Staršie vyhodnotené záznamy majú obmedzenú retenciu. Vstupné vintage sa deduplikujú podľa zdroja, hodnoty a UTC dňa, aby časté
ručné behy nespotrebovali archív. Dlhší archív je potrebný pre posun tréningového
okna; malý archív kratší než odstup tréning/test by fundamentálnu abláciu znemožnil.
Súhrnné celoživotné počty,
súčet chýb a zásahy smeru/pásma sa uchovávajú samostatne v pevných 18 slotoch;
medián a bootstrap sa počítajú iba z označeného zachovaného okna. Hlavné paper
metriky sa počítajú na neprekrývajúcich sa horizontoch; celoživotné súčty všetkých
prognóz sú iba opisné, nie počet nezávislých výsledkov. Re-run starého
GitHub ID mimo retencie nevytvorí novú prognózu pod starým ID. Maximálne 48 dozretých
endpointov sa načíta za beh; neúspešné sa nechajú nevyhodnotené pre ďalší beh.
Artifacts majú 14-dňovú retenciu. Nie sú trvalým úložiskom portfólia ani jedinou
kópiou paper prognóz, ak je zapnutý verejný denník. Pre dlhodobú nezávislú
reprodukciu historických testov treba stiahnuť vstupný Artifact; denník obsahuje
príznaky a hashe, nie kompletnú nekonečnú históriu OHLCV.

## Ďalší jeden experiment a podmienky rozhodnutia

Zmraziť túto špecifikáciu a zbierať budúce predikcie bez ladenia na ich výsledkoch.
Prvý kontrolný bod po 90 dňoch pre 24h smer/MAE; nevyhlásiť tým úspech 14d modelu.
Pri 14d horizonte by 30 neprekrývajúcich sa výsledkov vyžadovalo približne 420 dní.
Porovnať na rovnakých časoch nezmenenú cenu, trend a vopred vybraný model;
pre fundamentálnu abláciu rovnaké tréningové riadky aj testovacie originy.

Doterajší výsledok neoprávňuje produkčné zapojenie. Prípadné budúce schválenie
musí byť samostatné a zahŕňať preukázanú výhodu, kontrolu neistoty a zmenu
schváleného analytického runtime zdroja. Žiadne automatické preučenie alebo
prepnutie produkcie podľa niekoľkých dobrých výsledkov.
