# Scenario A: galactic core-collapse (Betelgeuse)

Demo path for Stage 0 **PRESN** → **SN_BURST** aimed at Betelgeuse. Keep real
catalog data real; label every simulated neutrino number.

## Real (catalog / literature)

| Artifact | Source |
| --- | --- |
| Star identity, ICRS RA/Dec, spectral type, class `RSG` | `data/stars/curated_stars.json` (SIMBAD main_id `* alf Ori`) |
| Distance `0.222` kpc | Vincent curated (Harper et al. 2017, ADS `2017AJ....154...11H`, ~222 pc; marked uncertain in curated) |
| Literature evidence bibcodes | `backend/literature/index.parquet` — `2020ApJ...902...63J`, `2017AJ....154...11H`, `2016ApJ...819....7D` |
| Detector WGS84 positions | Real lab coordinates (`backend.config.DETECTOR_TABLE`) |

## Simulated (`simulated=true` everywhere in `alerts.jsonl`)

| Artifact | What is simulated |
| --- | --- |
| PRESN alert | Stage 0 KamLAND + Super-K combined pre-SN notice (no direction); timing, FAR, event counts |
| SN_BURST alert | snewpy `Nakazato_2013` + SNOwGLoBES event rates at the curated distance |
| Detector arrival times | Geometric light-travel delays (−r·û/c) from the curated ICRS direction |
| Super-K pointing | Directional estimate centered on curated RA/Dec with a few-degree simulated error |
| Breakout countdown | Class-window estimate (`about 1 day` for RSG), not a star-specific prediction |

UI: every WebSocket event with `simulated: true` must show a **Simulated** badge.

## Regenerate (reads curated JSON — do not hardcode coords/distance)

```bash
python -c "from backend.literature.build_index import seed_betelgeuse_index; seed_betelgeuse_index()"
python -m backend.ingest.snewpy_sim \
  --from-curated Betelgeuse \
  --out data/cache/scenario_a_galactic_ccsn \
  --t0-utc 2026-10-24T21:46:00 \
  --presn-lead-s 3600
```

Do not invent numbers or citations. Alternate published distances (e.g. Harper
et al. 2017 ~222 pc) stay in the literature index as evidence; the scenario
burst uses only the curated Joyce 2020 distance.
