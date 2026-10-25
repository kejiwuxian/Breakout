# BREAKOUT — Phase 1 File Bundle

This bundle consolidates the unique Phase 1 files created during the conversation. No Phase 2 sponsor-integration output is included.

## Contents

- `data/stars/curated_stars.json` — original curated star catalog (40 objects, unchanged)
- `data/stars/citation_audit.json` — star evidence citation audit
- `data/stars/citation_audit.md` — human-readable citation audit
- `tests/test_curated_stars.py` — schema and provenance validation tests
- `tests/pytest_curated_stars_results.txt` — saved validation test output
- `docs/BREAKOUT_judge_science_QA.md` — provisional 20-question science judge Q&A sheet
- `scripts/build_breakout.py` — catalog-building source script, retained for provenance only
- `scripts/generate_citation_audit.py` — audit-generation source script, retained for provenance only
- `archive/breakout_curated_stars_validation.zip` — earlier two-file downloadable validation archive (historical copy; duplicates some files above)
- `manifest.json` — SHA-256 and file sizes for this bundle

## Subscribe to events (Phase 1)

Ranked-candidate push is Phase 1 (not sponsor Phase 2): open **access +
refresh** tokens (`POST /subscribe` / `/subscribe/refresh` — no prior
credentials), WebSocket dispatch on `/ws/subscribe`, `GET /alerts/latest`,
primary **frontend/** **Subscribe to events** panel (optional `frontend-v2`). See
[`docs/community-subscribe.md`](../community-subscribe.md) and
[`data/subscribers/README.md`](../../data/subscribers/README.md).

## After MVP gate

Features merged after `mvp_gate.sh` PASS are indexed in
[`docs/post-mvp.md`](../post-mvp.md).

## Important notes

- The curated star data has not been modified in this packaging pass.
- The recorded `pytest` run did **not** pass: 7 `lit.evidence[*].bibcode` values were null. Verify/correct the underlying citations before claiming an MVP gate PASS.
- The Q&A sheet labels plan-specific items unverified where the source plan page could not be accessed.
- `scripts/` contains provenance scripts from the creation process, **not** approved production integrations. Some paths are absolute to the original build environment; they are included as-is.
- The previous validation ZIP is retained to preserve all user-facing Phase 1 deliverables, though its contents are also present elsewhere in this folder.
- No Phase 2 sponsor files, environment settings, or sponsor connectors are included.
