import pathlib
from streamlit.testing.v1 import AppTest
from core import browser_cart, pipeline, tf
from ui import cart_check

APP = str(pathlib.Path(__file__).resolve().parent.parent / "app.py")
RES = lambda **r: dict(status="COMPLETED", result=r, num_of_steps=7)


def test_compare_statuses():
    c = cart_check.compare
    assert c(229.0, RES(added_to_cart=True, unit_price_inr=229))[0] == "match"
    assert c(229.0, RES(added_to_cart=True, unit_price_inr=230))[0] == "match"           # within ₹2
    assert c(229.0, RES(added_to_cart=True, unit_price_inr=299))[0] == "differs"
    assert c(229.0, RES(added_to_cart=False))[0] == "not added"
    assert c(229.0, RES(added_to_cart=True))[0] == "not read" and c(229.0, RES(unit_price_inr=0))[0] == "not read"
    assert c(229.0, RES(unit_price_inr=True))[0] == "not read" and c(229.0, {})[0] == "not read"      # a boolean or nothing is never a price


def test_options_only_lists_verified_chosen_listings():
    best = pipeline.select("line_follower", 5000, False, {})["best"]
    nano = best["parts"]["controller"]
    live = {nano["id"]: [dict(url="https://robu.in/p/1", price=229.0, quote="Price: ₹ 229", name=nano["name"])]}
    opts = cart_check.options(best["parts"], live, {})
    assert len(opts) == 1 and list(opts.values())[0] == ("https://robu.in/p/1", 229.0)
    assert cart_check.options(best["parts"], {}, {}) == {}


def test_run_stores_result_or_error_and_never_raises(monkeypatch):
    st = {}
    monkeypatch.setattr(tf, "agent", lambda url, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    assert cart_check.run(st, "u")["status"] == "ERROR" and "boom" in st["agent"]["u"]["error"]
    seen = {}
    monkeypatch.setattr(tf, "agent", lambda url, **k: (seen.update(k), RES(added_to_cart=True, unit_price_inr=229))[1])
    assert cart_check.run(st, "u2")["num_of_steps"] == 7 and seen["max_steps"] == cart_check.MAX_STEPS == 12


def _app_with_live(monkeypatch, host="robu.in"):
    monkeypatch.setenv("TINYFISH_API_KEY", "x")
    at = AppTest.from_file(APP, default_timeout=60).run()
    at.button[[b.label for b in at.button].index(next(l for l in [b.label for b in at.button] if "kip" in l))].click().run()
    live = {p["id"]: [dict(url=f"https://{host}/{p['id']}", price=float(p["seed_price"] or 100), quote=f"Price: ₹ {p['seed_price'] or 100}", name=p["name"], in_stock=None, method="page rules")]
            for p in pipeline.candidate_parts("line_follower")}
    at.session_state["live"] = live
    return at


def _run_panel(at):
    [b for b in at.button if b.label.startswith("Generate")][0].click().run()
    assert not at.exception, at.exception
    assert any("Cart check" in m.value for m in at.markdown)
    run_btn = [b for b in at.button if b.label == "Run cart check"]
    assert run_btn and not run_btn[0].disabled
    run_btn[0].click().run()
    assert not at.exception, at.exception
    return " ".join(str(e.value) for e in at.main if hasattr(e, "value"))


def test_cart_check_panel_uses_the_browser_for_robu_and_says_so(monkeypatch):
    at = _app_with_live(monkeypatch)
    monkeypatch.setattr(browser_cart, "run_browser", lambda url: dict(status="COMPLETED", method="browser", num_of_steps=7,
                        steps=[dict(actor="browser", text="Opened the product page on robu.in")],
                        result=dict(added_to_cart=True, unit_price_inr=450.0, cart_total_inr=499.0, in_stock=True)))
    monkeypatch.setattr(tf, "agent", lambda url, **k: (_ for _ in ()).throw(AssertionError("the agent must not run on robu.in")))
    text = _run_panel(at)
    assert "matches the bill" in text or "differs from the bill" in text            # a verdict was shown
    assert "Executed by the TinyFish Browser" in text and "Opened the product page on robu.in" in text
    assert any("steps used 7" in str(c.value) for c in at.caption)


def test_cart_check_panel_uses_the_agent_for_other_shops_and_says_so(monkeypatch):
    at = _app_with_live(monkeypatch, host="example-shop.in")
    monkeypatch.setattr(browser_cart, "run_browser", lambda url: (_ for _ in ()).throw(AssertionError("no browser for other shops")))
    monkeypatch.setattr(tf, "agent", lambda url, **k: RES(added_to_cart=True, unit_price_inr=450.0, cart_total_inr=499.0, delivery_estimate="3-5 days"))
    text = _run_panel(at)
    assert "matches the bill" in text or "differs from the bill" in text
    assert "Executed by the TinyFish Web Agent" in text
    assert any("steps used 7" in str(c.value) for c in at.caption)


def test_cart_check_is_disabled_without_a_tinyfish_key(monkeypatch):
    monkeypatch.delenv("TINYFISH_API_KEY", raising=False)
    at = AppTest.from_file(APP, default_timeout=60).run()
    [b for b in at.button if "kip" in b.label][0].click().run()
    [b for b in at.button if b.label.startswith("Generate")][0].click().run()
    assert not at.exception, at.exception
    assert any("Cart check" in m.value for m in at.markdown)
