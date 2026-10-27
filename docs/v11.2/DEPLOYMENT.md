# Bezpečná aktivácia a návrat — nič zatiaľ nebolo vykonané

## Pred merge

1. Skontrolovať jediný PR `feature/v112-analytical-review` → `main`, report REPORT.md a oba označené syntetické náhľady. CI musí prejsť166 testami v čistom Python3.12 prostredí.
2. Overiť diff: žiadna zmena main.py, bot_state.json, trial-public/v111-delivery.json, pôvodných súkromných pravidiel/úložiska alebo Secrets. Priebežné nové stavové commity main zachovať normálnym merge, nikdy resetom, force-pushom alebo checkoutom starého stavu z feature vetvy.
3. Vykonať nový **V11.1 Integration Shadow** z tejto vývojovej vetvy, phase=preview, `v112_preview=true`. Ide o existujúci read-only workflow: prázdne Telegram/Groq tokeny, iba verejné dáta, Artifact `v111-integration-<run_id>-<attempt>`. Nová voľba je definovaná aj pre workflow_call. Ak UI neukáže input z vývojovej verzie, nespúšťať naslepo produkčný run.yml; použiť skontrolovaný reusable caller s touto verziou a source_sha alebo test až po schválenom merge, ešte s vypnutou V11.2. Nie je potrebný nový repozitár, bot ani API kľúč.
4. Overiť dostupnosť makro/DeFiLlama z GitHub-hosted runnera. Lokálne HTTP403 tunela nie je overenie runnera. Prijať obmedzenia dát iba výslovne; pri chýbajúcich zdrojoch report nemá tvrdiť kompletné pokrytie.
5. Voliteľný skutočný ranný/večerný shadow pár: ráno07:00–08:30 Bratislava phase=morning s V11.2, večer20:00–21:30 phase=evening s ID ranného behu, rovnaký skontrolovaný source SHA. Checkpoint nesmie byť prepísaný. Ak zber/reference chýba, N/A; syntetické príklady ani preview sa nepočítajú ako nezávislé časové body.

## Po samostatnom schválení

1. Skontrolovať, že repo premenná V112_ANALYTICS_ENABLED ešte nie je true; jej živú hodnotu tento audit nečítal/nemenil. V111_INTEGRATION_ENABLED a V111_TRIAL_ENABLED ponechať zapnuté ako v súčasnej produkcii.
2. Merge vykonať mimo07:00–08:30,15:00–16:30 a20:00–21:30 Bratislava, po dokončení práve bežiaceho workflow. Zachovať dosiahnuteľnosť pripnutého runtime commitu (bežný merge commit alebo ponechaná feature vetva pri squash merge). Zatiaľ žiadne testovacie Telegram odoslanie.
3. Pri chýbajúcom/false V112_ANALYTICS_ENABLED workflow stále checkoutuje presný existujúci V11.1 pin `c012eca0fe8967220025deb60d431d7621f40485`. Starý929bd63 fallback pri vypnutej V11.1 sa nemení. Merge sám nemá aktivovať V11.2.
4. Až po schválení dát/kvality nastaviť v existujúcom repo Settings → Secrets and variables → Actions → Variables iba **V112_ANALYTICS_ENABLED=true**. Táto nová konfiguračná premenná nie je Secret; pôvodné Secrets a premenné sa nemenia. Výber nového zdroja vyžaduje zároveň V111_INTEGRATION_ENABLED=true. Konkrétny nemenný source SHA bude v SOURCE.json a vo workflow.
5. Používa sa pôvodný scheduler a jeden sender/denník:07:00/20:00 plná V11.2,15:00 pôvodný USA kontext, tichý15-minútový monitor. Ručne: Actions → Crypto AI Bot V10.6 → Run workflow → main → existujúci checkbox **Ručná analýza V11.1 — kompletný aktuálny report do Telegramu**. S prepínačom používa V11.2; ostatné ručné voľby vypnuté. Každý nový run_id nový report, rerun toho istého ID neduplikuje. Skutočné ručné odoslanie až s výslovným schválením.
6. Prvý nový report má porovnanie N/A, ak neexistuje úspešne doručená V11.2 referencia. Až ďalší úspešný, odlišný zber ho môže porovnať. Nepreberať staré výstupy ako nové osobné odporúčania. Ručné zbery nespotrebujú ranný/USA/večerný slot ani ranný checkpoint.
7. Verejný Artifact `v111-analytical-diagnostics-<run_id>` pridáva `v112_analysis.json` k pôvodným detailom, risk diagnostike, fundamentálnym dôkazom a market snapshotu. Skutočné vlastníctvo/údaje o pozíciách sú až vo finálnom Telegrame a do Artifaktu nejdú. Kontrola súkromia má konkrétny rozsah, nie absolútnu sémantickú DLP záruku.

## Rollback

- Mimo uvedených okien, po dokončení bežiaceho workflow, nastaviť iba **V112_ANALYTICS_ENABLED=false**. Zachovať V111_INTEGRATION_ENABLED=true. Ďalší beh použije presný pôvodný c012eca zdroj s ručným spustením a rovnakým spoločným denníkom.
- Neresetovať, nenahrádzať ani nemažte bot_state.json, trial-public/v111-delivery.json, manual_slots alebo attempting/uncertain/sent záznamy. last_analysis_v112 je verejný vlastný kľúč; stará verzia ho môže bezpečne ignorovať. Pri ďalšom zapnutí sa referencia staršia7 dní odmietne.
- Timeout/čiastočné doručenie neopakovať automaticky. Najprv preveriť chat a konkrétny slot; run_attempt nie je nový report. Nepoužívať V111_TRIAL_ENABLED=false ako rýchly fallback vnútri okna (iný natívny ledger môže vytvoriť duplicitu).
- Ak treba revert kódu, samostatne skontrolovaný revert iba tohto PR; nikdy force-push main alebo obnovenie starých stavových súborov.

Tento postup zatiaľ nie je vykonaný. Funkčné testy a úspešný live zber neznamenajú overenú výkonnosť osobných investičných odporúčaní. Nové BUY/SELL pravidlá naďalej vyžadujú samostatné historické a následné nové nezávislé overenie.
