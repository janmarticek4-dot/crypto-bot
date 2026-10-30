# Súkromná evidencia cez Telegram

Toto nie je obchodný systém. Príkaz oznamuje iba obchod, ktorý používateľ už sám vykonal. Jediným zdrojom pravdy zostáva `advisory_portfolio` v existujúcom AES-GCM zašifrovanom `crypto-bot-state-production`. Verejný `bot_state.json`, predikčné denníky a výstupy Artifacts sa nepoužívajú na súkromné údaje.

## Prvé použitie

V existujúcom súkromnom chate bota pošli `/pomoc`, potom `/portfolio`. Over skutočné množstvá. Následne oznám **iba už vykonaný nový obchod**, napríklad `/predal TAO 0.5 cena 250 poplatok 1`. Klikni na **POTVRDIŤ** alebo **ZRUŠIŤ**. Tlačidlo platí 30 minút od spracovania. Tieto príklady nie sú pokyn ani skutočný obchod a nasadenie ich nezapisuje.

- `/predal TAO`: uzavrie celú evidovanú pozíciu, cena/výnos zostanú neznáme.
- `/predal SOL TAO`: jedno potvrdenie pre obe pozície, všetko alebo nič.
- `/predal TAO 300 USD cena 250`: predaných presne 1,2 jednotky; hrubá hodnota 300 USD.
- `/kupil SOL 500 USD cena 100 poplatok 5`: 5 SOL, celkový výdavok 505 USD, all-in priemer 101 USD.
- `/kupil SOL 505 USD celkom cena 100 poplatok 5`: ten istý obchod zadaný ako celkový výdavok.
- `/kupil FET 1000 cena 0.18`: 1000 jednotiek, **neznámy skutočný poplatok**, all-in náklad neúplný.
- `/hotovost 8500 USD`: samostatná deklarácia hotovosti, až po potvrdení. Nákupy/predaje zostatok automaticky nemenia; po nich sa označí na kontrolu.
- `/kupil SUI 500 USD cena 1.50`: CoinGecko search overí identitu. Pri viacerých identitách bot vypíše možnosti `/token SUI id`. Po výbere zopakuj nákup a potvrď. Výber identity sám nezakladá pozíciu. Pri výpadku ceny je možná evidencia overenej identity s výslovným upozornením, bez vymyslenej ceny. Pri neoverenej identite sa zápis odmietne.

Množstvá a náklady používajú Decimal, uložia sa ako desatinné reťazce. Delenie s nekonečným desatinným rozvojom používa 60 platných číslic; nejde o float ani presnosť garantovanú eToro. Zachovávajú sa staršie číselné hodnoty a neznáme vstupy. Čiastočný predaj nemení jednotkový priemer; dokúpenie váži all-in náklady iba ak sú všetky známe. Starý náklad sa nevymýšľa. EUR pozície sa USD obchodom nemenia bez explicitnej konverzie. `/portfolio` používa čerstvú USD kotáciu (najviac 15 minút), inak neúplnú hodnotu. P/L je pred budúcimi nákladmi predaja. Priemerný all-in náklad nie je cena bez poplatkov.

Token v portfóliu automaticky nepridáva model V2, indikátory ani fundamenty. Hlavná šestica a jej analytika zostávajú rovnaké. Už nevlastnená minca sa vyhodnocuje ako kandidát na nový nákup, nie HOLD. Pri nečitateľnej súkromnej evidencii sa držba nepredpokladá.

## Dostupnosť a bezpečnosť

Polling je existujúca súčasť `run.yml`, každých 15 minút; GitHub môže beh oneskoriť alebo vynechať. Potvrdenie sa spracuje pri ďalšom behu; jeho 30-minútová platnosť sa kontroluje pri spracovaní. Preto pri pomalom pollingu môže potvrdenie vypršať aj po včasnom kliknutí — vtedy zopakuj príkaz. Nie je to nepretržitý chat. Možnosť `Spracovať príkazy portfólia` v **Run workflow** umožňuje urýchliť polling; neposiela analýzu. `cancel-in-progress: false` zachováva jeden produkčný beh. Telegram čakajúce updates uchováva najviac 24 hodín; staršie príkazy sa nezapisujú.

Prijímajú sa len privátne správy so zhodným `TELEGRAM_CHAT_ID` **aj** `ADVISORY_TELEGRAM_USER_ID`. Bez owner ID sa updates nespotrebujú. Webhook sa nikdy neodstráni automaticky; existujúci webhook polling zablokuje. V produkcii musí zostať jediný poller. Staré priame `POZICIA`/`UZAVRETA` príkazy sa už nevykonávajú, aby neobchádzali potvrdenie.

Offset, čakajúci návrh, potvrdená transakcia a evidencia sa ukladajú do rovnakého šifrovaného CAS checkpointu. Návrh sa viaže na hash inventára; zmena inventára medzi návrhom a potvrdením ho zneplatní. Zápis používa existujúce šifrované zálohy a ochranu SHA. Pri konflikte sa nič neprepisuje ani automaticky neopakuje. Po úspešnom zápise a zlyhaní Telegram odpovede sa obchod neopakuje; používateľ overí `/portfolio`. Históriu tvorí posledných 1000 transakcií v checkpointoch a staršie šifrované Git revízie/zálohy. Nie je to účtovný/exportný daňový systém.

Bezpečnostný workflow vykonáva offline simulácie, read-only kontrolu existujúceho stavu, owner konfigurácie a webhooku; nevypisuje identitu, množstvá, tokeny ani dešifrované dáta. Nevolá getUpdates a neposiela Telegram. Žiadne súkromné Artifacts. Vlastný testovací chat nebol použitý. Testy nikdy nezapisujú do skutočného portfólia.

## Nasadenie / návrat

Najskôr uložiť kód, spustiť `Telegram Inventory Safety Review`, potom pripnúť schválený plný SHA do existujúceho `private-advisory-updates` a analytickej časti `run.yml` (nový čítač musí podporovať Decimal reťazce a dynamické symboly). Nemenia sa Secrets, obchodné pravidlá, monitoring ani harmonogramy. Analytické nasadenie sa overí existujúcim read-only source validation.

Návrat: vypnúť iba príjem príkazov (`PRIVATE_INVENTORY_COMMANDS_ENABLED=false` ako repository variable; nový job rešpektuje), zachovať kompatibilný nový čítač súkromného stavu. **Nevracať starý priamy poller ani starý validátor po prvom novom zápise**. Šifrovaný stav nevracať/resetovať automaticky; prípadnú obnovu riešiť existujúcou explicitnou CAS obnovou.


## Overenie 30. 10. 2026

Offline regresie: **393 testov**, vrátane nových testov potvrdení, viacnásobného predaja, presných desatinných výpočtov, váženého priemeru, poplatkov, nejednoznačnej identity, zlyhania zdroja, neautorizovaných správ, duplicít, expirácie, CAS konfliktu, šifrovaných záloh a zmeny HOLD → WAIT po predaji. Všetky vstupy testov sú syntetické. Neskúšal sa skutočný zápis/obchod ani reálna Telegram odpoveď.

GitHub-hosted overenie potvrdilo čítanie existujúceho zašifrovaného stavu, nastavený chat, neprítomnosť webhooku, vyhľadávanie SUI aj jeho čerstvú cenu. **Chýba `ADVISORY_TELEGRAM_USER_ID`**, preto sa príjem príkazov pri chýbajúcom ID preskočí ešte pred getUpdates alebo zápisom. Analýzy sa tým nevypínajú. Bezpečnostný test rozlišuje úspešné offline testy od chýbajúceho prevádzkového nastavenia.

Na zapnutie: GitHub → tento repozitár → **Settings → Environments → production-advisory → Add environment secret**. Názov `ADVISORY_TELEGRAM_USER_ID`, hodnota tvoje **osobné číselné Telegram user ID**, nie token ani používateľské meno. Ak existujúci chat je naozaj súkromný s tebou, osobné ID sa zhoduje s jeho kladným chat ID; nepreberaj ID skupiny ani bota. Kód vie použiť aj rovnomennú environment variable, ale Secret je vhodnejší. Hodnotu neposielaj do verejného issue/logu. Nemusíš vytvárať nový PAT ani repozitár. Po uložení sa príkazy automaticky povolia pri ďalšom plánovanom behu (ak `PRIVATE_INVENTORY_COMMANDS_ENABLED` nie je `false`). Potom začni `/pomoc` a `/portfolio`.

Záložný bod: `backup/before-telegram-inventory-20261030` → `0388c90484e9149020c1a49406495aeabdf16b3d`. Medzitým pribudnutý produkčný stav `22f2700` bol zachovaný normálnym merge, nie resetom/force-push.
