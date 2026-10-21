# Phase 3 research

This is an isolated historical simulator, not a runtime trading strategy. Production code is intentionally unchanged. The full methods, caveats, commands and results are in [the phase 3 report](../../docs/phase3/REPORT.md).

- `design.json`: parameters and selection rules recorded before the first strategy matrix.
- `data.py`: validated public candles, closed-bar features and optional first-vintage global-data adapter.
- `regime.py`: causal BULL / NEUTRAL / BEAR state machine and ablations.
- `sim.py`: one shared cash wallet, delayed manual fills, costs and hourly valuation.
- `run.py`: complete strategy matrix, sensitivity, walk-forward and final short test.
- `diagnose.py`: retrospective diagnostics; forward outcomes never feed the simulator or selector.
- `plot.py`, `report.py`: standalone figure and generated Slovak report.
- `test_phase3.py`, `verify.py`: causal execution tests and independent artifact/accounting checks.

Run the complete pipeline in the report's order. A successful simulator run alone does not refresh the derived diagnostics/report. `verify.py` rejects changed source code, inputs or output artifacts. Raw market data stays under the ignored `backtesting/user_data/phase3/` directory; all committed trade records are simulations.

The current experiment has no reliable point-in-time total-market-cap or BTC-dominance dataset. Those features are **N/A**, not zero and not invented. Previously inspected 2024–September 2026 data is not a pristine holdout. No strategy in this experiment is approved for production.
