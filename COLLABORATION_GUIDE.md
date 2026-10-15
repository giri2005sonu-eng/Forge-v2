# BuilderBot — 3-Developer Collaboration & Architecture Guide

This guide establishes the division of responsibilities, directory organization, and workflow standards for a team of 3 developers building, extending, and maintaining **BuilderBot**.

---

## 1. The 3-Developer Ownership Model

To prevent merge conflicts and maintain high velocity, the codebase is segregated into three distinct domain layers:

```text
┌──────────────────────────────────────────────────────────────────────────┐
│                             API & WEB LAYER                              │
│                    Developer 3: API, Routes & Frontend                   │
│   (routes/builds.py, routes/catalog.py, routes/sourcing.py, static/)     │
└──────────────────┬────────────────────────────────────┬──────────────────┘
                   │                                    │
                   ▼                                    ▼
┌──────────────────────────────────────┐  ┌────────────────────────────────┐
│         ENGINEERING PIPELINE         │  │     INTELLIGENCE & SOURCING    │
│  Developer 1: Hardware & Rules Engine│  │ Developer 2: AI, LLM & Scraping│
│                                      │  │                                │
│ • Catalog & Specs Normalization      │  │ • Natural Language Parser (LLM)│
│ • Deterministic AST Rule Engine      │  │ • TinyFish Search & Fetch      │
│ • Cost-Ordered BOM Optimization      │  │ • Live Vendor Quotation Engine │
│ • Power Budget & Battery Simulation  │  │ • Anti-Hallucination Verifier  │
│ • Pinout & Wiring Synthesis          │  │ • Autonomous Catalog Discovery │
│ (core/engineering/)                  │  │ (core/intelligence/)           │
└──────────────────┬───────────────────┘  └────────────────┬───────────────┘
                   │                                       │
                   └───────────────────┬───────────────────┘
                                       ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                        SHARED FOUNDATION & MODELS                        │
│                   Shared ownership (Requires Consensus)                   │
│         (core/common/schemas.py, core/common/config.py, data/)           │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Directory Structure & Domain Responsibilities

```text
BuilderBot/
├── app.py                         # App entrypoint (Maintained by Dev 3)
├── routes/                        # API route controllers (Maintained by Dev 3)
│   ├── __init__.py                # Router aggregation
│   ├── helpers.py                 # Serialization & client helpers
│   ├── builds.py                  # POST /api/build, /api/parse, /api/swap
│   ├── catalog.py                 # GET/POST /api/catalog, /api/part/*
│   ├── sourcing.py                # Live TinyFish & price check endpoints
│   ├── exports.py                 # GET /api/export/*
│   └── system.py                  # Health, settings, tests, metadata
│
├── core/
│   ├── common/                    # Shared infrastructure (All devs)
│   │   ├── schemas.py             # Pydantic models (Part, Spec, Requirements)
│   │   ├── config.py              # YAML/JSON path & config loaders
│   │   ├── state.py               # Runtime keys & active session state
│   │   └── testrunner.py          # Offline regression suite runner
│   │
│   ├── engineering/               # Developer 1: Hardware & Rule Engine
│   │   ├── catalog.py             # Seed catalog loading & overlay merging
│   │   ├── rules.py               # Safe AST formula evaluator & rules loader
│   │   ├── validator.py           # Compatibility checks execution (derive/eval)
│   │   ├── selector.py            # Heap-based cost-ordered BOM optimizer
│   │   ├── power.py               # Power draw, C-rate margin & runtime modeling
│   │   └── wiring.py              # Pin routing, voltage rails & Mermaid syntax
│   │
│   ├── intelligence/              # Developer 2: AI & Web Sourcing
│   │   ├── llm.py                 # Google Gemini client & loose JSON parser
│   │   ├── parser.py              # NL requirements prompt & heuristic fallback
│   │   ├── tinyfish.py            # TinyFish Search/Fetch HTTP & CLI client
│   │   ├── sourcing.py            # Vendor query variants & store deduplication
│   │   └── live.py                # Verbatim quote verification & discovery
│   │
│   ├── reporting/                 # Developer 3: Presentation & Reporting
│   │   ├── bom.py                 # Pandas DataFrame formatting (BOM, ledger)
│   │   └── export.py              # Markdown & standalone HTML report generators
│   │
│   └── *.py (shims)               # Backward-compatibility import forwarding
│
├── data/                          # Hardware definitions & rules (Dev 1 & Dev 2)
│   ├── config.yaml                # Shipping rules, assumptions, vendors
│   ├── parts_catalog.json         # Seed components
│   ├── rules.yaml                 # Formal compatibility rules
│   ├── spec_defs.yaml             # Plausible spec bounds and units
│   └── test_builds.json           # Known-good & known-bad test cases
│
├── static/                        # Frontend UI (Maintained by Dev 3)
│   ├── index.html
│   ├── styles.css
│   └── app.js
│
├── tests/                         # Test suites
│   ├── test_all.py                # Core integration & unit tests
│   ├── test_enhancements.py       # Power, wiring & export tests
│   └── test_sourcing.py           # TinyFish & sourcing tests
│
├── COLLABORATION_GUIDE.md         # This document
├── PROJECT_ROADMAP.txt            # Roadmap & feature list
├── requirements.txt               # Dependencies
└── .gitignore                     # Ignored artifacts & secrets
```

---

## 3. Developer Playbooks

### Developer 1: Hardware & Rule Engine
- **Primary Directories**: [`core/engineering/`](file:///home/siddhant/project/BuilderBot/core/engineering), [`data/rules.yaml`](file:///home/siddhant/project/BuilderBot/data/rules.yaml), [`data/spec_defs.yaml`](file:///home/siddhant/project/BuilderBot/data/spec_defs.yaml), [`data/parts_catalog.json`](file:///home/siddhant/project/BuilderBot/data/parts_catalog.json)
- **Typical Tasks**:
  1. **Add a new compatibility rule**:
     - Define rule in [`data/rules.yaml`](file:///home/siddhant/project/BuilderBot/data/rules.yaml).
     - Ensure required specs exist in [`data/spec_defs.yaml`](file:///home/siddhant/project/BuilderBot/data/spec_defs.yaml).
     - Test in [`tests/test_all.py`](file:///home/siddhant/project/BuilderBot/tests/test_all.py).
  2. **Enhance power/battery modeling**:
     - Modify [`core/engineering/power.py`](file:///home/siddhant/project/BuilderBot/core/engineering/power.py).
     - Add new derived metrics to `PowerAnalysis` dataclass.
  3. **Expand wiring diagrams**:
     - Edit [`core/engineering/wiring.py`](file:///home/siddhant/project/BuilderBot/core/engineering/wiring.py) to add support for new microcontrollers, drivers, or I2C sensor topologies.

### Developer 2: AI, Web Scraping & Sourcing
- **Primary Directories**: [`core/intelligence/`](file:///home/siddhant/project/BuilderBot/core/intelligence), [`data/config.yaml`](file:///home/siddhant/project/BuilderBot/data/config.yaml) (`allowed_vendor_domains`)
- **Typical Tasks**:
  1. **Tune requirement parsing prompts**:
     - Modify `_prompt()` or heuristics in [`core/intelligence/parser.py`](file:///home/siddhant/project/BuilderBot/core/intelligence/parser.py).
  2. **Add support for new vendor stores**:
     - Add domain to `allowed_vendor_domains` in [`data/config.yaml`](file:///home/siddhant/project/BuilderBot/data/config.yaml).
     - Add fallback search URL template in [`core/intelligence/sourcing.py`](file:///home/siddhant/project/BuilderBot/core/intelligence/sourcing.py).
  3. **Optimize quote extraction & safety**:
     - Refine `extract_from_page()` in [`core/intelligence/live.py`](file:///home/siddhant/project/BuilderBot/core/intelligence/live.py) to improve quote-matching robustness.

### Developer 3: API, Presentation & Application Layer
- **Primary Directories**: [`routes/`](file:///home/siddhant/project/BuilderBot/routes), [`core/reporting/`](file:///home/siddhant/project/BuilderBot/core/reporting), [`static/`](file:///home/siddhant/project/BuilderBot/static), [`app.py`](file:///home/siddhant/project/BuilderBot/app.py)
- **Typical Tasks**:
  1. **Add new REST API endpoints**:
     - Add router function to relevant file in [`routes/`](file:///home/siddhant/project/BuilderBot/routes) (e.g. `routes/builds.py` or `routes/catalog.py`).
  2. **Create new report formats**:
     - Implement exporter in [`core/reporting/export.py`](file:///home/siddhant/project/BuilderBot/core/reporting/export.py) and expose route in [`routes/exports.py`](file:///home/siddhant/project/BuilderBot/routes/exports.py).
  3. **Frontend UI Features**:
     - Edit [`static/app.js`](file:///home/siddhant/project/BuilderBot/static/app.js), [`static/styles.css`](file:///home/siddhant/project/BuilderBot/static/styles.css), [`static/index.html`](file:///home/siddhant/project/BuilderBot/static/index.html).

---

## 4. Git Collaboration & Conflict Prevention Rules

1. **Feature Branches**:
   - Developer 1: `git checkout -b feat/eng-<feature-name>`
   - Developer 2: `git checkout -b feat/ai-<feature-name>`
   - Developer 3: `git checkout -b feat/api-<feature-name>`
2. **Schema Changes (Strict Policy)**:
   - Changes to [`core/common/schemas.py`](file:///home/siddhant/project/BuilderBot/core/common/schemas.py) (e.g. modifying `Part`, `Spec`, or `CheckResult`) must be agreed upon by all three developers before merging, as all layers depend on them.
3. **Backward Compatibility**:
   - Always maintain the top-level forwarding shims in `core/*.py` so that imports like `from core.catalog import load_seed` continue to work without breaking external scripts or regression suites.
4. **Testing before PR**:
   - Run the offline test suite before opening a PR:
     ```bash
     source .venv/bin/activate
     python -m pytest tests -q
     ```
