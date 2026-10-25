# BREAKOUT star literature (Apify Actor)

Public **ATel** + **arXiv** discovery feed for curated supernova-progenitor stars.

This Actor is BREAKOUT Phase 2.3. It runs **offline only** (never on the
trigger-time path). Dataset rows are real public notices/preprints with live
URLs (`simulated=false`). They are **not** ranked literature claims — the MVP
index still requires an **ADS bibcode** before a claim is accepted.

## Input

```json
{
  "stars": [
    { "star_id": "* alf Ori", "aliases": ["Betelgeuse"] },
    { "star_id": "* rho Cas", "aliases": ["Rho Cassiopeiae"] },
    { "star_id": "V* VY CMa", "aliases": ["VY Canis Majoris"] }
  ],
  "sources": ["atel", "arxiv"],
  "max_per_source": 10
}
```

## Output item

| Field | Meaning |
| --- | --- |
| `star_id` | Catalog id from input |
| `source` | `atel` or `arxiv` |
| `item_id` | ATel number or arXiv id |
| `title` | Title as published |
| `date` | ISO date when available (else null) |
| `url` | Canonical public URL |
| `simulated` | Always `false` for fetched rows |

## Local run

```bash
cd actors/breakout-star-literature
pip install -r requirements.txt
# Without Apify CLI:
python -m src.main --input examples/three_stars.json --out /tmp/out.jsonl
# With Apify CLI (optional):
# apify run
```

## Store listing (short)

**BREAKOUT star literature** collects Astronomer's Telegram notices and arXiv
preprints for named massive stars (RSG/BSG/WR/…). Built for Cal Hacks 13.0
BREAKOUT so the offline literature pipeline can browse real discovery feeds
without inventing citations. Claims still go through ADS bibcodes in the MVP
index builder.
