# IceCube historical alert catalog (real data)

Official IceCube data release: **catalog of alert events up through IceCube-170922A**.

| Artifact | Source |
| --- | --- |
| `catalog_of_alerts.txt` | Copied verbatim from the IceCube data release zip |
| Release page | https://icecube.wisc.edu/data-releases/2018/07/icecube-catalog-of-alert-events-up-through-icecube-170922a/ |
| Zip | https://icecube.wisc.edu/data-releases/20180712_IceCube_catalog_of_alert_events_up_through_IceCube-170922A.zip |

## Contents

- 50 HESE/EHE catalog rows (MJD, RA, Dec, asymmetric 90% errors)
- 45 well-localized (published ±errors); 5 marked `(-)` (would have been retracted)
- 10 realtime-era alerts, including **IceCube-170922A** at RA 77.43°, Dec +5.72°

All coordinates and times come from the IceCube file. Do not invent numbers.
`simulated=false` when converted to BREAKOUT `Alert` objects via
`backend.ingest.icecube_catalog`.

## Cross-check with Scenario B

Scenario B (`scenario_b_icecube_170922a`) uses the GCN Circular 21916 refined
direction (same RA/Dec as this catalog’s IC-170922A row). Trigger-time strings
may differ slightly (GCN circular vs MJD conversion); the sky position must match.
