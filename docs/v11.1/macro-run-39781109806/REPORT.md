# Macro Sources Diagnostics

UTC: 2026-10-22T12:46:28.460028+00:00; prostredie: github-hosted.

| Zdroj | Endpoint | Výsledok | Vrstva | HTTP/proxy | Záznamy |
|---|---|---|---|---|---:|
| Fed | fed_rss | SUCCESS | parsed_data | 200 | 20 |
| Fed | fomc_calendar | SUCCESS | parsed_data | 200 | 57 |
| BLS | bls_rss | SUCCESS | parsed_data | 200 | 1 |
| BLS | bls_calendar | SUCCESS | parsed_data | 200 | 313 |
| BEA | bea_rss | HTTP_ERROR | http_response | 406 | N/A |
| ECB | ecb_rss | SUCCESS | parsed_data | 200 | 15 |
| SEC | sec_rss | HTTP_ERROR | http_response | 404 | N/A |
| CFTC | cftc_rss | SUCCESS | parsed_data | 200 | 10 |
| Treasury | treasury_yields | NETWORK_ERROR | timeout | N/A | N/A |

SUCCESS znamená HTTPS + rozpoznaný formát, nie úplnosť alebo aktuálnosť kalendára. HTTP200 s HTML blokovacou stránkou je INVALID_FORMAT.
NETWORK_BLOCKED/CONNECT403 nie je HTTP403 pôvodného webu. HTTP_ERROR je odpoveď HTTPS endpointu/CDN/gateway; bez ďalšieho dôkazu ju nepripisujeme samotnému aplikačnému serveru.
Chyba zdroja je výsledok testu, nie zlyhanie workflow. DIAGNOSTIC_ERROR zlyhá job. Bez platených API, tajných údajov, Telegramu, bota, obchodných signálov a obchodov.

## Podrobnosti

### Fed — fed_rss
https://www.federalreserve.gov/feeds/press_all.xml
SUCCESS: Publication/update time is not event time. Zero entries does not prove no events; success is not coverage/freshness certification.
Oprava: detaily a merané polia v results.json

### Fed — fomc_calendar
https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm
SUCCESS: Meeting dates do not prove a decision time; no assumed Fed hour.
Oprava: detaily a merané polia v results.json

### BLS — bls_rss
https://www.bls.gov/feed/bls_latest.rss
SUCCESS: Publication/update time is not event time. Zero entries does not prove no events; success is not coverage/freshness certification.
Oprava: detaily a merané polia v results.json

### BLS — bls_calendar
https://www.bls.gov/schedule/news_release/bls.ics
SUCCESS: Format/reachability only; dates, timezone precision and future coverage require calendar-level validation.
Oprava: detaily a merané polia v results.json

### BEA — bea_rss
https://apps.bea.gov/rss/rss.xml
HTTP_ERROR: HTTP non-success response; no response body/credentials exported
Oprava: skontrolovať origin/CDN status, endpoint a fair-access pravidlá; pri429 rešpektovať Retry-After

### ECB — ecb_rss
https://www.ecb.europa.eu/rss/press.html
SUCCESS: Publication/update time is not event time. Zero entries does not prove no events; success is not coverage/freshness certification.
Oprava: detaily a merané polia v results.json

### SEC — sec_rss
https://www.sec.gov/newsroom/press-releases/rss.xml
HTTP_ERROR: HTTP non-success response; no response body/credentials exported
Oprava: skontrolovať origin/CDN status, endpoint a fair-access pravidlá; pri429 rešpektovať Retry-After

### CFTC — cftc_rss
https://www.cftc.gov/RSS/RSSGP/rssgp.xml
SUCCESS: Publication/update time is not event time. Zero entries does not prove no events; success is not coverage/freshness certification.
Oprava: detaily a merané polia v results.json

### Treasury — treasury_yields
https://home.treasury.gov/resource-center-data-chart-center/interest-rates/pages/xml?data=daily_treasury_yield_curve&field_tdr_date_value=2026
NETWORK_ERROR: Connection/read timeout
Oprava: preveriť DNS/TLS/dostupnosť runnera; neobchádzať overovanie certifikátu
