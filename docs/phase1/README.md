# BREAKOUT — Phase 1 File Bundle

This bundle consolidates the unique Phase 1 files created during the conversation. No Phase 2 sponsor-integration output is included.

## Contents

- `data/stars/curated_stars.json` — original curated star catalog (40 objects, unchanged; ranking / AOI inventory)
- `data/stars/sky_background.json` — Yale BSC5 all-sky SVG background (V≤6.5; post-MVP skymap field)
- `data/stars/sky_background_meta.json` — BSC5 provenance / attribution
- `data/stars/citation_audit.json` — star evidence citation audit
- `data/stars/citation_audit.md` — human-readable citation audit
- `tests/test_curated_stars.py` — schema and provenance validation tests
- `tests/test_sky_background.py` — all-sky background catalog coverage tests
- `tests/pytest_curated_stars_results.txt` — saved validation test output
- `scripts/build_sky_background_catalog.py` — rebuild BSC5 compact background from CDS V/50
- `docs/BREAKOUT_judge_science_QA.md` — provisional 20-question science judge Q&A sheet
- `scripts/build_breakout.py` — catalog-building source script, retained for provenance only
- `scripts/generate_citation_audit.py` — audit-generation source script, retained for provenance only
- `archive/breakout_curated_stars_validation.zip` — earlier two-file downloadable validation archive (historical copy; duplicates some files above)
- `manifest.json` — SHA-256 and file sizes for this bundle

## Community subscribe (Phase 1)

Ranked-candidate push is Phase 1 (not sponsor Phase 2): two-token email
confirm (`POST /subscribe/request` → `POST /subscribe/confirm`), email-only
dispatch to active subscribers (no webhook), `GET /alerts/latest`, classic +
**frontend-v2** subscribe panels. See
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
