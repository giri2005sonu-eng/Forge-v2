from core import pipeline, tf
from core.data import CATALOG

def test_extras_are_in_the_bom_and_cost():
    r = pipeline.select("line_follower", 3000)["best"]
    assert {"chassis", "wires", "switch"} <= set(r["parts"])
    base = sum(pipeline.price_of(p, {})[0] * (2 if k == "motor" else 1) for k, p in r["parts"].items())
    assert r["cost"] == base

def test_non_shop_pages_are_skipped():
    assert not pipeline.usable("https://www.youtube.com/watch?v=abc")
    assert not pipeline.usable("https://docs.cirkitdesigner.com/component/x")
    assert not pipeline.usable("https://zbotic.in/product-category/motors/n20/")
    assert pipeline.usable("https://robu.in/product/l298n-2a-based-motor-driver-module-good-quality/")

def test_source_part_only_fetches_usable_pages(monkeypatch):
    hits = [dict(title="", snippet="", url=u) for u in ("https://youtube.com/watch?v=1", "https://a.in/p/1", "https://b.in/p/2")]
    seen = []
    monkeypatch.setattr(tf, "search", lambda q: hits)
    monkeypatch.setattr(tf, "fetch", lambda urls: (seen.extend(urls) or {}))
    pipeline.source_part(CATALOG[0], log=lambda m: None)
    assert seen == ["https://a.in/p/1", "https://b.in/p/2"]
