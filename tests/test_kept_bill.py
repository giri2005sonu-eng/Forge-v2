"""Kept optimizer replacements preserve quantities and remain isolated to their build."""
import pytest
from core import bill, kept, tf
from core.data import CATALOG

P = {p["id"]: p for p in CATALOG}


@pytest.fixture(autouse=True)
def env(tmp_path, monkeypatch):
    for k in ("TINYFISH_API_KEY", "GEMINI_API_KEY"): monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("FORGE_LEARNED_PATH", str(tmp_path / "learned.json")); monkeypatch.setenv("FORGE_SWAP_STORE", str(tmp_path / "swap.json"))
    monkeypatch.setattr(tf, "cache_get", lambda k: None); monkeypatch.setattr(tf, "cache_set", lambda k, v: None)


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
