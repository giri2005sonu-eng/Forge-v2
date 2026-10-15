import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import app as app_module
import core.project_report as project_report
from core.config import load_config, load_spec_defs


SPEC_DEFS = load_spec_defs()
CONFIG = load_config()


def test_project_report_without_tinyfish_keeps_prices_tbd_and_includes_engineering_sections():
    report = project_report.generate_project_report(
        "mobile-robot",
        {"mission": "avoid", "environment": "outdoor", "fabrication": "3d", "budget": "mid"},
        {"degree": "robotics", "teamSize": "small"},
        None,
        None,
        SPEC_DEFS,
        CONFIG["allowed_vendor_domains"],
    )

    assert report["sourcing"]["status"] == "unavailable"
    assert all(row["unit_price"] is None and row["line_total"] is None for row in report["bom"])
    assert report["chassis"]["cad_needed"] is True
    assert report["wiring"]["connections"]
    assert "Bill of materials" in report["markdown"]
    assert "Chassis and CAD" in report["markdown"]
    assert "TBD" in report["markdown"]


def test_project_report_includes_only_quote_verified_sourcing(monkeypatch):
    source_url = "https://robu.in/product/test-component"

    def fake_find_sources(part, tinyfish, allowed_domains, **kwargs):
        return {"links": [{"url": source_url, "vendor": "Robu", "domain": "robu.in",
                           "title": part.name, "source": "tinyfish_search"}], "tinyfish_count": 1}

    def fake_check_prices(part, urls, tinyfish, llm_json, spec_defs):
        return {"prices": {source_url: {"price": 425.0, "matches": True, "in_stock": True,
                                        "quote": "Price: ₹ 425.00", "method": "page rules", "error": None}}}

    monkeypatch.setattr(project_report, "find_sources", fake_find_sources)
    monkeypatch.setattr(project_report, "check_prices", fake_check_prices)
    report = project_report.generate_project_report(
        "iot-system", {"mission": "climate", "fabrication": "kit", "budget": "low"}, {},
        object(), None, SPEC_DEFS, CONFIG["allowed_vendor_domains"]
    )

    assert report["sourcing"]["status"] == "live"
    assert report["sourcing"]["verified_price_count"] == len(report["bom"])
    assert report["verified_total_inr"] == sum(425 * row["qty"] for row in report["bom"])
    assert all(row["sources"][0]["quote"] == "Price: ₹ 425.00" for row in report["bom"])
    assert any(source_url in line for line in report["markdown"].splitlines())


def test_project_report_route_validates_project_and_supports_catalog_only_mode(monkeypatch):
    monkeypatch.setattr(app_module, "_tf", lambda: None)
    monkeypatch.setattr(app_module, "_llm", lambda: None)
    client = TestClient(app_module.app)

    response = client.post("/api/project/report", json={"project_id": "ev-power", "project_answers": {"fabrication": "3d"}})
    invalid = client.post("/api/project/report", json={"project_id": "unknown-bot"})

    assert response.status_code == 200
    assert response.json()["project"]["id"] == "ev-power"
    assert response.json()["sourcing"]["status"] == "unavailable"
    assert response.json()["chassis"]["cad_needed"] is True
    assert invalid.status_code == 422