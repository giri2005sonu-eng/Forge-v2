# BuilderBot — Robot BOM & Compatibility Agent

A classic, engineering-first web interface for planning robot builds, optimizing a budget-aware bill of materials, validating component compatibility, reviewing power and wiring, sourcing live parts, and exporting traceable engineering reports.

**The frontend is plain HTML/CSS/JavaScript. The backend is FastAPI. Streamlit is not used.** The deterministic rule engine, catalog, Gemini/TinyFish integrations, power model, wiring guide, and report exporters are all modularized in `core/`.

## Features

- Clean responsive desktop/mobile UI with overview dashboard and workflow navigation.
- Natural-language requirement parsing (Gemini when configured, local heuristic parser otherwise).
- Structured constraints for supported robot types, budget, motor count, runtime, Bluetooth, and sensor channels.
- Cost-ordered BOM selection with vendor shipping estimates and budget delta.
- Compatibility results separated into **PASS**, **FAIL**, and **UNKNOWN**; unknown specifications are never silently assumed.
- Component catalog search, detail/evidence inspector, source URLs, and stock/source indicators.
- TinyFish + Gemini live refresh, component discovery, and direct product URL import with quote verification.
- Interactive component swap simulator and offline regression test runner.
- Power budget, battery discharge margin, estimated runtimes, driver thermal warnings, pinout/interconnect guide, assembly steps, and Mermaid diagram source.
- BOM CSV, evidence ledger CSV, Markdown engineering report, and standalone HTML report exports.
- API keys can be loaded from `.env` or entered into Settings for the current server process only.

## Run on Ubuntu / Linux

```bash
cd BuilderBot
sudo apt update
sudo apt install python3 python3-venv python3-pip -y
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
cp .env.example .env
# Optional: edit .env and add your own Gemini/TinyFish API keys
uvicorn app:app --reload
```

Open **http://127.0.0.1:8000** in your browser. API documentation is at **http://127.0.0.1:8000/docs**.

## Run on Windows PowerShell

```powershell
cd BuilderBot
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
# Optional: edit .env and add your own API keys
uvicorn app:app --reload
```

Open http://127.0.0.1:8000.

## API key setup

The `.env` file is loaded when the server starts. Example:

```env
GEMINI_API_KEY=your_actual_gemini_key
TINYFISH_API_KEY=your_actual_tinyfish_key
GEMINI_MODEL=gemini-2.5-flash
```

Restart the server after changing `.env`. Alternatively, open **Settings & API keys** in the UI and enter keys; those settings remain in the running Python process only. The settings endpoint does not return secret values.

- Gemini key: https://aistudio.google.com/apikey
- TinyFish key: https://agent.tinyfish.ai/api-keys

The app works without API keys using the seed catalog and heuristic parser. Live sourcing requires both Gemini and TinyFish keys.

## Run tests

```bash
python -m pytest tests -q
```

Tests run offline against the seed catalog; they do not require live API keys.

## Project structure

```text
BuilderBot/
├── app.py                 # FastAPI application and JSON API
├── static/
│   ├── index.html         # UI structure
│   ├── styles.css         # Responsive design system
│   └── app.js             # Frontend interactions
├── core/                  # Parser, catalog, rules, BOM, live data, power, wiring, sourcing, exports
├── data/                  # Catalog, rules, specifications, config, live overlay
├── tests/                 # Offline regression tests
├── .env.example           # Safe placeholder template
├── .gitignore             # Git ignore file
└── requirements.txt
```

## Production deployment notes

This is a production-oriented application scaffold, not a claim that it is already hardened for public internet deployment. Before exposing it publicly, add authentication and authorization, HTTPS/TLS termination, per-user/session isolation for build state and settings, rate limits, request-size limits, structured access logs, and a persistent database for users/projects. Run behind a production ASGI server/process manager and configure allowed origins/hosts for your environment. Keep `.env` out of source control. Do not expose the API-key settings route to untrusted users.

## Engineering caveat

Seed prices and specs are approximate. Power/runtime and shipping values are estimates based on configuration assumptions. Verify vendor listings, component datasheets, battery discharge capability, and wiring before purchasing or powering hardware.

## Where to buy (TinyFish seller links)

Click **Inspect** on any part in *Parts & sourcing* to open the component popup. At the top is a
**Where to buy** panel:

1. **Search (TinyFish Search)** - runs up to 4 query variants for the part, drops non-shops
   (YouTube, Wikipedia, forums...), keeps one link per store first, ranks known Indian vendors
   (`allowed_vendor_domains` in `data/config.yaml`) first, and returns at least 5 selling links.
   If TinyFish finds fewer than 5 stores, the list is padded with vendor search pages that are
   labelled `SEARCH PAGE` so they are never mistaken for TinyFish results.
2. **Check live prices (TinyFish Fetch + Gemini)** - fetches each page live and extracts price and
   stock. A price is shown only when its quote appears verbatim on the page (same rule as the rest of
   the app); otherwise the row shows `NO PRICE` with the reason.

Results are cached in `data/sourcing_cache.json` (cleared by *Reset live overlay*); use
**Search again** to bypass the cache.

API: `GET /api/part/{id}/sources?refresh=false&min_links=5` and `POST /api/part/{id}/sources/prices {"urls": [...]}`.
Tests: `tests/test_sourcing.py` (uses a fake TinyFish client, no network needed).
