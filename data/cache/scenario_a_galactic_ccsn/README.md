# Scenario A: galactic core-collapse (Betelgeuse path)

**SIMULATED** SNEWPY burst (`Nakazato_2013`) aimed at Betelgeuse's published ICRS
direction (RA ≈ 88.7929°, Dec ≈ 7.4071°) at 0.2 kpc for a strong nearby-SN demo.

| Artifact | Real or simulated |
| --- | --- |
| `alerts.jsonl` | Simulated (`"simulated": true`, `"source": "snewpy_sim"`) |
| Detector WGS84 positions | Real lab coordinates (`backend.config.DETECTOR_TABLE`, sourced in comments) |
| Arrival times | Simulated geometric light-travel delays (−r·û/c) |
| `n_events` | Simulated via snewpy + SNOwGLoBES (mass-scaled configs) |
| Voice clips under `voice/` | Pre-rendered Grok TTS for `VOICE_MODE=cached` (later) |

Regenerate:

```bash
python -m backend.ingest.snewpy_sim \
  --ra 88.7929 --dec 7.4071 --distance-kpc 0.2 \
  --out data/cache/scenario_a_galactic_ccsn \
  --t0-utc 2026-10-24T21:46:00
```

Do not invent numbers. Label every simulated field in the UI.
