# Historical research results

Model is **not approved**: point forecast has larger MAE than unchanged-price baseline for every coin and horizon in the chronological research test. No independent untouched validation.

|Coin|Horizon|n (overlapping)|Point MAE %|Flat MAE %|Trend MAE %|Endpoint band hit %|
|---|---|---:|---:|---:|---:|---:|
|SOL|24 h|49|2.44|2.17|2.49|79.6|
|SOL|48–72 h|47|3.90|3.35|4.23|80.9|
|SOL|7–14 dní|36|13.16|11.31|20.30|75.0|
|TAO|24 h|49|4.74|4.14|4.82|67.3|
|TAO|48–72 h|47|7.49|6.06|7.84|72.3|
|TAO|7–14 dní|36|21.16|16.04|35.94|72.2|
|FET|24 h|49|5.83|4.69|6.04|71.4|
|FET|48–72 h|47|9.07|7.39|9.85|70.2|
|FET|7–14 dní|36|25.38|22.75|43.18|44.4|
|AAVE|24 h|49|4.51|3.98|4.58|61.2|
|AAVE|48–72 h|47|6.23|5.58|7.39|72.3|
|AAVE|7–14 dní|36|19.86|18.42|29.89|77.8|
|ONDO|24 h|49|4.45|3.88|4.85|79.6|
|ONDO|48–72 h|47|8.48|6.85|10.18|74.5|
|ONDO|7–14 dní|36|23.86|20.57|39.50|52.8|
|RENDER|24 h|49|4.24|3.78|4.44|71.4|
|RENDER|48–72 h|47|7.33|6.07|8.01|66.0|
|RENDER|7–14 dní|36|22.25|18.09|34.61|50.0|

Full per-coin development/test metrics, direction accuracy and exact dates: `historical-results.json`. MAE is forecast error, not investment return. Bands are endpoint bands, not full path coverage. Historical dates below are candle-open UTC timestamps.
- SOL: 2026-05-14T16:00:00+00:00 / 2026-09-08T04:00:00+00:00 / 2026-10-28T00:00:00+00:00 (start / split / end).
- TAO: 2026-05-14T16:00:00+00:00 / 2026-09-08T04:00:00+00:00 / 2026-10-28T00:00:00+00:00 (start / split / end).
- FET: 2026-05-14T16:00:00+00:00 / 2026-09-08T04:00:00+00:00 / 2026-10-28T00:00:00+00:00 (start / split / end).
- AAVE: 2026-05-14T16:00:00+00:00 / 2026-09-08T04:00:00+00:00 / 2026-10-28T00:00:00+00:00 (start / split / end).
- ONDO: 2026-05-14T16:00:00+00:00 / 2026-09-08T04:00:00+00:00 / 2026-10-28T00:00:00+00:00 (start / split / end).
- RENDER: 2026-05-14T16:00:00+00:00 / 2026-09-08T04:00:00+00:00 / 2026-10-28T00:00:00+00:00 (start / split / end).
