import datetime as dt
from core import bill, pipeline

DAY = dt.date(2026, 10, 16)
def off(u, p, n="Listing", stock=True): return dict(url=u, price=p, name=n, in_stock=stock, quote=f"Rs. {p}")

def setup(budget=5000):
    base = pipeline.select("line_follower", budget, False, {})["best"]["parts"]
    ids = {r: p["id"] for r, p in base.items()}
    live = {ids["controller"]: [off("https://a.in/x", 650), off("https://b.in/x", 400), off("https://c.in/x", 900), dict(url="https://d.in/x", price=None)],
            ids["motor"]: [off("https://a.in/m", 180), off("https://b.in/m", 260)]}
    res = pipeline.select("line_follower", budget, False, live)
    return res, live, ids

def test_default_is_cheapest_and_matches_the_pipeline_total():
    res, live, ids = setup()
    b = bill.make(res["best"]["parts"], live, {}, 5000, "Line follower", DAY)
    assert abs(b["tot"]["subtotal"] - res["best"]["cost"]) < 1e-6 and b["tot"]["premium"] == 0
    assert bill.chosen_url(ids["controller"], live, {}) == "https://b.in/x"

def test_offers_sorted_cheapest_first_and_unverified_excluded():
    _, live, ids = setup()
    assert [o["price"] for o in bill.offers_for(ids["controller"], live)] == [400, 650, 900]
    assert len(bill.unverified_for(ids["controller"], live)) == 1

def test_choosing_a_dearer_listing_raises_total_by_the_premium():
    res, live, ids = setup()
    parts = res["best"]["parts"]
    d = bill.make(parts, live, {}, 5000, "x", DAY)["tot"]
    c = bill.make(parts, live, {ids["motor"]: "https://b.in/m"}, 5000, "x", DAY)["tot"]
    assert c["premium"] == (260 - 180) * 2 and c["subtotal"] == d["subtotal"] + 160 and c["cheapest"] == d["cheapest"]

def test_stale_choice_falls_back_to_cheapest():
    _, live, ids = setup()
    assert bill.chosen_url(ids["controller"], live, {ids["controller"]: "https://gone.in"}) == "https://b.in/x"

def test_parts_without_live_offers_use_labelled_seed_price():
    res, live, _ = setup()
    lines = bill.build_lines(res["best"]["parts"], live, {})
    seeds = [l for l in lines if l["source"] == "seed"]
    assert seeds and all(bill.status_of(l)[0] == "est" for l in seeds)
    assert not any(l["name"] == "No sensor needed" for l in lines)

def test_budget_status():
    res, live, _ = setup()
    parts = res["best"]["parts"]
    assert bill.make(parts, live, {}, 100000, "x", DAY)["tot"]["left"] > 0
    assert bill.make(parts, live, {}, 100, "x", DAY)["tot"]["left"] < 0

def test_web_text_is_escaped_in_html_and_markdown():
    res, live, ids = setup()
    live[ids["controller"]][1]["name"] = '<script>alert(1)</script>'
    h = bill.make(res["best"]["parts"], live, {}, 5000, "x", DAY)["html"]
    assert "<script>" not in h and "&lt;script&gt;" in h
    assert "javascript:" not in bill.safe_url("javascript:alert(1)") and bill.md_escape("[a](b)") == r"\[a\]\(b\)"

def test_pdf_is_generated():
    res, live, _ = setup()
    pdf = bill.make(res["best"]["parts"], live, {}, 5000, "Line follower", DAY)["pdf"]
    assert pdf[:5] == b"%PDF-" and len(pdf) > 2000

def test_indian_grouping():
    assert bill.inr(123456.5) == "₹1,23,456.50" and bill.inr(999) == "₹999.00" and bill.inr(-1500) == "-₹1,500.00"
