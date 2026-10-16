import json
from core import pipeline

PAGE = "Price: Rs. 450"
class R:
    text = json.dumps(dict(price_inr=450, in_stock=True, quote="Price: Rs. 450"))
class M:
    def __init__(self, bad): self.bad, self.tried = bad, []
    def generate_content(self, model, **kw):
        self.tried.append(model)
        if model in self.bad: raise RuntimeError("404 NOT_FOUND model unavailable")
        return R()
class C:
    def __init__(self, bad): self.models = M(bad)

def test_falls_back_when_model_unavailable(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "x"); monkeypatch.setenv("GEMINI_MODEL", "gemini-2.5-flash")
    pipeline._G = C({"gemini-2.5-flash", "gemini-3.8-flash"})
    assert pipeline.extract_offer(PAGE, "Nano")["price"] == 450.0
    assert pipeline._G.models.tried == ["gemini-2.5-flash", "gemini-3.8-flash", "gemini-3.5-flash-lite"]

def test_other_errors_are_not_swallowed(monkeypatch):
    import pytest
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    class Boom(C):
        def __init__(self): self.models = type("M", (), {"generate_content": lambda s, **k: (_ for _ in ()).throw(RuntimeError("invalid api key"))})()
    pipeline._G = Boom()
    with pytest.raises(RuntimeError): pipeline.extract_offer(PAGE, "Nano")


def test_busy_model_is_retried_then_falls_back(monkeypatch):
    monkeypatch.setattr(pipeline.time, "sleep", lambda s: None)
    monkeypatch.setenv("GEMINI_API_KEY", "x"); monkeypatch.setenv("GEMINI_MODEL", "gemini-3.8-flash")
    class Busy(M):
        def generate_content(self, model, **kw):
            self.tried.append(model)
            if model == "gemini-3.8-flash": raise RuntimeError("503 UNAVAILABLE high demand")
            return R()
    c = C(set()); c.models = Busy(set()); pipeline._G = c
    assert pipeline.extract_offer(PAGE, "Nano")["price"] == 450.0
    assert c.models.tried == ["gemini-3.8-flash", "gemini-3.8-flash", "gemini-3.5-flash-lite"]

def test_busy_then_recovers_on_retry(monkeypatch):
    monkeypatch.setattr(pipeline.time, "sleep", lambda s: None)
    monkeypatch.setenv("GEMINI_API_KEY", "x"); monkeypatch.setenv("GEMINI_MODEL", "gemini-3.8-flash")
    class Flaky(M):
        def generate_content(self, model, **kw):
            self.tried.append(model)
            if len(self.tried) == 1: raise RuntimeError("503 UNAVAILABLE")
            return R()
    c = C(set()); c.models = Flaky(set()); pipeline._G = c
    assert pipeline.extract_offer(PAGE, "Nano")["price"] == 450.0 and len(c.models.tried) == 2
