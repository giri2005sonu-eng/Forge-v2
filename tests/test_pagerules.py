from core import pagerules as pr

P = dict(name="Arduino Nano", query="Arduino Nano")


def test_reads_price_with_a_verbatim_quote():
    page = "# Arduino Nano V3\nMRP ₹ 899  Price: ₹ 229  Free shipping above ₹ 499\nIn stock"
    v, q = pr.rule_price(page)
    assert v == 229 and pr.quote_on_page(q, page) and "229" in q


def test_skips_shipping_thresholds_ranges_and_tiny_numbers():
    assert pr.rule_price("COD Available on Order Value Between ₹500 to ₹3,000") is None
    assert pr.rule_price("Free Shipping on orders over ₹500") is None
    assert pr.rule_price("Stock: In Stock ₹4 FlyRobo") is None
    assert pr.rule_price("Arduino Nano compatible board only for ₹368.00 Rs.")[0] == 368


def test_page_name_comes_from_the_page():
    assert pr.page_name("# Arduino Nano V3 CH340\nPrice", "Arduino Nano") == "Arduino Nano V3 CH340"
    assert pr.page_name("some text\nno title here", "Arduino Nano") is None


def test_variant_check_catches_original_vs_clone():
    assert pr.variant_problem(P, "Arduino Nano V3 ATmega328P CH340 Rs 229") is None
    assert "original" in pr.variant_problem(P, "Buy Original Arduino Nano genuine Italy Rs 2755")
    assert pr.variant_problem(P, "Genuine Arduino Nano clone compatible board") is None   # says clone/compatible: fine
    assert pr.variant_problem(P, "Raspberry Pi Pico W") is not None


def test_price_window_keeps_the_price_in_long_pages():
    page = "x " * 20000 + "Price ₹ 549"
    w = pr.price_window(page)
    assert len(w) < 6200 and "549" in w
