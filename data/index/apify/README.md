# Apify literature discovery feed

Per-star JSON written by `backend/integrations/apify_literature.py` when
`APIFY_ENABLED=True` (offline only).

Files are named `<star_id_slug>.json`. Each file lists public ATel/arXiv items
with real URLs and `simulated=false`. Empty `items` means the actor found
nothing — never invent rows here.

These feeds do **not** replace ADS-backed claims in `backend/literature/index.parquet`.
