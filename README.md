# Project Supernova

**Neutrinos arrive first. We aim telescopes before the light.**

When a nearby star dies, a neutrino burst can reach Earth minutes to hours
ahead of optical shock breakout. Project Supernova turns that head start into
a sky localization, a ranked list of likely progenitor stars, and live alerts
observers can act on — before the flash.

Internal code and package names still say `breakout`; the product you demo is
**Project Supernova**.

## What it does

1. Ingests supernova / high-energy neutrino alerts (cached IceCube & galactic
   CCSN replays offline; live GCN / SNEWS-style channels when configured).
2. Draws a localization on an all-sky map and ranks stars inside the area of
   interest against a precomputed literature inventory.
3. Pushes ranked ICRS coordinates to anyone who **Subscribes to events** —
   campus scopes and backyard instruments included — over a live WebSocket.

No invented bibcodes. Simulated runs wear a **Simulated** badge. Community
packages are follow-up helpers, not official GCN notices.

## Why it matters

Core collapse releases neutrinos promptly; the explosion shock still has to
climb through the stellar envelope before light escapes. That gap is the race:
localize, prioritize known massive stars, and get coordinates onto real
instruments while the optical breakout window is still open. Class-dependent
models put that window from tens of seconds (compact WR) to about a day
(some RSG cases) — estimates, not countdown clocks for any one star.

## Demo in five steps

1. **Idle** — cold start listens (`live_waiting`); full Yale BSC5 sky, empty
   ranked list. Nothing auto-plays.
2. **Replay** — run IceCube-170922A or the galactic CCSN / Betelgeuse scenario
   from the UI rail (or `POST /scenario/.../start`).
3. **Skymap AOI** — dual red outlines appear; the view zooms to the outer
   aperture; field + ranked stars light up.
4. **Ranked progenitors** — posterior-sorted candidates with class life
   window, confidence, and ADS-backed evidence where the index already has it.
5. **Subscribe** — mint access + refresh tokens, open `/ws/subscribe`, watch
   the next candidate package land (also mirrored at `/alerts/latest`).

Mission UI: `frontend/` on port **5173** (Project Supernova redesign). Optional parallel `frontend-v2/` remains on **5174**.

## Built for Cal Hacks & SpaceX

**Cal Hacks (main track)**

- Clear problem → working demo path → measurable surface (skymap, ranking,
  subscribe).
- End-to-end product in one loop: alert → localization → ranked stars →
  actionable feed.
- Stack at a glance: FastAPI + Vite/TypeScript, SVG Mollweide skymap, offline
  progenitor inventory + optional Grok ranking, WebSocket community alerts.

**SpaceXAI — Make it Legendary**

- Real astrophysics data paths: SNEWS-style timing, IceCube historical alerts,
  Yale BSC5 sky field.
- Latency is the product: neutrino lead time becomes follow-up urgency.
- Actionable alerts for human observers — coordinates on the wire, not a
  slideshow. Grok Voice for announcer / judge Q&A when keys allow.

## What’s inside

| Surface | Role |
| --- | --- |
| **SVG skymap** | Yale BSC5 all-sky background; curated ∪ outer-AOI ranked overlay; dual red outlines; wheel zoom / drag pan. |
| **Progenitor ranking** | Offline inventory + enrich-replay; CandidateScore v1.1; Grok scoring when cached or keyed. |
| **Subscribe to events** | Open access + refresh tokens → `/ws/subscribe`; honesty labels preserved. |
| **Replay scenarios** | Galactic CCSN, IceCube-170922A and siblings under `data/cache/`. |
| **Actions / voice** | LCOGT / ToO / GCN draft builders; optional Grok Voice mission control. |

Deeper post-MVP feature index: [`docs/post-mvp.md`](docs/post-mvp.md).  
Science judge sheet: [`docs/BREAKOUT_judge_science_QA.md`](docs/BREAKOUT_judge_science_QA.md).

## For developers / setup

Install, ports, env flags, scenarios, `mvp_gate`, schemas, and Apify notes live in
**[`docs/developers.md`](docs/developers.md)** — kept out of this page so the
story stays scannable.

**Public demo:** [`https://supernova.lylinks.com`](https://supernova.lylinks.com)
(Cloudflare tunnel → local API + static UI). Local loopback still uses
`127.0.0.1:8000` / Vite `:5173`. See `BREAKOUT_PUBLIC_BASE_URL` / `scripts/run_public.sh`
in the developer doc.
