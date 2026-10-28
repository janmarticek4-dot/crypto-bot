# Záver kontroly

Predikčný model zostáva mimo produkcie. Výber sa vykonal na validácii; test nepreukázal robustnú výhodu nad nezmenenou cenou. Na viacerých kombináciách minca/horizont vybral samotný referenčný model flat.

Mierne lepšie výsledky jednotlivých alternatív existujú, ale príslušné párové intervaly zahŕňajú nulový rozdiel. Nevyberáme ich spätne na nasadenie. Príklady (nová MAE mínus flat; záporné je lepšie):
- AAVE, 24 h, ridge_technical: -0.022 p. b.; 95 % interval [-0.13557800863157035, 0.1168999418593101]; n=166.
- TAO, 7–14 dní, ridge_technical: -0.262 p. b.; 95 % interval [-2.233390508306167, 1.0300286433448798]; n=11.
- FET, 7–14 dní, regime_momentum: -0.391 p. b.; 95 % interval [-0.9444874805259786, 0.15630466363771967]; n=11.

Zlepšenie niektorých percent úspešnosti smeru oproti V1 nemožno pripísať iba modelu: zmenila sa definícia DO STRANY aj historický rozsah a frekvencia výsledkov. Všetky modely v novom porovnaní preto používajú rovnaké pravidlá.

Obdobia (UTC, začiatok / prvý validačný / prvý testovací bar / posledný uzavretý bar):
- SOL: 2024-07-17T04:00:00+00:00 / 2025-11-29T04:00:00+00:00 / 2026-05-14T20:00:00+00:00 / 2026-10-28T12:00:00+00:00
- TAO: 2024-07-17T04:00:00+00:00 / 2025-11-29T04:00:00+00:00 / 2026-05-14T20:00:00+00:00 / 2026-10-28T12:00:00+00:00
- FET: 2024-07-17T04:00:00+00:00 / 2025-11-29T04:00:00+00:00 / 2026-05-14T20:00:00+00:00 / 2026-10-28T12:00:00+00:00
- AAVE: 2024-07-17T04:00:00+00:00 / 2025-11-29T04:00:00+00:00 / 2026-05-14T20:00:00+00:00 / 2026-10-28T12:00:00+00:00
- ONDO: 2025-04-11T12:00:00+00:00 / 2026-03-16T12:00:00+00:00 / 2026-07-07T12:00:00+00:00 / 2026-10-28T12:00:00+00:00
- RENDER: 2024-07-26T08:00:00+00:00 / 2025-12-02T20:00:00+00:00 / 2026-05-16T16:00:00+00:00 / 2026-10-28T12:00:00+00:00

Ide iba o historický chronologický výskum už skúmaných rokov, nie nové nezávislé historické potvrdenie. Nová evidencia má zatiaľ **0 dozretých budúcich výsledkov**. Úspešnosť budúceho paper testu je N/A.

Pôvodné čísla z behu 40695605050 zostávajú neoverené pre Forbidden pri sťahovaní jeho Artifactu. Nový test nie je vydávaný za reprodukciu toho nedostupného súboru.
