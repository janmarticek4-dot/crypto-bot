# Predikčný výskum V2 — protokol, nie produkčná stratégia

## Čo sa opravilo

1. **Smer bez tolerancie:** V1 nazývala „DO STRANY“ iba presne nulový pohyb.
   V2 používa absolútny logaritmický výnos / volatilitu horizontu. Hranica je
   1/3-kvantil tejto veličiny z dozretých tréningových výsledkov, osobitne pre
   mincu a horizont. Faktor je potom zmrazený pre validáciu a test. Smer všetkých
   modelov aj skutočnosti sa klasifikuje rovnakou hranicou. Nie je to pravdepodobnosť.
2. **Sila trendu:** V1 lineárne extrapolovala 80-hodinový pohyb aj na 14 dní.
   Žiadne naučené váhy nemala. Nezmenená cena ju často porazila. V1 zostáva
   nemennou kontrolou. V2 testuje jeden vopred deklarovaný variant utlmenia
   momenta na 0,1 a regresiu s pevnou L2 penalizáciou 50; nejde o overené váhy.
   Po nahliadnutí do testových výsledkov sa tieto parametre nemenili.
3. **Volatilita:** audit nepotvrdil chybu indexovania vo V1: oba posunuté
   zoznamy v `zip(cs[-121:-1], cs[-120:])` správne zahŕňajú najnovší výnos.
   Vektorizovaná kontrola je testovaná aj na čerstvom cenovom šoku. Obe metódy
   používajú posledných 120 dostupných logaritmických výnosov. Škálovanie
   odmocninou času je predpoklad, nie dôkaz nezávislých výnosov; režimové
   a kvantilové testy skúmajú jeho nedostatočnosť, bez tvrdenia o opravenej chybe.
4. **Prekrývajúce sa výsledky:** historické testovacie originy sú teraz oddelené
   celým horizontom. 24h / 48–72h / 7–14d testujú konkrétne konce 24h / 72h / 14d,
   nie všetky extrémy medzi nimi. Závislosť medzi mincami a sériová závislosť
   môžu zostať. Počty sa nepovažujú za počet nezávislých investičných experimentov.
5. **Neistota:** priemer aj medián cenovej chyby, Wilsonov interval úspešnosti
   smeru/pásma, blokový bootstrap pre cenovú chybu a párové rozdiely. 400 pevných
   replikácií, kruhové bloky ceil(n^(1/3)); pri n < 5 interval chyby N/A.
   Výstupy obsahujú aj vyváženú úspešnosť a maticu zámen tried.
6. **Kalibrácia pásiem:** kvantily normalizovaných chýb dopredných prognóz iba
   v tréningovej časti, nie rezíduá modelu fitovaného na rovnakom výsledku.
   Kalibračné prognózy používajú iba vtedy dostupné dáta. Kvantily sú zmrazené.
   Pokrytie na teste je merané, nie garantované. Presné pravdepodobnosti N/A.
   Pôvodné V1 pásmo má samostatnú metriku; hlavné porovnanie všetkých bodových
   modelov používa rovnaký nový postup konštrukcie pásiem.
7. **Výber modelu:** prvých 60 % história tréning, ďalších 20 % validácia,
   posledných 20 % chronologický výskumný test. Labely cez hranicu sú vylúčené.
   Výber podľa validačnej MAE, minimum 8 výsledkov; žiadny výber podľa testu.
   Regresia sa v predpísanom walk-forward režime refituje z posledných 1200
   dozretých tréningových príkladov. Aj skoršie testovacie labely možno použiť
   neskôr, až po dozretí. Žiadna optimalizácia hyperparametrov na teste.
8. **Čas paper prognózy:** V1 zapisovala čas sviečky ako čas vytvorenia. Také
   záznamy sa zachovajú, ale nesmú sa označovať ako prospektívne potvrdenie.
   V2 ukladá reálny čas vytvorenia, dostupnosť zdrojov, verziu, hash kódu,
   vstupné príznaky, volatilitu a dátové hashe. Živá aktuálna cena kotví výnosový
   scenár založený na posledných uzavretých baroch. Cieľ je prvý minútový UTC
   bod najviac 60 sekúnd po požadovanom horizonte; skóruje sa presná OPEN cena
   danej 1m sviečky. Skutočný cieľový čas je uložený, chýbajúca cena = nehodnotené.
   Staré prognózy ani vyhodnotené výsledky sa pri opakovaní behu nemenia.

## Pevne testované modely

- flat: nezmenená cena;
- trend: lineárne pokračovanie posledných 20 uzavretých 4h barov;
- legacy_v1: pôvodná bodová metóda bez zásahu do originálneho modulu;
- regime_momentum: jeden pevný utlmený variant, bez predikčného skóre;
- ridge_technical: regularizovaná regresia normalizovaného log-výnosu;
- ridge_macro a ridge_macro_project: rovnaká regresia s historicky dostupnými
  pozorovaniami; chýbajúce skupiny sa nevyrábajú. Regresie sa nefitujú pri
  menej než 80 platných dozretých tréningových príkladoch.

Príznaky sú trend/momentum, RSI a jeho zmena, MACD a jeho zmena, realizovaná
volatilita, objem, BTC a relatívna sila. Korelované indikátory nie sú samostatné
potvrdenia; regresia ich regularizuje. Režim BULL/BEAR/SIDEWAYS určuje trend BTC,
HIGH_VOLATILITY/CRISIS_PROXY tréningový prah volatility a aktuálny výpredaj BTC.
CRISIS_PROXY nie je overená mimoriadna udalosť a nevytvára obchodný alert.
Historická kapitalizácia celého trhu, 1h multivariátna história, ETF toky, DXY,
orderbook a komplexná geopolitika tu nie sú preukázateľne pokryté. Živé 1h/1d
technické údaje ostávajú v diagnostických vstupoch; netvrdíme, že boli všetky
použité a historicky overené ako regresory.

## Fundamentálna ablácia bez spätného vymýšľania histórie

Porovnanie iba technika / technika+makro / technika+makro+projekty používa rovnaké
spoločné časové body aj rovnaké historické tréningové riadky. `ridge_technical_matched`
je kontrola pre túto abláciu; všeobecný `ridge_technical` využíva všetky dostupné
cenové dáta a nie je sám osebe kauzálnou kontrolou prínosu fundamentov. Ablácie
sa zatiaľ nezaraďujú do automatického výberu prognózy. Každé pozorovanie musí mať dostupnosť, čas zberu, URL a
identifikátor vintage. Revizia získaná dnes je dostupná až dnes. Nesmie sa
priradiť ku dňu meraného obdobia ako historicky známy údaj. Neznámy čas publikácie
ostáva null; konzervatívne available_at je prvé pozorovanie. Chýbajúce jednotlivé
premenné majú explicitný maskovací príznak; chýbajúca celá skupina znamená NO_DATA.
Pozorovania expirované po siedmich dňoch sa nešíria do nekonečna. Nie je
preukázaná prediktívna hodnota samotných úrovní makro veličín alebo titulkov.

Aktuálny archív historických vintage údajov chýba. Výsledok kombinovaných
modelov je preto **NO_POINT_IN_TIME_HISTORY**, nie „fundamenty nepomáhajú“.
Nový verejný paper denník môže uchovávať prvýkrát pozorované údaje pre budúce
porovnanie; nemení portfólio ani produkčný stav.

## Typ dôkazov a rozhodnutie

Roky 2024–2026 boli už skúmané. Ani chronologický test nie je nové nezávislé
potvrdenie. Pre každý režim sa uvádza vlastné n a neistota; najlepšia metóda
vybraná spätne v režime je iba opis, nie pravidlo prepínania modelov.
Viacero porovnaní zvyšuje riziko náhodného „víťaza“. Z výsledkov sa automaticky
nič neaktivuje. Cenová MAE nie je výnos stratégie. Nemení sa BUY/SELL/HOLD ani
nevzniká simulovaný výnos bez pravidiel vstupu/výstupu. Informačné zóny majú
nákladový scenár 1 % a 1,2 % na stranu plus 0,25 % nepriaznivý fill na stranu;
nie overený spread eToro. Falošný obrat môže nákladovú výhodu úplne zmazať.
