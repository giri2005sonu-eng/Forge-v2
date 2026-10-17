# FORGE — Robot BOM Agent

**Azinhack 2026 · AI Engineering track · Team: [Team name] — [Member 1], [Member 2], [Member 3], [Member 4]**

> AI reads. Rules decide. Every number has a source.

## Problem
Picking parts for a hobby robot is slow and error-prone. Specs are scattered across shop pages and datasheets, the same product name can mean very different things (a search for "Arduino Nano" returned verified listings from ₹229 to ₹2,755: a clone, a starter kit and the original), and one wrong voltage or current mismatch can burn a board.

## What FORGE does
1. **Recommendation helper (skippable):** a nine-question survey (career direction, experience, languages, schedule, budget, tools, hardware, goal, interests) plus an optional resume upload ranks projects from a catalog of 150 projects across 16 domains (`core/project_data/projects.csv`). Hard limits (budget, deadline hours, tools) filter first; deterministic scoring over 12 factors then ranks the rest, diversified by domain, and a radial chart shows how each factor fits the user. Gemini is used only to structure resume evidence (every item must carry an exact quote from the resume and is confirmed by the user), and TinyFish can research a dream job or industry. **Build to compete** lets users shortlist projects tagged for a competition event (`core/project_data/competition_projects.csv`). Users can also describe their own idea; keyword rules (then Gemini, if a key is set) map it to a BOM-supported project or say honestly that it is not supported yet.
2. **BOM generation:** the app tries every combination of controller, driver, motors, battery and sensor, rejects any that fail a compatibility rule, and picks the cheapest valid build within budget.
3. **Compatibility checks:** deterministic formulas give PASS / FAIL / UNKNOWN. A missing spec is UNKNOWN, never guessed.
4. **Live prices with proof:** TinyFish finds and reads real vendor pages; a price is accepted **only if its exact quote appears on the page**, shown next to the verified product name and link.

5. **Ideas outside the three builds (drone, robot arm, ...):** the idea goes to Gemini, which only *names* the components (name, quantity, shop search phrase). Each name is then handed to TinyFish (Search + Fetch) and priced with the same quote-checked rules. Gemini never supplies a price or a spec. Parts with no verified price show as "not found" and are left out of the total. Compatibility is **not** rule-checked for these builds; Gemini's "things to verify" list is shown as a suggestion only (`core/custom_bom.py`).
6. **Shop comparison and bill:** one row per part, one column per verified shop listing. The cheapest is ticked by default; tick another to buy that one. Listings whose price could not be verified are never suggested or used by default, but you can tick one yourself and type the price you saw; the bill and ledger label it as entered by you, not verified. A structured bill updates live and can be downloaded as a PDF. Nothing is added that the pages did not state (no tax or shipping guesses).

7. **Part specs and side-by-side comparison:** every one of the 231 parts in the library (`core/part_specs.py`) has typed specs (voltage ranges, current, clock/memory, range, accuracy, capacity, torque, and so on) or a stated reason it has none. Project BOMs pick them up automatically. In the **Part specs** panel you pick any component of your build to see its specs, then switch on "Compare with other microcontrollers / motor drivers / sensors ..." to put it next to similar library parts; the best value in each row is green (only where "better" is defined, e.g. lower voltage drop, longer range).


## How TinyFish is used
| Feature | TinyFish API | Cost |
|---|---|---|
| Find shop pages for each part (videos, social posts, category pages filtered out) | **Search** | free |
| Read the pages for price, product name and specs | **Fetch** | free |
| Research what a project needs: find build guides, list the components they state, with quotes | **Search + Fetch** | free |
| Cart check: open a verified listing, add one unit to the cart, read the cart | **Web Agent** | credits, opt-in |
| Real project examples in the recommendation helper | **Search** | free |

Prices are read from each page's text by **rules first (no LLM, no quota)**; Gemini is only a **capped backup** for pages the rules cannot read. Either way a value is kept **only if its quote is found on the page** (prices also need the number inside the quote). If prices for one part differ by more than 3x, the app warns they are probably different products or variants. Search and Fetch results are cached on disk.

**Web Agent safety and cost:** it runs only when you click, is capped at 12 steps (about 12 credits at TinyFish's published 1 credit per step) and 180 seconds, and is told never to check out, log in or enter personal details. That last part is an instruction to the agent, not a technical block, so run it only on public shop pages and never with saved logins or payment details. Repeat runs of the same listing are served from the cache.

## Evidence ledger, low Gemini use, clone-vs-original check
- **Evidence ledger** (expander under the bill, CSV download): every number in the BOM with status, source, URL, time, method and the quote. `verified` = read from a shop page. `seed` = typed in by the team and **not** checked on any page. Cells from web pages are neutralised against spreadsheet formula injection.
- **Rules first, Gemini last:** `core/pagerules.py` reads price, stock and product name from the page text (skipping shipping thresholds, EMI, price ranges and MRP). Gemini runs only for pages the rules cannot read, at most `GEMINI_FALLBACK_MAX` pages per part (default 1, `0` = never), with a short price-only prompt, and the first 429 switches it off for a minute. Live prices work with **no Gemini key at all**.
- **Clone-vs-original check:** a page that sells the *original/genuine* version of a generic part gets its price withheld with a note, instead of silently entering the BOM.

## The role of AI
- **AI reads (pretrained Gemini + TinyFish):** TinyFish finds and fetches pages; page rules read prices first, and Gemini is a capped backup that must return a quote containing the exact price; Gemini structures resume evidence (quote-checked, confirmed by the user) and names components for ideas not in the catalog (saved so each costs one call).
- **Rules decide:** compatibility is plain formulas written by us, so a wrong "compatible" can't be invented by a model. The recommendation scoring is also plain code (same answers, same result).
- We did **not** train our own model: this is an agentic pipeline with verification, not a trained model. Learning the recommender from data is listed under future scope.

## Architecture
```
app.py              Streamlit router (picker -> results / competition -> BOM agent)
ui/recommendation.py  survey, resume box, ranked results
ui/competition.py   Build-to-compete event shortlist
ui/bom.py           BOM screen: live prices, shop comparison, bill, evidence ledger
ui/research_tools.py  build-guide research, spec check, cart check
core/picker.py      survey normalisation, hard-limit filter, 12-factor ranking + radial chart
core/recommendation_catalog.py  loads the project CSVs into factor and label catalogs
core/resume.py      resume text reader (PDF/DOCX/TXT) + quote validation
core/project_data/  projects.csv (150 projects, 16 domains), competition_projects.csv (18 projects, 14 events)
assets/fonts/       DejaVu Sans (Bitstream Vera licence), used so the PDF can print the rupee sign
core/custom_bom.py  Gemini names components for unsupported ideas, TinyFish sources each one
core/pipeline.py    selector, TinyFish sourcing, Gemini extraction with quote check
core/research.py    project research from build guides (Search + Fetch + Gemini)
core/part_specs.py  typed specs for all 231 library parts + side-by-side comparison
core/specs.py       reader that compares typed specs with a shop page's text (kept and tested, not shown in the UI)
core/pagerules.py   rule-based page reader (price, stock, name) + clone-vs-original check, no LLM
core/ledger.py      evidence ledger rows + safe CSV export
core/bill.py        shop choice per part, bill totals, on-screen invoice and PDF
core/rules.py       PASS / FAIL / UNKNOWN engine
core/data.py        parts catalog, extras, rules, projects
core/tf.py          TinyFish wrapper (Search + Fetch, disk cache)
tests/              automated tests (run offline)
```

## Setup
Python 3.12 is recommended (that is what we tested on).
```
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env      # add your own keys, never commit .env
python -m pytest tests -q
streamlit run app.py
```
Keys: `TINYFISH_API_KEY` (agent.tinyfish.ai) and `GEMINI_API_KEY` (aistudio.google.com/apikey). Default model `gemini-3.8-flash`; if a model is busy or unavailable the app retries and falls back to `gemini-3.5-flash-lite`. Without keys the app still runs on seed prices, clearly labelled.
Check the TinyFish connection: `python -m core.tf`

## What is rule-checked and what is not
- **Rule-checked builds (3):** line follower, obstacle avoider, Bluetooth car. Compatibility (voltage, current, logic level) is checked by formulas for these only.
- **Catalog projects (168):** component lists drafted by the team (`bom_status: draft`, `reviewed: false`). They get live prices but **no compatibility checking**.
- **New ideas:** one Gemini call names the components (saved for next time), then TinyFish prices them. Also not compatibility-checked.

## Honest limitations
- **Part specs are typical values typed by the team** for the common hobby board or chip (for example the HC-SR04 module, the GY-521 MPU6050 board). A different listing of the same chip can differ (supply range, current, pinout), so they are labelled `seed` in the evidence ledger (not verified on any page). Specs are compared, not yet fed into the compatibility rules; only the catalog builds are rule-checked.
- The research, spec-check and cart-check features show results for review; they do not change the BOM automatically. Guide quality varies, and many components in guides will not be in our catalog (shown as not covered).
- The rule-checked parts catalog is small (11 parts plus 3 extras). **Specs are typical datasheet values we entered by hand;** only prices and product names are read live. The spec-check tool shows where a shop page disagrees but never changes a spec silently.
- The three rule-checked builds differ only by sensor type and a Bluetooth flag; the other part roles are shared. Sumo bot and maze solver are **planned but not built** as rule-checked builds: they need their own parts, specs and rules.
- Price reading uses heuristics. Shipping fees, price ranges, EMI figures, related-product prices and accessories are screened out, but some pages will still be misread, so every price shows its quote and link. Stock is never read.
- The recommendation helper's difficulty, time and cost scores are our estimates, not measured data.
- Extras (chassis, wires, switch) carry rough estimate prices until live sourcing verifies them, and chassis-to-motor fit is not rule-checked.
- Live sourcing depends on TinyFish and Gemini availability; results are cached, but some pages will show "price not verified".

## Future scope
1. Turn the research step's findings into each project's parts list (today they are shown as evidence, with a person deciding).
2. Apply verified live specs to the rule engine, with a confidence label, instead of showing them only as a diff.
3. Detect bundles and multi-packs so they are never used as a single-part price.
4. Project-specific rules and parts for sumo bot and maze solver, then drones.
5. Learn the recommender from real project outcomes.

## Project Optimizer
*Change any component. Understand the impact. Build smarter robots.* Generate a BOM, then press the separate **Project Optimizer** button directly below *Component details* (press again to close). The tool opens inline on the same page.
1. Pick a component role, then one or more alternatives (the catalog plus every part in the profile dataset), or type a part that is not listed. Every alternative is compared with the **original** build (kept in session state, never modified).
2. The top of each comparison lists **what changes** in plain language (e.g. Nano to ESP32: gains Wi-Fi and Bluetooth, 15x clock, 3.3 V logic needs level shifting, runtime -12%). Below it every metric shows original, proposed, difference, %, status, reason and a data label (Typical data / Estimated / No data yet).
3. Metrics: cost, compatibility, Wi-Fi, Bluetooth, clock, RAM, flash, ADC/PWM channels, spare GPIO, power, runtime, speed, torque, pushing force, motor-stage efficiency, weight. A metric the change cannot influence says "Not affected".
4. An incompatible alternative can be inspected but not kept. **Keep this replacement** builds a new BOM (existing bill and PDF export); **Undo all replacements** restores the original. "Find live price" reuses TinyFish sourcing.
5. Goals rank candidates by cost, fewest issues, connectivity, speed, torque, runtime, weight or processing where the data supports it.

### How the optimizer gets its data
```
core/profiles.py       part profiles: curated (data/part_profiles.json) + run-time additions (data/swap_store.json), field validation, atomic writes
core/swap_dataset.py   pair records "A -> B": shipped pairs, then run-time pairs, then computed from the two profiles and saved
core/impact.py         whole-build effects (speed, torque, current, runtime, efficiency, weight, GPIO) from profiles; first-order formulas stated in each row
core/profile_fill.py   fallback for a part with no profile: produces one, validates every field, stores it. Silent: never raises into the UI, never named on screen
ui/optimizer.py        the Streamlit panel (draws results only; every number comes from core/)
scripts/profile_seed.py + scripts/build_swap_dataset.py   rebuild data/part_profiles.json (python -m scripts.build_swap_dataset)
```
Lookup order for a swap: dataset pair, then run-time pair, then compute from profiles, and only when a profile is missing, the fallback. Each fallback result is saved, so the same swap is a dataset read afterwards. Values in the curated dataset are **typical** figures, not measurements of your exact board; fallback values are labelled **Estimated**. Fallback limits: `OPT_FILL_MAX` per process, a 10-minute pause per failing part, and out-of-range or incomplete data is rejected rather than stored. On hosts with a read-only or temporary disk the swap_store file does not persist between restarts.

### Where the optimizer applies
It works on the **rule-checked builds** (line follower, obstacle avoider, Bluetooth car): controller, driver, motor, battery and sensor. Catalog-dataset and Gemini/learned component lists have no compatibility rules or part profiles, so on those the button shows an explanation instead of numbers. It never calls Gemini for a part that already has a profile; the fallback runs only for a part you type that is not in the dataset, capped by `OPT_FILL_MAX`.
Verified-evidence values in `data/components.json` (for example Arduino Nano VIN 7-15 V from the Arduino datasheet) override the typical values and are flagged as catalog corrections. Rebuild/validate: `python -m core.specification_validator`.

## Hybrid planning: catalog first, Gemini only for genuinely new ideas
The BOM page has two inputs:
1. **Pick a project from the catalog** (all 168: 150 from `projects.csv`, 18 from `competition_projects.csv`). The component list comes from `core/project_data/project_boms.json`. **No Gemini call.** TinyFish then fetches live prices for each part. The three rule-checked builds (line follower, obstacle avoider, Bluetooth car) still use the rule builder.
2. **Build anything new.** Lookup order: learned plans -> exact catalog name match -> free keyword rules -> "similar catalog projects" suggestions (you choose) -> **one** Gemini call. That Gemini plan is saved to `core/project_data/learned_projects.json` (path: `FORGE_LEARNED_PATH`), so the same idea (any word order) is free next time. Ideas with numbers ("4 motor") never auto-match the catalog, because quantities must not be dropped. `FORGE_GEMINI_PLANS_PER_SESSION` (default 5) caps spend per visitor; a failed Gemini call saves nothing.

Planning no longer asks Gemini to guess which project an idea means (the idea box still uses keyword rules, then Gemini, only to pick one of the three rule-checked builds), and catalog/learned builds do not use Gemini to read shop pages unless `FORGE_DATASET_GEMINI_FALLBACK` is set above 0.

### What the dataset is, and is not
`project_boms.json` holds **draft component lists**: names, roles, quantities, shop search phrases and engineering notes, written from each project's description, skills, safety tags and (for competition projects) event and constraints. It contains **no prices** (TinyFish supplies those, each with a quote) and **no verified specs**. Every list is `bom_status: draft`, `reviewed: false`. Constraints such as "ExpressLRS radio" or "high-discharge LiPo" shape the parts but are requirements to check, not proof that a part satisfies them. Three projects are software-only and have no parts. Learned (Gemini) plans are likewise unreviewed.
- Rebuild after editing: `python scripts/build_project_boms.py` (recipes in that file, part archetypes in `scripts/parts_library.py`). It fails if any CSV project has no list.
- Review learned plans in `learned_projects.json` and promote good ones into the recipes. On hosts with an ephemeral disk, point `FORGE_LEARNED_PATH` at persistent storage or learned plans are lost on restart.

## EMI / instalment figures are never prices
"EMI starts at ₹86 per month" used to be read as an ₹86 product price. Now one rule (`pagerules.trusted_price`) decides, and it is applied when a page is read, when a price is used (BOM, cheapest price, price-range warning, ledger, cart check) and when it is shown. A price whose own quote shows EMI / per-month / instalment wording is moved to **Price not verified** with the reason. Old cached reads are ignored (cache key `x3:`), so nothing stale survives an upgrade.

## Same live panel for "Generate BOM"
Picking a rule-checked project in step 1 now opens the same "TinyFish is searching vendors and reading pages..." panel as "Plan new build": the rules define every candidate part (no AI), TinyFish prices **all candidates, not only the current winner** (no Gemini), and the build is re-selected with the verified prices so the comparison is fair. Parts that already have listings are kept, so reopening a project is quick. Without a TinyFish key no panel is shown.

## Price safeguards
- **Shipping, ranges, EMI:** a figure after "shipping/delivery/handling...", a price followed by "- ₹450" or "to ₹450", and EMI/instalment wording are never read as the product price. Prices printed before the product name's first appearance on the page are ignored when a later one exists (banners, related items).
- **Strict quote check:** a price from Gemini is accepted only if a number written in its quote **equals** the price (`5` does not match "Rs 1,599.00"; decimals are kept).
- **Suspiciously low prices:** a verified price far below the team's estimate for that part, or far below the other listings while not clearly named like the part, is flagged "UNUSUALLY LOW · CHECK". It stays selectable, but it is never the default and never sets the BOM price. A genuine cheap clone named like the part is not flagged by the comparison rule.
- **Cache expiry:** cached TinyFish and price results expire after `FORGE_CACHE_HOURS` (default 72; 0 = never). The cache lives in the project folder, not the folder you run from.
- **Pinned dependencies:** `requirements.txt` uses compatible-release pins to the versions we tested.
