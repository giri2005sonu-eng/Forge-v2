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
    return pipeline.extract_offer(PAGE, "Arduino Nano")

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
