# V11.2 na kontrolu

- [Audit, skutočné opravy, testy a zostávajúce obmedzenia](REPORT.md)
- [Syntetická ranná analýza](examples/morning.txt)
- [Syntetická ručná analýza a porovnanie od rána](examples/manual.txt)
- [Pôvodný V11.1 formát nad rovnakými syntetickými vstupmi](examples/v111-original-format.txt)
- [Izolovaný živý verejný preview — bez portfólia](examples/live-public-preview.txt)
- [Skutočná dostupnosť zdrojov v lokálnom prostredí](SOURCE_DIAGNOSTICS.json)
- [Kontroly živého testu a súkromia](LIVE_CHECK.json)
- [Postup aktivácie a rollback](DEPLOYMENT.md)

Nič nemergované/aktivované, žiadny testovací Telegram. Nové obchodné stratégie nie sú súčasťou PR. Osobné kontexty sa vytvárajú až pred odoslaním a nikdy sa neexportujú verejne.

## Stav PR

Vetva `feature/v112-analytical-review` je uložená na GitHube. Automatické vytvorenie draft PR bolo odmietnuté GitHub REST API chybou Forbidden; PR týmto nevznikol. Pripravený popis je v [PR_DESCRIPTION.md](PR_DESCRIPTION.md).

[Otvoriť porovnanie a vytvoriť jediný PR](https://github.com/janmarticek4-dot/crypto-bot/compare/main...feature/v112-analytical-review?expand=1)

GitHub CI sa nepovažuje za dokončené, kým PR nevznikne a jeho nový beh úspešne nedobehne. Uvedených166 testov je lokálny izolovaný offline výsledok, nie predstieraný výsledok GitHub runnera. Nemenil sa žiadny token ani Secret kvôli vytvoreniu PR.

## Následná požiadavka: priamy merge

Používateľ následne schválil integráciu do main bez nového PR. Aktuálny postup kontroly, zálohy a oddelenej aktivácie je v DEPLOYMENT.md. Staršia sekcia Stav PR opisuje historický pokus, nie požiadavku vytvoriť ďalší PR. Pri záverečnej kontrole pribudli4 opravné testy; aktuálny výsledok je170 offline testov.
