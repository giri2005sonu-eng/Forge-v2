import copy
import streamlit as st
from core import bill, delivery_optimizer as dopt

def render(state, parts, lines, project_label="Project Build"):
    """Draw the BOM Cost vs Delivery Optimizer and 1-Click Multi-Store Cart studio."""
    if not lines or not parts:
        return

    live = state.live
    current_choice = state.choice

    # Run delivery optimization analysis
    analysis = dopt.analyze_sourcing_strategies(
        parts=parts,
        live=live,
        current_choice=current_choice,
        manual=state.manual,
        shipping_fee=dopt.DEFAULT_SHIPPING_FEE,
        free_threshold=dopt.FREE_SHIPPING_THRESHOLD
    )

    split = analysis["split"]
    cons = analysis["consolidated"]
    smart = analysis["smart"]
    current_pkg = analysis["current"]["packages_info"]

    st.markdown("""
<div style="display:flex;align-items:center;gap:12px;margin:1.6rem 0 0.6rem">
  <div style="background:linear-gradient(135deg,#059669,#10B981);border-radius:10px;width:34px;height:34px;
              display:flex;align-items:center;justify-content:center;font-size:18px;box-shadow:0 2px 10px rgba(16,185,129,.35)">🚚</div>
  <div>
    <h4 style="margin:0;font-size:1.15rem;font-weight:700;color:#F1F5F9;letter-spacing:-0.01em">
      Multi-Store Cart &amp; Delivery Optimizer
    </h4>
    <p style="margin:0;color:#94A3B8;font-size:0.78rem;font-weight:500">
      Optimize total landing cost (parts + delivery charges) vs multi-package splitting · 1-click cart export
    </p>
  </div>
</div>
""", unsafe_allow_html=True)

    # ---------------- 1. SOURCING STRATEGY COMPARISON ----------------
    col_split, col_cons, col_smart = st.columns(3)

    # CARD 1: SPLIT STORE
    with col_split:
        with st.container(border=True):
            st.markdown("<div style='font-size:12px;font-weight:700;color:#94A3B8;text-transform:uppercase'>🏪 Split Store</div>", unsafe_allow_html=True)
            st.markdown("<div style='font-size:13px;font-weight:600;color:#E2E8F0'>Cheapest Item Prices</div>", unsafe_allow_html=True)
            st.caption(f"Parts: **{bill.inr(split['packages_info']['total_parts'])}**")
            st.caption(f"Est. Delivery: **{bill.inr(split['packages_info']['total_shipping'])}** ({split['packages_info']['n_packages']} stores)")
            st.markdown(f"**Landing Cost: {bill.inr(split['packages_info']['total_landing_cost'])}**")
            st.caption(f"📦 {split['packages_info']['n_packages']} separate packages")
            if st.button("Apply Split Sourcing", key="btn_apply_split", use_container_width=True):
                state.choice = copy.deepcopy(split["choice"])
                st.success("Applied lowest unit-price sourcing!")
                st.rerun()

    # CARD 2: CONSOLIDATED VENDOR
    with col_cons:
        with st.container(border=True):
            v_name = cons["vendor"] if cons else "Single Store"
            cov = f"{cons['coverage']}/{cons['total_parts']} parts" if cons else "N/A"
            st.markdown(f"<div style='font-size:12px;font-weight:700;color:#38BDF8;text-transform:uppercase'>🏢 Consolidated ({v_name})</div>", unsafe_allow_html=True)
            st.markdown(f"<div style='font-size:13px;font-weight:600;color:#E2E8F0'>Coverage: {cov}</div>", unsafe_allow_html=True)
            if cons:
                st.caption(f"Parts: **{bill.inr(cons['parts_cost'])}**")
                ship_label = "Free Delivery 🎉" if cons['shipping_cost'] == 0 else bill.inr(cons['shipping_cost'])
                st.caption(f"Est. Delivery: **{ship_label}**")
                st.markdown(f"**Landing Cost: {bill.inr(cons['landing_cost'])}**")
                st.caption(f"📦 {cons['n_packages']} package(s) ({cons['coverage_pct']:.0f}% in 1 box)")
                if st.button(f"Consolidate at {v_name}", key="btn_apply_cons", use_container_width=True):
                    state.choice = copy.deepcopy(cons["choice"])
                    st.success(f"Consolidated parts at {v_name}!")
                    st.rerun()
            else:
                st.caption("No single dominant vendor identified.")

    # CARD 3: SMART DELIVERY OPTIMIZER
    with col_smart:
        with st.container(border=True):
            st.markdown("<div style='font-size:12px;font-weight:700;color:#10B981;text-transform:uppercase'>⚡ Smart Landing Cost</div>", unsafe_allow_html=True)
            st.markdown(f"<div style='font-size:13px;font-weight:600;color:#A7F3D0'>{smart['name']}</div>", unsafe_allow_html=True)
            st.caption(f"Parts: **{bill.inr(smart['packages_info']['total_parts'])}**")
            ship_smart = "Free Delivery 🎉" if smart['packages_info']['total_shipping'] == 0 else bill.inr(smart['packages_info']['total_shipping'])
            st.caption(f"Est. Delivery: **{ship_smart}**")
            st.markdown(f"**Landing Cost: {bill.inr(smart['packages_info']['total_landing_cost'])}**")
            if smart["savings_vs_split"] > 0:
                st.caption(f"💰 **Saves {bill.inr(smart['savings_vs_split'])}** in delivery fees!")
            else:
                st.caption("Lowest overall out-of-pocket landing cost")
            if st.button("👉 Apply Smart Sourcing", key="btn_apply_smart", type="primary", use_container_width=True):
                state.choice = copy.deepcopy(smart["choice"])
                st.success("Applied Smart Delivery Optimized sourcing!")
                st.rerun()

    # ---------------- 2. 1-CLICK MULTI-STORE CART ACTIONS ----------------
    st.markdown("<div style='margin-top:10px'></div>", unsafe_allow_html=True)
    cart_csv_str = dopt.export_cart_csv(lines, dopt.DEFAULT_SHIPPING_FEE, dopt.FREE_SHIPPING_THRESHOLD)
    live_urls = [l["url"] for l in lines if l.get("url")]

    c_btn1, c_btn2, c_btn3 = st.columns([2, 2, 2])

    with c_btn1:
        st.download_button(
            label="📥 Export Cart CSV (Bulk Order)",
            data=cart_csv_str,
            file_name=f"forge_cart_{project_label.lower().replace(' ', '_')}.csv",
            mime="text/csv",
            use_container_width=True,
            help="Download standardized parts cart spreadsheet for purchasing / inventory."
        )

    with c_btn2:
        # Multi-tab opener using client-side HTML/JS button
        urls_js_array = str(live_urls)
        open_all_html = f"""
<button onclick="
  const urls = {urls_js_array};
  if (!urls.length) {{ alert('No verified store URLs found'); return; }}
  let opened = 0;
  urls.forEach(u => {{
    const w = window.open(u, '_blank');
    if (w) opened++;
  }});
  if (opened === 0) {{
    alert('Please allow popups in your browser to open all store tabs at once!');
  }}
" style="width:100%;background:linear-gradient(135deg,#06B6D4,#0891B2);color:#fff;border:none;border-radius:8px;
         padding:8px 14px;font-size:13px;font-weight:700;cursor:pointer;box-shadow:0 2px 8px rgba(6,182,212,.3)">
  🚀 1-Click Open All Links in Tabs ({len(live_urls)})
</button>
"""
        st.components.v1.html(open_all_html, height=45)

    with c_btn3:
        if st.button("📋 View All Purchase Links", key="btn_view_links", use_container_width=True):
            state.opt_show_links = not state.get("opt_show_links", False)

    if state.get("opt_show_links"):
        with st.expander("🔗 All Verified Store URLs", expanded=True):
            for idx, l in enumerate(lines, 1):
                if l.get("url"):
                    st.markdown(f"{idx}. **{l['name']}** ({l.get('vendor')}) · [{l['url']}]({l['url']})")
                else:
                    st.caption(f"{idx}. {l['name']} · No verified shop link yet (Seed estimate)")

    # ---------------- 3. GROUPED VENDOR PACKAGES BREAKDOWN ----------------
    with st.expander(f"📦 Vendor Packages Breakdown ({current_pkg['n_packages']} Shipments · {bill.inr(current_pkg['total_landing_cost'])})", expanded=False):
        for idx, pkg in enumerate(current_pkg["packages"], 1):
            ship_text = "Free Delivery 🎉" if pkg["free_shipping"] else bill.inr(pkg["shipping"])
            st.markdown(f"##### 📦 Package {idx}: **{pkg['vendor']}** · {pkg['item_count']} item(s) · Subtotal: {bill.inr(pkg['subtotal'])} · Delivery: `{ship_text}`")
            for it in pkg["items"]:
                link_text = f"[Shop Listing ↗]({it['url']})" if it.get("url") else "*(Seed estimate)*"
                st.markdown(f"&nbsp;&nbsp;&nbsp;&nbsp;• **{it['name']}** × {it['qty']} · {bill.inr(it['total'])} · {link_text}")
            st.markdown("---")
