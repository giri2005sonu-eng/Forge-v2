"""The live-price step must never freeze the screen: every TinyFish call has a time limit and parts are looked up in parallel."""
import threading, time
import pytest
from core import custom_bom, pipeline, tf


def parts(n): return [dict(id=f"p{i}", name=f"Part {i}", role="sensor", query=f"part {i}", seed_price=100) for i in range(n)]


def test_with_timeout_returns_raises_and_gives_up():
    assert tf.with_timeout(lambda: 7, 1) == 7
    with pytest.raises(ValueError): tf.with_timeout(lambda: (_ for _ in ()).throw(ValueError("boom")), 1)
    t0 = time.time()
    with pytest.raises(TimeoutError): tf.with_timeout(lambda: time.sleep(3), 0.2)
    assert time.time() - t0 < 1.5


def test_search_gives_up_instead_of_hanging(monkeypatch, tmp_path):
    monkeypatch.setattr(tf, "CACHE", tmp_path); monkeypatch.setattr(tf, "TIMEOUT_S", 0.2)
    slow = type("S", (), {"query": lambda self, *a, **k: time.sleep(3)})()
    monkeypatch.setattr(tf, "_client", lambda: type("C", (), {"search": slow})())
    t0 = time.time()
    with pytest.raises(TimeoutError): tf.search("arduino nano")
    assert time.time() - t0 < 1.5


def test_all_lookups_hanging_stops_with_a_clear_message(monkeypatch):
    monkeypatch.setattr(tf, "TIMEOUT_S", 0.2)
    def hang(part, **k): raise TimeoutError("TinyFish did not answer within 0s")
    monkeypatch.setattr(pipeline, "source_part", hang)
    msgs, live = [], {}
    t0 = time.time(); custom_bom.source_all(parts(8), live, log=msgs.append, workers=2)
    assert time.time() - t0 < 2 and live == {} and any("not answering" in m for m in msgs)


def test_failures_do_not_block_other_parts_and_logs_stay_on_the_calling_thread(monkeypatch):
    main, seen = threading.current_thread(), []
    def fake(part, log=print, **k):
        log(f"Searching for {part['name']}...")
        if part["id"] == "p1": raise RuntimeError("shop exploded")
        time.sleep(0.05); return [dict(url="https://a.in/x", price=1.0)]
    monkeypatch.setattr(pipeline, "source_part", fake)
    live = {}
    custom_bom.source_all(parts(5), live, log=lambda m: seen.append((m, threading.current_thread() is main)), workers=3)
    assert set(live) == {"p0", "p2", "p3", "p4"} and all(on_main for _, on_main in seen)
    assert any("shop exploded" in m for m, _ in seen) and any("5 of 5" in m for m, _ in seen)


def test_skip_done_keeps_existing_offers(monkeypatch):
    calls = []
    monkeypatch.setattr(pipeline, "source_part", lambda part, log=print, **k: calls.append(part["id"]) or [])
    live = {"p0": [dict(url="u", price=1)]}
    custom_bom.source_all(parts(3), live, skip_done=True, log=lambda m: None)
    assert sorted(calls) == ["p1", "p2"]


def test_cache_survives_a_corrupt_file(monkeypatch, tmp_path):
    monkeypatch.setattr(tf, "CACHE", tmp_path)
    tf.cache_set("k", {"a": 1}); assert tf.cache_get("k") == {"a": 1}
    tf._file("k").write_text("{half written"); assert tf.cache_get("k") is None
