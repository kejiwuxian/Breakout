# BREAKOUT data schemas (v1)

Every module reads and writes these JSON shapes. Coordinates are ICRS degrees.
Times are ISO-8601 UTC (astropy `Time` in code). Any value from a simulation
carries `"simulated": true` and the UI labels it with a Simulated badge.

## Alert

Emitted by every ingest source; consumed by `localize/`.

```json
{
  "alert_id": "string",
  "kind": "PRESN | SN_BURST | HE_NEUTRINO",
  "source": "presn | snews2 | gcn_kafka | snewpy_sim | cache",
  "simulated": true,
  "t0_utc": "ISO-8601",
  "detectors": [{
    "name": "Super-K | SNO+ | IceCube | KamLAND | JUNO",
    "lat_deg": 0.0,
    "lon_deg": 0.0,
    "height_m": 0.0,
    "t_arrival_utc": "ISO-8601",
    "t_err_ms": 0.0,
    "n_events": 0,
    "pointing": { "ra_deg": 0.0, "dec_deg": 0.0, "err_deg": 0.0 }
  }],
  "significance": 0.0,
  "raw": {}
}
```

## SkyMap

Output of `localize/fuse.py`. HEALPix maps use healpy, **NESTED** ordering,
and always sum to 1.

```json
{
  "alert_id": "string",
  "nside": 64,
  "ordering": "NESTED",
  "frame": "ICRS",
  "prob_path": "data/run/<alert_id>/skymap.fits",
  "components": ["superk_pointing", "timing:SuperK-SNO+", "timing:SuperK-IceCube"],
  "credible_90_deg2": 0.0,
  "peak": { "ra_deg": 0.0, "dec_deg": 0.0 }
}
```

## CandidateScore

One row per star; output of `literature/rerank.py`. Every literature claim
stores an ADS bibcode; no bibcode, no claim.

```json
{
  "star_id": "string",
  "ra_deg": 0.0,
  "dec_deg": 0.0,
  "class": "RSG | BSG | YSG | WR | LBV",
  "spectral_type": "string",
  "distance_kpc": 0.0,
  "extinction_av_mag": 0.0,
  "p_sky": 0.0,
  "lit": {
    "mass_loss": 0.0,
    "variability": 0.0,
    "evolved_stage": 0.0,
    "confidence": 0.0,
    "evidence": [{ "bibcode": "string", "claim": "string" }]
  },
  "presn_watch": false,
  "posterior": 0.0,
  "breakout": {
    "class_window": "minutes | hours | about 1 day",
    "countdown_from": "ISO-8601"
  },
  "ir_followup": false
}
```

## Proposed v2

Reserved for post-MVP schema extensions. Do not implement until
`scripts/mvp_gate.sh` prints PASS (Phase 2 is out of scope until then).

Exported JSON Schema files (when generated) live under `docs/schemas/`.
