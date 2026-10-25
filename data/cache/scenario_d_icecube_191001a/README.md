# Scenario D: IceCube-191001A (GCN Circular 25913)

**REAL** IceCube Astrotrack Gold alert. Direction and timing come from the
public GCN Circular and AMON notice archives (not invented).

| Artifact | Source |
| --- | --- |
| `alerts.jsonl` | GCN Circular 25913 refined direction (RA 314.08°, Dec +12.94° J2000; 2019-10-01 20:09:18.17 UTC) |
| `notice.json` | Same fields in GCN Unified Schema shape for `normalize_gcn_payload` |
| `gcn_circular_25913.txt` | Local copy of https://gcn.gsfc.nasa.gov/gcn3/25913.gcn3 |
| `gcn_amon_notice_133119_22683750.txt` | Local copy of https://gcn.gsfc.nasa.gov/notices_amon_g_b/133119_22683750.amon |
| Pointing `err_deg` ≈ 2.95° | AMON revision-1 `SRC_ERROR` 177 arcmin (90% containment, stat-only) |
| Detector WGS84 (IceCube) | Real lab coordinates (`backend.config.DETECTOR_TABLE`) |

## Real vs simulated

- All alert fields use `simulated: false`. UI should show **Real data**.
- No curated counterpart is asserted here (TDE AT2019dsg follow-up is
  literature context only; not required for pointing/fuse validation).
- Asymmetric 90% PSF errors from GCN 25913:
  RA +6.56/−2.26°, Dec +1.50/−1.47° (dust-layer track; larger than average).

## References

- GCN Circular 25913: https://gcn.nasa.gov/circulars/25913
- AMON notice: https://gcn.gsfc.nasa.gov/notices_amon_g_b/133119_22683750.amon

## Replay

```bash
USE_CACHED_STREAM=True SCENARIO=scenario_d_icecube_191001a uvicorn backend.app:app --reload
# or POST /scenario/scenario_d_icecube_191001a/start
```

Do not invent numbers or citations. Keep real notice fields real.
