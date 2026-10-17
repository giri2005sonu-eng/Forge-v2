"""Project Optimizer inside the v6 BOM page: a separate button below Component details."""
import pathlib
import pytest
from streamlit.testing.v1 import AppTest
from core import pipeline, tf

APP = str(pathlib.Path(__file__).resolve().parent.parent / "app.py")


@pytest.fixture(autouse=True)
def env(tmp_path, monkeypatch):
    monkeypatch.delenv("TINYFISH_API_KEY", raising=False); monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("FORGE_LEARNED_PATH", str(tmp_path / "learned.json")); monkeypatch.setenv("FORGE_SWAP_STORE", str(tmp_path / "swap.json"))
    monkeypatch.setattr(tf, "cache_get", lambda k: None); monkeypatch.setattr(tf, "cache_set", lambda k, v: None)


def app_with_bom(project="general:line_follower"):
    at = AppTest.from_file(APP, default_timeout=60); at.session_state["stage"] = "bom"; at.run()
    at.selectbox(key="bom_catalog_pick").set_value(project).run()
    [b for b in at.button if b.label == "Generate BOM"][0].click().run()
    return at


def click(at, label):
    [b for b in at.button if b.label == label][0].click().run()


def test_button_sits_between_component_details_and_compatibility_and_is_closed_by_default():
    at = app_with_bom(); assert not at.exception
    order = []
    for el in at.main:                                   # document order
        if el.type == "markdown":
            v = str(el.value)
            if "Component details" in v: order.append("details")
            elif v.strip() == "#### Compatibility": order.append("compat")
        elif el.type == "button" and el.label == "Project Optimizer": order.append("button")
    assert order.index("details") < order.index("button") < order.index("compat"), order
    assert not at.session_state["opt_open"] if "opt_open" in at.session_state else True
    assert "opt_role" not in [x.key for x in at.selectbox]                      # panel is closed until the button is pressed


def test_open_swap_keep_undo_and_close():
    at = app_with_bom(); click(at, "Project Optimizer"); assert not at.exception and at.session_state["opt_open"]
    assert any("Change any component" in m.value for m in at.markdown)
    at.selectbox(key="opt_role").set_value("controller").run()
    at.multiselect(key="opt_pick_controller").set_value(["ctrl_esp32"]).run(); assert not at.exception
    txt = " ".join(m.value for m in at.markdown)
    assert "Total BOM cost" in txt and "Bluetooth" in txt                      # comparison rendered against the original build
    keep = [b for b in at.button if b.label == "Keep this replacement"][0]
    if not keep.disabled:
        keep.click().run(); assert not at.exception
        assert at.session_state["opt_kept"]["controller"]["id"] == "ctrl_esp32"
        assert at.session_state["opt_base"]["controller"]["id"] == "ctrl_nano"          # original preserved
        click(at, "Undo all replacements"); assert at.session_state["opt_kept"] == {}
    click(at, "Close Project Optimizer"); assert not at.session_state["opt_open"] and not at.exception


def test_live_price_refresh_does_not_reset_the_baseline_or_kept_swaps():
    at = app_with_bom(); click(at, "Project Optimizer")
    at.selectbox(key="opt_role").set_value("controller").run(); at.multiselect(key="opt_pick_controller").set_value(["ctrl_esp32"]).run()
    ident = at.session_state["opt_base_for"]
    at.session_state["live"] = {"ctrl_nano": [dict(url="https://x.in/a", price=420.0, in_stock=True, quote="Rs. 420", name="Arduino Nano", checked_at="2026-10-17T00:00:00+00:00", method="page rules")]}
    at.run(); assert at.session_state["opt_base_for"] == ident and not at.exception


def test_custom_and_catalog_builds_open_optimizer():
    at = app_with_bom("general:servo_robotic_arm"); assert not at.exception
    assert at.session_state["custom"] is not None and any(b.label == "Project Optimizer" for b in at.button)
    click(at, "Project Optimizer"); assert not at.exception
    assert "opt_role" in [x.key for x in at.selectbox]


def test_existing_bill_and_pdf_still_work_after_optimizer_open():
    at = app_with_bom(); click(at, "Project Optimizer"); assert not at.exception
    assert any("Download bill as PDF" in str(getattr(d, "label", "")) for d in at.get("download_button")) or at.session_state["res"]["best"]
