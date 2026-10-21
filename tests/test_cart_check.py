from core import cart_check, pipeline, tf
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
