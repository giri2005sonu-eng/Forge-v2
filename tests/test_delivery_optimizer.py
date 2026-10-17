"""Tests for core.delivery_optimizer (BOM Cost vs Delivery Optimizer & Cart Export)."""
import pytest
from core import delivery_optimizer as dopt

def test_calculate_vendor_packages_free_shipping():
    lines = [
        {"name": "Arduino Nano", "qty": 1, "unit": 250.0, "total": 250.0, "vendor": "robu.in", "url": "https://robu.in/nano"},
        {"name": "L298N", "qty": 1, "unit": 150.0, "total": 150.0, "vendor": "robu.in", "url": "https://robu.in/l298n"},
        {"name": "Battery 3S", "qty": 1, "unit": 700.0, "total": 700.0, "vendor": "robu.in", "url": "https://robu.in/bat"},
        {"name": "Sensor", "qty": 1, "unit": 120.0, "total": 120.0, "vendor": "quartzcomponents.com", "url": "https://quartzcomponents.com/sensor"}
    ]
    res = dopt.calculate_vendor_packages(lines, shipping_fee=60.0, free_threshold=999.0)
    assert res["n_packages"] == 2
    
    # robu total: 250 + 150 + 700 = 1100 (>= 999 -> Free shipping)
    robu_pkg = next(p for p in res["packages"] if p["vendor"] == "robu.in")
    assert robu_pkg["free_shipping"] is True
    assert robu_pkg["shipping"] == 0.0
    assert robu_pkg["subtotal"] == 1100.0
    assert robu_pkg["total"] == 1100.0

    # quartz total: 120 (< 999 -> 60 shipping)
    quartz_pkg = next(p for p in res["packages"] if p["vendor"] == "quartzcomponents.com")
    assert quartz_pkg["free_shipping"] is False
    assert quartz_pkg["shipping"] == 60.0
    assert quartz_pkg["total"] == 180.0

    # overall
    assert res["total_parts"] == 1220.0
    assert res["total_shipping"] == 60.0
    assert res["total_landing_cost"] == 1280.0

def test_analyze_sourcing_strategies_consolidation_savings():
    parts = {
        "controller": {"id": "ctrl_nano", "name": "Arduino Nano", "role": "controller", "qty": 1, "seed_price": 250.0},
        "driver": {"id": "drv_l298n", "name": "L298N Driver", "role": "driver", "qty": 1, "seed_price": 140.0},
        "sensor": {"id": "sen_line", "name": "Line Sensor", "role": "sensor", "qty": 1, "seed_price": 100.0}
    }
    # Live prices:
    # Option 1 (Split):
    # - Nano at shop_a for 240 (cheapest)
    # - L298N at shop_b for 130 (cheapest)
    # - Sensor at shop_c for 90 (cheapest)
    # Total parts: 460. Shipping: 3 x 60 = 180 -> Landing: 640
    #
    # Option 2 (Consolidated at robu.in):
    # - Nano at robu.in for 250
    # - L298N at robu.in for 140
    # - Sensor at robu.in for 100
    # Total parts: 490. Shipping: 1 x 60 = 60 -> Landing: 550 (Saves Rs 90!)
    live = {
        "ctrl_nano": [
            {"url": "https://shopa.in/nano", "price": 240.0, "quote": "Rs 240"},
            {"url": "https://robu.in/nano", "price": 250.0, "quote": "Rs 250"}
        ],
        "drv_l298n": [
            {"url": "https://shopb.in/l298n", "price": 130.0, "quote": "Rs 130"},
            {"url": "https://robu.in/l298n", "price": 140.0, "quote": "Rs 140"}
        ],
        "sen_line": [
            {"url": "https://shopc.in/sensor", "price": 90.0, "quote": "Rs 90"},
            {"url": "https://robu.in/sensor", "price": 100.0, "quote": "Rs 100"}
        ]
    }

    res = dopt.analyze_sourcing_strategies(parts, live, shipping_fee=60.0, free_threshold=999.0)
    
    # Split strategy
    split = res["split"]
    assert split["packages_info"]["n_packages"] == 3
    assert split["packages_info"]["total_shipping"] == 180.0
    assert split["packages_info"]["total_landing_cost"] == 640.0

    # Consolidated strategy
    cons = res["consolidated"]
    assert cons["vendor"] == "robu.in"
    assert cons["coverage"] == 3
    assert cons["n_packages"] == 1
    assert cons["shipping_cost"] == 60.0
    assert cons["landing_cost"] == 550.0

    # Smart optimizer strategy selects the lower landing cost
    smart = res["smart"]
    assert smart["packages_info"]["total_landing_cost"] == 550.0
    assert smart["savings_vs_split"] == 90.0
    assert all("robu.in" in url for url in smart["choice"].values())

def test_export_cart_csv():
    lines = [
        {"name": "Arduino Nano", "role": "controller", "qty": 1, "unit": 250.0, "total": 250.0, "vendor": "robu.in", "url": "https://robu.in/nano", "listing": "Arduino Nano V3", "source": "live", "in_stock": True}
    ]
    csv_str = dopt.export_cart_csv(lines)
    assert "Component,Role,Quantity,Vendor" in csv_str
    assert "Arduino Nano" in csv_str
    assert "robu.in" in csv_str
    assert "https://robu.in/nano" in csv_str
