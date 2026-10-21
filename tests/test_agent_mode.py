"""The Web Agent cart check works on TinyFish accounts without the strict-mode / custom-step-cap / custom-time-cap betas,
and always reports honestly which limits were really applied."""
from core import browser_cart, tf

STRICT = "Your account is not enabled for strict agent mode yet. Join the beta program at /beta, then retry."
STEPS = "Your account is not enabled for custom max steps yet. Join the beta program at /beta, then retry."
DURATION = "Your account is not enabled for custom max duration yet. Join the beta program at /beta, then retry."
SHOP = "https://www.reliancedigital.in/usb-webcam-720p/p/1"          # not robu.in / robocraze.com, so it goes to the Web Agent


def _cfg(cfg):
    g = (lambda k: cfg.get(k)) if isinstance(cfg, dict) else (lambda k: getattr(cfg, k, None))
    mode = g("mode")
    return dict(mode=getattr(mode, "value", mode), max_steps=g("max_steps"), max_duration_seconds=g("max_duration_seconds"))


def _done(steps=6):
    return type("R", (), {"model_dump": lambda s: dict(status="COMPLETED", num_of_steps=steps, result=dict(added_to_cart=True, unit_price_inr=499, product_name="USB webcam 720p"))})()


def _fake(monkeypatch, tmp_path, rules):
    """rules(cfg) -> raises / returns a response. Returns the list of configs TinyFish was asked to run."""
    monkeypatch.setattr(tf, "CACHE", tmp_path); monkeypatch.setattr(tf, "_UNAVAILABLE", set())
    seen = []
    class Ag:
        def run(self, **kw):
            seen.append(_cfg(kw["agent_config"])); return rules(seen[-1])
    monkeypatch.setattr(tf, "_client", lambda: type("C", (), {"agent": Ag()})())
    return seen


def refuse(*msgs_by_option):
    """Account without some betas: refuse any config that uses a gated option."""
    gated = dict(msgs_by_option)
    def rules(cfg):
        if "strict" in gated and cfg["mode"] == "strict": raise RuntimeError(gated["strict"])
        if "steps" in gated and cfg["max_steps"] is not None: raise RuntimeError(gated["steps"])
        if "duration" in gated and cfg["max_duration_seconds"] is not None: raise RuntimeError(gated["duration"])
        return _done()
    return rules


def test_strict_refused_falls_back_to_default_and_keeps_the_caps(monkeypatch, tmp_path):
    seen = _fake(monkeypatch, tmp_path, refuse(("strict", STRICT)))
    r = tf.agent("https://x.in/p/1")
    assert [c["mode"] for c in seen] == ["strict", "default"] and r["status"] == "COMPLETED"
    assert r["mode"] == "default" and r["step_cap"] == 12 and r["time_cap"] == 180


def test_the_exact_error_from_the_screenshot_custom_max_steps(monkeypatch, tmp_path):
    seen = _fake(monkeypatch, tmp_path, refuse(("strict", STRICT), ("steps", STEPS)))
    r = tf.agent("https://x.in/p/2")
    assert [(c["mode"], c["max_steps"]) for c in seen] == [("strict", 12), ("default", 12), ("default", None)]
    assert r["status"] == "COMPLETED" and r["mode"] == "default" and r["step_cap"] is None and r["time_cap"] == 180   # time cap still applied
    tf.agent("https://x.in/p/3")
    assert [(c["mode"], c["max_steps"]) for c in seen][3:] == [("default", None)]    # remembered: goes straight to the working config


def test_an_account_with_none_of_the_betas_still_works_and_says_so(monkeypatch, tmp_path):
    seen = _fake(monkeypatch, tmp_path, refuse(("strict", STRICT), ("steps", STEPS), ("duration", DURATION)))
    r = tf.agent("https://x.in/p/4")
    assert seen[-1] == dict(mode="default", max_steps=None, max_duration_seconds=None) and len(seen) == 4
    assert r["step_cap"] is None and r["time_cap"] is None and r["mode"] == "default"


def test_refusals_returned_as_a_failed_result_are_handled_too(monkeypatch, tmp_path):
    def rules(cfg):
        if cfg["max_steps"] is not None: return type("R", (), {"model_dump": lambda s: dict(status="FAILED", result=None, error=STEPS)})()
        return _done()
    seen = _fake(monkeypatch, tmp_path, rules)
    r = tf.agent("https://x.in/p/5")
    assert r["status"] == "COMPLETED" and r["step_cap"] is None and len(seen) == 2


def test_other_errors_are_not_retried_and_nothing_is_marked_unavailable(monkeypatch, tmp_path):
    seen = _fake(monkeypatch, tmp_path, lambda cfg: (_ for _ in ()).throw(RuntimeError("TinyFish rejected the API key (HTTP 401)")))
    try: tf.agent("https://x.in/p/6"); assert False
    except RuntimeError as e: assert "401" in str(e)
    assert len(seen) == 1 and tf._UNAVAILABLE == set()                      # a bad key must not drop safety options or spend a second call
    seen2 = _fake(monkeypatch, tmp_path, lambda cfg: _done())
    r = tf.agent("https://x.in/p/7")
    assert seen2 == [dict(mode="strict", max_steps=12, max_duration_seconds=180)] and r["mode"] == "strict" and r["step_cap"] == 12


def test_a_refusal_that_keeps_coming_does_not_loop_forever(monkeypatch, tmp_path):
    seen = _fake(monkeypatch, tmp_path, lambda cfg: (_ for _ in ()).throw(RuntimeError(STRICT)))   # refuses even in default mode
    try: tf.agent("https://x.in/p/8"); assert False
    except RuntimeError as e: assert "strict" in str(e).lower()
    assert len(seen) == 2


def test_the_run_is_cached_with_what_was_applied(monkeypatch, tmp_path):
    seen = _fake(monkeypatch, tmp_path, refuse(("strict", STRICT), ("steps", STEPS)))
    tf.agent("https://x.in/p/9"); n = len(seen)
    again = tf.agent("https://x.in/p/9")
    assert len(seen) == n and again["cached"] is True and again["step_cap"] is None and again["mode"] == "default"


# ---------------------------------------------------------------- what the cart-check panel says
def test_cart_check_for_another_shop_succeeds_on_the_account_from_the_screenshot(monkeypatch, tmp_path):
    from core import cart_check
    _fake(monkeypatch, tmp_path, refuse(("strict", STRICT), ("steps", STEPS)))
    res = cart_check.run({}, SHOP)
    assert res["status"] == "COMPLETED" and res["method"] == "agent" and "error" not in res
    assert cart_check.compare(499.0, res)[0] == "match"
    line = cart_check.executor_line(res)
    assert "Web Agent" in line and "default mode" in line and "NO step cap" in line and "used 6 steps" in line
    assert "no time cap" not in line                                         # the 180 s cap did apply


def test_the_panel_does_not_claim_caps_that_were_not_applied():
    from core import cart_check
    base = dict(method="agent")
    full = cart_check.executor_line(dict(base, mode="strict", step_cap=12, time_cap=180, num_of_steps=5))
    assert "NO step cap" not in full and "default mode" not in full and "no time cap" not in full
    none = cart_check.executor_line(dict(base, mode="default", step_cap=None, time_cap=None, num_of_steps=9))
    assert "NO step cap" in none and "used 9 steps" in none and "no time cap either" in none
    assert cart_check.executor_line(dict(method="browser")) == "🌐 Executed by the TinyFish Browser"      # browser runs are unchanged


def test_robu_and_robocraze_still_use_the_browser_and_never_touch_agent_options(monkeypatch, tmp_path):
    monkeypatch.setattr(tf, "CACHE", tmp_path)
    called = []
    monkeypatch.setattr(browser_cart, "run_browser", lambda url, timeout=None: dict(status="COMPLETED", num_of_steps=4, method="browser", steps=[],
                                                                                      result=dict(added_to_cart=True, unit_price_inr=129.0, product_name="L298N")))
    out = browser_cart.check("https://robu.in/product/l298n", agent=lambda u: called.append(u))
    assert out["method"] == "browser" and not called
