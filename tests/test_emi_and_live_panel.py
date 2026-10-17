"""EMI / instalment figures are never prices, and 'Generate BOM' shows the live TinyFish panel for rule-checked builds."""
import contextlib

from core import bill, pagerules as pr, pipeline, tf
from core.data import QTY
from core.ledger import rows

NANO_PAGE = ("# Arduino Nano V3 ATmega328P CH340\n| EMI starts at ₹86 per month.\nBuy now. Price: ₹ 229\nIn stock\n")


# ------------------------------------------------------------ EMI
def test_emi_figures_are_not_read_as_prices():
    assert pr.rule_price("| EMI starts at ₹86 per month.") is None
    assert pr.rule_price("Pay ₹ 86/month with No Cost EMI") is None
    assert pr.rule_price("Monthly instalments of ₹ 86") is None
    assert pr.rule_price("EMI from ₹86 per month. Price: ₹ 229")[0] == 229          # the real price after the EMI line still wins
    assert pr.rule_price(NANO_PAGE)[0] == 229


def test_a_page_with_only_an_emi_line_yields_no_price(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    assert pipeline.extract_offer("Arduino Nano board\n| EMI starts at ₹86 per month.", "Arduino Nano") is None


def test_gemini_cannot_smuggle_an_emi_figure_in(monkeypatch):
    monkeypatch.setattr(pipeline, "_gemini_offer", lambda t, n: dict(price=86.0, in_stock=None, quote="| EMI starts at ₹86 per month.", name=None))
    monkeypatch.setattr(pipeline, "_QUOTA_UNTIL", 0.0)
    o = pipeline.extract_offer("Arduino Nano board. Details inside.", "Arduino Nano")
    assert o["price"] is None and "EMI" in o["note"]


def test_a_stored_emi_price_is_ignored_everywhere():
    """Offers already in the session / old cache: ₹86 from the screenshot must not reach the BOM, the cheapest price or the warning."""
    part = pipeline.select("line_follower", 5000, False, {})["best"]["parts"]["controller"]
    emi = dict(url="https://www.amazon.in/n", price=86.0, quote="| EMI starts at ₹86 per month.", name=None, in_stock=True)
    good = dict(url="https://quartzcomponents.com/n", price=229.0, quote="Price: ₹ 229", name="Arduino Nano V3", in_stock=True)
    live = {part["id"]: [emi, good]}
    assert [o["price"] for o in bill.offers_for(part["id"], live)] == [229.0]
    assert pipeline.price_of(part, live) == (229.0, "live")
    assert pipeline.spread_warning([emi, good, dict(good, price=2755.0, quote="Rs 2,755")]) is None or "86" not in pipeline.spread_warning([emi, good, dict(good, price=2755.0, quote="Rs 2,755")])
    un = bill.unverified_for(part["id"], live)
    assert len(un) == 1 and un[0]["price"] is None and "EMI" in un[0]["note"] and un[0]["url"] == emi["url"]
    parts = {"controller": part}
    assert bill.make(parts, live, {}, 5000, "x")["lines"][0]["unit"] == 229.0
    ledger = rows(parts, live, {})
    assert all(r.get("value") != 86.0 for r in ledger if r["field"] == "price_inr")


def test_a_cached_emi_read_from_before_this_fix_is_not_reused(monkeypatch):
    part = dict(id="ctrl_nano", name="Arduino Nano", query="Arduino Nano")
    url = "https://www.amazon.in/n"
    stale = dict(price=86.0, quote="| EMI starts at ₹86 per month.", name=None, in_stock=None, method="page rules")
    monkeypatch.setattr(tf, "search", lambda q, **k: [dict(title="", url=url, snippet="")])
    monkeypatch.setattr(tf, "fetch", lambda urls: {u: NANO_PAGE for u in urls})
    monkeypatch.setattr(tf, "cache_get", lambda k: stale if k.startswith("x:") else None)   # the old cache key
    monkeypatch.setattr(tf, "cache_set", lambda k, v: None)
    out = pipeline.source_part(part, log=lambda m: None, gemini_max=0)
    assert out[0]["price"] == 229.0


# ------------------------------------------------------------ live panel for "Generate BOM"
class SS(dict):
    __getattr__ = dict.get
    def __setattr__(self, k, v): self[k] = v


class FakeStatus:
    def __init__(self, label, expanded): self.label, self.expanded, self.state = label, expanded, "running"
    def update(self, label=None, state=None):
        self.label = label or self.label; self.state = state or self.state
    def __enter__(self): return self
    def __exit__(self, *a): return False


class FakeSt:
    def __init__(self): self.panels, self.writes = [], []
    def status(self, label, expanded=False):
        self.panels.append(FakeStatus(label, expanded)); return self.panels[-1]
    def write(self, msg): self.writes.append(msg)


def _state():
    return SS(live={}, res=None, log=[], custom=None, custom_error=None, suggest=None, choice={}, manual={}, project="line_follower", bom_origin=None)


def test_generate_bom_for_a_rule_build_opens_the_live_panel_and_reprices(monkeypatch):
    from ui import bom
    fake = FakeSt(); monkeypatch.setattr(bom, "st", fake)
    seen = {}
    def source_all(parts, live, log=print, gemini_max=None, skip_done=False):
        seen.update(n=len(parts), gemini_max=gemini_max, skip_done=skip_done)
        for p in parts:
            log(f"Search: 8 results for {p['name']} (4 look like shop pages)")
            live[p["id"]] = [dict(url=f"https://robu.in/{p['id']}", price=100.0, quote="Price: ₹ 100", name=p["name"], in_stock=True)]
    monkeypatch.setattr(bom.custom_bom, "source_all", source_all)
    state = _state()
    bom._open_catalog_project(state, "general:line_follower", 5000, False, True)
    first = pipeline.select("line_follower", 5000, False, {})["best"]
    assert len(fake.panels) == 1 and fake.panels[0].expanded is True                      # the same live panel as 'Plan new build'
    assert "components chosen. Fetching live prices" in " ".join([fake.panels[0].label]) or fake.panels[0].state == "complete"
    assert fake.panels[0].state == "complete" and fake.panels[0].label.startswith("Done")
    assert any(w.startswith("Search: 8 results for") for w in fake.writes) and state.log == fake.writes   # live log lines shown and kept
    assert seen["n"] == len(pipeline.candidate_parts("line_follower")) and seen["gemini_max"] == 0 and seen["skip_done"] is True   # every candidate is priced, not only the winner
    assert {p["id"] for p in first["parts"].values() if not p.get("none")} <= set(state.live)
    assert state.res and state.res["best"] and all(state.live[p["id"]] for p in first["parts"].values() if not p.get("none"))
    assert state.res["best"]["cost"] < first["cost"]                                      # re-selected with the verified prices


def test_generate_bom_without_a_tinyfish_key_shows_no_panel(monkeypatch):
    from ui import bom
    fake = FakeSt(); monkeypatch.setattr(bom, "st", fake)
    monkeypatch.setattr(bom.custom_bom, "source_all", lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not fetch without a key")))
    state = _state()
    bom._open_catalog_project(state, "general:line_follower", 5000, False, False)
    assert not fake.panels and state.res and state.res["best"]
