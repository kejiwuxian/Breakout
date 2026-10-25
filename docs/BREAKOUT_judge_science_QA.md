# Project Supernova — Science Judge Q&A (Phase 1)

Public name: **Project Supernova** (repo / schemas may still say BREAKOUT).

**Source-status note:** The linked Cursor Canvas “Science basis” section returned an access error, so this is a provisional judge sheet based on opened scientific literature and official documentation, *not* a verified summary of the inaccessible page. Each answer has 2–3 sentences and links to opened sources. Project implementation, rankings, integrations, and instrument access remain **unverified** unless explicitly indicated.

## Scientific premise and timing

### 1. Are we predicting when Betelgeuse or another star will explode?
No: the defensible scientific goal is to respond to an observed neutrino alert and prioritize follow-up, not to forecast an individual star's collapse date. The shock-breakout literature says no reliable observational signature has been established that tells us a specific massive star will collapse within a designated timeframe.  
**Source:** [Kistler, Haxton & Yüksel, *Tomography of Massive Stars from Core Collapse to Supernova Shock Breakout*](https://arxiv.org/abs/1211.6770).

### 2. Why would neutrinos arrive before the first light?
A collapsing core releases neutrinos promptly, while the explosion shock must travel through the stellar envelope before its radiation escapes. That makes a neutrino burst a potential early warning for the first electromagnetic signal, known as shock breakout.  
**Source:** [Kistler et al.](https://arxiv.org/abs/1211.6770).

### 3. How long until the light breaks out?
There is no universal countdown: published progenitor-model estimates give roughly 10–100 seconds for a compact Wolf–Rayet star, at most a few hours for a blue supergiant, and about 1–2 days for some red-supergiant models. These are theoretical class-dependent examples, **not** a measured prediction for Betelgeuse or a live BREAKOUT event.  
**Source:** [LIGO/Virgo, *First targeted search for gravitational-wave bursts from core-collapse supernovae*, Section II](https://link.aps.org/accepted/10.1103/PhysRevD.94.102001).

### 4. Why do red, blue, and Wolf–Rayet progenitors have different warning windows?
Their envelopes differ enormously in size and structure, affecting how far the shock travels before reaching the surface. Compact stripped-envelope Wolf–Rayet progenitors generally offer a much shorter window than extended red supergiants, although individual stellar models and circumstellar material add uncertainty.  
**Source:** [LIGO/Virgo, Section II](https://link.aps.org/accepted/10.1103/PhysRevD.94.102001); [Kistler et al.](https://arxiv.org/abs/1211.6770).

## Localization, ranking, and evidence

### 5. Why fuse Super-Kamiokande pointing with neutrino timing?
The neutrino burst helps establish **when** the collapse occurred, while forward-scattered electrons in Super-Kamiokande can constrain **where** on the sky to search. Together, a time window and a sky region make urgent electromagnetic follow-up more targeted than an untimed all-sky search.  
**Source:** [Adams et al., *Observing the Next Galactic Supernova*](https://arxiv.org/abs/1306.0559).

### 6. Isn't timing triangulation the same as Super-K pointing?
No: Super-Kamiokande uses directional information from neutrino–electron scattering, while timing triangulation compares burst arrival information across multiple detectors. SNEWS 2.0 describes combining detector triggers and directional information, so these methods are complementary rather than interchangeable.  
**Source:** [Adams et al.](https://arxiv.org/abs/1306.0559); [Kara et al., *SNEWS 2.0 Alert Software*](https://arxiv.org/abs/2406.17743).

### 7. How do we know a neutrino alert isn't a false alarm?
A single trigger should not automatically be treated as a confirmed supernova; coincidence across independent detectors reduces accidental-alert risk. SNEWS 2.0 implements a coincidence system and reports false-positive estimates, but **BREAKOUT's live access to SNEWS is unverified**.  
**Source:** [Kara et al.](https://arxiv.org/abs/2406.17743).

### 8. Can neutrino pointing identify the exact star immediately?
Not necessarily: published Galactic-supernova studies anticipate localization uncertainties of a few degrees, not a unique stellar identification. A curated candidate list can prioritize a search, but a specific counterpart needs supporting observations.  
**Source:** [Adams et al.](https://arxiv.org/abs/1306.0559); [Walter, Scolnic & Slosar, LSST Target-of-Opportunity proposal](https://arxiv.org/abs/1901.01599).

### 9. Why precompute the literature instead of searching when the alert arrives?
Shock-breakout opportunities can be short, so having already resolved stellar names, sky coordinates, classifications, and provenance avoids literature lookups on the critical path. SIMBAD supplies cross-identifications and published object metadata, while the shock-breakout literature explicitly discusses using known likely sources to focus searches; **the speed benefit in BREAKOUT is an engineering rationale, not a measured benchmark**.  
**Source:** [SIMBAD documentation](https://simbad.cds.unistra.fr/Pages/guide/ch02.htx); [Kistler et al.](https://arxiv.org/abs/1211.6770).

### 10. Does a high candidate score mean a high probability that the star will explode soon?
No: a candidate's compatibility with an alert is different from the probability that a particular star is about to collapse. **BREAKOUT's scoring formula, training, and probability calibration are unverified**, so the dashboard must not present an arbitrary ranking score as a validated astrophysical probability.  
**Source:** [Kistler et al. on likely-source prioritization and limits of pre-collapse indicators](https://arxiv.org/abs/1211.6770).

### 11. Why use Betelgeuse as a flagship scenario?
Betelgeuse is a nearby, intensively observed red supergiant with documented surface variability and dust formation, making it useful for explaining candidate-specific evidence. In a *Betelgeuse-labeled* test, it should rank first only when the scenario's alert localization and other inputs actually favor it; **the dashboard's ranking is unverified**.  
**Source:** [Montargès et al., *A dusty veil shading Betelgeuse during its Great Dimming*](https://arxiv.org/abs/2201.10551).

### 12. Did Betelgeuse's Great Dimming mean it was about to explode?
No such conclusion follows from the cited observations: the 2019–2020 dimming is explained by local photospheric cooling and formation of dust near the star. It is evidence about atmospheric processes and mass loss, not a validated collapse countdown.  
**Source:** [Montargès et al.](https://arxiv.org/abs/2201.10551).

### 13. Why track mass loss and variability in the star index?
Mass loss changes a progenitor's surroundings, and dust or other circumstellar material can influence the observed signal and interpretation of its evolution. Variability is valuable context, but it is **not** by itself proof that collapse is imminent.  
**Source:** [Montargès et al.](https://arxiv.org/abs/2201.10551); [Kistler et al.](https://arxiv.org/abs/1211.6770).

## Observing strategy

### 14. Why prioritize ultraviolet and soft X-ray observations for shock breakout?
Shock breakout is a brief, hot first-light signal expected to be strong in ultraviolet and soft X-rays. The later optical brightening is not the same moment, so missing the breakout flash loses information about shock propagation and progenitor structure.  
**Source:** [Kistler et al.](https://arxiv.org/abs/1211.6770).

### 15. Why include infrared follow-up if the breakout is hot?
Infrared observations are valuable because Galactic dust obscures optical light more strongly and can hide or confuse progenitor identification. Adams et al. model near-infrared searches as a promising route for a Galactic event, but the **spectral peak of a normal shock breakout remains in the UV/soft X-ray**, not necessarily the infrared.  
**Source:** [Adams et al.](https://arxiv.org/abs/1306.0559); [Kistler et al.](https://arxiv.org/abs/1211.6770).

### 16. Why use a wide-field follow-up strategy instead of one pinpoint image?
Even a useful neutrino localization can cover several degrees, requiring a search area larger than a single narrow-field view. A published LSST/Rubin observing proposal specifically discusses observing that area and applying difference imaging, although **actual telescope availability is not established by the proposal**.  
**Source:** [Walter, Scolnic & Slosar, LSST Target-of-Opportunity proposal](https://arxiv.org/abs/1901.01599).

### 17. Why not point JWST at the alert immediately?
JWST's documented Target-of-Opportunity proposal rules require response times of at least 48 hours, making it unsuitable for guaranteeing the earliest seconds-to-hours shock-breakout observations. It could potentially help with later infrared science under an approved observing program, but **BREAKOUT has no verified authority to schedule it**.  
**Source:** [STScI, *JWST General Special Requirements*, Target of Opportunity](https://jwst-docs.stsci.edu/jppom/special-requirements/general-special-requirements).

### 18. What if there is a neutrino burst but no bright optical supernova?
Core collapse can, in some models, lead to black-hole formation without a normal luminous supernova, so an optical non-detection does not automatically invalidate a credible neutrino burst. Follow-up plans should preserve uncertainty and consider dust, visibility, and the possibility of a failed supernova.  
**Source:** [Adams et al.](https://arxiv.org/abs/1306.0559).

### 18b. Can community telescopes help catch a potential counterpart today?
Yes as a follow-up strategy: published Galactic-supernova plans emphasize searching a localization region quickly, and small optical/NIR instruments can cover ranked progenitor coordinates while large facilities ramp up. BREAKOUT's Phase 1 **Subscribe to events** path delivers those ranked ICRS targets via access + refresh tokens over WebSocket (`/ws/subscribe`) and `/alerts/latest`; they are **not** official GCN notices and do not confirm a supernova by themselves.  
**Source:** [Adams et al.](https://arxiv.org/abs/1306.0559); [Walter, Scolnic & Slosar](https://arxiv.org/abs/1901.01599).

## Demonstration integrity

### 19. Why replay IceCube-170922A, and should TXS 0506+056 come out first?
TXS 0506+056 is the literature-supported leading counterpart for the historical 2017 IceCube high-energy neutrino, which coincided with a gamma-ray flare; **the actual BREAKOUT ranking has not been inspected**. This event concerns a distant blazar rather than a Galactic MeV core-collapse burst, and the often-quoted 3.5σ evidence refers to a *separate 2014–2015 archival excess*, not a certainty score for the 2017 event.  
**Source:** [IceCube et al., 2017-event paper](https://arxiv.org/abs/1807.08816); [IceCube et al., archival analysis](https://arxiv.org/abs/1807.08794).

### 20. What is real, and what is simulated in the demo?
Published stellar metadata, literature references, and historical IceCube records are real; injected triggers, generated measurements, or hypothetical observations are simulations and must be marked `simulated=true` in JSON and visibly **Simulated** in the interface. **Unverified:** I have not inspected the running app or the inaccessible plan page, so I cannot certify that every synthetic output is actually labeled or that any live detector/telescope integration exists.  
**Source:** [SIMBAD documentation](https://simbad.cds.unistra.fr/Pages/guide/ch02.htx); [IceCube historical data release](https://icecube.wisc.edu/data-releases/2018/07/icecube-data-from-2008-to-2017-related-to-analysis-of-txs-0506056/).

---

**Presentation guardrails:** Never promise an explosion date, interpret a ranking score as a calibrated probability without validation, confuse MeV supernova bursts with TeV blazar events, treat the 2014–2015 3.5σ historical excess as a 2017 significance, or claim control over telescopes. All numerical timings above are explicitly *published model estimates* or official instrument requirements, not simulated BREAKOUT outputs.

**Source review provenance:** These scientific and documentation links were opened during this review. The user's Cursor Canvas link was inaccessible; the wording above is not verified against its “Science basis” section.
