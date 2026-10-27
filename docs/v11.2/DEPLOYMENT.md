# Priama integrácia a samostatná aktivácia V11.2

Používateľ autorizoval bezpečný merge do main bez nového PR, nie aktiváciu. Opravy zostávajú v existujúcej feature/v112-analytical-review do ukončenia kontrol. Nevytvára sa ďalšia vývojová vetva.

## Kontroly a záloha

- 170 offline testov musí prejsť; nový public-source-check v existujúcom V11.1 Analytical Release Review overí bezplatné zdroje na GitHub runneri bez Telegram/portfóliových Secrets. Artifact: v112-runner-sources-<run_id>; tabuľka je aj v job summary. Test nemení produkčné súbory, súkromné úložisko alebo doručovací denník.
- Main pred merge sa označí nemenným tagom backup/main-before-v112-20261027-<shortsha>. Tag je bod návratu kódu, nie pokyn obnovovať starý bot_state alebo ledger.
- Bežný merge zachová najnovší bot_state.json a trial-public/v111-delivery.json z main. Konflikt/rejected push sa rieši fetch+merge, nikdy force-push/reset. Pôvodné obchodné pravidlá, main.py, private helper, USA kontext, cron a manuálny input sa nemenia.

## Prečo sa po merge V11.2 nezapne

GitHub API odmieta čítanie hodnôt repo Variables. Nemožno preto bezpečne predpokladať, že už existujúci V112_ANALYTICS_ENABLED nie je true. Výber nového zdroja vyžaduje navyše **V112_APPROVED_SOURCE**, ktorý sa musí presne rovnať novému runtime commitu zo SOURCE.json. Bez tohto nového konkrétneho schválenia sa aj pri náhodne true flagu stále používa pôvodný V11.1 pin c012eca. Žiadna premenná ani Secret sa v tejto práci nenastavuje.

## Zapnutie až po samostatnom súhlase

1. Skontrolovať výsledky runnera a prijateľnosť zostávajúcich zdrojových N/A. Odlišovať dostupnosť/aktuálnosť od úplnosti pokrytia. Softvérové testy nepreukazujú úspešnosť investovania.
2. Po schválení, mimo07:00–08:30,15:00–16:30 a20:00–21:30 Bratislava a po dokončení prebiehajúceho behu otvoriť existujúce repo → Settings → Secrets and variables → Actions → Variables.
3. V111_INTEGRATION_ENABLED a V111_TRIAL_ENABLED ponechať zapnuté. Nastaviť V112_APPROVED_SOURCE na presný candidate_v112_source zo SOURCE.json a V112_ANALYTICS_ENABLED na true. Obe sú konfiguračné premenné, nie Secrets. Ich hodnoty sa teraz nemenia.
4. Automatické07/20 prejdú na schválenú V11.2;15:00 ostáva existujúci USA kontext; tichý monitoring a mimoriadne alerty ostávajú. Ručne používať pôvodný checkbox Ručná analýza V11.1 v Actions → Crypto AI Bot V10.6 → Run workflow → main. Opakovaný ten istý run_id zostáva deduplikovaný.
5. Prvá doručená V11.2 analýza vytvorí vlastnú verejnú referenciu. Ďalšia sa porovná iba s odlišným, dôveryhodným predchádzajúcim zberom. Vlastníctvo, množstvá a nákupné ceny sa verejne neukladajú. Pokiaľ sa vyžaduje skutočný ranný/večerný test, spustiť existujúci Integration Shadow s v112_preview=true v reálnych oknách a rovnakým source SHA, večer s ID ranného behu; chýbajúca referencia znamená N/A.

## Rollback bez straty živého stavu

- Mimo reportových okien a po dokončení behu V112_ANALYTICS_ENABLED=false alebo odstrániť iba V112_APPROVED_SOURCE. V111_INTEGRATION_ENABLED=true zostáva. Tým sa vyberie presný pôvodný V11.1 zdroj s ručným spustením a rovnakým denníkom.
- Nerestaurovať bot_state.json, ledger, manual_slots ani súkromné úložisko zo záložného tagu. Sent/attempting/uncertain sa nesmú vymazať a report po timeoute sa automaticky neopakuje. last_analysis_v112 možno ponechať; stará verzia ho ignoruje, nová odmietne starú/neplatnú referenciu.
- Ak treba vrátiť kód, riadny revert iba integračných zmien s kontrolou chránených stavových súborov, nikdy reset alebo force-push main.

Žiadne nové obchodné pravidlá ani E1 sa neaktivujú. V11.2 zostáva bez individuálneho súhlasu vypnutá a žiadny testovací Telegram sa neposiela.
