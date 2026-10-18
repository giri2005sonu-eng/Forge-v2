"""Kept optimizer replacements must show in the live 'Your bill' (not only in the PDF), keep their quantity, and never leak into another build."""
import copy, pathlib
import pytest
from streamlit.testing.v1 import AppTest
from core import bill, kept, tf
from core.data import CATALOG

APP = str(pathlib.Path(__file__).resolve().parent.parent / "app.py")
P = {p["id"]: p for p in CATALOG}


@pytest.fixture(autouse=True)
def env(tmp_path, monkeypatch):
    for k in ("TINYFISH_API_KEY", "GEMINI_API_KEY"): monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("FORGE_LEARNED_PATH", str(tmp_path / "learned.json")); monkeypatch.setenv("FORGE_SWAP_STORE", str(tmp_path / "swap.json"))
    monkeypatch.setattr(tf, "cache_get", lambda k: None); monkeypatch.setattr(tf, "cache_set", lambda k, v: None)


def open_build(project):
    at = AppTest.from_file(APP, default_timeout=90); at.session_state["stage"] = "bom"; at.run()
    at.selectbox(key="bom_catalog_pick").set_value(project).run()
    [b for b in at.button if b.label == "Generate BOM"][0].click().run()
    return at


def page_bill(at):
    return " ".join(m.value for m in at.markdown if "bill of materials" in m.value.lower())


def click(at, label):
    [b for b in at.button if b.label == label][0].click().run()


# ---------------- the helper ----------------
def parts(*specs):
    return [dict(id=i, role=r, name=n, qty=q, query=n, seed_price=None) for i, r, n, q in specs]


def test_keys_match_the_optimizer_panel_for_repeated_roles():
    k = kept.keyed_parts(parts(("d_a", "wiring", "A", 1), ("d_b", "wiring", "B", 1), ("d_c", "sensor", "C", 1)))
    assert list(k) == ["wiring", "wiring_d_b", "sensor"]


def test_replacement_inherits_quantity_and_original_is_untouched():
    base = kept.keyed_parts(parts(("d_s", "sensor", "Old sensor", 3)))
    new = dict(id="sen_new", role="sensor", name="New sensor", seed_price=50)
    out = kept.apply(base, {"sensor": new})
    assert out["sensor"]["name"] == "New sensor" and out["sensor"]["qty"] == 3 and base["sensor"]["name"] == "Old sensor"
    assert "qty" not in new                                           # input not mutated
    explicit = kept.apply(base, {"sensor": dict(new, qty=2)}); assert explicit["sensor"]["qty"] == 2


def test_swap_only_applies_to_the_build_it_was_made_for():
    base = kept.keyed_parts(parts(("d_s", "sensor", "Old", 1)))
    state = {"opt_kept": {"sensor": dict(id="x", role="sensor", name="New", qty=1)}, "opt_base_for": kept.identity("proj_a", base)}
    class S(dict): __getattr__ = dict.__getitem__
    s = S(state)
    assert kept.active_build(s, "proj_a", base)["sensor"]["name"] == "New" and kept.count(s, "proj_a", base) == 1
    other = kept.keyed_parts(parts(("d_z", "sensor", "Other", 1)))
    assert kept.active_build(s, "proj_a", other)["sensor"]["name"] == "Other" and kept.count(s, "proj_a", other) == 0   # different parts: ignored
    assert kept.active_build(s, "proj_b", base)["sensor"]["name"] == "Old"                                             # different project: ignored


def test_same_part_id_twice_adds_quantities_instead_of_dropping_one():
    active = {"a": dict(id="p", role="r", name="P", qty=2), "b": dict(id="p", role="r", name="P", qty=1)}
    assert kept.by_id(active)["p"]["qty"] == 3


def test_page_and_pdf_use_the_same_parts():
    base = kept.keyed_parts(parts(("d_m", "controller", "MCU", 1), ("d_s", "sensor", "Old", 2)))
    active = kept.apply(base, {"sensor": dict(P["sen_hcsr04"])})
    pdf_lines = bill.build_lines(active, {}, {}); page_lines = bill.build_lines(kept.by_id(active), {}, {})
    key = lambda ls: sorted((l["part_id"], l["name"], l["qty"]) for l in ls)
    assert key(pdf_lines) == key(page_lines) and ("sen_hcsr04", "HC-SR04 ultrasonic", 2) in key(page_lines)


# ---------------- the screen (the reported bug) ----------------
def test_catalog_build_bill_shows_the_kept_replacement():
    at = open_build("general:imu_kalman_fusion"); assert not at.exception
    assert "MPU6050 IMU" in page_bill(at) and "HC-SR04" not in page_bill(at)
    click(at, "Project Optimizer")
    at.session_state["opt_kept"] = {"sensor": copy.deepcopy(P["sen_hcsr04"])}         # exactly what 'Keep this replacement' stores
    at.run(); assert not at.exception
    html = page_bill(at)
    assert "HC-SR04" in html and "MPU6050 IMU" not in html                              # the live bill changed
    assert "(optimized)" in " ".join(s.value for s in at.subheader)
    assert any("includes 1 replacement" in s.value for s in at.success)
    # component cards and the returned build use the new part too
    assert any("HC-SR04" in str(e.label) for e in at.expander) or "HC-SR04" in " ".join(m.value for m in at.markdown)


def test_undo_returns_the_original_bill():
    at = open_build("general:imu_kalman_fusion"); click(at, "Project Optimizer")
    at.session_state["opt_kept"] = {"sensor": copy.deepcopy(P["sen_hcsr04"])}; at.run()
    click(at, "Undo all replacements"); assert not at.exception
    assert "MPU6050 IMU" in page_bill(at) and "HC-SR04" not in page_bill(at)


def test_kept_swap_does_not_leak_into_another_project_when_the_panel_is_closed():
    at = open_build("general:imu_kalman_fusion"); click(at, "Project Optimizer")
    at.session_state["opt_kept"] = {"sensor": copy.deepcopy(P["sen_hcsr04"])}; at.run()
    assert "HC-SR04" in page_bill(at)
    click(at, "Close Project Optimizer")
    at.selectbox(key="bom_catalog_pick").set_value("general:esp_now_mesh").run()
    [b for b in at.button if b.label == "Generate BOM"][0].click().run(); assert not at.exception
    assert "HC-SR04" not in page_bill(at) and "(optimized)" not in " ".join(s.value for s in at.subheader)


def test_rule_checked_build_still_applies_kept_swaps_and_guards_other_builds():
    at = open_build("general:line_follower"); click(at, "Project Optimizer")
    at.session_state["opt_kept"] = {"controller": copy.deepcopy(P["ctrl_esp32"])}; at.run(); assert not at.exception
    assert "ESP32" in page_bill(at) and "(optimized)" in " ".join(s.value for s in at.subheader)
    click(at, "Close Project Optimizer")
    at.selectbox(key="bom_catalog_pick").set_value("general:obstacle_avoider").run()
    [b for b in at.button if b.label == "Generate BOM"][0].click().run(); assert not at.exception
    assert "ESP32" not in page_bill(at)
