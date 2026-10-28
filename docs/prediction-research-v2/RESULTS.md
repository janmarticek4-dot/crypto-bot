# Prediction research V2 — no production activation

Historical research, not new independent confirmation. No calibrated probabilities. Every test origin is spaced by its horizon; approximate confidence intervals can still understate serial dependence.

|Coin|Horizon|Selected using validation|Test n|MAE %|Flat MAE %|Direction %|Band coverage %|
|---|---|---|---:|---:|---:|---:|---:|
|SOL|24 h|flat|166|2.097|2.097|38.6|81.3|
|SOL|48–72 h|flat|55|3.929|3.929|40.0|80.0|
|SOL|7–14 dní|regime_momentum|11|11.067|11.052|27.3|54.5|
|TAO|24 h|flat|166|3.015|3.015|38.6|77.7|
|TAO|48–72 h|flat|55|5.756|5.756|41.8|81.8|
|TAO|7–14 dní|regime_momentum|11|9.525|9.293|45.5|63.6|
|FET|24 h|flat|166|3.789|3.789|31.9|79.5|
|FET|48–72 h|flat|55|7.232|7.232|41.8|74.5|
|FET|7–14 dní|regime_momentum|11|11.063|11.453|18.2|81.8|
|AAVE|24 h|regime_momentum|166|3.108|3.098|32.5|80.7|
|AAVE|48–72 h|flat|55|5.793|5.793|32.7|72.7|
|AAVE|7–14 dní|ridge_technical|11|19.122|15.950|18.2|45.5|
|ONDO|24 h|flat|112|3.773|3.773|25.0|83.0|
|ONDO|48–72 h|flat|37|7.039|7.039|35.1|81.1|
|ONDO|7–14 dní|flat|8|13.856|13.856|50.0|75.0|
|RENDER|24 h|flat|164|2.834|2.834|34.8|80.5|
|RENDER|48–72 h|ridge_technical|54|5.129|4.910|38.9|81.5|
|RENDER|7–14 dní|ridge_technical|11|12.200|9.725|27.3|72.7|

Complete validation/test metrics, median errors, CIs, confusion matrices, regimes and paired comparisons: diagnostics.json.
Fundamental ablations without valid archived inputs are NO_POINT_IN_TIME_HISTORY, not zero improvement.
Paper results are separate. Legacy forecasts have ambiguous backdated origins and are not future confirmation.
New-version paper forecasts: 18; matured: 0.
No automatic production promotion; historical selection is not proof, especially after testing multiple hypotheses.
