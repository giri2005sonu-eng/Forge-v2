import datetime as dt
from core import bill, ledger, pipeline

DAY = dt.date(2026, 10, 17)
def setup():
    parts = pipeline.select("line_follower", 5000, False, {})["best"]["parts"]
    ctrl = parts["controller"]
    live = {ctrl["id"]: [dict(url="https://a.in/ok", price=450.0, name="Verified Nano", quote="Rs. 450", in_stock=True),
                         dict(url="https://b.in/unv", price=None, name="Other Nano", note="Price not used: original")]}
    return parts, ctrl, live

def test_unverified_listing_is_never_chosen_by_default():
    parts, ctrl, live = setup()
    b = bill.make(parts, live, {}, 5000, "x", DAY)
    line = next(l for l in b["lines"] if l["part_id"] == ctrl["id"])
    assert line["source"] == "live" and line["url"] == "https://a.in/ok" and b["tot"]["n_manual"] == 0

def test_user_can_pick_an_unverified_listing_with_their_own_price():
    parts, ctrl, live = setup()
    man = {ctrl["id"]: dict(url="https://b.in/unv", name="Other Nano", price=300.0)}
    b = bill.make(parts, live, {}, 5000, "x", DAY, manual=man)
    line = next(l for l in b["lines"] if l["part_id"] == ctrl["id"])
    assert line["source"] == "manual" and line["unit"] == 300.0 and line["url"] == "https://b.in/unv" and not line["is_cheapest"]
    assert b["tot"]["n_manual"] == 1 and "entered by you" in b["html"] and b["pdf"][:4] == b"%PDF"
    assert "not verified" in bill.status_of(line)[1]

def test_pick_without_a_price_or_with_a_bad_link_is_ignored():
    parts, ctrl, live = setup()
    for bad in (dict(url="https://b.in/unv", price=0), dict(url="javascript:alert(1)", price=100), dict(url="https://b.in/unv", price="abc"), dict(url="https://b.in/unv", price=-5)):
        b = bill.make(parts, live, {}, 5000, "x", DAY, manual={ctrl["id"]: bad})
        assert next(l for l in b["lines"] if l["part_id"] == ctrl["id"])["source"] == "live"

def test_manual_pick_never_touches_verified_prices():
    parts, ctrl, live = setup()
    assert [o["price"] for o in bill.offers_for(ctrl["id"], live)] == [450.0]
    bill.make(parts, live, {}, 5000, "x", DAY, manual={ctrl["id"]: dict(url="https://b.in/unv", price=1.0)})
    assert [o["price"] for o in bill.offers_for(ctrl["id"], live)] == [450.0] and pipeline.spread_warning(live[ctrl["id"]]) is None

def test_ledger_says_the_price_was_typed_by_the_user():
    parts, ctrl, live = setup()
    rows = ledger.rows(parts, live, {}, {ctrl["id"]: dict(url="https://b.in/unv", price=300.0)})
    mine = [r for r in rows if r["status"] == "user-entered"]
    assert len(mine) == 1 and mine[0]["value"] == 300.0 and "NOT read" in mine[0]["note"]
    assert not any(r["status"] == "verified" and r["note"] == "Chosen listing" and r["part_id"] == ctrl["id"] for r in rows)
    assert ledger.summary(rows)["manual"] == 1
