"""Build project-specific engineering reports with evidence-aware TinyFish sourcing."""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any, Callable

from .schemas import Part
from .sourcing import check_prices, find_sources
from .tinyfish import TinyFishClient


PROJECTS: dict[str, dict[str, Any]] = {
    "mobile-robot": {
        "name": "Autonomous mobile robot",
        "focus": "Line following, obstacle avoidance, or indoor patrol",
        "components": [
            ("controller", "ESP32 DevKit controller", 1, "3.3 V logic; enough PWM and digital I/O for two motors and sensors", "ESP32 DevKit V1 development board buy India"),
            ("driver", "Dual H-bridge motor driver", 1, "Two channels; choose continuous current above motor running current", "TB6612FNG dual H bridge motor driver module buy India"),
            ("motor", "Low-voltage geared DC motor", 2, "Matched pair; select gear ratio for target speed and wheel size", "TT BO 6V geared DC motor 100 RPM buy India"),
            ("sensor", "Line or distance sensor module", 1, "Select the sensor matching the chosen first mission", "robot line tracking sensor array or HC-SR04 distance sensor buy India"),
            ("battery", "Protected rechargeable battery pack", 1, "Voltage and discharge current must suit both controller and motor driver", "2S 7.4V 18650 battery pack BMS buy India"),
            ("chassis", "Two-wheel-drive chassis kit", 1, "Match motor bracket type; include wheels, caster, and mounting deck", "2WD robot chassis kit TT BO motor wheels caster buy India"),
        ],
        "wiring": [
            ("Battery pack", "Motor driver", "Motor supply + and GND", "Add an inline fuse and master switch; size conductors for stall current."),
            ("Motor driver", "Left and right motors", "Two H-bridge outputs", "Keep motor leads short and verify polarity before mounting wheels."),
            ("Controller", "Motor driver", "PWM, direction, standby, and common GND", "Check controller logic voltage against driver input thresholds."),
            ("Controller", "Line / distance sensor", "3.3 V or 5 V, GND, and signal pins", "Confirm sensor output voltage is safe for the selected GPIO."),
        ],
        "chassis": {"structure": "2WD base plate with two geared motors, a caster, and a top electronics deck", "recommendation": "Use a kit chassis for the first prototype; reserve space for battery access, sensor sightlines, cable strain relief, and the center of gravity.", "cad_deliverables": ["Top-deck hole pattern", "Sensor bracket", "Battery restraint", "Cable-clearance check"]},
    },
    "iot-system": {
        "name": "Smart environment monitor",
        "focus": "Room conditions, energy use, or equipment monitoring",
        "components": [
            ("controller", "ESP32 Wi-Fi/Bluetooth controller", 1, "3.3 V logic; choose GPIO and connectivity for the selected sensors", "ESP32 DevKit WiFi Bluetooth development board buy India"),
            ("sensor", "Environmental sensor module", 1, "Choose a calibrated range and interface (I2C, SPI, or UART) for the variable measured", "DHT22 SHT31 temperature humidity sensor module buy India"),
            ("sensor", "Optional current or air-quality sensor", 1, "Include only if required by the selected mission; verify isolation and measurement range", "INA219 current sensor module or air quality sensor module buy India"),
            ("battery", "USB supply or protected battery pack", 1, "Use a regulated 5 V supply or a protected cell with a compatible regulator", "5V USB power supply or protected 18650 battery module buy India"),
            ("chassis", "Sensor enclosure and mounting hardware", 1, "Allow airflow to environmental sensors; protect terminals from accidental contact", "electronics project enclosure ABS box IP rated sensor enclosure buy India"),
        ],
        "wiring": [
            ("Regulated supply", "ESP32 controller", "5 V input and common GND", "Use a regulated supply with adequate current margin for radio transmit peaks."),
            ("ESP32 controller", "Environmental sensor", "I2C / SPI / UART, supply, and GND", "Confirm bus voltage, pull-ups, pin mapping, and cable length."),
            ("ESP32 controller", "Optional measurement sensor", "I2C or analog signal", "Use isolation and appropriate dividers for mains or higher-voltage measurements."),
        ],
        "chassis": {"structure": "Ventilated electronics enclosure with wall, desk, or equipment mounting", "recommendation": "Keep temperature and humidity sensing exposed to representative airflow while covering the PCB and power terminals. Do not enclose a heat source with the sensor.", "cad_deliverables": ["Enclosure outline", "Sensor vent pattern", "PCB standoff locations", "Cable-entry strain relief"]},
    },
    "vision-robot": {
        "name": "Edge-vision inspection rover",
        "focus": "Object detection, visual tracking, or surface inspection",
        "components": [
            ("controller", "Single-board computer", 1, "Select RAM, camera interface, and power budget for the vision workload", "Raspberry Pi 4 4GB single board computer buy India"),
            ("sensor", "Camera module", 1, "Match connector/interface and field of view to the inspection distance", "Raspberry Pi camera module autofocus buy India"),
            ("driver", "Dual-channel motor driver", 1, "Continuous and stall current ratings must suit the selected motors", "TB6612FNG dual motor driver module buy India"),
            ("motor", "Matched geared DC motors", 2, "Select reduction and encoder feedback based on speed and localization needs", "N20 metal gear motor encoder buy India"),
            ("battery", "Protected battery pack and regulated rails", 1, "Budget separate regulated rails for compute and motors; verify peak current", "2S 7.4V 18650 battery pack BMS 5V regulator buy India"),
            ("chassis", "Two-wheel rover chassis with camera mast", 1, "Keep the camera rigid, vibration-aware, and clear of wheel occlusion", "2WD robot rover chassis camera mount buy India"),
        ],
        "wiring": [
            ("Battery pack", "Motor driver", "Motor supply through fuse and switch", "Keep motor supply return currents away from camera/compute ground paths where practical."),
            ("Regulated compute rail", "Single-board computer", "Regulated 5 V supply and GND", "Size for board and camera peaks; do not power compute from a motor-driver logic output."),
            ("Camera module", "Single-board computer", "CSI / USB camera interface", "Secure the ribbon/cable and validate camera orientation before finalizing the mast."),
            ("Computer GPIO / MCU", "Motor driver", "Direction and PWM control", "Use a level-compatible interface; add a dedicated controller if real-time motor control requires it."),
        ],
        "chassis": {"structure": "2WD rover deck with a rigid camera mast and isolated compute/battery mounts", "recommendation": "Keep the camera above wheel spray and away from vibration. Place the battery low and centered; leave access to the storage card, cooling path, and wiring.", "cad_deliverables": ["Camera mast with tilt adjustment", "Compute-board standoffs", "Battery restraint", "Wheel and sensor clearance"]},
    },
    "assistive-device": {
        "name": "Assistive mobility or gesture aid",
        "focus": "Gesture-controlled aid, smart cane, or posture feedback",
        "components": [
            ("controller", "Low-power ESP32 controller", 1, "3.3 V logic; sleep/wake support and adequate sensor interfaces", "ESP32 low power development board BLE buy India"),
            ("sensor", "IMU or gesture sensor", 1, "Choose range, noise, mounting orientation, and calibration method for the use case", "MPU6050 IMU accelerometer gyroscope module buy India"),
            ("sensor", "Proximity or ranging sensor", 1, "Set a safe detection range and verify outdoor/ambient-light performance", "VL53L0X time of flight distance sensor module buy India"),
            ("motor", "Haptic feedback actuator", 1, "Use a driver transistor if actuator current exceeds GPIO limits", "coin vibration motor 3V haptic actuator module buy India"),
            ("battery", "Protected rechargeable battery", 1, "Use protected cells and an accessible charge/status indication", "protected 3.7V lithium battery pack charger module buy India"),
            ("chassis", "Wearable or cane-mount enclosure", 1, "Rounded edges, secure mounting, washable surfaces, and accessible controls", "wearable electronics enclosure project case ABS buy India"),
        ],
        "wiring": [
            ("Protected battery", "Controller and regulator", "Regulated supply and common GND", "Provide charge protection and a physical power disconnect."),
            ("Controller", "IMU / ranging sensor", "I2C or digital signals", "Mount orientation must match firmware axes; validate sensor limits on a bench."),
            ("Controller", "Haptic actuator", "GPIO through a transistor/driver stage", "Do not drive a vibration motor directly from a GPIO; include flyback protection as required."),
        ],
        "chassis": {"structure": "Small wearable enclosure or cane-mounted sensor pod; not a load-bearing mobility structure", "recommendation": "Keep the enclosure lightweight, rounded, and securely retained. Any structure supporting a person must use a separately engineered, rated frame and supervised safety review.", "cad_deliverables": ["Enclosure and strap/mount interface", "Sensor field-of-view keep-out", "Battery access cover", "Rounded-edge check"]},
    },
    "uav-platform": {
        "name": "UAV telemetry and navigation",
        "focus": "Flight telemetry, waypoint navigation, or payload sensing",
        "components": [
            ("controller", "Flight controller", 1, "Select a supported firmware ecosystem and sensor set; verify power and failsafe inputs", "Pixhawk flight controller autopilot buy India"),
            ("sensor", "GPS and compass module", 1, "Mount away from high-current wiring and electromagnetic interference", "M8N GPS compass module UAV buy India"),
            ("driver", "Electronic speed controllers", 4, "Match motor KV, battery cell count, and current with margin", "30A BLHeli ESC electronic speed controller buy India"),
            ("motor", "Brushless propulsion motor", 4, "Match thrust requirements, propeller, ESC, and battery voltage", "2212 brushless outrunner motor UAV buy India"),
            ("battery", "LiPo propulsion battery", 1, "Choose cell count and discharge rating from measured current; use a balance charger", "3S LiPo battery UAV 2200mAh buy India"),
            ("chassis", "Quadcopter frame", 1, "Arm length and propeller clearance must suit the motor/propeller combination", "450mm quadcopter frame kit buy India"),
        ],
        "wiring": [
            ("Flight battery", "Power distribution / ESCs", "High-current battery bus", "Use a correctly rated distribution board, connectors, and battery restraint."),
            ("ESC signal leads", "Flight controller outputs", "PWM / DShot signal and signal ground", "Follow the flight-controller pin map and check motor order with propellers removed."),
            ("GPS/compass", "Flight controller", "UART plus I2C or integrated bus", "Mount away from ESC and battery power leads; calibrate before flight."),
        ],
        "chassis": {"structure": "Four-arm frame with matched motors, propeller clearance, and protected flight-controller stack", "recommendation": "Use a proven off-the-shelf frame for the first flight-capable prototype. Custom frame geometry requires structural, vibration, and propeller-clearance analysis before flight.", "cad_deliverables": ["Arm and motor pattern", "Propeller swept-volume envelope", "Stack/standoff layout", "Battery and GPS placement"]},
    },
    "ev-power": {
        "name": "EV battery and motor test bench",
        "focus": "Battery monitoring, motor control, or regenerative braking demo",
        "components": [
            ("controller", "Microcontroller development board", 1, "Choose ADC/timer capability, isolation needs, and safe low-voltage interfaces", "STM32 development board Nucleo buy India"),
            ("sensor", "Current and voltage sensor", 1, "Measurement range and isolation must exceed the planned test envelope", "INA219 current voltage sensor module buy India"),
            ("driver", "Low-voltage motor driver", 1, "Select a protected driver with current limit and thermal headroom", "BTS7960 motor driver module buy India"),
            ("motor", "Low-voltage DC motor", 1, "Use a guarded motor sized for a bench demonstration, not vehicle propulsion", "12V DC geared motor low voltage buy India"),
            ("battery", "Current-limited low-voltage supply", 1, "Begin with a current-limited bench supply; batteries require fusing and supervision", "12V current limited bench power supply buy India"),
            ("chassis", "Guarded electrical test-bench plate", 1, "Nonconductive standoffs, fuse cover, cable restraint, and motor guard", "non conductive electronics project enclosure test bench plate buy India"),
        ],
        "wiring": [
            ("Current-limited supply", "Fuse and emergency disconnect", "Protected low-voltage supply path", "Set a conservative current limit and keep an accessible disconnect in series."),
            ("Fuse / disconnect", "Motor driver", "Motor bus and return", "Never bypass current protection; confirm polarity and thermal limits."),
            ("Sensor module", "Controller", "ADC / I2C signal and reference ground", "Use isolation or differential sensing where the common-mode voltage requires it."),
            ("Controller", "Motor driver", "Logic/PWM control", "Validate logic levels and driver enable defaults before connecting the motor."),
        ],
        "chassis": {"structure": "Guarded, nonconductive bench plate with separated power, control, and rotating-motor zones", "recommendation": "Provide a fuse cover, emergency disconnect, motor guard, insulated standoffs, and clear measurement points. Do not use this concept for traction/high-voltage EV packs.", "cad_deliverables": ["Guard and fastener pattern", "Insulated standoff layout", "Fuse/disconnect access", "Cable and rotating-part keep-outs"]},
    },
}


ANSWER_LABELS = {
    "mission": {"line": "Follow a line / marked path", "avoid": "Avoid obstacles", "patrol": "Patrol or monitor an indoor area", "delivery": "Carry a small item between points", "climate": "Monitor temperature and humidity", "energy": "Track energy or power use", "equipment": "Monitor a machine or storage area", "alert": "Build a sensor-based alert system", "detect": "Detect and classify objects", "track": "Track a moving object", "inspect": "Inspect a surface or product", "navigate": "Navigate using visual landmarks", "gesture": "Gesture-controlled assistance", "mobility": "Mobility or obstacle alerts", "posture": "Posture or movement feedback", "wearable": "Wearable health or activity sensing", "telemetry": "Collect flight and sensor telemetry", "waypoint": "Navigate between waypoints", "mapping": "Map or inspect an area", "payload": "Carry a lightweight sensor payload", "battery": "Monitor battery voltage and current", "motor": "Control a low-voltage motor", "thermal": "Measure temperature and thermal behavior", "regen": "Demonstrate regenerative braking concepts"},
    "environment": {"indoor": "Indoor, clean and level", "outdoor": "Outdoor, mostly level", "rough": "Uneven, dusty, or wet", "industrial": "Near machinery or electrical equipment"},
    "target": {"runtime": "Maximize operating time", "accuracy": "Repeatable path tracking", "speed": "Higher travel speed", "payload": "Carry a useful payload", "uptime": "Long unattended uptime", "response": "Fast alerts", "cost": "Lowest practical cost", "realtime": "Real-time frame rate", "lighting": "Work across changing light", "reliability": "Reliable alerts with few false triggers", "comfort": "Low weight and comfort", "flighttime": "Longer flight time", "range": "Greater communication range", "stability": "Stable autonomous flight", "voltage": "Accurate voltage measurements", "current": "Accurate current measurements", "control": "Precise motor control"},
    "sizeLoad": {"compact": "Compact and lightweight", "small-load": "Carry up to about 500 g", "medium-load": "Carry about 0.5–2 kg", "larger": "Larger payload or bench-mounted system"},
    "budget": {"low": "Under ₹5,000", "mid": "₹5,000–₹15,000", "high": "₹15,000–₹40,000", "very-high": "Above ₹40,000"},
    "fabrication": {"kit": "Use an off-the-shelf kit / enclosure", "hand": "Hand tools and basic workshop", "laser": "Laser-cut plates or sheet material", "3d": "CAD and 3D printing"},
    "power": {"battery": "Rechargeable battery", "mains": "Mains adapter / bench supply", "solar": "Solar-assisted power", "host": "Powered by an existing system"}
};


def _project_requirements(project_answers: dict[str, str | None], survey_answers: dict[str, str | None]) -> list[dict[str, str]]:
    return [{"key": key, "label": label, "value": ANSWER_LABELS.get(key, {}).get(value, "Not specified") if value else "Not specified"}
            for key, label in (("mission", "Primary mission"), ("environment", "Operating environment"),
                               ("target", "Success criterion"), ("sizeLoad", "Size / load envelope"),
                               ("budget", "Parts budget"), ("fabrication", "Fabrication access"), ("power", "Power source"))
            for value in [project_answers.get(key) or (survey_answers.get("budget") if key == "budget" else None)]]


def _cad_guidance(project_id: str, project_answers: dict[str, str | None], base: dict[str, Any]) -> dict[str, Any]:
    fabrication = project_answers.get("fabrication")
    cad_needed = fabrication in {"laser", "3d"} or project_id == "uav-platform" and fabrication != "kit"
    if fabrication == "3d":
        material = "CAD-designed printed brackets/enclosure; use a suitable material and verify heat/impact limits."
    elif fabrication == "laser":
        material = "Laser-cut sheet or acrylic panels with standard fasteners and standoffs."
    elif fabrication == "hand":
        material = "Off-the-shelf plate/enclosure with hand-drilled mounting only where necessary."
    else:
        material = "Off-the-shelf kit or enclosure; adapt with simple brackets if needed."
    if cad_needed:
        cad_reason = "Custom fabrication was selected; dimensioned CAD is needed to make and check the parts."
    elif project_id == "uav-platform":
        cad_reason = "An off-the-shelf frame avoids custom airframe validation; model only payload mounts if needed."
    else:
        cad_reason = "A standard kit/enclosure can be used without custom CAD; a mounting sketch is still recommended."
    environment = ANSWER_LABELS["environment"].get(project_answers.get("environment"), "the selected environment")
    recommendation = f"{base['recommendation']} Selected operating environment: {environment}."
    if project_answers.get("sizeLoad") in {"medium-load", "larger"}:
        recommendation += " Recheck payload, center of gravity, fasteners, and motor/structure ratings before build."
    return {"structure": base["structure"], "recommendation": recommendation, "material": material,
            "cad_needed": cad_needed, "cad_reason": cad_reason, "cad_deliverables": base["cad_deliverables"]}


def _markdown_report(report: dict[str, Any]) -> str:
    lines = [f"# Engineering Project Report: {report['project']['name']}", "", f"**Generated:** {report['generated_at']}",
             f"**Live sourcing:** {report['sourcing']['status']} — {report['sourcing']['message']}", "", "## Project specifications"]
    lines.extend(f"- **{item['label']}:** {item['value']}" for item in report["requirements"])
    lines.extend(["", "## Bill of materials", "", "| Category | Planned component | Qty | Design requirement | Verified unit price | Verified line total | Stock |",
                  "|---|---|---:|---|---:|---:|---|"])
    for row in report["bom"]:
        unit = f"INR {row['unit_price']:,.2f}" if row["unit_price"] is not None else "TBD"
        total = f"INR {row['line_total']:,.2f}" if row["line_total"] is not None else "TBD"
        stock = "In stock" if row["in_stock"] is True else "Out of stock" if row["in_stock"] is False else "Unknown"
        lines.append(f"| {row['category']} | {row['name']} | {row['qty']} | {row['requirements']} | {unit} | {total} | {stock} |")
        for source in row["sources"]:
            price = f"INR {source['price']:,.2f}" if source["price"] is not None else "unverified price"
            lines.append(f"  - [{source['vendor']}]({source['url']}) — {price}; {source['method'] or 'no quote'}")
            if source["quote"]:
                lines.append(f"    - Page quote: “{source['quote']}”")
    if report["verified_total_inr"] is not None:
        lines.extend(["", f"**Verified-price subtotal (partial if any TBD rows):** INR {report['verified_total_inr']:,.2f}"])
    lines.extend(["", "## Wiring plan", f"_{report['wiring']['note']}_", "", "| From | To | Connection | Implementation note |", "|---|---|---|---|"])
    lines.extend(f"| {row['from']} | {row['to']} | {row['signal']} | {row['notes']} |" for row in report["wiring"]["connections"])
    chassis = report["chassis"]
    lines.extend(["", "## Chassis and CAD", f"- **Structure:** {chassis['structure']}", f"- **Recommendation:** {chassis['recommendation']}",
                  f"- **Material/fabrication:** {chassis['material']}", f"- **CAD needed:** {'Yes' if chassis['cad_needed'] else 'Optional'} — {chassis['cad_reason']}",
                  f"- **CAD deliverables:** {', '.join(chassis['cad_deliverables'])}", "", "## Sourcing and verification"])
    lines.extend(f"- {warning}" for warning in report["warnings"])
    lines.extend(["", "Prices are included only when TinyFish-fetched page text contained a matching, quote-verifiable price. Confirm stock, shipping, datasheets, electrical ratings, and safety before purchase or powering hardware."])
    return "\n".join(lines)


def generate_project_report(project_id: str, project_answers: dict[str, str | None], survey_answers: dict[str, str | None],
                            tinyfish: TinyFishClient | None, llm_json: Callable[[str, str], dict] | None,
                            spec_defs: dict, allowed_domains: list[str]) -> dict[str, Any]:
    """Create a project-specific BOM and evidence report; never invent component prices."""
    project = PROJECTS[project_id]
    bom: list[dict[str, Any]] = []
    live_search_count = 0
    verified_price_count = 0
    warnings: list[str] = []

    for index, (category, name, qty, requirements, search_query) in enumerate(project["components"]):
        combined_query = f"{search_query} {project_answers.get('environment') or ''} India".strip()
        part_id = "project_" + hashlib.sha1(f"{project_id}|{index}|{combined_query}".encode()).hexdigest()[:16]
        part = Part(id=part_id, category=category, name=name, search_query=combined_query)
        sources: list[dict[str, Any]] = []
        unit_price = None
        vendor = "TBD"
        price_quote = None
        in_stock = None
        if tinyfish is not None:
            try:
                source_result = find_sources(part, tinyfish, allowed_domains, target=2, max_queries=2)
                live_links = [link for link in source_result["links"] if link["source"] == "tinyfish_search"][:2]
                live_search_count += len(live_links)
                prices = {}
                if live_links:
                    price_result = check_prices(part, [link["url"] for link in live_links], tinyfish, llm_json, spec_defs)
                    prices = price_result.get("prices", {})
                for link in source_result["links"][:3]:
                    checked = prices.get(link["url"], {})
                    matches = checked.get("matches") is not False
                    quote_price = checked.get("price") if matches else None
                    sources.append({"url": link["url"], "vendor": link.get("vendor") or link.get("domain") or "Vendor",
                                    "domain": link.get("domain", ""), "title": checked.get("product") or link.get("title", ""),
                                    "source_type": link.get("source", "fallback_search_page"), "price": quote_price,
                                    "in_stock": checked.get("in_stock") if matches else None,
                                    "quote": checked.get("quote") if quote_price is not None else None,
                                    "method": checked.get("method") if quote_price is not None else None,
                                    "error": checked.get("error") if quote_price is None else None})
                verified = [source for source in sources if source["price"] is not None]
                if verified:
                    best = min(verified, key=lambda source: source["price"])
                    unit_price = float(best["price"])
                    vendor = best["vendor"]
                    price_quote = best["quote"]
                    in_stock = best["in_stock"]
                    verified_price_count += 1
            except Exception as error:
                warnings.append(f"{name}: TinyFish sourcing failed ({str(error)[:180]}). Price left TBD.")
        bom.append({"category": category.title(), "name": name, "qty": qty, "requirements": requirements,
                    "unit_price": unit_price, "line_total": unit_price * qty if unit_price is not None else None,
                    "vendor": vendor, "quote": price_quote, "in_stock": in_stock, "sources": sources})

    total = sum(row["line_total"] or 0 for row in bom) if verified_price_count else None
    if tinyfish is None:
        sourcing_status = "unavailable"
        source_message = "TinyFish is not configured. No live seller results were requested; prices remain TBD. Configure a TinyFish API key and generate the report again."
    elif verified_price_count == len(bom):
        sourcing_status = "live"
        source_message = f"TinyFish search and quote checks verified prices for all {verified_price_count} BOM lines."
    elif live_search_count:
        sourcing_status = "partial"
        source_message = f"TinyFish returned {live_search_count} live seller links and verified {verified_price_count} of {len(bom)} BOM prices. Unverified prices remain TBD."
    else:
        sourcing_status = "unavailable"
        source_message = "TinyFish was configured but returned no usable product links. Prices remain TBD."
    if verified_price_count < len(bom):
        warnings.append(f"Only {verified_price_count} of {len(bom)} BOM rows have quote-verified live prices; the rest are TBD.")
    if any(row["in_stock"] is False for item in bom for row in item["sources"]):
        warnings.append("At least one live source reported an item out of stock; choose an available alternative before procurement.")
    if any(row["unit_price"] is not None and row["in_stock"] is None for row in bom):
        warnings.append("Stock could not be verified for one or more quote-priced BOM lines.")
    if project_id in {"uav-platform", "ev-power", "assistive-device"}:
        warnings.append("This concept has elevated safety needs. Use supervised testing and verify applicable standards before human, flight, battery, or motor trials.")

    cad = _cad_guidance(project_id, project_answers, project["chassis"])
    report = {
        "project": {"id": project_id, "name": project["name"], "focus": project["focus"]},
        "requirements": _project_requirements(project_answers, survey_answers),
        "bom": bom,
        "verified_total_inr": total,
        "sourcing": {"status": sourcing_status, "message": source_message,
                     "live_search_count": live_search_count, "verified_price_count": verified_price_count},
        "wiring": {"note": "Concept-level connections only. Confirm exact pin numbers, polarity, current limits, logic levels, isolation, and datasheets for the final selected parts.",
                   "connections": [{"from": row[0], "to": row[1], "signal": row[2], "notes": row[3]} for row in project["wiring"]]},
        "chassis": cad,
        "warnings": warnings,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    }
    report["markdown"] = _markdown_report(report)
    return report