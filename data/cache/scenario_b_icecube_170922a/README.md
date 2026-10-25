# Scenario B: IceCube-170922A / TXS 0506+056

**REAL** high-energy neutrino alert associated with the flaring blazar TXS 0506+056.
All alert fields in `alerts.jsonl` use `simulated: false`.

## Real (archive / catalog)

| Artifact | Source |
| --- | --- |
| `alerts.jsonl` | GCN Circular 21916 refined direction (RA 77.43°, Dec +5.72° J2000; 2017-09-22 20:54:30.43 UTC) |
| `gcn_circular_21916.txt` | Local copy of GCN Circular 21916 text (archive) |
| `gcn_amon_notice_50579430_130033.txt` | Local copy of the AMON notice text (archive) |
| `blazars.json` | SIMBAD/astroquery blazar neighborhood cache (offline; `simulated=false`) |
| Pointing `err_deg` ≈ 0.7° | Approximate 90% PSF containment scale from GCN 21916 asymmetric errors (not a simulated draw) |
| Detector WGS84 (IceCube) | Real lab coordinates (`backend.config.DETECTOR_TABLE`) |
| TXS 0506+056 in curated catalog | RA 77.36°, Dec +5.69° from IceCube Collaboration et al. 2018 Science (ADS `2018Sci...361.1378I` / arXiv:1807.08816) |
| Progenitor / blazar catalog rows | Vincent `data/stars/curated_stars.json` (+ `citation_audit.json`) |

## Simulated

None in this scenario’s alert record. UI should show the **Real data** badge (`simulated=false`).

## References

- GCN Circular 21916: https://gcn.nasa.gov/circulars/21916
- Multimessenger paper: https://arxiv.org/abs/1807.08816 (ADS `2018Sci...361.1378I`)
- Initial AMON notice: https://gcn.gsfc.nasa.gov/notices_amon/50579430_130033.amon

## Replay

```bash
USE_CACHED_STREAM=True SCENARIO=scenario_b_icecube_170922a uvicorn backend.app:app --reload
# or POST /scenario/scenario_b_icecube_170922a/start
```

Do not invent numbers or citations. Keep real notice fields real.
