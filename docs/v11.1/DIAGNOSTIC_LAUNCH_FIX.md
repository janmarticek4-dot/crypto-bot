# Repair of the missing test_offline.py launch

The failure was caused by the existing V11.1 development version of `.github/workflows/run.yml`: it checked out **main**, then tried to execute `scripts/test_offline.py`, which is absent on production main. This explains the supplied log exactly; it was not a failure of the standalone macro diagnostic.

Fix applied ONLY on feature/v11-1-review:
- Preserve previous V11.1 production-workflow proposal, unchanged, as inactive documentation at PRODUCTION_WORKFLOW_REFERENCE.yml.
- Replace the development branch version of the already-registered run.yml path with a manual-only macro diagnostic entrypoint.
- Checkout the selected immutable commit, run the standalone stdlib diagnostic, publish Artifacts. No tests from main, bot startup, secrets, private state, Telegram, schedule or writeback.
- Guard execution to feature/v11-1-review. Original main and its scheduled production workflow are not edited or merged.

Because run.yml already exists on the repository default branch, this entrypoint avoids the discovery limitation for a brand-new workflow file. It does not bypass Actions permissions. The standalone macro-sources-diagnostics.yml remains available too.

Manual UI route if an API client is unavailable:
Actions → select the existing workflow with file path `.github/workflows/run.yml` (the list may still show **Crypto AI Bot V10.6** from default main) → Run workflow → **Use workflow from: feature/v11-1-review**. Do NOT leave main selected. The selected research version executes diagnostics only; it cannot start the production bot. Results appear in Summary and `macro-sources-diagnostics-RUN_ID-ATTEMPT` Artifacts.

API dispatch uses the existing workflow path directly:

```bash
gh api --method POST repos/janmarticek4-dot/crypto-bot/actions/workflows/run.yml/dispatches -f ref=feature/v11-1-review
```

Successful push, successful dispatch and successful completed run are separate facts. Only claim the latter with actual run evidence. This repair is not authorization to deploy V11.1 or restore the archived production proposal on main.
