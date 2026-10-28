# Zdroje a čas dostupnosti

Lokálny zber: 2026-10-28T14:20:07.132537+00:00; 4 aktuálne z 33 pokusov.
Stavy: {'NETWORK_BLOCKED': 25, 'STALE': 2, 'OK_NO_RECENT_RELEVANT_ITEMS': 2, 'OK_CURRENT': 4}.

NETWORK_BLOCKED s HTTP 403 vo vrstve network_tunnel je blokovanie prostredia, nie dôkaz nefunkčného pôvodného servera. Opakovanie toho istého volania alebo vymyslená náhrada tento problém neopraví. Existujúce bezplatné primárne/záložné zdroje sa testujú aj na GitHub runneri. Dostupný GitHub feed s bežným commitom sa nepovažuje za významný fundament.

Historické makro vstupy z dnešného FRED CSV sú revidované merania, nie prvé release vintages. Bez doloženého archívu sa nepoužijú spätne. Nový archív ukladá prvé pozorovanie až v čase zberu; neznámy čas publikovania ostáva null. Zlepšuje evidenciu budúcich dát, nepredstiera doplnenú minulosť.

Momentálne žiadna historická ablácia technika/makro/projekty nemá dostatočné doložené vstupy: NO_POINT_IN_TIME_HISTORY. ETF toky, DXY, orderbook a úplná geopolitika zostávajú nepokryté.

|Zdroj|Stav|Vrstva chyby|HTTP|
|---|---|---|---|
|fed|NETWORK_BLOCKED|network_tunnel|403|
|bls|NETWORK_BLOCKED|network_tunnel|403|
|fomc_calendar|NETWORK_BLOCKED|network_tunnel|403|
|bea|NETWORK_BLOCKED|network_tunnel|403|
|fed_monetary|NETWORK_BLOCKED|network_tunnel|403|
|bls_calendar|NETWORK_BLOCKED|network_tunnel|403|
|ecb|NETWORK_BLOCKED|network_tunnel|403|
|cftc|NETWORK_BLOCKED|network_tunnel|403|
|bea_www|NETWORK_BLOCKED|network_tunnel|403|
|sec|NETWORK_BLOCKED|network_tunnel|403|
|bls_year_calendar|NETWORK_BLOCKED|network_tunnel|403|
|ecb_blog|NETWORK_BLOCKED|network_tunnel|403|
|aave|NETWORK_BLOCKED|network_tunnel|403|
|ondo|NETWORK_BLOCKED|network_tunnel|403|
|sec_new_path|NETWORK_BLOCKED|network_tunnel|403|
|aave_aip|STALE|—|None|
|ondo_secondary|OK_NO_RECENT_RELEVANT_ITEMS|—|None|
|fet_fetchd|STALE|—|None|
|cointelegraph|OK_CURRENT|—|None|
|tao_subtensor|OK_NO_RECENT_RELEVANT_ITEMS|—|None|
|render_rnp|OK_CURRENT|—|None|
|sol_agave|OK_CURRENT|—|None|
|coindesk|OK_CURRENT|—|None|
|/protocol/aave|NETWORK_BLOCKED|network_tunnel|403|
|/tvl/aave|NETWORK_BLOCKED|network_tunnel|403|
|/v2/historicalChainTvl/Solana|NETWORK_BLOCKED|network_tunnel|403|
|/protocol/ondo-finance|NETWORK_BLOCKED|network_tunnel|403|
|AAVE_fees|NETWORK_BLOCKED|network_tunnel|403|
|AAVE_revenue|NETWORK_BLOCKED|network_tunnel|403|
|SOL_fees|NETWORK_BLOCKED|network_tunnel|403|
|/resource-center-data-chart-center/interest-rates/pages/xml|NETWORK_BLOCKED|network_tunnel|403|
|/graph/fredgraph.csv|NETWORK_BLOCKED|network_tunnel|403|
|/graph/fredgraph.csv|NETWORK_BLOCKED|network_tunnel|403|
