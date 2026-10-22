import json
import os
import io
import zipfile
import pytest
from fastapi.testclient import TestClient

from server.main import app

client = TestClient(app)


def test_static_index():
    res = client.get("/")
    assert res.status_code == 200
    assert "FORGE" in res.text
    assert 'id="view-home"' in res.text
    assert 'data-go="discovery"' in res.text
    assert 'data-go="competition"' in res.text
    assert 'data-go="stars"' in res.text
    assert 'data-feature="recommendations"' in res.text
    assert 'data-feature="workflow"' in res.text
    assert 'id="btn-universal-back"' in res.text
    assert 'class="fg-copilot-badge"' not in res.text
    assert 'class="fg-header-subtitle"' not in res.text
    assert 'class="fg-header-tagline"' not in res.text
    assert 'id="project-optimizer-card"' in res.text
    assert 'id="research-guides-card"' in res.text
    assert 'id="btn-research-build-guides"' in res.text
    assert 'id="research-results-container"' in res.text
    assert 'id="specs-studio-card"' in res.text
    assert 'id="select-specs-component"' in res.text
    assert 'id="toggle-compare-specs"' in res.text
    assert 'id="specs-table-container"' in res.text
    assert 'id="evidence-ledger-section"' in res.text
    assert 'id="table-evidence-ledger"' in res.text
    assert 'id="btn-download-ledger-csv"' in res.text
    assert 'id="btn-evaluate-swap"' in res.text
    assert "Star projects" in res.text
    assert 'id="star-project-grid"' in res.text
    assert 'class="card star-goal-panel"' in res.text
    assert res.text.index('id="detail-radar-chart"') < res.text.index('class="card star-goal-panel"')
    assert 'id="star-project-search"' not in res.text
    assert 'id="star-project-sort"' in res.text
    assert 'value="hours_asc"' in res.text
    assert 'value="hours_desc"' in res.text
    assert 'value="cost_asc"' in res.text
    assert 'value="cost_desc"' in res.text
    assert 'id="has-completed-projects"' in res.text
    assert 'id="completed-project-search"' in res.text
    assert 'id="recommendation-hours"' not in res.text
    assert 'class="project-search-input"' in res.text
    assert 'data-wiring-tab="mermaid"' in res.text
    assert 'id="btn-copy-mermaid"' in res.text
    assert 'id="btn-prepare-wokwi"' in res.text
    assert 'href="/api/wiring/wokwi-project.zip"' in res.text
    assert "/css/forge.css" in res.text
    assert "/js/app.js" in res.text


def test_static_frontend_assets_use_the_black_and_orange_theme():
    css = client.get("/css/forge.css")
    js = client.get("/js/app.js")

    assert css.status_code == 200
    assert "--bg-space-dark: #05060A" in css.text
    assert "--primary-orange: #FF7A1A" in css.text
    assert "html {" in css.text
    assert "background-color: #05060A !important" in css.text
    assert "--toggle-orange: #FFC078" in css.text
    assert "color-scheme: dark" in css.text
    assert js.status_code == 200
    assert "DOMContentLoaded" in js.text
    assert "function goBack()" in js.text
    assert "stageHistory.pop()" in js.text


def test_get_state():
    res = client.get("/api/state")
    assert res.status_code == 200
    data = res.json()
    assert "stage" in data
    assert "budget" in data


def test_survey_questions():
    res = client.get("/api/survey/questions")
    assert res.status_code == 200
    qs = res.json()
    assert len(qs) == 9
    assert qs[0]["key"] == "career"


def test_survey_rank():
    payload = {
        "answers": {
            "career": "Robotics engineer",
            "experience": ["arduino"],
            "interests": ["autonomous_navigation"]
        },
        "limit": 5
    }
    res = client.post("/api/survey/rank", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert "results" in data
    assert len(data["results"]) <= 5
    if data["results"]:
        first = data["results"][0]
        assert "score" in first
        assert "chart_svg" in first
        assert "<svg" in first["chart_svg"]
        assert "SCAN 12 AXES" in first["chart_svg"]
        assert len(first["fit_breakdown"]) == 12
        assert all("fit_score" in factor for factor in first["fit_breakdown"])
        assert data["goal"]["label"]
        assert len(data["goal"]["step_labels"]) == len(data["goal"]["steps"])


def test_project_search_and_recommendation_feedback(tmp_path, monkeypatch):
    from server.routes import survey

    res = client.get("/api/projects/search", params={"q": "line follower"})
    assert res.status_code == 200
    assert any("line" in project["label"].lower() for project in res.json()["projects"])

    feedback_path = tmp_path / "feedback.jsonl"
    monkeypatch.setattr(survey, "FEEDBACK_PATH", feedback_path)
    feedback = client.post("/api/survey/feedback", json={
        "project_id": "line_follower",
        "signal": "built",
        "context": {"level": 2, "role": "robotics"},
    })
    assert feedback.status_code == 200
    event = json.loads(feedback_path.read_text(encoding="utf-8"))
    assert event["project_id"] == "line_follower"
    assert event["signal"] == "built"
    assert event["context"] == {"level": 2, "role": "robotics"}
    assert not {"email", "name", "user_id"} & event.keys()


def test_star_projects_include_bom_selection_support():
    response = client.get("/api/stars")
    assert response.status_code == 200
    projects = response.json()["projects"]
    assert projects
    assert all("bom_supported" in project for project in projects)
    assert any(project["bom_supported"] for project in projects)
    assert any(not project["bom_supported"] for project in projects)
    supported = next(project for project in projects if project["bom_supported"])
    bom = client.post("/api/bom/generate", json={
        "project": supported["key"],
        "budget": supported["cost_inr"] or 3500,
    })
    assert bom.status_code == 200
    assert bom.json()["label"] == supported["name"]


def test_survey_rank_v2_response(monkeypatch):
    from server.routes import survey

    monkeypatch.setattr(survey, "RECOMMENDER_VERSION", "v2")
    response = client.post("/api/survey/rank", json={
        "answers": {
            "career": "Robotics",
            "experience": ["Used a motor driver"],
            "languages": ["Python"],
            "schedule": {"hours_per_week": 6, "deadline_weeks": 8},
            "budget_inr": 15000,
            "tools": ["Soldering iron", "Multimeter"],
            "hardware": ["Arduino"],
            "goal": ["Portfolio"],
            "interests": ["Robotics", "Embedded"],
        },
        "hours_per_week": 6,
        "deadline_weeks": 8,
        "completed_project_ids": [],
    })
    assert response.status_code == 200
    data = response.json()
    assert data["recommender_version"] == "v2"
    assert not data["needs_more_info"]
    assert data["results"]
    first = data["results"][0]
    assert "debug_score" in first
    assert "score" not in first
    assert set(first["breakdown"]) == {"interest", "level", "feasibility", "impact"}
    assert "goal" in data
    assert "SCAN 12 AXES" in first["chart_svg"]
    assert len(first["fit_breakdown"]) == 12
    assert data["goal"]["label"]
    assert len(data["goal"]["step_labels"]) == len(data["goal"]["steps"])


def test_survey_rank_marks_dataset_projects_bom_supported(monkeypatch):
    from types import SimpleNamespace
    from server.routes import survey

    monkeypatch.setattr(survey, "RECOMMENDER_VERSION", "v2")
    item = SimpleNamespace(
        key="ldr_light_tracker",
        final=0.8,
        tier="baseline",
        reasons=[],
        flags=[],
        learn_skills=[],
        unlocks=[],
        interest=0.8,
        level=0.8,
        feasibility=0.8,
        impact=0.8,
        readiness=0.8,
        is_star=False,
    )
    monkeypatch.setattr(
        survey.picker,
        "rank_factor_projects_v2",
        lambda profile, limit: {
            "results": [item],
            "goal": None,
            "needs_more_info": False,
            "missing": [],
        },
    )

    response = client.post("/api/survey/rank", json={"limit": 1})

    assert response.status_code == 200
    assert response.json()["results"][0]["key"] == "ldr_light_tracker"
    assert response.json()["results"][0]["bom_supported"] is True

    bom_response = client.post(
        "/api/bom/generate",
        json={"project": "ldr_light_tracker", "budget": 3500},
    )
    assert bom_response.status_code == 200
    assert bom_response.json()["label"] == "Light-following servo"


def test_idea_match():
    res = client.post("/api/idea/match", json={"text": "plant watering robot"})
    assert res.status_code == 200
    data = res.json()
    assert "reason" in data
    assert "supported" in data


def test_competition_events_and_projects():
    res = client.get("/api/competition/events")
    assert res.status_code == 200
    events = res.json()
    assert len(events) > 0
    first_ev = events[0]["name"]

    p_res = client.get(f"/api/competition/projects?event={first_ev}")
    assert p_res.status_code == 200
    p_data = p_res.json()
    assert "projects" in p_data


def test_bom_catalog_and_generate():
    cat_res = client.get("/api/bom/catalog")
    assert cat_res.status_code == 200
    catalog = cat_res.json()
    assert catalog["total"] == 168

    gen_res = client.post("/api/bom/generate", json={
        "project": "general:line_follower",
        "budget": 3500,
        "bluetooth": False
    })
    assert gen_res.status_code == 200
    bom = gen_res.json()
    assert bom["status"] == "ok"
    assert "parts" in bom
    assert "bill" in bom
    assert bom["bill"]["grand_total"] > 0


def test_bom_choice_and_manual_unverified():
    # Generate line follower build
    client.post("/api/bom/generate", json={"project": "general:line_follower", "budget": 3500})

    # Pick a verified offer
    pick_res = client.post("/api/bom/choice", json={
        "action": "pick",
        "part_id": "ctrl_nano",
        "url": "https://robu.in/product/arduino-nano"
    })
    assert pick_res.status_code == 200
    assert pick_res.json()["choice"]["ctrl_nano"] == "https://robu.in/product/arduino-nano"

    # User-picked unverified listing with typed price
    manual_res = client.post("/api/bom/choice", json={
        "action": "manual",
        "part_id": "ctrl_nano",
        "url": "https://example.com/unverified-nano",
        "price": 280.0,
        "name": "Local Store Nano"
    })
    assert manual_res.status_code == 200
    assert manual_res.json()["manual"]["ctrl_nano"]["price"] == 280.0

    # Bill should reflect the manual price line
    bill_res = client.get("/api/bom/bill")
    assert bill_res.status_code == 200
    bill_data = bill_res.json()
    nano_line = next((l for l in bill_data["lines"] if l["part_id"] == "ctrl_nano"), None)
    assert nano_line is not None
    assert nano_line["source"] == "manual"
    assert nano_line["unit"] == 280.0

    # Reset choice
    reset_res = client.post("/api/bom/choice", json={"action": "reset"})
    assert reset_res.status_code == 200
    assert reset_res.json()["choice"] == {}


def test_bom_downloads_pdf_and_csv():
    client.post("/api/bom/generate", json={"project": "general:line_follower", "budget": 3500})

    # PDF download
    pdf_res = client.get("/api/bom/bill.pdf")
    assert pdf_res.status_code == 200
    assert pdf_res.headers["content-type"] == "application/pdf"
    assert len(pdf_res.content) > 100

    # Ledger CSV download
    csv_res = client.get("/api/bom/ledger.csv")
    assert csv_res.status_code == 200
    assert "text/csv" in csv_res.headers["content-type"]
    assert "Part ID" in csv_res.text or "part_id" in csv_res.text.lower()


def test_wiring_and_firmware():
    client.post("/api/bom/generate", json={"project": "general:line_follower", "budget": 3500})
    w_res = client.get("/api/wiring")
    assert w_res.status_code == 200
    w_data = w_res.json()
    assert "controller" in w_data
    assert "connections" in w_data
    assert "arduino_code" in w_data
    assert "void setup()" in w_data["arduino_code"]
    assert "mermaid_code" in w_data
    assert "graph LR" in w_data["mermaid_code"]

    bundle_res = client.get("/api/wiring/wokwi-project.zip")
    assert bundle_res.status_code == 200
    assert bundle_res.headers["content-type"] == "application/zip"
    with zipfile.ZipFile(io.BytesIO(bundle_res.content)) as bundle:
        assert {"diagram.json", "sketch.ino", "wiring.mmd", "README.txt"} <= set(bundle.namelist())
        assert "void setup()" in bundle.read("sketch.ino").decode()


def test_star_projects_catalog():
    response = client.get("/api/stars")
    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 20
    assert len(data["projects"]) == 20
    racecar = next(project for project in data["projects"] if project["key"] == "f1tenth_autonomous_racecar")
    assert racecar["cost_inr"] == 55000
    assert racecar["price_status"] == "unverified_estimate"
    assert racecar["tier"] == "star"
    assert "ros" in racecar["skills"]
    cubesat = next(project for project in data["projects"] if project["key"] == "cubesat_flatsat")
    assert cubesat["domain"] == "space_aerospace"
    assert cubesat["cost_inr"] is None
    assert cubesat["price_status"] == "pending_verification"
    assert "withheld pending verification" in client.get("/js/app.js").text


def test_delivery_optimization():
    client.post("/api/bom/generate", json={"project": "general:line_follower", "budget": 3500})
    d_res = client.post("/api/delivery/optimize")
    assert d_res.status_code == 200
    d_data = d_res.json()
    assert "split" in d_data
    assert "smart" in d_data


def test_project_optimizer_compare_apply_and_reset():
    bom = client.post("/api/bom/generate", json={
        "project": "general:line_follower",
        "budget": 3500,
    }).json()
    controller = next(part for part in bom["parts"].values() if part.get("role") == "controller")

    candidates_res = client.get("/api/optimizer/candidates?role=controller")
    assert candidates_res.status_code == 200
    replacement = None
    evaluation = None
    rejected_incompatible = False
    for candidate in candidates_res.json():
        if candidate["id"] == controller["id"]:
            continue
        evaluation_res = client.post("/api/optimizer/evaluate", json={
            "role": "controller",
            "swap_part_id": candidate["id"],
        })
        if evaluation_res.status_code == 200 and not evaluation_res.json()["summary"]["ready"] and not rejected_incompatible:
            rejected = client.post("/api/optimizer/apply", json={
                "role": "controller",
                "swap_part_id": candidate["id"],
            })
            assert rejected.status_code == 409
            rejected_incompatible = True
        if evaluation_res.status_code == 200 and evaluation_res.json()["summary"]["ready"]:
            replacement = candidate
            evaluation = evaluation_res.json()
            break
    assert rejected_incompatible
    assert replacement is not None and evaluation is not None
    assert evaluation["summary"]["ready"] in (True, False)
    assert any(row["key"] == "cost" for row in evaluation["evaluation"]["rows"])
    assert any(row["key"] == "compat" for row in evaluation["evaluation"]["rows"])

    apply_res = client.post("/api/optimizer/apply", json={
        "role": "controller",
        "swap_part_id": replacement["id"],
    })
    assert apply_res.status_code == 200
    changed_bom = client.get("/api/bom").json()
    assert next(part for part in changed_bom["parts"].values() if part.get("role") == "controller")["id"] == replacement["id"]

    reset_res = client.post("/api/optimizer/reset")
    assert reset_res.status_code == 200
    restored_bom = client.get("/api/bom").json()
    assert next(part for part in restored_bom["parts"].values() if part.get("role") == "controller")["id"] == controller["id"]


def test_project_optimizer_requires_a_bom_and_rejects_wrong_role():
    with TestClient(app) as isolated_client:
        no_bom = isolated_client.post("/api/optimizer/evaluate", json={
            "role": "controller",
            "swap_part_id": "ctrl_esp32",
        })
        assert no_bom.status_code == 400

        isolated_client.post("/api/bom/generate", json={"project": "general:line_follower"})
        wrong_role = isolated_client.get("/api/optimizer/candidates?role=not-a-component")
        assert wrong_role.status_code == 404


def test_project_optimizer_auto_resolve_flow():
    with TestClient(app) as test_client:
        # Generate build with Bluetooth requirement
        bom_res = test_client.post("/api/bom/generate", json={"project": "general:line_follower", "bluetooth": True})
        assert bom_res.status_code == 200

        # Evaluate swap controller to Arduino Nano
        eval_res1 = test_client.post("/api/optimizer/evaluate", json={
            "role": "controller",
            "swap_part_id": "ctrl_nano",
        })
        assert eval_res1.status_code == 200
        data1 = eval_res1.json()
        assert data1["summary"]["ready"] is False
        assert data1["summary"]["fail"] > 0

        # Check failing rule and auto-resolve actions
        failed_rules = [r for r in data1["evaluation"]["compat_proposed"] if r["status"] == "FAIL"]
        bt_fail = next((r for r in failed_rules if r["rule_id"] == "bluetooth"), None)
        assert bt_fail is not None
        assert "auto_fixes" in bt_fail
        fix_ids = [f["id"] for f in bt_fail["auto_fixes"]]
        assert "add_hc05_bluetooth" in fix_ids

        # Evaluate swap with staged 1-click auto-resolve action
        eval_res2 = test_client.post("/api/optimizer/evaluate", json={
            "role": "controller",
            "swap_part_id": "ctrl_nano",
            "staged_fixes": ["add_hc05_bluetooth"]
        })
        assert eval_res2.status_code == 200
        data2 = eval_res2.json()
        assert data2["summary"]["ready"] is True
        assert data2["summary"]["fail"] == 0
        assert len(data2["evaluation"]["resolved_failures"]) > 0

        # Apply swap with staged auto-resolve fix
        apply_res = test_client.post("/api/optimizer/apply", json={
            "role": "controller",
            "swap_part_id": "ctrl_nano",
            "staged_fixes": ["add_hc05_bluetooth"]
        })
        assert apply_res.status_code == 200

        # Verify active BOM now has Arduino Nano and HC-05
        bom_updated = test_client.get("/api/bom").json()
        part_names = [p["name"] for p in bom_updated["parts"].values()]
        assert "Arduino Nano" in part_names
        assert "HC-05 Bluetooth Serial Module" in part_names


def test_specs_and_comparison_endpoints():
    test_client = TestClient(app)
    # 1. Generate BOM for Line Follower
    gen_res = test_client.post("/api/bom/generate", json={"project": "general:line_follower", "budget": 3500})
    assert gen_res.status_code == 200

    # 2. Get specs for build
    specs_res = test_client.get("/api/research/specs")
    assert specs_res.status_code == 200
    data = specs_res.json()
    assert "parts" in data
    assert "spec_parts" in data
    assert len(data["parts"]) > 0

    # Check controller part (Arduino Nano)
    ctrl_part = next((p for p in data["parts"] if "nano" in p["name"].lower() or p["role"] == "controller"), None)
    assert ctrl_part is not None
    assert ctrl_part["plural_role"] == "microcontrollers"
    assert "logic_v" in ctrl_part["specs"]
    assert len(ctrl_part["alternatives"]) > 0

    # 3. Compare specs with alternatives
    alt_names = [a["name"] for a in ctrl_part["alternatives"][:3]]
    cmp_res = test_client.post("/api/research/specs/compare", json={
        "part_name": ctrl_part["name"],
        "compare_with": alt_names
    })
    assert cmp_res.status_code == 200
    cmp_data = cmp_res.json()
    assert "table" in cmp_data
    assert "html" in cmp_data
    assert ctrl_part["name"] in cmp_data["table"]["columns"]
    for alt in alt_names:
        assert alt in cmp_data["table"]["columns"]

    assert "<table class=\"cmp\">" in cmp_data["html"]
    assert "class=\"best\"" in cmp_data["html"]

    # 4. Verify Evidence Ledger API
    ledger_res = test_client.get("/api/bom/ledger")
    assert ledger_res.status_code == 200
    ledger_data = ledger_res.json()
    assert "rows" in ledger_data
    assert "summary" in ledger_data
    assert len(ledger_data["rows"]) > 0
    assert any(r["field"] == "vin_min_v" for r in ledger_data["rows"])

    csv_res = test_client.get("/api/bom/ledger.csv")
    assert csv_res.status_code == 200
    assert "part_id,part,role" in csv_res.text

    # 5. Verify Research Guides API
    research_get = test_client.get("/api/research/guides")
    assert research_get.status_code == 200
    res_data = research_get.json()
    assert "label" in res_data
    assert "enabled" in res_data




