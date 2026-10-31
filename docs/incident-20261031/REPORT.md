# Incident 31. 10. 2026 – overené príčiny

Read-only audit GitHub API a job logov: https://github.com/janmarticek4-dot/crypto-bot/actions/runs/41185084555 (Artifact obsahuje úplný bezpečný prehľad).

* Produkčné schedule behy dnes: 41157775801 vytvorený/začal 01:57:44 UTC (02:57 Bratislava), native job 01:57:46; následne 41183335169 vytvorený/začal 08:08:00 UTC (09:08 Bratislava), native job 08:08:03. V 06:00–07:30 UTC (07:00–08:30 Bratislava) neexistoval beh. Nie je to rad runnera: created_at = run_started_at pri oboch existujúcich behoch. GitHub neposkytol dôkaz interného dôvodu vynechania schedule; netvrdíme konkrétnu príčinu infraštruktúry.
* V 09:08 pilot-slot skončil úspešne, analytical job bol SKIPPED, nie FAILED. Staré okno bolo 07:00–08:30. Ranný canonical slot v denníku chýba; žiadny Telegram pokus o rannú analýzu nebol vykonaný. Health job správne zistil MISSING a spôsobil červený celkový beh. Nešlo o zlyhanie market API ani Python exception pri rannej analýze – tá sa vôbec nespustila.
* Native monitoring na commite cc9e04355d620bf0d4f1ced8d6c8c37f790c0d29 použil nezmenený main.py V10.6; log potvrdzuje native_alert_sent. Analytický zdroj bol nastavený 297a888, ale job sa v tomto behu nevykonal. Private command source 297a888; health source 929bd638. Rozdiel verzií bol skutočný rozdiel ciest, nie iba nadpis.
* main.py _crash_alert_prompt vyžadoval voľné AI confidence/drawdown; _validated_crash_alert akceptoval >=80 a >10. Uložený public crash_monitor má confidence=88 a expected_drawdown=13. Nie je to kalibrovaný model ani empirická pravdepodobnosť. Nová produkčná monitor cesta túto funkciu nevolá. Obchodné evaluate/BUY/SELL pravidlá main.py zostávajú nezmenené.

## Opravy

* Zdieľané časové okná s ZoneInfo: ranný catch-up 07:00–11:00; USA 15:00–17:00; večer 20:00–23:00. Ciele zostávajú 07/15/20. Zmeškaný report sa označí plánovaným aj aktuálnym časom a používa čerstvé údaje. UTC posuny sa nevypočítavajú napevno.
* Rovnaké canonical slot IDs, aj pri ručnom bezpečnom doplnení. Pre-send výpadok API môže mať jeden retry až po prečítaní denníka a dôkaze, že neexistuje pokus. attempting/uncertain sa nikdy automaticky neprehrá. Telegram má jeden HTTP pokus na časť; SENT až po ok=true a message_id pre každú časť. Timeout po odoslaní zostáva UNCERTAIN, nie falošný úspech.
* Monitor V11.2: žiadne AI volania/probability. Dve čerstvé redakcie s odlišnými titulkami + aktuálne časované kombinované trhové oslabenie; žiadny alert len podľa indikátora. Zmrazené aktíva sú zmiernenie, nie ďalšia strata; plné krytie + obnovené výbery potlačia alert. Cena za24h je explicitne minulý pohyb. Nepredpovedá sa ďalší percentuálny pokles. Redakčná zhoda nie je dôkaz nezávislého pôvodného overenia ani potvrdenie samotnou Binance.
* Incidentové CAS záznamy v existujúcom verejnom analytickom denníku obsahujú iba verejné zdroje a stav doručenia; žiadne portfólio. Rovnaký incident sa neobnovuje iba po cooldowne/inom titulku; nové potvrdené zhoršenie (napr. obmedzenie výberov alebo insolvencia) sa vyhodnocuje oddelene. Starý odoslaný alert sa zohľadní bez nového odoslania, no jeho AI tvrdenia sa nepoužívajú ako dôkazy.

## Obmedzenia

GitHub cron nie je SLA. Pridané catch-up okno ani doplnkové UTC behy negarantujú presne 07:00; ak žiadny runner nepríde do konca okna, zostane MISSING. Nie je možné bezpečne garantovať exactly-once Telegram pri sieťovom timeoute; neistý pokus sa musí preveriť ručne. Monitor nepokrýva všetky udalosti; nedostupné/nespoľahlivé údaje znamenajú ticho a konkrétny diagnostický dôvod. Pozície, Secrets a obchodné výpočty sa nemenia. Testovacie vstupy sú syntetické, testy neposielajú Telegram.
