"""Generate comprehensive Markdown and HTML engineering reports."""
from __future__ import annotations

from typing import Optional

from .bom import bom_table, checks_table, ledger_table
from core.power import PowerAnalysis, analyze_power
from core.schemas import Requirements
from core.selector import Build
from core.wiring import WiringPlan, generate_wiring_plan


def generate_markdown_report(build: Build, req: Requirements, config: dict, spec_defs: dict,
                             power: Optional[PowerAnalysis] = None, wiring: Optional[WiringPlan] = None) -> str:
    if power is None:
        power = analyze_power(build, config)
    if wiring is None:
        wiring = generate_wiring_plan(build)

    badge = {"verified": "✅ FULLY VERIFIED", "unverified": "⚠️ UNVERIFIED (Some Unknowns)", "invalid": "❌ INVALID"}.get(build.status, build.status.upper())
    budget_diff = req.budget_inr - build.total
    budget_status = f"₹{abs(budget_diff):,.0f} under budget" if budget_diff >= 0 else f"₹{abs(budget_diff):,.0f} OVER budget"

    lines = [
        f"# Robot Engineering Report: {req.robot_type.replace('_', ' ').title()}",
        f"**Validation Status:** {badge}  |  **Total Cost:** ₹{build.total:,.0f} ({budget_status})  |  **Est. Runtime:** {build.derived.get('runtime_h', 0):.1f}h",
        "",
        "---",
        "## 1. Project Requirements & Design Constraints",
        f"- **Robot Type:** {req.robot_type.replace('_', ' ').title()}",
        f"- **Target Budget:** ₹{req.budget_inr:,.0f}",
        f"- **Motor Count:** {req.motor_count}",
        f"- **Minimum Runtime:** {req.min_runtime_h} hours",
        f"- **Bluetooth Connectivity:** {'Required' if req.needs_bluetooth else 'Not requested'}",
        f"- **Sensor Channels:** {req.sensor_channels or 'Default for robot type'}",
        "",
        "---",
        "## 2. Bill of Materials (BOM)",
        "| Category | Component | Vendor | Qty | Unit Price (INR) | Line Total (INR) | Stock |",
        "| :--- | :--- | :--- | :--- | :--- | :--- | :--- |",
    ]

    for cat, p in build.parts.items():
        q = build.qty[cat]
        u = float(p.price.value)
        stock_str = "In Stock" if (p.in_stock and p.in_stock.value) else ("Out of Stock" if (p.in_stock and p.in_stock.value is False) else "Unknown")
        lines.append(f"| {cat.title()} | {p.name} | {p.vendor} | {q} | ₹{u:,.0f} | ₹{u * q:,.0f} | {stock_str} |")

    lines.extend([
        "",
        f"**Parts Subtotal:** ₹{build.parts_cost:,.0f}  |  **Estimated Shipping:** ₹{build.shipping_total:,.0f}  |  **Final Total:** ₹{build.total:,.0f}",
        "",
        "### Shipping Breakdown",
        "| Vendor | Order Subtotal | Shipping Estimate |",
        "| :--- | :--- | :--- |",
    ])
    for s in build.shipping_rows:
        ship_txt = "FREE" if s["shipping"] == 0 else f"₹{s['shipping']:,.0f}"
        lines.append(f"| {s['vendor']} | ₹{s['subtotal']:,.0f} | {ship_txt} |")

    lines.extend([
        "",
        "---",
        "## 3. Compatibility Rule Verification",
        f"- **Checks Passed:** {build.counts.get('pass', 0)}",
        f"- **Checks Unknown:** {build.counts.get('unknown', 0)} (missing datasheet specs)",
        f"- **Checks Failed:** {build.counts.get('fail', 0)}",
        "",
        "| Status | Category | Rule Title | Message | Evidence Used |",
        "| :--- | :--- | :--- | :--- | :--- |",
    ])
    for c in build.checks:
        icon = {"pass": "✅ PASS", "fail": "❌ FAIL", "unknown": "❓ UNKNOWN"}.get(c.status, c.status)
        ev_str = "; ".join(f"{e.field}={e.value}{(' ' + e.unit) if e.unit else ''}" for e in c.evidence) or "None"
        lines.append(f"| {icon} | {c.category.title()} | {c.title} | {c.message} | {ev_str} |")

    if power:
        lines.extend([
            "",
            "---",
            "## 4. Power & Battery Discharge Analysis",
            f"- **System Idle Current:** {power.system_idle_current_a * 1000:.0f} mA",
            f"- **Typical Working Current:** {power.system_typical_current_a * 1000:.0f} mA",
            f"- **Peak Stall Current:** {power.system_peak_stall_current_a:.2f} A",
            f"- **Battery Usable Capacity:** {power.battery_usable_mah:.0f} mAh (of {power.battery_capacity_mah:.0f} mAh rated)",
            f"- **Battery Discharge Safety Margin:** {power.battery_safety_margin_pct:.1f}%",
            f"- **Estimated Operational Runtime:** {power.runtime_typical_h:.1f} hours",
            f"- **Continuous Full Stall Margin:** {power.runtime_stall_min:.1f} minutes",
            f"- **Driver Power Dissipation:** {power.driver_thermal_loss_w:.2f} W ({'Needs heatsink' if power.thermal_warning else 'Acceptable passive cooling'})",
        ])

    if wiring:
        lines.extend([
            "",
            "---",
            "## 5. Pinout & Interconnect Wiring Guide",
            "| From Component | Pin | To Component | Pin | Signal Type | Notes |",
            "| :--- | :--- | :--- | :--- | :--- | :--- |",
        ])
        for w in wiring.connections:
            lines.append(f"| {w.source_component} | {w.source_pin} | {w.target_component} | {w.target_pin} | {w.wire_type} | {w.notes or ''} |")

        lines.extend([
            "",
            "### Assembly Steps",
        ])
        for step in wiring.assembly_steps:
            lines.append(f"- {step}")

    lines.extend([
        "",
        "---",
        "## 6. Audit & Evidence Ledger",
        "| Component | Parameter | Verified Value | Method | Source URL |",
        "| :--- | :--- | :--- | :--- | :--- |",
    ])
    for cat, p in build.parts.items():
        lines.append(f"| {p.name} | Price | ₹{p.price.value} | {p.price.evidence.method} | {p.price.evidence.source_url or 'Seed catalog'} |")
        for k, s in p.specs.items():
            if s.value is not None:
                lines.append(f"| {p.name} | {k} | {s.value} {s.unit or ''} | {s.evidence.method} | {s.evidence.source_url or 'Seed catalog'} |")

    return "\n".join(lines)


def generate_html_report(build: Build, req: Requirements, config: dict, spec_defs: dict) -> str:
    md = generate_markdown_report(build, req, config, spec_defs)
    # Simple, standalone HTML generator with responsive CSS styling
    html_lines = [
        "<!DOCTYPE html>",
        "<html lang='en'>",
        "<head>",
        "<meta charset='utf-8'>",
        "<meta name='viewport' content='width=device-width, initial-scale=1'>",
        f"<title>Engineering Report - {req.robot_type.replace('_', ' ').title()}</title>",
        "<style>",
        "body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; line-height: 1.6; color: #1e293b; max-width: 1000px; margin: 40px auto; padding: 0 20px; background: #f8fafc; }",
        "h1, h2, h3 { color: #0f172a; margin-top: 1.5em; }",
        "h1 { border-bottom: 2px solid #e2e8f0; padding-bottom: 12px; }",
        "table { width: 100%; border-collapse: collapse; margin: 20px 0; background: #ffffff; border-radius: 8px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }",
        "th, td { padding: 12px 14px; text-align: left; border-bottom: 1px solid #e2e8f0; font-size: 14px; }",
        "th { background-color: #f1f5f9; font-weight: 600; color: #334155; }",
        "tr:hover { background-color: #f8fafc; }",
        ".badge { display: inline-block; padding: 4px 10px; border-radius: 6px; font-weight: 600; font-size: 13px; }",
        ".badge-pass { background: #dcfce7; color: #15803d; }",
        ".badge-fail { background: #fee2e2; color: #b91c1c; }",
        ".badge-unknown { background: #fef3c7; color: #b45309; }",
        ".card { background: #ffffff; padding: 20px; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); margin: 20px 0; }",
        "</style>",
        "</head>",
        "<body>",
        f"<h1>🤖 Robot Engineering Report: {req.robot_type.replace('_', ' ').title()}</h1>",
        f"<p><strong>Validation:</strong> {build.status.upper()} | <strong>Total:</strong> ₹{build.total:,.0f} | <strong>Runtime:</strong> {build.derived.get('runtime_h', 0):.1f}h</p>",
        "<hr>",
        "<h2>Bill of Materials</h2>",
        "<table>",
        "<thead><tr><th>Category</th><th>Component</th><th>Vendor</th><th>Qty</th><th>Unit (INR)</th><th>Line (INR)</th></tr></thead>",
        "<tbody>",
    ]
    for cat, p in build.parts.items():
        q = build.qty[cat]
        u = float(p.price.value)
        html_lines.append(f"<tr><td>{cat.title()}</td><td><strong>{p.name}</strong></td><td>{p.vendor}</td><td>{q}</td><td>₹{u:,.0f}</td><td>₹{u*q:,.0f}</td></tr>")
    html_lines.extend([
        "</tbody></table>",
        f"<div class='card'><strong>Parts Subtotal:</strong> ₹{build.parts_cost:,.0f} | <strong>Shipping:</strong> ₹{build.shipping_total:,.0f} | <strong>Total:</strong> ₹{build.total:,.0f}</div>",
        "<h2>Compatibility Checks</h2>",
        "<table><thead><tr><th>Status</th><th>Category</th><th>Rule</th><th>Result Message</th></tr></thead><tbody>"
    ])
    for c in build.checks:
        cls = "badge-pass" if c.status == "pass" else ("badge-fail" if c.status == "fail" else "badge-unknown")
        html_lines.append(f"<tr><td><span class='badge {cls}'>{c.status.upper()}</span></td><td>{c.category}</td><td>{c.title}</td><td>{c.message}</td></tr>")
    html_lines.extend([
        "</tbody></table>",
        "</body></html>"
    ])
    return "\n".join(html_lines)
