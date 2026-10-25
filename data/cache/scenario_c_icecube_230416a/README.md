# Scenario C: IceCube-230416A (GCN public schema example)

**REAL-format** IceCube gold/bronze track notice from the NASA GCN Unified Schema
public example (not a simulated SNEWPY burst).

| Artifact | Source |
| --- | --- |
| `notice.json` | `tests/fixtures/gcn_icecube_gold_bronze_public_example.json` (GCN schema example) |
| `alerts.jsonl` | Normalized via `backend.ingest.gcn_kafka.normalize_gcn_payload(..., simulated=False)` |
| Schema | https://gcn.nasa.gov/schema (IceCube single_neutrino_alerts) |

## Real vs example

- Fields (`ra`, `dec`, `trigger_time`, `p_astro`, `far`, …) are those published in
  the GCN schema **example** notice for pipeline testing.
- `simulated=false` because this is not a SNEWPY injection; it is a published
  example of a real notice schema. UI should show **Real data**.
- No curated counterpart is asserted for this scenario (unlike TXS for 170922A).

## Replay

```bash
USE_CACHED_STREAM=True SCENARIO=scenario_c_icecube_230416a uvicorn backend.app:app --reload
# or POST /scenario/scenario_c_icecube_230416a/start
```
