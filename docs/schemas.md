# BREAKOUT data schemas (v1.1)

**Contract version:** `v1.1` (`backend.schemas.CONTRACT_VERSION`)

Frozen between Light's pipeline (SkyMap producers) and Tony's ranking code
(`CandidateScore` consumers). **Any later field change needs a version bump
and a note in this file.**

Coordinates are ICRS degrees. Times are ISO-8601 UTC (`astropy.time.Time` in
code). Any value from a simulation carries `"simulated": true` and the UI
labels it with a Simulated badge. Never invent numbers or citations: every
literature claim needs an ADS bibcode.

Machine-readable JSON Schema (exported from pydantic):

| Model | File |
| --- | --- |
| Alert | [`schemas/Alert.schema.json`](schemas/Alert.schema.json) |
| SkyMap | [`schemas/SkyMap.schema.json`](schemas/SkyMap.schema.json) |
| CandidateScore | [`schemas/CandidateScore.schema.json`](schemas/CandidateScore.schema.json) |

Regenerate after editing `backend/schemas.py`:

```bash
python scripts/export_schemas.py
```

Contract fixtures (all `simulated=true`, labeled as fixtures):

- `data/fixtures/skymap_example.json`
- `data/fixtures/candidate_scores_example.json`

---

## Alert

Emitted by every ingest source; consumed by `localize/`.
Pydantic: `backend.schemas.Alert` (with `DetectorHit`, `Pointing`).

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

`pointing` may be `null`. Detector WGS84 positions: `backend.config.DETECTOR_TABLE`.

See full schema: [`schemas/Alert.schema.json`](schemas/Alert.schema.json).

---

## SkyMap

Output of `localize/fuse.py`. HEALPix via healpy, **NESTED**, sums to 1.
Also writes `data/run/<alert_id>/skymap.png` (Mollweide fallback).
Pydantic: `backend.schemas.SkyMap`.

```json
{
  "alert_id": "string",
  "nside": 64,
  "ordering": "NESTED",
  "frame": "ICRS",
  "prob_path": "data/run/<alert_id>/skymap.fits",
  "components": ["superk_pointing", "timing:Super-K-SNO+", "timing:Super-K-IceCube"],
  "credible_90_deg2": 0.0,
  "peak": { "ra_deg": 0.0, "dec_deg": 0.0 },
  "simulated": false
}
```

See full schema: [`schemas/SkyMap.schema.json`](schemas/SkyMap.schema.json).

---

## CandidateScore (v1.1)

One row per star; output of `literature/rerank.py` and `progenitors/rank_runtime.py`.
Pydantic: `backend.schemas.CandidateScore` with nested:

- `Evidence` — `{ bibcode, claim }` (no bibcode → no claim)
- `Literature` — `{ mass_loss, variability, evolved_stage, confidence }` each in `[0, 1]`, plus `evidence: list[Evidence]`
- `Breakout` — `{ class_window: minutes | hours | about 1 day, countdown_from }`
- `LifeExpectancyInfo` (v1.1, optional) — class optical-breakout window + optional ADS stage note

```json
{
  "star_id": "string",
  "ra_deg": 0.0,
  "dec_deg": 0.0,
  "class": "RSG | BSG | YSG | WR | LBV",
  "spectral_type": "string",
  "distance_kpc": null,
  "extinction_av_mag": null,
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
  "ir_followup": false,
  "simulated": false,
  "rank_confidence": null,
  "rank_reasoning": null,
  "life_expectancy": null,
  "composition": null
}
```

v1.1 additive fields default to `null` so legacy consumers keep working. They are
filled by `backend.progenitors.rank_runtime.rank_with_grok` from the offline
inventory (and optional live Grok shortlist rank when keys allow).

Tony imports:

```python
from backend.schemas import CandidateScore, Evidence, Literature, Breakout, SkyMap, Alert
```

See full schema: [`schemas/CandidateScore.schema.json`](schemas/CandidateScore.schema.json).

### Changelog

| Version | Date (PT) | Note |
| --- | --- | --- |
| v1.1 | Sun 25 Oct 2026 | Additive CandidateScore fields: `rank_confidence`, `rank_reasoning`, `life_expectancy`, `composition` (progenitor inventory / Grok rank). |
| v1 | Sat 24 Oct 2026 | Initial freeze: Alert, SkyMap, CandidateScore (+ Evidence, Literature, Breakout). |

---

## Exported JSON Schema (rendered)
### Alert

```json
{
  "$defs": {
    "DetectorHit": {
      "description": "One detector's contribution to an Alert (WGS84 position + arrival).",
      "properties": {
        "height_m": {
          "title": "Height M",
          "type": "number"
        },
        "lat_deg": {
          "title": "Lat Deg",
          "type": "number"
        },
        "lon_deg": {
          "title": "Lon Deg",
          "type": "number"
        },
        "n_events": {
          "title": "N Events",
          "type": "integer"
        },
        "name": {
          "enum": [
            "Super-K",
            "SNO+",
            "IceCube",
            "KamLAND",
            "JUNO"
          ],
          "title": "Name",
          "type": "string"
        },
        "pointing": {
          "anyOf": [
            {
              "$ref": "#/$defs/Pointing"
            },
            {
              "type": "null"
            }
          ],
          "default": null
        },
        "t_arrival_utc": {
          "title": "T Arrival Utc",
          "type": "string"
        },
        "t_err_ms": {
          "title": "T Err Ms",
          "type": "number"
        }
      },
      "required": [
        "name",
        "lat_deg",
        "lon_deg",
        "height_m",
        "t_arrival_utc",
        "t_err_ms",
        "n_events"
      ],
      "title": "DetectorHit",
      "type": "object"
    },
    "Pointing": {
      "description": "Directional estimate in ICRS degrees.",
      "properties": {
        "dec_deg": {
          "title": "Dec Deg",
          "type": "number"
        },
        "err_deg": {
          "title": "Err Deg",
          "type": "number"
        },
        "ra_deg": {
          "title": "Ra Deg",
          "type": "number"
        }
      },
      "required": [
        "ra_deg",
        "dec_deg",
        "err_deg"
      ],
      "title": "Pointing",
      "type": "object"
    }
  },
  "$id": "https://breakout.local/schemas/Alert.schema.json",
  "description": "Emitted by every ingest source; consumed by localize/.",
  "properties": {
    "alert_id": {
      "title": "Alert Id",
      "type": "string"
    },
    "detectors": {
      "items": {
        "$ref": "#/$defs/DetectorHit"
      },
      "title": "Detectors",
      "type": "array"
    },
    "kind": {
      "enum": [
        "PRESN",
        "SN_BURST",
        "HE_NEUTRINO"
      ],
      "title": "Kind",
      "type": "string"
    },
    "raw": {
      "additionalProperties": true,
      "title": "Raw",
      "type": "object"
    },
    "significance": {
      "title": "Significance",
      "type": "number"
    },
    "simulated": {
      "description": "True when any value is from a simulation; UI must label it.",
      "title": "Simulated",
      "type": "boolean"
    },
    "source": {
      "enum": [
        "presn",
        "snews2",
        "gcn_kafka",
        "snewpy_sim",
        "cache"
      ],
      "title": "Source",
      "type": "string"
    },
    "t0_utc": {
      "title": "T0 Utc",
      "type": "string"
    }
  },
  "required": [
    "alert_id",
    "kind",
    "source",
    "simulated",
    "t0_utc",
    "detectors",
    "significance"
  ],
  "title": "BREAKOUT Alert (v1)",
  "type": "object"
}
```

### SkyMap

```json
{
  "$defs": {
    "SkyPeak": {
      "description": "Peak of a fused HEALPix sky map (ICRS degrees).",
      "properties": {
        "dec_deg": {
          "title": "Dec Deg",
          "type": "number"
        },
        "ra_deg": {
          "title": "Ra Deg",
          "type": "number"
        }
      },
      "required": [
        "ra_deg",
        "dec_deg"
      ],
      "title": "SkyPeak",
      "type": "object"
    }
  },
  "$id": "https://breakout.local/schemas/SkyMap.schema.json",
  "description": "Output of localize/fuse.py (healpy NESTED map, sums to 1).",
  "properties": {
    "alert_id": {
      "title": "Alert Id",
      "type": "string"
    },
    "components": {
      "items": {
        "type": "string"
      },
      "title": "Components",
      "type": "array"
    },
    "credible_90_deg2": {
      "title": "Credible 90 Deg2",
      "type": "number"
    },
    "frame": {
      "const": "ICRS",
      "default": "ICRS",
      "title": "Frame",
      "type": "string"
    },
    "nside": {
      "default": 64,
      "title": "Nside",
      "type": "integer"
    },
    "ordering": {
      "const": "NESTED",
      "default": "NESTED",
      "title": "Ordering",
      "type": "string"
    },
    "peak": {
      "$ref": "#/$defs/SkyPeak"
    },
    "prob_path": {
      "title": "Prob Path",
      "type": "string"
    },
    "simulated": {
      "default": false,
      "title": "Simulated",
      "type": "boolean"
    }
  },
  "required": [
    "alert_id",
    "prob_path",
    "components",
    "credible_90_deg2",
    "peak"
  ],
  "title": "BREAKOUT SkyMap (v1)",
  "type": "object"
}
```

### CandidateScore

```json
{
  "$defs": {
    "Breakout": {
      "description": "Per-class breakout countdown window (estimate; label as such in UI).",
      "properties": {
        "class_window": {
          "enum": [
            "minutes",
            "hours",
            "about 1 day"
          ],
          "title": "Class Window",
          "type": "string"
        },
        "countdown_from": {
          "description": "ISO-8601 UTC",
          "title": "Countdown From",
          "type": "string"
        }
      },
      "required": [
        "class_window",
        "countdown_from"
      ],
      "title": "Breakout",
      "type": "object"
    },
    "Evidence": {
      "description": "One literature claim; bibcode is required (no bibcode, no claim).",
      "properties": {
        "bibcode": {
          "description": "ADS bibcode",
          "minLength": 1,
          "title": "Bibcode",
          "type": "string"
        },
        "claim": {
          "minLength": 1,
          "title": "Claim",
          "type": "string"
        }
      },
      "required": [
        "bibcode",
        "claim"
      ],
      "title": "Evidence",
      "type": "object"
    },
    "Literature": {
      "description": "Precomputed offline literature scores (each 0..1) plus evidence.",
      "properties": {
        "confidence": {
          "maximum": 1.0,
          "minimum": 0.0,
          "title": "Confidence",
          "type": "number"
        },
        "evidence": {
          "items": {
            "$ref": "#/$defs/Evidence"
          },
          "title": "Evidence",
          "type": "array"
        },
        "evolved_stage": {
          "maximum": 1.0,
          "minimum": 0.0,
          "title": "Evolved Stage",
          "type": "number"
        },
        "mass_loss": {
          "maximum": 1.0,
          "minimum": 0.0,
          "title": "Mass Loss",
          "type": "number"
        },
        "variability": {
          "maximum": 1.0,
          "minimum": 0.0,
          "title": "Variability",
          "type": "number"
        }
      },
      "required": [
        "mass_loss",
        "variability",
        "evolved_stage",
        "confidence"
      ],
      "title": "Literature",
      "type": "object"
    }
  },
  "$id": "https://breakout.local/schemas/CandidateScore.schema.json",
  "description": "One row per star; output of literature/rerank.py (CandidateScore v1).",
  "properties": {
    "breakout": {
      "$ref": "#/$defs/Breakout"
    },
    "class": {
      "enum": [
        "RSG",
        "BSG",
        "YSG",
        "WR",
        "LBV"
      ],
      "title": "Class",
      "type": "string"
    },
    "dec_deg": {
      "title": "Dec Deg",
      "type": "number"
    },
    "distance_kpc": {
      "anyOf": [
        {
          "type": "number"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "title": "Distance Kpc"
    },
    "extinction_av_mag": {
      "anyOf": [
        {
          "type": "number"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "title": "Extinction Av Mag"
    },
    "ir_followup": {
      "default": false,
      "title": "Ir Followup",
      "type": "boolean"
    },
    "lit": {
      "$ref": "#/$defs/Literature"
    },
    "p_sky": {
      "title": "P Sky",
      "type": "number"
    },
    "posterior": {
      "title": "Posterior",
      "type": "number"
    },
    "presn_watch": {
      "default": false,
      "title": "Presn Watch",
      "type": "boolean"
    },
    "ra_deg": {
      "title": "Ra Deg",
      "type": "number"
    },
    "simulated": {
      "default": false,
      "description": "True when scores/values are simulated; UI must label it.",
      "title": "Simulated",
      "type": "boolean"
    },
    "spectral_type": {
      "title": "Spectral Type",
      "type": "string"
    },
    "star_id": {
      "title": "Star Id",
      "type": "string"
    }
  },
  "required": [
    "star_id",
    "ra_deg",
    "dec_deg",
    "class",
    "spectral_type",
    "p_sky",
    "lit",
    "posterior",
    "breakout"
  ],
  "title": "BREAKOUT CandidateScore (v1)",
  "type": "object"
}
```


## Proposed v2

Reserved for post-MVP schema extensions. Do not implement until
`scripts/mvp_gate.sh` prints PASS (Phase 2 is out of scope until then).
Any v2 work starts by bumping `CONTRACT_VERSION` and adding a changelog row above.

### Requests from Tony (ranking / UI) — do not implement on v1

| Proposed field | Why |
| --- | --- |
| `ir_followup_reason: string` | Extinction module already records why IR was recommended (`ExtinctionDecision.reason`); UI needs it on the wire without a side channel. |
| `ranking_terms: { w_class, w_lit, w_watch, weight }` | Explainability for the posterior (config weights × p_sky); useful for judge Q&A / dashboard. |
| `common_name: string \| null` | Catalog display name (e.g. Betelgeuse) separate from `star_id` / SIMBAD main_id. |

These stay off `CandidateScore` v1. Ranking keeps reasons/weights in logs until Light freezes v2.
