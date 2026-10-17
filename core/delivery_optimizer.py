"""BOM Cost vs Delivery Optimizer & Multi-Store Cart Export.
Analyzes verified part listings across vendors to optimize total landing cost
(parts subtotal + vendor shipping charges) vs splitting across multiple stores,
and generates 1-click cart exports & multi-tab checkout launchers.
"""
import copy
import csv
from io import StringIO
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse
from . import bill

DEFAULT_SHIPPING_FEE = 60.0
FREE_SHIPPING_THRESHOLD = 999.0

def get_vendor(url: str) -> str:
    """Return clean vendor domain name (e.g. robu.in, quartzcomponents.com)."""
    return bill.vendor(url)

def calculate_vendor_packages(lines: List[Dict[str, Any]],
                              shipping_fee: float = DEFAULT_SHIPPING_FEE,
                              free_threshold: float = FREE_SHIPPING_THRESHOLD) -> Dict[str, Any]:
    """Group bill lines by vendor and calculate per-vendor shipping and landing totals."""
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for line in lines:
        v = line.get("vendor") or "Estimated / Direct"
        groups.setdefault(v, []).append(line)

    packages = []
    tot_parts = 0.0
    tot_shipping = 0.0

    for vendor_name, v_lines in groups.items():
        subtotal = sum(l.get("total", 0.0) or 0.0 for l in v_lines)
        has_live_url = any(bool(l.get("url")) for l in v_lines)
        
        # Free delivery if order reaches free_threshold or if no online shop URL
        is_free = (subtotal >= free_threshold) or (not has_live_url)
        ship = 0.0 if is_free else shipping_fee

        tot_parts += subtotal
        tot_shipping += ship

        packages.append({
            "vendor": vendor_name,
            "items": v_lines,
            "subtotal": subtotal,
            "shipping": ship,
            "free_shipping": is_free,
            "total": subtotal + ship,
            "item_count": sum(l.get("qty", 1) for l in v_lines),
            "urls": [l["url"] for l in v_lines if l.get("url")]
        })

    # Sort packages by subtotal descending (largest order first)
    packages.sort(key=lambda p: p["subtotal"], reverse=True)

    return {
        "packages": packages,
        "n_packages": len(packages),
        "total_parts": tot_parts,
        "total_shipping": tot_shipping,
        "total_landing_cost": tot_parts + tot_shipping
    }

def analyze_sourcing_strategies(parts: Dict[str, Any],
                                live: Dict[str, List[Dict[str, Any]]],
                                current_choice: Optional[Dict[str, str]] = None,
                                manual: Optional[Dict[str, Any]] = None,
                                shipping_fee: float = DEFAULT_SHIPPING_FEE,
                                free_threshold: float = FREE_SHIPPING_THRESHOLD) -> Dict[str, Any]:
    """Analyze alternative sourcing strategies:
    1. Split Store (lowest unit price for every part, incurring separate shipping per store)
    2. Single-Store / Consolidated (maximize parts from a single dominant vendor like Robu/ElectronicsComp)
    3. Smart Delivery Optimizer (minimum overall landing cost = parts + shipping)
    """
    current_choice = current_choice or {}

    # Extract all verified offers per part
    part_offers: Dict[str, List[Dict[str, Any]]] = {}
    all_vendors: set = set()
    for key, p in parts.items():
        if p.get("none"):
            continue
        pid = p["id"]
        offers = bill.offers_for(pid, live)
        part_offers[pid] = offers
        for o in offers:
            v = get_vendor(o.get("url", ""))
            if v and v != "unknown shop":
                all_vendors.add(v)

    # 1. CURRENT SELECTION STRATEGY
    current_lines = bill.build_lines(parts, live, current_choice, manual=manual)
    current_pkg = calculate_vendor_packages(current_lines, shipping_fee, free_threshold)

    # 2. SPLIT STORE (CHEAPEST UNIT PRICE EVERYWHERE)
    split_choice: Dict[str, str] = {}
    for pid, offs in part_offers.items():
        if offs:
            split_choice[pid] = offs[0]["url"]  # cheapest offer
    split_lines = bill.build_lines(parts, live, split_choice, manual=manual)
    split_pkg = calculate_vendor_packages(split_lines, shipping_fee, free_threshold)

    # 3. CONSOLIDATED SINGLE-STORE STRATEGIES
    # Evaluate every vendor that appears in verified offers
    vendor_candidates = []
    for v in sorted(all_vendors):
        coverage_count = sum(1 for pid, offs in part_offers.items() if any(get_vendor(o.get("url", "")) == v for o in offs))
        if coverage_count == 0:
            continue

        v_choice: Dict[str, str] = {}
        for pid, offs in part_offers.items():
            match = next((o for o in offs if get_vendor(o.get("url", "")) == v), None)
            if match:
                v_choice[pid] = match["url"]
            elif offs:
                v_choice[pid] = offs[0]["url"]  # fallback cheapest

        v_lines = bill.build_lines(parts, live, v_choice, manual=manual)
        v_pkg = calculate_vendor_packages(v_lines, shipping_fee, free_threshold)
        
        vendor_candidates.append({
            "vendor": v,
            "coverage": coverage_count,
            "total_parts": len(part_offers),
            "coverage_pct": (coverage_count / max(1, len(part_offers))) * 100,
            "choice": v_choice,
            "packages_info": v_pkg,
            "landing_cost": v_pkg["total_landing_cost"],
            "parts_cost": v_pkg["total_parts"],
            "shipping_cost": v_pkg["total_shipping"],
            "n_packages": v_pkg["n_packages"]
        })

    # Sort vendor candidates by coverage desc, then landing cost asc
    vendor_candidates.sort(key=lambda vc: (-vc["coverage"], vc["landing_cost"]))

    best_consolidated = vendor_candidates[0] if vendor_candidates else None

    # 4. SMART LANDING COST OPTIMIZER (Minimum Overall Total Cost)
    # Check if a 1-vendor or 2-vendor combination or split yields the lowest landing cost
    best_strategy_name = "Split Store (Lowest Item Price)"
    best_landing_cost = split_pkg["total_landing_cost"]
    best_choice = split_choice
    best_pkg = split_pkg

    # Check consolidated option
    if best_consolidated and best_consolidated["landing_cost"] < best_landing_cost:
        best_landing_cost = best_consolidated["landing_cost"]
        best_choice = best_consolidated["choice"]
        best_pkg = best_consolidated["packages_info"]
        best_strategy_name = f"Consolidated at {best_consolidated['vendor']}"

    # Also test top two vendor pair combination if >= 2 vendors exist
    if len(vendor_candidates) >= 2:
        for i in range(min(3, len(vendor_candidates))):
            v1 = vendor_candidates[i]["vendor"]
            for j in range(i + 1, min(4, len(vendor_candidates))):
                v2 = vendor_candidates[j]["vendor"]
                pair_choice: Dict[str, str] = {}
                for pid, offs in part_offers.items():
                    v_offs = [o for o in offs if get_vendor(o.get("url", "")) in (v1, v2)]
                    if v_offs:
                        pair_choice[pid] = v_offs[0]["url"]
                    elif offs:
                        pair_choice[pid] = offs[0]["url"]
                
                pair_lines = bill.build_lines(parts, live, pair_choice, manual=manual)
                pair_pkg = calculate_vendor_packages(pair_lines, shipping_fee, free_threshold)
                if pair_pkg["total_landing_cost"] < best_landing_cost:
                    best_landing_cost = pair_pkg["total_landing_cost"]
                    best_choice = pair_choice
                    best_pkg = pair_pkg
                    best_strategy_name = f"Optimized 2-Store ({v1} + {v2})"

    savings = max(0.0, split_pkg["total_landing_cost"] - best_landing_cost)

    return {
        "current": {
            "name": "Current Selection",
            "lines": current_lines,
            "packages_info": current_pkg,
            "choice": current_choice
        },
        "split": {
            "name": "Split Store (Lowest Item Price)",
            "description": "Picks the cheapest individual item price across all shops. Incurs separate delivery fees per vendor.",
            "lines": split_lines,
            "packages_info": split_pkg,
            "choice": split_choice
        },
        "consolidated": best_consolidated,
        "smart": {
            "name": best_strategy_name,
            "description": "Optimizes combined item prices + shipping fees to minimize your total out-of-pocket cost and package count.",
            "packages_info": best_pkg,
            "choice": best_choice,
            "savings_vs_split": savings
        },
        "vendor_ranking": vendor_candidates,
        "shipping_fee": shipping_fee,
        "free_threshold": free_threshold
    }

def export_cart_csv(lines: List[Dict[str, Any]],
                    shipping_fee: float = DEFAULT_SHIPPING_FEE,
                    free_threshold: float = FREE_SHIPPING_THRESHOLD) -> str:
    """Export standardized procurement cart CSV ready for bulk orders."""
    pkg_info = calculate_vendor_packages(lines, shipping_fee, free_threshold)
    vendor_ship_map = {p["vendor"]: p["shipping"] for p in pkg_info["packages"]}

    output = StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Component",
        "Role",
        "Quantity",
        "Vendor",
        "Unit Price (INR)",
        "Item Total (INR)",
        "Vendor Shipping (INR)",
        "In Stock",
        "Product URL",
        "Listing Title",
        "Price Verification"
    ])

    for l in lines:
        v = l.get("vendor") or "Estimated / Direct"
        v_ship = vendor_ship_map.get(v, 0.0)
        writer.writerow([
            l.get("name", ""),
            l.get("role", ""),
            l.get("qty", 1),
            v,
            f"{l['unit']:.2f}" if l.get("unit") is not None else "0.00",
            f"{l['total']:.2f}" if l.get("total") is not None else "0.00",
            f"{v_ship:.2f}",
            "Yes" if l.get("in_stock") is True else "Unknown" if l.get("in_stock") is None else "No",
            l.get("url", ""),
            l.get("listing", "") or l.get("name", ""),
            l.get("source", "seed")
        ])

    return output.getvalue()
