import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.catalog import load_seed
from core.config import load_config, load_spec_defs
from core.sourcing import ApplyError, apply_price, check_prices, find_sources, pick_links, query_variants, rule_price, rule_stock, variant_matches

SD = load_spec_defs()
CFG = load_config()
SEED = load_seed(SD)
UNO = SEED["ctrl_uno"]
ALLOWED = CFG["allowed_vendor_domains"]


def hits(*domains, prefix="p"):
    return [{"url": f"https://{d}/{prefix}-uno", "title": f"Uno at {d}", "snippet": "Arduino Uno R3", "site_name": d} for d in domains]


class FakeTF:
    """Each query returns a different slice, like real search."""
    def __init__(self, per_query, text="Arduino Uno R3 compatible board. Price: ₹ 549. In stock."):
        self.per_query, self.calls, self.text = list(per_query), [], text
    def search(self, q):
        self.calls.append(q)
        return self.per_query[len(self.calls) - 1] if len(self.calls) <= len(self.per_query) else []
    def fetch(self, urls, ttl=0):
        pages = [{"url": u, "text": self.text} for u in urls if "robu" in u or "amazon" in u]
        errs = [{"url": u, "error": "403"} for u in urls if u not in {p["url"] for p in pages}]
        return pages, errs


def test_five_distinct_stores_from_one_query(tmp_path):
    tf = FakeTF([hits("robu.in", "robocraze.com", "amazon.in", "quartzcomponents.com", "electronicscomp.com", "randomshop.com")])
    out = find_sources(UNO, tf, ALLOWED, target=5, data_dir=tmp_path)
    assert len(tf.calls) == 1  # stops as soon as 5 distinct stores are found
    assert out["tinyfish_count"] >= 5 and out["fallback_count"] == 0
    assert len({l["domain"] for l in out["links"]}) >= 5
    assert [l["rank"] for l in out["links"]] == list(range(1, len(out["links"]) + 1))


def test_multiple_queries_merge_and_junk_is_dropped(tmp_path):
    tf = FakeTF([hits("robu.in", "youtube.com", "wikipedia.org"), hits("robu.in", "amazon.in", "robocraze.com"),
                 hits("thinkrobotics.com", "evelta.com")])
    out = find_sources(UNO, tf, ALLOWED, target=5, data_dir=tmp_path)
    doms = [l["domain"] for l in out["links"]]
    assert "youtube.com" not in doms and "wikipedia.org" not in doms
    assert len(set(doms)) == len(doms) >= 5 and len(tf.calls) == 3
    assert doms[0] in ALLOWED  # known Indian vendors rank first


def test_fallback_is_labelled_when_search_is_thin(tmp_path):
    tf = FakeTF([hits("robu.in", "amazon.in")] * 4)
    out = find_sources(UNO, tf, ALLOWED, target=5, data_dir=tmp_path)
    assert len(out["links"]) == 5 and out["tinyfish_count"] == 2 and out["fallback_count"] == 3
    assert all(l["source"] == "fallback_search_page" for l in out["links"][2:])
    assert len({l["domain"] for l in out["links"]}) == 5


def test_cache_hit_skips_search_and_refresh_bypasses(tmp_path):
    tf = FakeTF([hits("robu.in", "robocraze.com", "amazon.in", "quartzcomponents.com", "electronicscomp.com")])
    find_sources(UNO, tf, ALLOWED, data_dir=tmp_path)
    n = len(tf.calls)
    again = find_sources(UNO, tf, ALLOWED, data_dir=tmp_path)
    assert again["cached"] and len(tf.calls) == n
    find_sources(UNO, tf, ALLOWED, data_dir=tmp_path, refresh=True)
    assert len(tf.calls) > n


def test_total_search_failure_raises(tmp_path):
    class Boom:
        def search(self, q): raise RuntimeError("TinyFish down")
    try:
        find_sources(UNO, Boom(), ALLOWED, data_dir=tmp_path)
        assert False
    except RuntimeError as e:
        assert "TinyFish down" in str(e)


def test_gemini_reads_price_first_and_rules_back_it_up(tmp_path):
    tf = FakeTF([hits("robu.in", "robocraze.com", "amazon.in", "quartzcomponents.com", "electronicscomp.com")])
    out = find_sources(UNO, tf, ALLOWED, data_dir=tmp_path)
    urls = [l["url"] for l in out["links"]]
    good = {"product_name": "Arduino Uno R3", "matches_requested_part": True, "specs": {},
            "price_inr": {"value": 549, "quote": "Price: ₹ 549"}, "in_stock": {"value": True, "quote": "In stock"}}
    res = check_prices(UNO, urls, tf, lambda p, s: good, SD, data_dir=tmp_path)["prices"]
    ok = [u for u, r in res.items() if r["price"] == 549.0]
    assert len(ok) == 2 and all(res[u]["method"] == "Gemini + quote check" and res[u]["in_stock"] is True for u in ok)
    assert all(r["error"] for u, r in res.items() if u not in ok)          # blocked pages carry an error
    def quota(p, s): raise RuntimeError("Gemini error: 429 RESOURCE_EXHAUSTED")
    r429 = check_prices(UNO, ok[:1], tf, quota, SD, data_dir=tmp_path)["prices"][ok[0]]
    assert r429["price"] == 549.0 and r429["method"] == "page rules" and r429["error"] is None   # 429 -> rules take over
    assert check_prices(UNO, ok[:1], tf, None, SD, data_dir=tmp_path)["prices"][ok[0]]["price"] == 549.0  # no Gemini key


def test_gemini_backup_is_quote_checked_and_quota_errors_are_friendly(tmp_path):
    tf = FakeTF([hits("robu.in")], text="Arduino Uno R3 compatible board. Sale today only, call us.")
    u = "https://robu.in/p-uno"
    good = {"product_name": "x", "matches_requested_part": True, "specs": {},
            "price_inr": {"value": 99, "quote": "Only Rs 99 today"}}           # quote NOT on the page -> rejected
    assert check_prices(UNO, [u], tf, lambda p, s: good, SD, data_dir=tmp_path)["prices"][u]["price"] is None
    def quota(p, s): raise RuntimeError("Gemini error: 429 RESOURCE_EXHAUSTED")
    err = check_prices(UNO, [u], tf, quota, SD, data_dir=tmp_path)["prices"][u]
    assert err["price"] is None and "quota" in err["error"].lower()


def test_rule_price_skips_shipping_thresholds_and_junk():
    assert rule_price("COD Available on Order Value Between ₹500 to ₹3,000") is None
    assert rule_price("Sale 11% Buy it now Free Shipping on orders over ₹500 - ship all over") is None
    assert rule_price("Stock: In Stock ₹4 FlyRobo") is None                          # too small to be a board price
    v, q = rule_price("Arduino Uno R3  MRP ₹ 899  Price: ₹ 549  Free shipping above ₹ 499")
    assert v == 549 and "549" in q
    assert rule_price("Arduino UNO R3 Compatible Board only for ₹368.00 Rs.")[0] == 368
    assert rule_stock("Currently unavailable")[0] is False and rule_stock("In stock, add to cart")[0] is True


def test_variant_check_flags_original_vs_compatible():
    assert variant_matches(UNO, "Arduino Uno R3 compatible board") is True
    assert variant_matches(UNO, "Buy Original Arduino UNO R3 genuine Italy") is False
    assert variant_matches(UNO, "Raspberry Pi Pico W") is False


def test_query_variants_are_distinct():
    qs = query_variants(UNO)
    assert len(qs) == len({q.lower() for q in qs}) >= 3


def test_http_endpoints(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    import app as appmod
    real = appmod.find_sources
    monkeypatch.setattr(appmod, "find_sources", lambda *a, **k: real(*a, **{**k, "data_dir": tmp_path}))
    c = TestClient(appmod.app)
    appmod._runtime_keys["tinyfish"] = ""
    assert c.get("/api/part/ctrl_uno/sources").status_code == 400
    assert c.get("/api/part/nope/sources").status_code == 404
    tf = FakeTF([hits("robu.in", "robocraze.com", "amazon.in", "quartzcomponents.com", "electronicscomp.com")])
    monkeypatch.setattr(appmod, "_tf", lambda: tf)
    r = c.get("/api/part/ctrl_uno/sources")
    assert r.status_code == 200 and len(r.json()["links"]) >= 5


def test_apply_price_writes_evidence_and_blocks_bad_cases(tmp_path):
    tf = FakeTF([hits("robu.in", "robocraze.com", "amazon.in", "quartzcomponents.com", "electronicscomp.com")])
    out = find_sources(UNO, tf, ALLOWED, data_dir=tmp_path)
    urls = [l["url"] for l in out["links"]]
    good = {"product_name": "Arduino Uno R3", "matches_requested_part": True,
            "price_inr": {"value": 549, "quote": "Price: ₹ 549"}, "in_stock": {"value": True, "quote": "In stock"}, "specs": {}}
    check_prices(UNO, urls, tf, None, SD, data_dir=tmp_path)
    robu = next(u for u in urls if "robu" in u)
    new = apply_price(UNO, robu, data_dir=tmp_path)
    assert new.price.value == 549.0 and new.price.evidence.method == "scraped"
    assert new.price.evidence.source_url == robu and "549" in new.price.evidence.quote and new.price.evidence.retrieved_at
    assert new.vendor == "robu.in" and new.in_stock.value is True
    assert UNO.price.evidence.method == "curated"                    # original untouched
    for bad in (urls[0].replace("robu.in", "evil.com"), next(u for u in urls if "quartz" in u)):  # unknown / unverified link
        try: apply_price(UNO, bad, data_dir=tmp_path); assert False
        except ApplyError: pass
    tf.text = "Genuine Original Arduino UNO R3. Price: ₹ 2027. In stock."
    check_prices(UNO, [robu], tf, None, SD, data_dir=tmp_path)
    try: apply_price(UNO, robu, data_dir=tmp_path); assert False
    except ApplyError as e: assert "different" in str(e)
