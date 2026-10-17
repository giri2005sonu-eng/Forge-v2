from core import ledger
from core.data import CATALOG

P = {p["id"]: p for p in CATALOG}
PARTS = dict(controller=P["ctrl_nano"], driver=P["drv_l298n"])
LIVE = {"ctrl_nano": [
    dict(url="https://robu.in/p/nano", price=229.0, quote="Price: ₹ 229", name="Arduino Nano V3", in_stock=True,
         method="page rules", checked_at="2026-10-15T10:00:00+00:00"),
    dict(url="https://x.in/nano", price=None, quote=None, name=None, in_stock=None, note="Price not used: page sells the original/genuine version")]}


def test_every_number_has_a_status_and_verified_rows_have_proof():
    rs = ledger.rows(PARTS, LIVE)
    ver = [r for r in rs if r["status"] == "verified"]
    assert ver and all(r["source_url"].startswith("https://") and r["quote"] and r["retrieved_at"] and r["method"] for r in ver if r["field"] == "price_inr")
    seed = [r for r in rs if r["status"] == "seed"]
    assert any(r["part_id"] == "drv_l298n" and r["field"] == "price_inr" for r in seed)     # no live data -> seed estimate, labelled
    assert all(not r["source_url"] and not r["quote"] for r in seed)                          # seed rows never pretend to have a source
    assert not any(r["part_id"] == "ctrl_nano" and r["status"] == "seed" and r["field"] == "price_inr" for r in rs)
    un = [r for r in rs if r["status"] == "unverified"]
    assert len(un) == 1 and "original" in un[0]["note"]
    s = ledger.summary(rs)
    assert s["verified"] >= 2 and s["unverified"] == 1 and not any(r["field"] == "in_stock" for r in rs)  # stock is never recorded and s["total"] == len(rs)


def test_chosen_listing_is_marked():
    rs = ledger.rows(PARTS, LIVE)
    price = next(r for r in rs if r["part_id"] == "ctrl_nano" and r["field"] == "price_inr" and r["status"] == "verified")
    assert price["note"] == "Chosen listing" and price["value"] == 229.0


def test_csv_is_safe_against_formula_injection():
    live = {"ctrl_nano": [dict(url="https://a.in/p", price=229.0, quote="=HYPERLINK(\"http://evil\")", name="@cmd", in_stock=None, method="m", checked_at="t")]}
    csv_text = ledger.to_csv(ledger.rows(PARTS, live))
    assert csv_text.splitlines()[0].startswith("part_id,part,role,field")
    assert "\"'=HYPERLINK" in csv_text and ",'@cmd," in csv_text
    assert "\n=" not in csv_text and ",=" not in csv_text
