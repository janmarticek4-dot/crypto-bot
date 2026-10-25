# Macro Sources Diagnostics

UTC: 2026-10-25T20:29:46.167561+00:00; prostredie: github-hosted.

| Zdroj | Endpoint | Výsledok | Vrstva | HTTP/proxy | Záznamy |
|---|---|---|---|---|---:|
| Fed | fed_rss | SUCCESS | parsed_data | 200 | 20 |
| Fed | fomc_calendar | SUCCESS | parsed_data | 200 | 57 |
| BLS | bls_rss | SUCCESS | parsed_data | 200 | 1 |
| BLS | bls_calendar | SUCCESS | parsed_data | 200 | 313 |
| BEA | bea_rss | HTTP_ERROR | http_response | 406 | N/A |
| BEA | bea_rss_alternative | HTTP_ERROR | http_response | 406 | N/A |
| SEC | sec_legacy_rss | SUCCESS | parsed_data | 200 | 25 |
| ECB | ecb_rss | SUCCESS | parsed_data | 200 | 15 |
| SEC | sec_rss | HTTP_ERROR | http_response | 404 | N/A |
| CFTC | cftc_rss | SUCCESS | parsed_data | 200 | 10 |
| BEA | bea_calendar_candidate | INVALID_FORMAT | body_validation | 200 | N/A |
| BLS | bls_year_calendar | HTTP_ERROR | http_response | 404 | N/A |
| Treasury | treasury_csv_candidate | NETWORK_ERROR | timeout | N/A | N/A |
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

### BEA — bea_rss_alternative
https://www.bea.gov/rss/rss.xml
HTTP_ERROR: HTTP non-success response; no response body/credentials exported
Oprava: skontrolovať origin/CDN status, endpoint a fair-access pravidlá; pri429 rešpektovať Retry-After

### SEC — sec_legacy_rss
https://www.sec.gov/news/pressreleases.rss
SUCCESS: Publication/update time is not event time. Zero entries does not prove no events; success is not coverage/freshness certification.
Oprava: detaily a merané polia v results.json

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

### BEA — bea_calendar_candidate
https://www.bea.gov/news/schedule/ics/online-calendar-subscription
INVALID_FORMAT: Expected iCalendar; HTML/error page is not a calendar
Oprava: preveriť Content-Type, schému a prípadnú challenge stránku; nemeníme odpoveď na vymyslené dáta

### BLS — bls_year_calendar
https://www.bls.gov/schedule/news_release/current_year.ics
HTTP_ERROR: HTTP non-success response; no response body/credentials exported
Oprava: skontrolovať origin/CDN status, endpoint a fair-access pravidlá; pri429 rešpektovať Retry-After

### Treasury — treasury_csv_candidate
https://home.treasury.gov/resource-center-data-chart-center/interest-rates/daily-treasury-rates.csv/2026/all?type=daily_treasury_yield_curve&field_tdr_date_value=2026&page&_format=csv
NETWORK_ERROR: Connection/read timeout
Oprava: preveriť DNS/TLS/dostupnosť runnera; neobchádzať overovanie certifikátu

### Treasury — treasury_yields
https://home.treasury.gov/resource-center-data-chart-center/interest-rates/pages/xml?data=daily_treasury_yield_curve&field_tdr_date_value=2026
NETWORK_ERROR: Connection/read timeout
Oprava: preveriť DNS/TLS/dostupnosť runnera; neobchádzať overovanie certifikátu
