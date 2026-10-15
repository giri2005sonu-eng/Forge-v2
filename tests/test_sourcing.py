import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.catalog import load_seed
from core.config import load_config, load_spec_defs
from core.sourcing import check_prices, find_sources, pick_links, query_variants

SD = load_spec_defs()
CFG = load_config()
SEED = load_seed(SD)
UNO = SEED["ctrl_uno"]
ALLOWED = CFG["allowed_vendor_domains"]


def hits(*domains, prefix="p"):
    return [{"url": f"https://{d}/{prefix}-uno", "title": f"Uno at {d}", "snippet": "Arduino Uno R3", "site_name": d} for d in domains]


class FakeTF:
    """Each query returns a different slice, like real search."""
    def __init__(self, per_query):
        self.per_query, self.calls = list(per_query), []
    def search(self, q):
        self.calls.append(q)
        return self.per_query[len(self.calls) - 1] if len(self.calls) <= len(self.per_query) else []
    def fetch(self, urls, ttl=0):
        pages = [{"url": u, "text": "Arduino Uno R3 compatible board. Price: ₹ 549. In stock."} for u in urls if "robu" in u or "amazon" in u]
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


def test_price_check_only_accepts_quoted_prices(tmp_path):
    tf = FakeTF([hits("robu.in", "robocraze.com", "amazon.in", "quartzcomponents.com", "electronicscomp.com")])
    out = find_sources(UNO, tf, ALLOWED, data_dir=tmp_path)
    good = {"product_name": "Arduino Uno R3", "matches_requested_part": True,
            "price_inr": {"value": 549, "quote": "Price: ₹ 549"}, "in_stock": {"value": True, "quote": "In stock"}, "specs": {}}
    res = check_prices(UNO, [l["url"] for l in out["links"]], tf, lambda p, s: good, SD, data_dir=tmp_path)["prices"]
    ok = [u for u, r in res.items() if r["price"] == 549.0]
    assert len(ok) == 2 and all(res[u]["in_stock"] is True for u in ok)           # robu + amazon
    assert all(r["error"] for u, r in res.items() if u not in ok)                 # 403s surface an error
    # hallucinated price (quote not on page) must be rejected
    bad = {**good, "price_inr": {"value": 99, "quote": "Only Rs 99 today"}}
    res2 = check_prices(UNO, ok, tf, lambda p, s: bad, SD, data_dir=tmp_path)["prices"]
    assert all(r["price"] is None for r in res2.values())


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
