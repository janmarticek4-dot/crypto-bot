Production analyses currently use a pinned pilot while the reviewed V11.1 format and evidence modules remain outside main. This PR brings only the analytical runtime and its safety checks into the existing bot; E1, AdaptiveHold, backtesting results and new production trading rules are excluded.

The compact report labels native V10.6 SELL/REDUCE as technical risk, not a confirmed forecast or a personal instruction to liquidate holdings. Fundamentals retain provenance/freshness and missing-data limits. Morning/evening references require different dated observations. Public diagnostics are generated before private inventory is appended and use an explicit artifact file list.

Activation is deliberately separate: absent/false V111_INTEGRATION_ENABLED keeps the exact original 929bd63 pilot source, entrypoint and tests. True selects immutable analytical runtime 0da0fc3bd67f197b15e1744934e8c8792775db21. The same sender, CAS-before-send journal, 07:00/15:00/20:00 windows and silent monitor remain. Proposed state guards reject corruption/reset/private contamination and stop ignoring rebase conflicts. Other production jobs, Secrets references, main.py, bot_state.json and the live delivery journal are unchanged.

Validation: 139 offline tests passed with unmocked networking blocked, plus workflow YAML/unchanged schedule/concurrency/other jobs/protected-file checks. No real Telegram or portfolio access. A final live runner and genuine morning/evening pair have not been verified. AAVE TVL, ONDO, historical/stale macro feeds and incomplete ETF/geopolitical/unlock coverage remain explicitly documented limits.

Review and exact activation/rollback:
- docs/v11.1-release/REVIEW.md
- docs/v11.1-release/ACTIVATION.md
- docs/v11.1-release/VERIFICATION.json

Do not merge or activate without the owner's explicit approval. Rollback selects the old pinned source with the same journal; never restore older state files or clear uncertain slots.
