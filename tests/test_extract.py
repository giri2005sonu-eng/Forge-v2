import json
from core import pipeline

PAGE = "Arduino Nano Board - Soldered\nPrice: Rs. 1,299.00 incl. tax\nIn stock"

class Resp:
    def __init__(self, d): self.text = json.dumps(d)
class Models:
    def __init__(self, d): self.d = d
    def generate_content(self, **kw): return Resp(self.d)
class Fake:
    def __init__(self, d): self.models = Models(d)

def run(monkeypatch, d):
    monkeypatch.setenv("GEMINI_API_KEY", "x"); pipeline._G = Fake(d)
    return pipeline.extract_offer(PAGE, "Arduino Nano", use_rules=False)  # these tests are about the Gemini quote check

def test_accepts_price_with_verbatim_quote(monkeypatch):
    o = run(monkeypatch, dict(price_inr=1299, in_stock=True, quote="Price: Rs. 1,299.00 incl. tax"))
    assert o and o["price"] == 1299.0
def test_rejects_quote_not_on_page(monkeypatch):
    assert run(monkeypatch, dict(price_inr=1299, in_stock=True, quote="Only Rs. 1,299 today!")) is None
def test_rejects_quote_without_the_number(monkeypatch):
    assert run(monkeypatch, dict(price_inr=999, in_stock=True, quote="Price: Rs. 1,299.00 incl. tax")) is None
def test_gemini_client_is_reused(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "x"); pipeline._G = None
    assert pipeline._gemini("x") is pipeline._gemini("x")


# ---- rules first, Gemini only as a capped backup ----
def _boom(*a, **k): raise AssertionError("Gemini must not be called when the page rules find the price")

def test_rules_read_the_price_without_calling_gemini(monkeypatch):
    monkeypatch.setattr(pipeline, "_gemini_offer", _boom)
    o = pipeline.extract_offer(PAGE, "Arduino Nano")
    assert o["price"] == 1299.0 and o["method"] == "page rules" and o["checked_at"] and o["in_stock"] is None   # stock is never guessed

def test_gemini_is_a_backup_and_respects_the_budget(monkeypatch):
    page = "Arduino Nano board. Sale today only."                                    # rules find no price here
    calls = []
    monkeypatch.setattr(pipeline, "_gemini_offer", lambda t, n: calls.append(1) or dict(price=99.0, in_stock=None, quote="x", name=None))
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    b = dict(left=1)
    assert pipeline.extract_offer(page, "Arduino Nano", budget=b)["method"] == "Gemini + quote check"
    assert pipeline.extract_offer(page, "Arduino Nano", budget=b) is None and len(calls) == 1   # budget used up -> no 2nd call

def test_a_429_switches_gemini_off_for_a_while(monkeypatch):
    import time
    def quota(t, n): raise RuntimeError("429 RESOURCE_EXHAUSTED")
    monkeypatch.setattr(pipeline, "_gemini_offer", quota); monkeypatch.setattr(pipeline, "_QUOTA_UNTIL", 0.0)
    try: pipeline.extract_offer("Arduino Nano board. Sale today only.", "Arduino Nano"); assert False
    except RuntimeError: pass
    assert pipeline.quota_off()
    monkeypatch.setattr(pipeline, "_gemini_offer", _boom)
    assert pipeline.extract_offer("Arduino Nano board. Sale today only.", "Arduino Nano") is None                        # skipped, not called
    pipeline._QUOTA_UNTIL = 0.0

def test_original_version_price_is_withheld_with_a_note(monkeypatch):
    monkeypatch.setattr(pipeline, "_gemini_offer", _boom)
    o = pipeline.extract_offer("Original Genuine Arduino Nano. Price: ₹ 2755. In stock", "Arduino Nano")
    assert o["price"] is None and "original" in o["note"].lower()

def test_source_part_spends_at_most_the_gemini_budget_per_part(monkeypatch, tmp_path):
    from core import tf
    monkeypatch.setattr(tf, "CACHE", tmp_path)
    urls = [f"https://shop{i}.in/nano" for i in range(4)]
    monkeypatch.setattr(tf, "search", lambda q, **k: [dict(title="", url=u, snippet="") for u in urls])
    pages = {urls[0]: "Arduino Nano. Price: ₹ 229. In stock", **{u: "Arduino Nano board. Sale today only." for u in urls[1:]}}
    monkeypatch.setattr(tf, "fetch", lambda us: {u: pages[u] for u in us})
    n = []
    monkeypatch.setattr(pipeline, "_gemini_offer", lambda t, nm: n.append(1) or None)
    monkeypatch.setenv("GEMINI_API_KEY", "x"); monkeypatch.setattr(pipeline, "_QUOTA_UNTIL", 0.0)
    offers = pipeline.source_part(dict(id="ctrl_nano", name="Arduino Nano", query="Arduino Nano"), log=lambda m: None, gemini_max=2)
    assert offers[0]["price"] == 229.0 and len(n) == 2 and len(offers) == 4


def test_stock_is_never_reported_even_when_the_page_mentions_it(monkeypatch):
    """'Out of Stock' text on a page (related products, banners) must not become a claim about the listing."""
    page = "Arduino Nano V3\nOut of Stock Price ₹410 – ₹490+ Pay\nPrice: ₹ 410\nSold out: Nano Every"
    monkeypatch.setattr(pipeline, "_gemini_offer", lambda t, n: dict(price=410.0, in_stock=False, quote="Price: ₹ 410", name=None))
    o = pipeline.extract_offer(page, "Arduino Nano")
    assert o["price"] == 410.0 and o["in_stock"] is None
    assert not hasattr(pipeline.pagerules, "rule_stock")
