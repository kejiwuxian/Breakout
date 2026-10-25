# Scenario B: IceCube-170922A / TXS 0506+056

**REAL** high-energy neutrino alert associated with the flaring blazar TXS 0506+056.
Every numeric field in `alerts.jsonl` is taken from the public GCN archive
(`simulated=false`). The blazar list is a one-shot SIMBAD/astroquery pull for
the published error region — TXS 0506+056 is matched from that catalog, not
hardcoded.

## Artifacts

| Artifact | Real or simulated | Source |
| --- | --- | --- |
| `gcn_circular_21916.txt` | Real | [GCN Circular 21916](https://gcn.nasa.gov/circulars/21916) ([txt](https://gcn.nasa.gov/circulars/21916.txt)) |
| `gcn_amon_notice_50579430_130033.txt` | Real | [AMON IceCube EHE notice](https://gcn.gsfc.nasa.gov/notices_amon/50579430_130033.amon) |
| `alerts.jsonl` | Real (`simulated=false`) | Direction + 90% PSF from Circular 21916; energy / signalness from AMON notice; Alert via `normalize_gcn_payload` |
| `blazars.json` | Real (`simulated=false`) | SIMBAD via `astroquery.simbad.Simbad.query_region` around GCN 21916 center, otypes `BLL`/`Bla` |
| Skymap | Real map from published pointing | IceCube pointing Gaussian; 1σ derived from circularized GCN 21916 90% PSF (not invented coords) |
| Breakout countdown | Skipped | Non-stellar (`BLAZAR`) → `class_window: n/a` |

## Published numbers used (do not invent alternatives)

From **GCN Circular 21916** (refined offline reconstruction):

- Trigger time: `2017-09-22 20:54:30.43 UTC`
- RA: `77.43 deg` (−0.80 / +1.30 deg, 90% PSF containment) J2000
- Dec: `+5.72 deg` (−0.40 / +0.70 deg, 90% PSF containment) J2000

From the **AMON automated notice** (same event, run 130033 / event 50579430):

- `ENERGY`: `1.1998e+02` TeV
- `SIGNALNESS`: `5.6507e-01`

Derived (documented, not invented): circularized 90% radius =
√(⟨RA½⟩⟨Dec½⟩), then 1σ = R₉₀ / √(−2 ln 0.1) for the HEALPix pointing map.

## Source URLs

- Circular HTML: https://gcn.nasa.gov/circulars/21916
- Circular text: https://gcn.nasa.gov/circulars/21916.txt
- AMON notice: https://gcn.gsfc.nasa.gov/notices_amon/50579430_130033.amon
- Event index: https://gcn.nasa.gov/circulars/events/icecube-170922a
- Multimessenger paper (context only; not used to invent alert fields): https://arxiv.org/abs/1807.08816 (ADS `2018Sci...361.1378I`)

## Regenerate blazar cache (network once; not on the trigger path)

```bash
python -c "from backend.candidates.blazars import pull_and_cache_scenario_b; print(pull_and_cache_scenario_b())"
```

UI: WebSocket events with `simulated: false` on this scenario show the **Real data** badge.
