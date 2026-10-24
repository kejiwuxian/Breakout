# Scenario A: galactic core-collapse (Betelgeuse path)

**SIMULATED** SNEWPY burst with Stage 0 KamLAND + Super-K pre-SN alert.

| Artifact | Real or simulated |
| --- | --- |
| `alerts.jsonl` | Simulated (every Alert has `"simulated": true`) |
| Detector geometry (WGS84) | Real EarthLocation positions |
| Arrival times / rates | Simulated via snewpy |
| Voice clips under `voice/` | Pre-rendered Grok TTS for `VOICE_MODE=cached` (later) |

Do not invent numbers. Later prompts fill `alerts.jsonl`.
