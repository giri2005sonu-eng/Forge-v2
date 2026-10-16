import json
import pytest
from core import pipeline, research, specs, tf
from core.data import CATALOG

class R:
    def __init__(self, d): self.text = json.dumps(d)
class G:
    def __init__(self, d): self.models = type("M", (), {"generate_content": lambda s, **k: R(d)})()
def gem(monkeypatch, d):
    monkeypatch.setenv("GEMINI_API_KEY", "x"); pipeline._G = G(d)
P = {p["id"]: p for p in CATALOG}

def test_role_mapping():
    r = research.role_of
    assert r("L298N motor driver module") == "driver" and r("N20 gear motor") == "motor" and r("HC-SR04 ultrasonic sensor") == "sensor"
    assert r("2S 18650 battery pack") == "battery" and r("Arduino Nano") == "controller" and r("breadboard") == "other"

def test_research_keeps_only_quoted_components(monkeypatch, tmp_path):
    monkeypatch.setattr(tf, "CACHE", tmp_path)
    page = "You will need:\n- Arduino Nano board\n- L298N motor driver\n- IR sensors"
    gem(monkeypatch, dict(components=[dict(name="Arduino Nano", quote="- Arduino Nano board"), dict(name="Jetpack", quote="- Jetpack engine")]))
    monkeypatch.setattr(tf, "search", lambda q: [dict(title="", snippet="", url="https://a.in/guide")])
    monkeypatch.setattr(tf, "fetch", lambda urls: {"https://a.in/guide": page})
    out = research.research("Line follower", log=lambda m: None)
    assert [i["name"] for i in out["items"]] == ["Arduino Nano"] and out["items"][0]["role"] == "controller"

def test_spec_compare_statuses(monkeypatch):
    page = "Operating voltage 5V. Input voltage (recommended) 7-9V"
    gem(monkeypatch, dict(vin_min_v=dict(value=7, quote="Input voltage (recommended) 7-9V"), vin_max_v=dict(value=9, quote="Input voltage (recommended) 7-9V"),
                          logic_v=dict(value=3.3, quote="made up quote")))
    found = specs.find_specs(P["ctrl_nano"], page, "x")
    assert set(found) == {"vin_min_v", "vin_max_v"}  # unquoted logic_v rejected
    rows = {r["spec"]: r["status"] for r in specs.compare(P["ctrl_nano"], found)}
    assert rows == {"vin_min_v": "match", "vin_max_v": "differs", "logic_v": "not stated"}

def test_spec_number_must_be_in_quote(monkeypatch):
    gem(monkeypatch, dict(vin_min_v=dict(value=9, quote="Input voltage 7-12V")))
    assert specs.find_specs(P["ctrl_nano"], "Input voltage 7-12V", "x") == {}

def test_agent_is_capped_and_cached(monkeypatch, tmp_path):
    monkeypatch.setattr(tf, "CACHE", tmp_path); seen = []
    class Ag:
        def run(self, **kw): seen.append(kw); return type("Res", (), {"model_dump": lambda s: dict(status="COMPLETED", result={"added_to_cart": True}, num_of_steps=7)})()
    monkeypatch.setattr(tf, "_client", lambda: type("C", (), {"agent": Ag()})())
    r1 = tf.agent("https://robu.in/p/1"); r2 = tf.agent("https://robu.in/p/1")
    assert seen[0]["agent_config"].max_steps == 12 and "Do NOT click checkout" in seen[0]["goal"]
    assert len(seen) == 1 and r2.get("cached") and r1["num_of_steps"] == 7

def test_failed_agent_run_is_not_cached(monkeypatch, tmp_path):
    monkeypatch.setattr(tf, "CACHE", tmp_path); n = []
    class Ag:
        def run(self, **kw): n.append(1); return type("Res", (), {"model_dump": lambda s: dict(status="FAILED", result=None, num_of_steps=3)})()
    monkeypatch.setattr(tf, "_client", lambda: type("C", (), {"agent": Ag()})())
    tf.agent("https://robu.in/p/2"); tf.agent("https://robu.in/p/2")
    assert len(n) == 2
