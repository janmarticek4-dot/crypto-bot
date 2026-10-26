# One-bot integration candidate

The main-based integration candidate is on `integration/v11-1-main-review` in this same repository. It keeps production `main.py`, production workflow and `bot_state.json` unchanged and adds an opt-in report adapter with the native V10.6 rule engine.

Review: https://github.com/janmarticek4-dot/crypto-bot/blob/integration/v11-1-main-review/docs/integration/REVIEW.md

The manual entrypoint is the already registered https://github.com/janmarticek4-dot/crypto-bot/actions/workflows/run.yml on **feature/v11-1-review**, task **integration-shadow**. It calls a frozen, tested integration commit. No new repository is needed, and this does not select the production main workflow.

- `phase=preview`: current one-time sample, not an independent pair.
- `phase=morning`: 07:00–08:30 Europe/Bratislava, retain successful run ID.
- `phase=evening`, `morning_run_id=<ID>`: 20:00–21:30, new actual fetch and strict reference validation.
- Without a genuine morning reference the comparison is N/A. Do not claim a real temporal pair from a preview.

Download `v111-integration-<run_id>-<attempt>` from the run's Artifacts. This is public market evidence only: no private portfolio, Telegram, migration or trading. Automated scheduling in the original main is not modified or activated by this work.

If the UI does not expose the development task:

```sh
gh workflow run run.yml --repo janmarticek4-dot/crypto-bot --ref feature/v11-1-review -f task=integration-shadow -f phase=preview
```

Do not use main or advisory_import for this test. The production rollout patch is a separate, unapplied review artifact; approval is still required for any merge or activation.
