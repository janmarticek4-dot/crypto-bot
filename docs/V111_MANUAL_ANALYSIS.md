# Ručná kompletná analýza V11.1

Táto zmena je návrh v samostatnej vetve. Zatiaľ nie je zlúčená ani testovaná skutočným odoslaním do Telegramu.

## Po schválení a nasadení

1. Otvor existujúci repozitár `janmarticek4-dot/crypto-bot` → **Actions**.
2. Vľavo vyber existujúci workflow **Crypto AI Bot V10.6** (názov workflow zostáva zachovaný).
3. Klikni **Run workflow**, ponechaj vetvu **main**.
4. Zaškrtni **Ručná analýza V11.1 — kompletný aktuálny report do Telegramu**. Všetky ostatné ručné možnosti ponechaj vypnuté, najmä staršiu ručnú analýzu V10.6, deep search a import portfólia.
5. Klikni zelené **Run workflow**. Aktuálny kompletný report príde po pridelení runnera, zbere a spracovaní dát. GitHub môže beh zaradiť do frontu; presná okamžitá minúta nie je garantovaná.

Môžeš takto spustiť nový report aj desaťkrát denne. Každé nové Run workflow má nové GITHUB_RUN_ID. **Re-run jobs/Re-run all jobs toho istého behu nevytvoria nový report**, aj keď sa zvýši GITHUB_RUN_ATTEMPT. Na zámerne nový report použite znova Run workflow, nie Re-run.

## Implementácia a hranice

- Rovnaký schválený immutable source SHA pre automatický aj ručný job, ten istý integrated renderer, pôvodné technické pravidlá V10.6, fundamenty, makroúdaje, metriky a súkromná príloha. Žiadny druhý analytický bot alebo nový výpočtový model. Zmenený source pin je potrebný na sprístupnenie ručnej vetvy; naplánovaná cesta má regresné testy.
- Nový checkbox vyberie existujúci v111-analytical-pilot job aj mimo07/15/20 okien. Vždy ide o kompletnú kryptomenovú analýzu, nie o USA-only report. Nadpis RUČNÁ a ID behu odlišujú správu od plánovanej analýzy.
- Predkontrola vyžaduje explicitný workflow_dispatch na main, aktívne V111_INTEGRATION_ENABLED=true a vypnuté ostatné ručné akcie. Pri konflikte voľby zlyhajú bezpečne, nevykoná sa import súkromnej evidencie ani starý V10.6 report.
- Pri novom checkboxe sa job crypto-bot nespúšťa, takže jeden ručný beh nemôže naraz poslať aj starý V10.6 report. Pravidelný schedule a native main.py zostávajú bez zmeny; plánované behy ďalej vykonávajú tichý monitoring a bezpečnostné alerty. Pôvodná concurrency skupina a cancel-in-progress=false zostávajú: behy môžu čakať vo fronte, nepoužíva sa rušenie monitoringu.
- V rovnakom existujúcom verejnom denníku pribudne oddelená sekcia `manual_slots`, kľúč `github-run-<GITHUB_RUN_ID>`. Neukladá skutočné pozície ani celú správu, iba stav a čas. Nevytvára sa nový repo/súbor so stavom a existujúci denník sa neresetuje. Tento PR nemení jeho aktuálny obsah.
- Ručný report nemení/prerezáva žiadny plánovaný slot, ranné quotes, makro históriu ani prognózy. Ani ručné spustenie priamo o07:00 alebo15:00 nespotrebuje automatický slot. Ručné ID nezávisí od času ani run_attempt a zostáva zachované pri plánovanom mesačnom čistení slots.
- Existujúci SHA/CAS zápis attempting pred Telegramom zostáva. Konflikt zabráni odoslaniu. Sent/attempting/uncertain sa nikdy automaticky neposielajú znovu. Zlyhanie pred zápisom attempting nevykonalo Telegram a môže sa bezpečne skúsiť znova. Zlyhanie po odoslaní, vrátane zápisu finálneho sent, môže zanechať attempting; aj ten blokuje automatické opakovanie.
- Dlhý report sa delí pôvodnou funkciou chunks a posiela postupne, jeden HTTP pokus na časť. Po chybe časti sa ďalšie neposielajú, stav je uncertain a rerun neposiela report znovu. Nejde o absolútnu exactly-once sieťovú garanciu; po neurčitom alebo čiastočnom doručení musí človek overiť chat. Automaticky nemažte manual_slots ani neprerábajte uncertain na nový pokus.
- Súkromný text sa pripája až po verejnom journal zápise a nejde do neho ani do diagnostického Artifaktu. Portfólio sa iba číta existujúcou schválenou cestou; ručný beh nemení evidenciu ani obchody.
- Zostáva limit veľkosti existujúceho denníka800kB. Manuálne záznamy sú malé a neobsahujú quotes/report. Pri dosiahnutí limitu systém odmietne ďalší zápis/odoslanie, nemaže potichu deduplikačné záznamy; archivácia vyžaduje samostatnú kontrolu.

## Overenie pred merge

149 offline testov (pôvodných139 +10 ručných): kedykoľvek,10 nových behov, deduplikácia rovnakého run_id aj s novým attempt, všetky tri doručovacie statusy, CAS konflikt, Telegram timeout, multipart prerušenie, manuálne spustenie v rannom/USA okne, následný nezávislý plánovaný report a canary súkromného textu iba v mockovanom odoslaní. Použité syntetické fixtures, skutočný Telegram, bot_state, denník a súkromné úložisko sa nevolali/neprepisovali.

Produkčný main.py, USA implementácia, obchodné pravidlá, Secrets a živý stav sú bez zmeny. Toto je samostatný PR; nič nemergovať ani neskúšať v produkčnom Telegrame pred schválením.

## Návrat späť

Ak po nasadení ručné spúšťanie nebude fungovať, nepoužívať Re-run na opakované doručenie. Automatické reporty zostávajú vo vlastných slotových záznamoch. Vrátiť iba tento PR/workflow source pin riadnym revertom, nikdy bot_state alebo doručovací denník zo starého commitu. Nevymazať manual_slots — už odoslané/neurčité záznamy musia blokovať opakované pokusy.
