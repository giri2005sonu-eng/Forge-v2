"""Cart check routing: TinyFish Browser for robu.in / robocraze.com, Web Agent for everything else, and every step says who did it."""
import sys, types
import pytest
from core import browser_cart as bc, tf

URL = "https://robu.in/product/arduino-nano/"
AGENT_RES = dict(status="COMPLETED", result=dict(added_to_cart=True, unit_price_inr=229.0), num_of_steps=7)
BROWSER_RES = dict(status="COMPLETED", num_of_steps=3, method="browser", steps=[dict(actor="browser", text="x")],
                   result=dict(added_to_cart=True, unit_price_inr=229.0, cart_total_inr=299.0, in_stock=True))


# ---------- fake shops (served to a local Chromium, so the script is tested without any network) ----------
NAME = "Arduino Nano V3 Board"
WOO_PRODUCT = f"""<h1 class="product_title">{NAME}</h1><p>₹ 229.00</p>
<button class="single_add_to_cart_button" onclick="localStorage.setItem('cart','1')">Add to cart</button>"""
SHOPIFY_PRODUCT = f"""<h1>{NAME}</h1><p>Rs. 229.00</p>
<form action="/cart/add"><button type="submit" name="add" onclick="event.preventDefault();localStorage.setItem('cart','1')">Add to cart</button></form>"""
OUT_OF_STOCK = f"<h1>{NAME}</h1><p>Out of stock</p>"
EMPTY = "<p>Your cart is currently empty.</p>"
WOO_CART = f"""<div id=c></div><script>if(localStorage.getItem('cart'))document.getElementById('c').innerHTML=
'<table><tr class="cart_item"><td>{NAME}</td><td>₹229.00</td><td>1</td><td>₹229.00</td></tr></table><p>Subtotal ₹229.00</p><p>Total ₹299.00</p>';
else document.getElementById('c').textContent='Your cart is currently empty.'</script>"""
SHOP_CART = f"""<div id=c></div><script>if(localStorage.getItem('cart'))document.getElementById('c').innerHTML=
'<ul><li class="cart-item">{NAME} Rs. 229.00 Qty 1 Rs. 229.00</li></ul><p>Estimated total Rs. 229.00</p>';
else document.getElementById('c').textContent='Your cart is empty'</script>"""


def run_on_fake_shop(product_html, cart_html):
    sync = pytest.importorskip("playwright.sync_api") if hasattr(pytest, "importorskip") else None
    try: from playwright.sync_api import sync_playwright
    except ImportError: pytest.skip("playwright not installed")
    with sync_playwright() as p:
        try: browser = p.chromium.launch()
        except Exception: pytest.skip("no local Chromium (run: playwright install chromium)")
        ctx = browser.new_context()
        ctx.route("**/*", lambda r: r.fulfill(status=200, content_type="text/html; charset=utf-8", body=cart_html if r.request.url.rstrip("/").endswith("/cart") else product_html))
        page, steps = ctx.new_page(), []
        out = bc.drive(page, "https://robu.in/product/arduino-nano/", steps)
        browser.close()
    return out, steps


def test_route_only_the_two_shops():
    assert bc.route("https://robu.in/product/x") == "browser" and bc.route("https://www.robocraze.com/products/y") == "browser"
    assert bc.route("https://m.robu.in/p") == "browser"
    for u in ("https://notrobu.in/p", "https://robu.in.evil.com/p", "https://amazon.in/dp/1", "ftp://robu.in/x", "", None, "robu.in/product"):
        assert bc.route(u) == "agent", u


def test_drive_a_woocommerce_style_shop():
    out, steps = run_on_fake_shop(WOO_PRODUCT, WOO_CART)
    assert out["added_to_cart"] is True and out["unit_price_inr"] == 229.0 and out["cart_total_inr"] == 299.0 and out["product_name"] == NAME
    assert steps and all(s["actor"] == "browser" for s in steps) and any("Clicked Add to cart" in s["text"] for s in steps)


def test_drive_a_shopify_style_shop():
    out, _ = run_on_fake_shop(SHOPIFY_PRODUCT, SHOP_CART)
    assert out["added_to_cart"] is True and out["unit_price_inr"] == 229.0 and out["cart_total_inr"] == 229.0


def test_drive_out_of_stock_and_missing_item_are_reported_not_faked():
    out, steps = run_on_fake_shop(OUT_OF_STOCK, EMPTY)
    assert out["added_to_cart"] is False and out["in_stock"] is False and "unit_price_inr" not in out
    out, _ = run_on_fake_shop(WOO_PRODUCT, EMPTY)          # button works but the cart stays empty
    assert out["added_to_cart"] is False and "unit_price_inr" not in out


# ---------- dispatcher ----------
def agent_spy(calls):
    def agent(url): calls.append(url); return dict(AGENT_RES)
    return agent


def test_supported_shop_uses_the_browser_and_never_the_agent(monkeypatch, tmp_path):
    monkeypatch.setattr(tf, "CACHE", tmp_path); calls = []
    monkeypatch.setattr(bc, "run_browser", lambda url: dict(BROWSER_RES))
    out = bc.check(URL, agent_spy(calls))
    assert out["method"] == "browser" and calls == [] and "robu.in" in out["route_note"] and out["steps"][0]["actor"] == "browser"


def test_other_shops_use_the_agent_and_never_start_a_browser(monkeypatch, tmp_path):
    monkeypatch.setattr(tf, "CACHE", tmp_path); calls = []
    monkeypatch.setattr(bc, "run_browser", lambda url: (_ for _ in ()).throw(AssertionError("browser must not start")))
    out = bc.check("https://amazon.in/dp/1", agent_spy(calls))
    assert out["method"] == "agent" and calls == ["https://amazon.in/dp/1"] and out["steps"][0]["actor"] == "agent" and "not robu.in" in out["route_note"]
    assert out["num_of_steps"] == 7 and out["result"]["unit_price_inr"] == 229.0       # the agent's own fields are kept


def test_browser_failure_falls_back_to_the_agent_and_says_why(monkeypatch, tmp_path):
    monkeypatch.setattr(tf, "CACHE", tmp_path); calls = []
    monkeypatch.setattr(bc, "run_browser", lambda url: (_ for _ in ()).throw(TimeoutError("TinyFish Browser did not answer within 150s")))
    out = bc.check(URL, agent_spy(calls))
    assert out["method"] == "agent" and calls == [URL] and "150s" in out["fallback_reason"]
    assert [s["actor"] for s in out["steps"]] == ["browser", "agent"]                    # the failed browser step and the agent step are both listed


def test_browser_that_cannot_add_falls_back_but_sold_out_is_final(monkeypatch, tmp_path):
    monkeypatch.setattr(tf, "CACHE", tmp_path); calls = []
    stuck = dict(BROWSER_RES, result=dict(added_to_cart=False, in_stock=None))
    monkeypatch.setattr(bc, "run_browser", lambda url: dict(stuck))
    out = bc.check(URL, agent_spy(calls))
    assert out["method"] == "agent" and calls == [URL] and [s["actor"] for s in out["steps"]] == ["browser", "agent"]
    sold = dict(BROWSER_RES, result=dict(added_to_cart=False, in_stock=False))
    monkeypatch.setattr(bc, "run_browser", lambda url: dict(sold)); calls.clear()
    out = bc.check(URL, agent_spy(calls))
    assert out["method"] == "browser" and calls == []                                    # genuinely sold out: no credits spent asking again


def test_key_or_quota_errors_do_not_waste_agent_credits(monkeypatch, tmp_path):
    monkeypatch.setattr(tf, "CACHE", tmp_path); calls = []
    monkeypatch.setattr(bc, "run_browser", lambda url: (_ for _ in ()).throw(RuntimeError("403 Forbidden: invalid API key")))
    with pytest.raises(RuntimeError): bc.check(URL, agent_spy(calls))
    assert calls == []


def test_complete_browser_answers_are_cached_incomplete_ones_are_not(monkeypatch, tmp_path):
    monkeypatch.setattr(tf, "CACHE", tmp_path); n = []
    monkeypatch.setattr(bc, "run_browser", lambda url: (n.append(1), dict(BROWSER_RES))[1])
    a = bc.check(URL, agent_spy([])); b = bc.check(URL, agent_spy([]))
    assert len(n) == 1 and b["cached"] is True and a["method"] == b["method"] == "browser"


def test_session_is_always_closed_even_when_the_run_fails(monkeypatch):
    closed = []
    monkeypatch.setattr(bc, "_end_session", lambda sid: closed.append(sid))
    sess = types.SimpleNamespace(session_id="sess-1", cdp_url="wss://x")
    monkeypatch.setattr(tf, "_client", lambda: types.SimpleNamespace(browser=types.SimpleNamespace(sessions=types.SimpleNamespace(create=lambda url: sess))))
    class PW:
        def __enter__(self): raise RuntimeError("cdp refused")
        def __exit__(self, *a): return False
    mod = types.ModuleType("playwright.sync_api"); mod.sync_playwright = lambda: PW()
    monkeypatch.setitem(sys.modules, "playwright", types.ModuleType("playwright")); monkeypatch.setitem(sys.modules, "playwright.sync_api", mod)
    with pytest.raises(RuntimeError): bc.run_browser(URL, timeout=5)
    assert closed == ["sess-1"]


def test_missing_playwright_is_a_clear_fallback_reason(monkeypatch, tmp_path):
    monkeypatch.setattr(tf, "CACHE", tmp_path); calls = []
    monkeypatch.setitem(sys.modules, "playwright", None); monkeypatch.setitem(sys.modules, "playwright.sync_api", None)   # None makes the import fail
    out = bc.check(URL, agent_spy(calls))
    assert out["method"] == "agent" and "Playwright is not installed" in out["fallback_reason"]


# ---------- regression: a RELATED product's Add to cart button must never be clicked ----------
# Real-world case: the main product is out of stock (no main button), but the page still lists related products with their own buttons.
RELATED = """<section class="related products"><h2>Related products</h2><ul class="products"><li class="product"><h2>Some Other Board</h2>
<button class="button add_to_cart_button" onclick="localStorage.setItem('cart','1')">Add to cart</button></li></ul></section>"""
MAIN_OUT_WITH_RELATED = f"<div class='product'><div class='summary'><h1 class='product_title'>{NAME}</h1><p class='price'>₹ 229.00</p><p class='stock out-of-stock'>Out of stock</p></div></div>{RELATED}"
RELATED_OUT_BADGE = RELATED.replace("Some Other Board", "Other Board (Out of stock)")


def _clicked(page_html, cart_html):
    out, steps = run_on_fake_shop(page_html, cart_html)
    return out, steps, any("Clicked" in s["text"] for s in steps)


def test_out_of_stock_main_product_does_not_click_a_related_products_button():
    out, steps, clicked = _clicked(MAIN_OUT_WITH_RELATED, WOO_CART)    # WOO_CART would show a product if ANYTHING had been added
    assert not clicked, steps
    assert out["added_to_cart"] is False and out["in_stock"] is False and "unit_price_inr" not in out
    assert any("out of stock" in s["text"] for s in steps)


def test_a_related_products_out_of_stock_label_does_not_mark_the_main_product_unavailable():
    page = f"<div class='product'><div class='summary'><h1 class='product_title'>{NAME}</h1><p>₹ 229.00</p><form class='cart'><button type='submit' class='single_add_to_cart_button' onclick=\"localStorage.setItem('cart','1')\">Add to cart</button></form></div></div>{RELATED_OUT_BADGE}"
    out, _, clicked = _clicked(page, WOO_CART)
    assert clicked and out["added_to_cart"] is True and out["unit_price_inr"] == 229.0           # it clicked the MAIN button, not the related one


def test_no_main_button_and_no_stock_message_is_unknown_not_a_claim():
    page = f"<div class='product'><div class='summary'><h1 class='product_title'>{NAME}</h1><p>₹ 229.00</p></div></div>{RELATED}"
    out, _, clicked = _clicked(page, WOO_CART)
    assert not clicked and out["added_to_cart"] is False and out["in_stock"] is None              # unknown, so the dispatcher may ask the agent


def test_related_products_out_of_stock_text_alone_is_not_taken_as_the_main_products_stock():
    page = f"<div class='product'><div class='summary'><h1 class='product_title'>{NAME}</h1><p>₹ 229.00</p></div></div>{RELATED_OUT_BADGE}"
    out, _, _ = _clicked(page, EMPTY)
    assert out["in_stock"] is None


def test_shopify_style_sold_out_button_is_reported_as_out_of_stock():
    page = f"<h1>{NAME}</h1><form action='/cart/add'><button type='submit' name='add' disabled>Sold out</button></form>{RELATED}"
    out, _, clicked = _clicked(page, EMPTY)
    assert not clicked and out["added_to_cart"] is False and out["in_stock"] is False


def test_item_that_never_reaches_the_cart_is_unknown_stock_not_in_stock():
    out, _ = run_on_fake_shop(WOO_PRODUCT, EMPTY)           # button clicks, cart stays empty
    assert out["added_to_cart"] is False and out["in_stock"] is None


# ---------- end to end: out-of-stock main product, as seen on robu.in ----------
def test_out_of_stock_product_is_settled_by_the_browser_without_spending_agent_credits(monkeypatch, tmp_path):
    from core import cart_check
    monkeypatch.setattr(tf, "CACHE", tmp_path); calls = []
    out, steps = run_on_fake_shop(MAIN_OUT_WITH_RELATED, WOO_CART)
    monkeypatch.setattr(bc, "run_browser", lambda url, timeout=None: dict(status="COMPLETED", num_of_steps=len(steps), method="browser", steps=steps, result=out))
    res = bc.check(URL, agent_spy(calls))
    assert res["method"] == "browser" and calls == []                       # before: the agent was called (credits) just to learn the item is out of stock
    status, msg = cart_check.compare(149.0, res)
    assert status == "not added" and "out of stock" in msg and "cannot buy it right now" in msg
    assert not any("Clicked" in s["text"] for s in res["steps"])            # and no button was clicked at all


def test_not_added_without_a_stock_reason_keeps_the_neutral_message():
    from core import cart_check
    status, msg = cart_check.compare(149.0, dict(status="COMPLETED", result=dict(added_to_cart=False, in_stock=None), num_of_steps=3))
    assert status == "not added" and "out of stock" not in msg and "variant" in msg
