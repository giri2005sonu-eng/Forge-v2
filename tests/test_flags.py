import json
from core import pipeline

PAGE = "Arduino Nano V3 ATmega328P CH340 Mini USB\nPrice: Rs. 229.00\nIn stock"
class R:
    def __init__(self, d): self.text = json.dumps(d)
class M:
    def __init__(self, d): self.d = d
    def generate_content(self, **kw): return R(self.d)
class C:
    def __init__(self, d): self.models = M(d)

def run(monkeypatch, name):
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    pipeline._G = C(dict(product_name=name, price_inr=229, in_stock=True, quote="Price: Rs. 229.00"))
    return pipeline.extract_offer(PAGE, "Arduino Nano")

def test_name_kept_when_verbatim_on_page(monkeypatch):
    assert run(monkeypatch, "Arduino Nano V3 ATmega328P CH340 Mini USB")["name"].startswith("Arduino Nano V3")
def test_invented_name_is_dropped_but_price_kept(monkeypatch):
    o = run(monkeypatch, "Genuine Arduino Nano Original")
    assert o["name"] is None and o["price"] == 229.0

def test_wide_price_spread_is_flagged():
    w = pipeline.spread_warning([dict(price=229), dict(price=2755), dict(price=None)])
    assert w and "229" in w and "2,755" in w
def test_close_prices_not_flagged():
    assert pipeline.spread_warning([dict(price=229), dict(price=300)]) is None
def test_single_or_no_price_not_flagged():
    assert pipeline.spread_warning([dict(price=229)]) is None and pipeline.spread_warning([]) is None
