# BREAKOUT star literature

Apify Actor that collects public **Astronomer's Telegram** notices and **arXiv**
preprints for curated massive-star progenitors.

Built at **Cal Hacks 13.0** for [BREAKOUT](https://github.com/kejiwuxian/Breakout)
(Phase 2.3), starting from:

```bash
apify create breakout-star-literature --template python-start
```

## What it does

For each input star (`star_id` + `aliases`), the Actor searches ATel and/or the
arXiv API, keeps only hits that **actually mention** the star, rate-limits
requests, and pushes one dataset item per hit.

These rows are a **discovery feed**. BREAKOUT’s ranked literature index still
requires an **ADS bibcode** before a claim is accepted (`build_index.py`
resolves Apify items through ADS and drops anything without a bibcode).

## Input

See `.actor/input_schema.json`:

```json
{
  "stars": [
    { "star_id": "* alf Ori", "aliases": ["Betelgeuse"] },
    { "star_id": "* rho Cas", "aliases": ["Rho Cassiopeiae"] },
    { "star_id": "V* VY CMa", "aliases": ["VY Canis Majoris"] }
  ],
  "sources": ["atel", "arxiv"],
  "max_items_per_star": 10
}
```

## Output example

```json
{
  "star_id": "* alf Ori",
  "source": "arxiv",
  "item_id": "2006.09837",
  "title": "…",
  "date": "2020-06-17",
  "url": "https://arxiv.org/abs/2006.09837",
  "abstract_or_summary": "…",
  "simulated": false
}
```

Every fetched item is `simulated=false`. Empty results mean nothing matched —
rows are never invented.

## Local run

```bash
cd actors/breakout-star-literature
pip install -r requirements.txt
# INPUT.json is under storage/key_value_stores/default/ (3 stars)
apify run
# Or without the CLI:
python -m src
```

Dataset items should open at their `url` fields in a browser.

## Store listing (short)

**BREAKOUT star literature** collects ATel notices and arXiv preprints for named
massive stars so BREAKOUT’s offline index can browse real discovery feeds without
inventing citations. Claims still go through ADS bibcodes in the MVP index builder.
