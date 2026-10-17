"""Regression tests for the review fixes: price misreads, strict quote check, suspicious-low prices, full candidate pricing, cache expiry."""
import json, os, pathlib, subprocess, sys, time
from core import bill, pagerules, pipeline, tf
from core.data import CATALOG

NANO = next(p for p in CATALOG if p["id"] == "ctrl_nano")
ROOT = pathlib.Path(__file__).resolve().parent.parent


# ---- 1. price reader ----
def test_shipping_charge_is_not_a_price():
    assert pagerules.rule_price("Arduino Nano V3\nShipping charge ₹49. Delivery in 3 days.", anchor="Arduino Nano") is None
    assert pagerules.rule_price("Delivery fee: ₹60\nArduino Nano V3 Price: ₹229.00", anchor="Arduino Nano")[0] == 229.0

def test_price_range_is_not_a_price():
    assert pagerules.rule_price("Arduino Nano V3 board ₹120 - ₹450 depending on variant", anchor="Arduino Nano") is None
    assert pagerules.rule_price("₹120 to ₹450 range. Arduino Nano V3 Price: ₹229.00", anchor="Arduino Nano")[0] == 229.0

def test_discount_dash_is_not_mistaken_for_a_range():
    assert pagerules.rule_price("Arduino Nano V3 Price: ₹229 - 5% off today", anchor="Arduino Nano")[0] == 229.0

def test_price_before_the_product_name_is_ignored_when_a_later_one_exists():
    page = "Related: jumper wire ₹30\nArduino Nano V3 ₹229.00"
    assert pagerules.rule_price(page, anchor="Arduino Nano")[0] == 229.0
    assert pagerules.rule_price(page)[0] == 30.0                       # without an anchor behaviour is unchanged

def test_anchor_falls_back_when_no_price_follows_the_name():
    assert pagerules.rule_price("₹300 jumper pack\nArduino Nano V3", anchor="Arduino Nano")[0] == 300.0

def test_extract_offer_end_to_end_on_tricky_pages(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    ex = lambda t: pipeline.extract_offer(t, "Arduino Nano", part=NANO)
    assert ex("Arduino Nano V3\nShipping charge ₹49. Delivery in 3 days.") is None
    assert ex("Arduino Nano V3 board ₹120 - ₹450 depending on variant") is None
    assert ex("Related: jumper wire ₹30\nArduino Nano V3 ₹229.00")["price"] == 229.0
    assert ex("Arduino Nano V3 ATmega328P\nPrice: Rs. 229.00 incl. tax")["price"] == 229.0

def test_quote_with_a_range_just_before_the_real_price_still_counts():
    q = "₹410 – ₹490+ Pay Price: ₹ 410 Sold out:"
    assert not pagerules.bad_price_quote(q, 410.0)
    assert pagerules.bad_price_quote("Shipping charge ₹49.", 49.0) and pagerules.bad_price_quote("₹120 - ₹450", 120.0)


# ---- 2. strict Gemini quote check ----
class _R:
    def __init__(self, d): self.text = json.dumps(d)
class _G:
    def __init__(self, d): self.models = type("M", (), {"generate_content": lambda s, **k: _R(d)})()

def _gem(monkeypatch, price):
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    pipeline._G = _G(dict(product_name="x", price_inr=price, quote="Rs 1,599.00"))
    return pipeline._gemini_offer("Delivery charge applies. Total Rs 1,599.00 for the kit.", "Kit")

def test_gemini_price_must_equal_a_number_in_its_quote(monkeypatch):
    assert _gem(monkeypatch, 5) is None            # '5' is only a digit inside 1,599
    assert _gem(monkeypatch, 1599.5) is None       # decimals are no longer dropped
    assert _gem(monkeypatch, 1599)["price"] == 1599.0

def test_quote_has_amount():
    assert pagerules.quote_has_amount("Rs 1,599.00", 1599) and pagerules.quote_has_amount("₹229", 229.0)
    assert not pagerules.quote_has_amount("Rs 1,599.00", 599) and not pagerules.quote_has_amount("", 5) and not pagerules.quote_has_amount("₹229", None)


# ---- 3. suspicious-low prices ----
def _offer(url, price, name): return dict(url=url, price=price, quote=f"Price: ₹ {price:.0f}", name=name)

def test_cheap_accessory_is_flagged_but_a_cheap_clone_is_not():
    acc = [_offer("a", 30, "Jumper wire pack"), _offer("b", 229, "Arduino Nano V3"), _offer("c", 250, "Arduino Nano clone"), _offer("d", 260, "Nano board")]
    assert pagerules.suspect_low(NANO, acc) == {"a"}
    clone = [_offer("a", 229, "Arduino Nano V3.0 CH340"), _offer("b", 1699, "Nano starter kit"), _offer("c", 2755, "Arduino Nano Original")]
    assert pagerules.suspect_low(NANO, clone) == set()          # the ₹229 clone is named like the part, so it stays eligible
    assert pagerules.suspect_low(NANO, [_offer("a", 229, "Arduino Nano V3"), _offer("b", 250, "Nano board")]) == set()   # plausible prices, too few to compare
    assert pagerules.suspect_low(NANO, [_offer("a", 30, "Arduino Nano jumper pack")]) == {"a"}      # far below the team's estimate, even alone and even if the name matches

def test_suspect_offer_is_never_the_default_or_the_bom_price():
    live = {"ctrl_nano": [dict(_offer("a", 30, "Jumper wire pack"), suspect=True), _offer("b", 229, "Arduino Nano V3")]}
    assert pipeline.price_of(NANO, live) == (229.0, "live")
    assert [o["url"] for o in bill.offers_for("ctrl_nano", live)] == ["b", "a"]
    assert bill.chosen_url("ctrl_nano", live, {}) == "b"
    assert bill.chosen_url("ctrl_nano", live, {"ctrl_nano": "a"}) == "a"      # the user can still choose it

def test_source_part_flags_the_accessory(monkeypatch, tmp_path):
    monkeypatch.setattr(tf, "CACHE", tmp_path); monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    pages = {"https://a.in/1": "Arduino Nano jumper wire pack\nPrice: Rs. 30.00", "https://b.in/2": "Arduino Nano V3 ATmega328P\nPrice: Rs. 229.00",
             "https://c.in/3": "Arduino Nano clone board\nPrice: Rs. 250.00", "https://d.in/4": "Nano V3 board\nPrice: Rs. 260.00"}
    monkeypatch.setattr(tf, "search", lambda q: [dict(title="", snippet="", url=u) for u in pages])
    monkeypatch.setattr(tf, "fetch", lambda urls: {u: pages[u] for u in urls})
    offers = pipeline.source_part(NANO, log=lambda m: None, gemini_max=0)
    assert [o["url"] for o in offers if o.get("suspect")] == ["https://a.in/1"]
    assert pipeline.price_of(NANO, {"ctrl_nano": offers})[0] == 229.0


# ---- 4. every candidate gets priced ----
def test_candidate_parts_cover_every_option_and_the_extras():
    ids = [p["id"] for p in pipeline.candidate_parts("line_follower")]
    assert len(ids) == len(set(ids)) == 13 and {"sen_line5", "x_chassis", "x_wires", "x_switch"} <= set(ids) and "sen_hcsr04" not in ids
    assert not any(p["role"] == "sensor" for p in pipeline.candidate_parts("bluetooth_car"))


# ---- 5. cache expiry and location ----
def test_cache_expires_after_ttl(monkeypatch, tmp_path):
    monkeypatch.setattr(tf, "CACHE", tmp_path); monkeypatch.delenv("FORGE_CACHE_HOURS", raising=False)
    tf.cache_set("k", {"v": 1}); assert tf.cache_get("k") == {"v": 1}
    old = time.time() - 4 * 24 * 3600; os.utime(tf._file("k"), (old, old))
    assert tf.cache_get("k") is None                                   # older than the 72 h default
    monkeypatch.setenv("FORGE_CACHE_HOURS", "0"); assert tf.cache_get("k") == {"v": 1}    # 0 = never expires
    monkeypatch.setenv("FORGE_CACHE_HOURS", "200"); assert tf.cache_get("k") == {"v": 1}

def test_expired_search_is_fetched_again(monkeypatch, tmp_path):
    monkeypatch.setattr(tf, "CACHE", tmp_path); monkeypatch.delenv("FORGE_CACHE_HOURS", raising=False); n = []
    monkeypatch.setattr(tf, "_client", lambda: type("C", (), {"search": type("S", (), {"query": lambda s, q, **k: (n.append(1), dict(results=[]))[1]})()})())
    tf.search("nano"); tf.search("nano"); assert len(n) == 1
    old = time.time() - 5 * 24 * 3600; [os.utime(f, (old, old)) for f in tmp_path.iterdir()]
    tf.search("nano"); assert len(n) == 2

def test_cache_lives_next_to_the_project_not_the_working_directory(tmp_path):
    out = subprocess.run([sys.executable, "-c", "import core.tf as t; print(t.CACHE)"], cwd=tmp_path, capture_output=True, text=True,
                         env=dict(os.environ, PYTHONPATH=str(ROOT)))
    assert out.stdout.strip() == str(ROOT / ".cache"), out.stderr
