"""Test that selecting or clicking any project in 'Build to compete' redirects directly to Stage 4 (BOM)."""
import os
import pathlib
import pytest
from streamlit.testing.v1 import AppTest

APP = str(pathlib.Path(__file__).resolve().parent.parent / "app.py")


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    monkeypatch.delenv("TINYFISH_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)


def test_competition_quick_build_button_redirects_to_bom():
    at = AppTest.from_file(APP, default_timeout=30)
    at.session_state["stage"] = "competition"
    at.run()
    assert not at.exception

    # Candidate projects must display direct build buttons
    build_buttons = [b for b in at.button if "Open & Plan BOM" in b.label]
    assert len(build_buttons) >= 1

    # Click the first candidate build button
    build_buttons[0].click().run()
    assert not at.exception
    assert at.session_state["stage"] == "bom"
    assert at.session_state.get("bom_catalog_pick", "").startswith("competition:")
    assert at.session_state.get("custom") is not None
    assert len(at.session_state["custom"]["parts"]) >= 1


def test_competition_shortlisted_project_redirects_to_bom():
    at = AppTest.from_file(APP, default_timeout=30)
    at.session_state["stage"] = "competition"
    at.run()

    # Pick Robo Soccer and select Heavyweight Tactical Soccer Bot
    at.selectbox(key="competition_event").set_value("Robo Soccer").run()
    at.multiselect(key="competition_projects_0").set_value(["heavyweight_tactical_soccer_bot"]).run()
    assert not at.exception

    # Verify action buttons exist on the selected project card and top banner
    plan_buttons = [b for b in at.button if "Plan & Build BOM" in b.label]
    assert len(plan_buttons) >= 1

    # Click Plan & Build BOM
    plan_buttons[0].click().run()
    assert not at.exception
    assert at.session_state["stage"] == "bom"
    assert at.session_state["bom_catalog_pick"] == "competition:heavyweight_tactical_soccer_bot"
    assert at.session_state["custom"]["label"] == "Heavyweight Tactical Soccer Bot"
    assert len(at.session_state["custom"]["parts"]) == 13
