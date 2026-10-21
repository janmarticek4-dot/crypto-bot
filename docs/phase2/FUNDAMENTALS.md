# Fundamentálna vrstva fázy 2

Nový modul `v11/fundamentals.py` je informačná vrstva. **Nemení produkčné
BUY/SELL ani pravidlá alertov.** Neoverené titulky sa nemenia na potvrdené udalosti.

## Pokrytie a aktuálne overenie

Skutočné výsledky požiadaviek, čas overenia a citované verejné udalosti sú v
`fundamental_sources.json`.

| Oblasť | Zdroj | Aktuálny výsledok |
|---|---|---|
| Fed / menová politika | federalreserve.gov press RSS | N/A, cloud proxy 403 |
| CPI / zamestnanosť | bls.gov RSS | N/A, cloud proxy 403 |
| Budúce termíny CPI / jobs | bls.gov release calendar ICS | N/A, cloud proxy 403 |
| PCE / spotreba | apps.bea.gov RSS | N/A, cloud proxy 403 |
| Regulačné udalosti | sec.gov press releases RSS | N/A, cloud proxy 403 |
| AAVE governance | governance.aave.com RSS | N/A, cloud proxy 403 |
| ONDO udalosti | blog.ondo.finance RSS | N/A, cloud proxy 403 |
| Incidenty / regulácia / crypto udalosti | Cointelegraph RSS | dostupné aktuálne klasifikované titulky |
| Rovnaké sekundárne pokrytie | CoinDesk RSS | HTTP úspech, nula relevantných čerstvých položiek |
| Token unlock | overiteľný štruktúrovaný projektový kalendár | N/A; bez potvrdeného zdroja sa neimplementuje odhad |
| SOL / TAO / FET technické vydania | overené GitHub Atom feedy anza-xyz/agave, opentensor/subtensor, fetchai/fetchd | HTTP 200, bez čerstvých relevantných položiek v 72h okne |
| RENDER governance | rendernetwork/RNPs commit Atom | HTTP 200, bez čerstvých položiek; návrh ≠ schválenie |

Fed/BLS/BEA/SEC/project endpointy sú implementované ako adaptéry, **ich aktuálna
funkčnosť na sieti nebola preukázaná**. HTTP 403 vzniká už pri proxy CONNECT;
nejde o dôkaz, že samotný web feed neexistuje alebo že odmietol používateľa.
Keď bude sieťový prístup povolený, treba overiť endpointy, formáty a prípadné
oficiálne presmerovania. Žiadna sieťová politika nebola obchádzaná ani publikovaná.

## Spracovanie

- RSS aj Atom, timezone-aware dátumy; pri Atom `updated` sa zmena nezamieňa s dátumom vydania ani s aktiváciou upgrade na sieti.
- Oficiálne projektové URL sa overujú aj podľa presnej cesty repozitára, nie iba github.com hosta.
- chýbajúca časová pečiatka sa nevymýšľa.
- Len novinky za posledných 72 hodín; budúce RSS dátumy sa odmietnu.
- ICS udalosti do 30 dní, explicitná časová zóna/DST, rozlíšený dátum vydania a
  dátum udalosti. Floating/all-day termín sa nepremení na vymyslený presný čas.
- Deduplikácia URL + normalizovaný titulok; odstránené tracking parametre.
  Mesiace rovnakého kalendára zostanú oddelené podľa dátumu udalosti.
- Cache 6 hodín, timeout, obmedzená veľkosť odpovede; zlyhanie = N/A s dôvodom,
  nie nulový počet udalostí vydávaný za potvrdenie pokoja na trhu.
- Oficiálny štítok len pri URL daného vydavateľa; komunitná governance a médiá
  sú označené ako návrh/správa vyžadujúca nezávislé potvrdenie.
- Každá udalosť má zdroj, URL, pečiatku, kvalitatívnu dôveryhodnosť a vysvetlený
  možný mechanizmus dopadu. Mechanizmus nepredstiera nameraný účinok na cenu.
- AI nemá právo dopĺňať nové fakty. Nové dáta sa neprenášajú do obchodných pravidiel.

## Čo zostáva na overenie

Povoliť pri samostatnom rozhodnutí o ďalšom teste cloud domény:
`www.federalreserve.gov`, `www.bls.gov`, `apps.bea.gov`, `www.sec.gov`,
`governance.aave.com`, `blog.ondo.finance`. Potom zopakovať požiadavky a parsery
na skutočných dátach; token unlocky potrebujú priamy overiteľný zdroj projektu.
Bez toho sa nemá tvrdiť plné makro a fundamentálne pokrytie.
