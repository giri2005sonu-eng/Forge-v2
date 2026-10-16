# FORGE — Robot BOM Agent

**Azinhack 2026 · AI Engineering track · Team: [Team name] — [Member 1], [Member 2], [Member 3], [Member 4]**

> AI reads. Rules decide. Every number has a source.

## Problem
Picking parts for a hobby robot is slow and error-prone. Specs are scattered across shop pages and datasheets, the same product name can mean very different things (a search for "Arduino Nano" returned verified listings from ₹229 to ₹2,755: a clone, a starter kit and the original), and one wrong voltage or current mismatch can burn a board.

## What FORGE does
1. **Recommendation helper (skippable):** a landing page with two optional inputs: a survey (six multi-select questions that open when you click the box) and a resume/CV upload (PDF, DOCX or TXT). Projects are ranked from the survey, the resume, or both, and a radial chart shows how each attribute fits the user. The resume is a scored factor, and the page quotes the resume lines that justify a match. Users can also describe their own idea; Gemini maps it to a supported project or says honestly that it is not supported yet.
2. **BOM generation:** the app tries every combination of controller, driver, motors, battery and sensor, rejects any that fail a compatibility rule, and picks the cheapest valid build within budget.
3. **Compatibility checks:** deterministic formulas give PASS / FAIL / UNKNOWN. A missing spec is UNKNOWN, never guessed.
4. **Live prices with proof:** TinyFish finds and reads real vendor pages; a price is accepted **only if its exact quote appears on the page**, shown next to the verified product name and link.

5. **Shop comparison and bill:** one row per part, one column per verified shop listing. The cheapest is ticked by default; tick another to buy that one. A structured bill updates live and can be downloaded as a PDF. Nothing is added that the pages did not state (no tax or shipping guesses).

## How TinyFish is used
| Feature | TinyFish API | Cost |
|---|---|---|
| Find shop pages for each part (videos, social posts, category pages filtered out) | **Search** | free |
| Read the pages for price, product name and specs | **Fetch** | free |
| Research what a project needs: find build guides, list the components they state, with quotes | **Search + Fetch** | free |
| Check our typed specs against what the shop pages state | **Fetch** (pages already read) | free |
| Cart check: open a verified listing, add one unit to the cart, read the cart | **Web Agent** | credits, opt-in |
| Real project examples in the recommendation helper | **Search** | free |

Gemini reads fetched text; a value is kept **only if its quote is found on the page** (prices also need the number inside the quote). If prices for one part differ by more than 3x, the app warns they are probably different products or variants. Search and Fetch results are cached on disk.

**Web Agent safety and cost:** it runs only when you click, is capped at 12 steps (about 12 credits at TinyFish's published 1 credit per step) and 180 seconds, and is told never to check out, log in or enter personal details. That last part is an instruction to the agent, not a technical block, so run it only on public shop pages and never with saved logins or payment details. Repeat runs of the same listing are served from the cache.

## The role of AI
- **AI reads (pretrained Gemini + TinyFish):** Gemini converts an uploaded resume into structured factors with verbatim evidence quotes. TinyFish searches and reads public career pages for the student's target role. Neither service chooses or scores projects.
- **Rules decide:** compatibility is plain formulas written by us, so a wrong "compatible" can't be invented by a model. Recommendation scoring and hard-limit filtering are also deterministic code.
- We did **not** train our own model. Learning the recommender from data is listed under future scope.

## Architecture
```
app.py              Streamlit setup, shared session state, and page routing
ui/recommendation.py  landing page (survey + resume upload), results, and project handoff
ui/bom.py           BOM selection, compatibility display, sourcing, vendor comparison, and bill
ui/research_tools.py build-guide research, spec comparison, and optional cart check
core/picker.py      recommendation scoring (survey + resume factor) + radial chart
core/resume.py      resume text extraction + quote-verified Gemini factor validation
core/recommendation_catalog.py  project CSV loader and recommendation-only project metadata
core/project_data/  supplied project catalog and competition project variants
assets/fonts/       DejaVu Sans (Bitstream Vera licence), used so the PDF can print the rupee sign
core/pipeline.py    selector, TinyFish sourcing, Gemini extraction with quote check
core/research.py    project research from build guides (Search + Fetch + Gemini)
core/specs.py       typed specs vs specs stated on shop pages
core/bill.py        shop choice per part, bill totals, on-screen invoice and PDF
core/rules.py       PASS / FAIL / UNKNOWN engine
core/data.py        parts catalog, extras, rules, projects
core/tf.py          TinyFish wrapper (Search + Fetch, disk cache)
tests/              automated tests (run offline)
```

### Parallel work areas
- **Recommendation page:** `ui/recommendation.py`, `core/picker.py` and `core/resume.py`.
- **BOM page:** `ui/bom.py`, `core/pipeline.py`, `core/bill.py`, and `core/rules.py`.
- **Research and extras:** `ui/research_tools.py`, `core/research.py`, `core/specs.py`, and `core/tf.py`.

`app.py` is the shared integration point: it initializes session-state keys and routes to each UI module. Keep feature-specific UI changes in their module; coordinate before changing shared state keys or the core data contract.

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

## Supported projects
The BOM builder supports line follower, obstacle avoider, and Bluetooth car. Recommendations consider the 147 unique projects in `core/project_data/projects.csv` and 18 competition variants in `core/project_data/competition_projects.csv`; the three existing BOM projects are excluded from recommendation results, and recommendation-only projects cannot yet generate a project-specific BOM. Catalog factor ratings, budgets, and timelines are estimates.

## Honest limitations
- The research, spec-check and cart-check features show results for review; they do not change the BOM automatically. Guide quality varies, and many components in guides will not be in our catalog (shown as not covered).
- The catalog is small (11 parts plus 3 extras). **Specs are typical datasheet values we entered by hand;** only prices and product names are read live today.
- Each project is described only by its sensor type and a Bluetooth flag; the other parts roles are shared. Sumo bot and maze solver are **planned but not built**: they need their own parts lists, catalog parts and rules.
- The recommendation helper's difficulty, time and cost scores are our estimates, not measured data.
- Resume factors are extracted by Gemini, but every retained item must have an exact quote from the source resume. Students confirm factors that are not already reported in the survey. Resume text is sent to Gemini for extraction, processed in memory, and not stored; only quote-verified factors remain in session.
- Extras (chassis, wires, switch) carry rough estimate prices until live sourcing verifies them, and chassis-to-motor fit is not rule-checked.
- Live sourcing depends on TinyFish and Gemini availability; results are cached, but some pages will show "price not verified".

## Future scope
1. Turn the research step's findings into each project's parts list (today they are shown as evidence, with a person deciding).
2. Apply verified live specs to the rule engine, with a confidence label, instead of showing them only as a diff.
3. Detect bundles and multi-packs so they are never used as a single-part price.
4. Project-specific rules and parts for sumo bot and maze solver, then drones.
5. Learn the recommender from real project outcomes.
