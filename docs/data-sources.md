# Source provenance and connection status

The header light reports the browser's WebSocket connection to this app.
It does not establish a connection to a neutrino observatory and is not a
supernova detection indicator. Click it to inspect **Data sources & connection**.

`GET /api/data-sources` reports the server's actual cached/live configuration,
source receipt timestamps and counters. It returns no access credentials.
All receipt evidence is local to the running server process and resets on restart.
Replaying a fixture does not advance live-source receipt counters.

| Displayed state | Evidence |
| --- | --- |
| Off in demo mode | `USE_CACHED_STREAM=True`; live ingestion is disabled. |
| Not configured | A required credential pair is missing. |
| Awaiting broker traffic | Live mode and credentials are configured; receipt has not been observed. A subscription request is not proof of a broker connection. |
| Traffic received | This process received a message on that transport. Check the separate science/test counters before interpreting it. |
| Feed unavailable | The listener failed. |
| Catalog / reference | A catalog or literature reference, rather than an alert stream. |

## Supported observatory feeds

| Feed | Documented distribution | Meaning |
| --- | --- | --- |
| [IceCube Gold/Bronze tracks](https://gcn.nasa.gov/missions/icecube) | `gcn.notices.icecube.gold_bronze_track_alerts` | Selected high-energy neutrino candidates. NASA GCN estimates about 26 alerts per year; these are not confirmed supernovae. |
| [IceCube cascades](https://gcn.nasa.gov/missions/icecube) | `gcn.classic.text.ICECUBE_CASCADE` | An additional event topology. The documented rate is about eight alerts per year, with wider localization uncertainty. |
| [Super-K direct burst notices](https://gcn.nasa.gov/missions/sksn) | `gcn.notice.superk.sn_alert` | Direct observatory burst notices, including explicit service tests. The GCN page lists an expected 0.03 real core-collapse alerts per year and 24 tests per year. Tests are not detections. |
| [SNEWS coincidences](https://gcn.nasa.gov/missions/snews) | `gcn.classic.text.SNEWS` | Coincidences across the network. NASA GCN lists an expected 0.03 real alerts per year and 52 test notices per year. |
| [Optional SNEWS Hopskotch](https://snews2.org/) | Configured authorized SNEWS channel | Another transport for SNEWS, not another independent detector. Requires the optional client and separate credentials. |

The cascade Kafka topic name is also present in NASA GCN's
[published topic metadata](https://github.com/nasa-gcn/gcn.nasa.gov/blob/main/app/components/NoticeTypeCheckboxes/rates.ts).
Schemas for direct Super-K notices are published by
[NASA GCN](https://github.com/nasa-gcn/gcn-schema/tree/main/gcn/notices/superk).
The collaboration's
[cascade specification](https://gcn.gsfc.nasa.gov/doc/High_Energy_Neutrino_Cascade_Alerts.pdf)
defines the text fields and localization containment.

The reserved pre-supernova JSON topic and unverified SNEWS2 JSON topic are not
default public subscriptions. Their existing payload normalizers remain
available for authorized integrations and explicit fixtures.

## Measurements and derived outputs

Background star positions come from the committed
[Yale BSC5 catalog snapshot](https://heasarc.gsfc.nasa.gov/W3Browse/star-catalog/bsc5p.html).
Candidate evidence links to existing [ADS](https://ui.adsabs.harvard.edu/) records.
Neither catalog membership nor a literature ranking is a neutrino detection.

The new notice normalizers preserve the original payload and published
uncertainty. The fallback localization is a circular spherical Gaussian matched
to the published containment probability; it is not the collaboration's full
probability map. Missing positions are rejected rather than replaced with zero
coordinates. A supplied usable HEALPix map remains the preferred map input.

Declared tests, injections and retractions are excluded before science ranking
and community notification. They can demonstrate transport activity without
raising the science count. The 2017 IceCube replay remains **Historical**; the
Galactic CCSN fixture remains **Simulated**. Frequent real neutrino interactions
inside a detector do not imply frequent public, localized astrophysical alerts.

## Focused verification

```sh
python -m pytest tests/test_source_provenance_safety.py tests/test_live_channels.py tests/test_gcn_kafka.py
```

The tests use format examples and mocked broker traffic. They verify missing
measurement rejection, scientific containment, excluded test/retraction
traffic, credential non-disclosure, and observed receipts versus configured
access. They do not subscribe to live brokers or send notifications.
