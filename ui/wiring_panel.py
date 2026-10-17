"""UI panel for the Interactive Pin-to-Pin Wiring Guide, 1-Click Wokwi Simulation, and Auto-Generated Firmware."""
import streamlit as st
from core import firmware, wiring

def render(state, parts, project_label="Project Build"):
    """Draw the Interactive Pin-to-Pin Wiring Guide, Wokwi Simulation, and Starter Firmware studio."""
    if not parts:
        return

    # Convert parts to dictionary if passed as list
    parts_dict = parts if isinstance(parts, dict) else {p.get("role", f"part_{i}"): p for i, p in enumerate(parts)}

    # Generate wiring, Wokwi diagram, and firmware
    data = wiring.generate_wiring(parts_dict, project_label=project_label)
    ctrl = data["controller"]
    conns = data["connections"]

    # Generate complete C++ and MicroPython firmware
    ard_fw = firmware.generate_arduino_firmware(parts_dict, conns, ctrl, project_label)
    mpy_fw = firmware.generate_micropython_firmware(parts_dict, conns, ctrl, project_label)

    st.markdown("---")
    st.markdown("""
<div style="display:flex;align-items:center;gap:12px;margin:1.2rem 0 0.4rem">
  <div style="background:linear-gradient(135deg,#7C3AED,#06B6D4);border-radius:10px;width:34px;height:34px;
              display:flex;align-items:center;justify-content:center;font-size:18px;box-shadow:0 2px 10px rgba(124,58,237,.35)">⚡</div>
  <div>
    <h3 style="margin:0;font-size:1.25rem;font-weight:700;color:#F1F5F9;letter-spacing:-0.01em">
      Hardware Wiring, Wokwi Simulator &amp; Starter Firmware
    </h3>
    <p style="margin:0;color:#64748B;font-size:0.78rem;font-weight:500">
      Verified physical pinouts, color-coded power rails, 1-click cloud simulation, and compilable code
    </p>
  </div>
</div>
""", unsafe_allow_html=True)

    tab_visual, tab_table, tab_wokwi, tab_code = st.tabs([
        "🎨 Visual Schematic",
        "📋 Pinout Table",
        "🚀 1-Click Wokwi Simulation",
        "💻 Auto-Generated Firmware"
    ])

    # ---------------- TAB 1: VISUAL SCHEMATIC ----------------
    with tab_visual:
        st.caption(f"Hardware schematic for **{project_label}** using **{ctrl['name']}** ({ctrl['logic_v']}V logic).")
        
        # Color legend pill bar
        st.markdown("""
<div style="display:flex;flex-wrap:wrap;gap:8px;margin-bottom:14px;font-size:11px;font-weight:600">
  <span style="background:#EF4444;color:#fff;padding:2px 10px;border-radius:99px">🔴 5V Power</span>
  <span style="background:#F59E0B;color:#fff;padding:2px 10px;border-radius:99px">🟠 3.3V Power</span>
  <span style="background:#DC2626;color:#fff;padding:2px 10px;border-radius:99px">🛑 Battery (+)</span>
  <span style="background:#1E293B;color:#94A3B8;border:1px solid #475569;padding:2px 10px;border-radius:99px">⚫ Common GND</span>
  <span style="background:#10B981;color:#fff;padding:2px 10px;border-radius:99px">🟢 I2C SDA</span>
  <span style="background:#06B6D4;color:#fff;padding:2px 10px;border-radius:99px">🔵 I2C SCL</span>
  <span style="background:#3B82F6;color:#fff;padding:2px 10px;border-radius:99px">🔷 PWM Speed</span>
  <span style="background:#F97316;color:#fff;padding:2px 10px;border-radius:99px">🔶 Digital I/O</span>
</div>
""", unsafe_allow_html=True)

        st.markdown(data["svg_canvas"], unsafe_allow_html=True)

        with st.expander("Show Mermaid Block Flowchart", expanded=False):
            st.markdown(f"```mermaid\n{data['mermaid_code']}\n```")

    # ---------------- TAB 2: PINOUT TABLE ----------------
    with tab_table:
        st.caption("Complete point-to-point physical connection list:")
        
        table_rows = []
        for c in conns:
            table_rows.append({
                "From Component": c["from_part"],
                "From Pin": c["from_pin"],
                "Target Component": c["to_part"],
                "Target Pin": c["to_pin"],
                "Signal Type": c["type"],
                "Wiring Note": c["note"]
            })
        st.dataframe(table_rows, use_container_width=True, hide_index=True)

    # ---------------- TAB 3: 1-CLICK WOKWI SIMULATION ----------------
    with tab_wokwi:
        with st.container(border=True):
            st.markdown("""
<div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:16px;margin-bottom:12px">
  <div>
    <h4 style="margin:0 0 4px;font-size:1.05rem;font-weight:700;color:#F8FAFC">Simulate on Wokwi</h4>
    <p style="margin:0;color:#94A3B8;font-size:0.82rem">
      Test your circuit and firmware in the cloud simulator before purchasing physical hardware.
    </p>
  </div>
  <div>
    <a href="https://wokwi.com" target="_blank" style="text-decoration:none">
      <div style="background:linear-gradient(135deg,#06B6D4,#0891B2);color:#fff;font-weight:700;
                  font-size:0.85rem;padding:8px 18px;border-radius:10px;box-shadow:0 4px 14px rgba(6,182,212,.35)">
        Open Wokwi.com ↗
      </div>
    </a>
  </div>
</div>
""", unsafe_allow_html=True)

            col1, col2 = st.columns(2)
            with col1:
                st.download_button(
                    label="📥 Download diagram.json (Wokwi Circuit)",
                    data=data["wokwi_json_str"],
                    file_name="diagram.json",
                    mime="application/json",
                    use_container_width=True
                )
            with col2:
                st.download_button(
                    label="📥 Download sketch.ino (Starter Firmware)",
                    data=ard_fw["code"],
                    file_name="sketch.ino",
                    mime="text/plain",
                    use_container_width=True
                )

            st.markdown("""
##### ⚡ How to run the simulation:
1. Click **Open Wokwi.com ↗** above and create a new **Arduino Nano** or **ESP32** project.
2. In Wokwi's editor, click the **`diagram.json`** tab and paste the JSON below (or upload the downloaded file).
3. In the **`sketch.ino`** tab, paste the generated starter firmware.
4. Press the **Play (▶)** button to simulate your sensors, motors, and displays!
""")

            with st.expander("Preview Wokwi diagram.json", expanded=False):
                st.code(data["wokwi_json_str"], language="json")

    # ---------------- TAB 4: AUTO-GENERATED FIRMWARE STUDIO ----------------
    with tab_code:
        st.caption("Complete, compilable firmware boilerplate with pin assignments matching the wiring map, library includes, and Power-On Self-Test (POST).")

        lang_col, download_col = st.columns([2, 1])
        lang = lang_col.radio("Language / Framework", ["Arduino C++ (.ino)", "MicroPython (main.py)"], horizontal=True, key="fw_lang_select")

        # Hardware Self-Test Checklist Card
        st.markdown("""
<div style="background:rgba(15,23,42,0.8);border:1px solid rgba(124,58,237,0.3);border-radius:12px;padding:12px 16px;margin:8px 0 16px">
  <div style="font-size:12px;font-weight:700;color:#A5B4FC;text-transform:uppercase;letter-spacing:0.06em;margin-bottom:6px">
    ⚡ Built-In Power-On Self-Test (POST) in setup()
  </div>
  <div style="font-size:12.5px;color:#CBD5E1;line-height:1.6">
    ✔ <b>Status LED:</b> Double-blinks onboard LED on boot to confirm clock and power.<br>
    ✔ <b>Motor Drive Pulse:</b> Spins DC motors forward for 1.0 second at 40% duty cycle, then brakes.<br>
    ✔ <b>Sensor Telemetry:</b> Pings sensors (ultrasonic / line array / DHT) and prints readings over Serial.<br>
    ✔ <b>Display Check:</b> Writes initialization banner to OLED / LCD screens.
  </div>
</div>
""", unsafe_allow_html=True)

        if "Arduino" in lang:
            if ard_fw["libraries"]:
                st.markdown(f"**Required Arduino Libraries:** " + ", ".join(f"`{lib}`" for lib in ard_fw["libraries"]))
                st.caption("Install via Arduino IDE: **Tools ➔ Manage Libraries...**")
            
            with download_col:
                st.download_button(
                    label="📥 Download sketch.ino",
                    data=ard_fw["code"],
                    file_name=f"{ctrl['id']}_{project_label.lower().replace(' ', '_')}.ino",
                    mime="text/plain",
                    use_container_width=True
                )
            st.code(ard_fw["code"], language="cpp")

        else:
            if mpy_fw["libraries"]:
                st.markdown(f"**MicroPython Modules:** " + ", ".join(f"`{lib}`" for lib in mpy_fw["libraries"]))
                st.caption("Standard built-in modules `machine`, `time`, `sys` are used.")
            
            with download_col:
                st.download_button(
                    label="📥 Download main.py",
                    data=mpy_fw["code"],
                    file_name="main.py",
                    mime="text/plain",
                    use_container_width=True
                )
            st.code(mpy_fw["code"], language="python")
