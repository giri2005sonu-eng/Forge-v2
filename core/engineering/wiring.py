"""Pinout and wiring guide generator for validated robot builds."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .selector import Build


@dataclass
class WireConnection:
    source_component: str
    source_pin: str
    target_component: str
    target_pin: str
    wire_type: str  # "Power", "Ground", "Logic Signal", "PWM", "I2C"
    notes: Optional[str] = None


@dataclass
class WiringPlan:
    connections: list[WireConnection]
    common_ground_required: bool
    warnings: list[str]
    assembly_steps: list[str]
    mermaid_diagram: str


def generate_wiring_plan(build: Build) -> WiringPlan:
    ctrl = build.parts.get("controller")
    drv = build.parts.get("driver")
    mot = build.parts.get("motor")
    bat = build.parts.get("battery")
    sens = build.parts.get("sensor")

    ctrl_id = ctrl.id if ctrl else ""
    drv_id = drv.id if drv else ""
    sens_id = sens.id if sens else ""

    connections: list[WireConnection] = []
    warnings: list[str] = []

    # 1. Power connections
    connections.append(WireConnection(
        source_component=f"Battery ({bat.name if bat else 'Battery'})",
        source_pin="V+ (Positive / Red)",
        target_component=f"Motor Driver ({drv.name if drv else 'Driver'})",
        target_pin="VCC / Motor Power (+)",
        wire_type="Power",
        notes="Heavy gauge wire (20-22 AWG) recommended for motor stall current."
    ))

    connections.append(WireConnection(
        source_component=f"Battery ({bat.name if bat else 'Battery'})",
        source_pin="GND (Negative / Black)",
        target_component=f"Motor Driver ({drv.name if drv else 'Driver'})",
        target_pin="GND (-)",
        wire_type="Ground",
        notes="Main system ground reference."
    ))

    # Controller Vin / power
    ctrl_vin_min = ctrl.spec_value("vin_min_v") if ctrl else 7.0
    bat_nom = bat.spec_value("nominal_v") if bat else 7.4
    if bat_nom and ctrl_vin_min and bat_nom >= ctrl_vin_min:
        connections.append(WireConnection(
            source_component=f"Battery ({bat.name if bat else 'Battery'})",
            source_pin="V+ (Positive)",
            target_component=f"Controller ({ctrl.name if ctrl else 'MCU'})",
            target_pin="VIN",
            wire_type="Power",
            notes="Powers the onboard linear voltage regulator of the controller."
        ))
    else:
        connections.append(WireConnection(
            source_component=f"Motor Driver ({drv.name if drv else 'Driver'})",
            source_pin="5V Output (if enabled by jumper)",
            target_component=f"Controller ({ctrl.name if ctrl else 'MCU'})",
            target_pin="5V / VBUS",
            wire_type="Power",
            notes="Powers controller from 5V regulated rail."
        ))

    # CRITICAL: Common Ground
    connections.append(WireConnection(
        source_component=f"Controller ({ctrl.name if ctrl else 'MCU'})",
        source_pin="GND",
        target_component=f"Motor Driver ({drv.name if drv else 'Driver'})",
        target_pin="GND",
        wire_type="Ground",
        notes="ESSENTIAL: Common ground required for logic level signals to trigger properly."
    ))

    # 2. Driver Control Pins
    is_esp32 = "esp32" in ctrl_id.lower()
    if "l298n" in drv_id.lower():
        p_ena, p_in1, p_in2, p_in3, p_in4, p_enb = (
            ("GPIO 14 (PWM)", "GPIO 27", "GPIO 26", "GPIO 25", "GPIO 33", "GPIO 32 (PWM)")
            if is_esp32 else
            ("Pin D5 (PWM)", "Pin D7", "Pin D8", "Pin D9", "Pin D4", "Pin D6 (PWM)")
        )
        connections.extend([
            WireConnection(ctrl.name, p_ena, drv.name, "ENA (Left Motor Speed)", "PWM", "Remove ENA jumper to enable PWM speed control"),
            WireConnection(ctrl.name, p_in1, drv.name, "IN1 (Left Motor Dir A)", "Logic Signal"),
            WireConnection(ctrl.name, p_in2, drv.name, "IN2 (Left Motor Dir B)", "Logic Signal"),
            WireConnection(ctrl.name, p_in3, drv.name, "IN3 (Right Motor Dir A)", "Logic Signal"),
            WireConnection(ctrl.name, p_in4, drv.name, "IN4 (Right Motor Dir B)", "Logic Signal"),
            WireConnection(ctrl.name, p_enb, drv.name, "ENB (Right Motor Speed)", "PWM", "Remove ENB jumper to enable PWM speed control"),
        ])
    elif "tb6612" in drv_id.lower():
        p_pwma, p_ain1, p_ain2, p_stby, p_bin1, p_bin2, p_pwmb = (
            ("GPIO 14 (PWM)", "GPIO 27", "GPIO 26", "GPIO 13", "GPIO 25", "GPIO 33", "GPIO 32 (PWM)")
            if is_esp32 else
            ("Pin D5 (PWM)", "Pin D7", "Pin D8", "Pin D10", "Pin D9", "Pin D4", "Pin D6 (PWM)")
        )
        connections.extend([
            WireConnection(ctrl.name, p_pwma, drv.name, "PWMA", "PWM"),
            WireConnection(ctrl.name, p_ain1, drv.name, "AIN1", "Logic Signal"),
            WireConnection(ctrl.name, p_ain2, drv.name, "AIN2", "Logic Signal"),
            WireConnection(ctrl.name, p_stby, drv.name, "STBY", "Logic Signal", "Must be pulled HIGH (logic 1) to enable driver"),
            WireConnection(ctrl.name, p_bin1, drv.name, "BIN1", "Logic Signal"),
            WireConnection(ctrl.name, p_bin2, drv.name, "BIN2", "Logic Signal"),
            WireConnection(ctrl.name, p_pwmb, drv.name, "PWMB", "PWM"),
        ])
    else:  # Generic / DRV8833
        p_in1, p_in2, p_in3, p_in4 = (
            ("GPIO 14 (PWM)", "GPIO 27", "GPIO 26 (PWM)", "GPIO 25")
            if is_esp32 else
            ("Pin D5 (PWM)", "Pin D7", "Pin D6 (PWM)", "Pin D8")
        )
        connections.extend([
            WireConnection(ctrl.name, p_in1, drv.name, "IN1 (Motor A)", "PWM"),
            WireConnection(ctrl.name, p_in2, drv.name, "IN2 (Motor A)", "Logic Signal"),
            WireConnection(ctrl.name, p_in3, drv.name, "IN3 (Motor B)", "PWM"),
            WireConnection(ctrl.name, p_in4, drv.name, "IN4 (Motor B)", "Logic Signal"),
        ])

    # Motors to Driver output
    connections.append(WireConnection(
        source_component=f"Motor Driver ({drv.name if drv else 'Driver'})",
        source_pin="OUT1 & OUT2",
        target_component=f"Motor Left ({mot.name if mot else 'Motor 1'})",
        target_pin="Motor Terminals (+ / -)",
        wire_type="Power",
        notes="Reverse wires if motor rotates backward."
    ))
    connections.append(WireConnection(
        source_component=f"Motor Driver ({drv.name if drv else 'Driver'})",
        source_pin="OUT3 & OUT4",
        target_component=f"Motor Right ({mot.name if mot else 'Motor 2'})",
        target_pin="Motor Terminals (+ / -)",
        wire_type="Power",
        notes="Reverse wires if motor rotates backward."
    ))

    # 3. Sensor Wiring
    if sens:
        sens_vcc_pin = "3.3V" if (sens.spec_value("min_supply_v") or 5.0) <= 3.3 and is_esp32 else "5V"
        connections.append(WireConnection(
            source_component=f"Controller ({ctrl.name})",
            source_pin=sens_vcc_pin,
            target_component=f"Sensor ({sens.name})",
            target_pin="VCC",
            wire_type="Power"
        ))
        connections.append(WireConnection(
            source_component=f"Controller ({ctrl.name})",
            source_pin="GND",
            target_component=f"Sensor ({sens.name})",
            target_pin="GND",
            wire_type="Ground"
        ))

        if "hcsr04" in sens_id.lower() or "ultrasonic" in sens.name.lower():
            p_trig, p_echo = ("GPIO 5", "GPIO 18") if is_esp32 else ("Pin D11", "Pin D12")
            connections.append(WireConnection(ctrl.name, p_trig, sens.name, "Trig", "Logic Signal"))
            if is_esp32:
                connections.append(WireConnection(
                    ctrl.name, p_echo, sens.name, "Echo", "Logic Signal",
                    notes="CAUTION: HC-SR04 Echo output is 5V. Use a 1k/2k resistor voltage divider to protect ESP32 3.3V GPIO!"
                ))
                warnings.append("HC-SR04 Echo pin outputs 5V. ESP32 GPIO is 3.3V tolerant only: use a voltage divider (1kΩ/2kΩ).")
            else:
                connections.append(WireConnection(ctrl.name, p_echo, sens.name, "Echo", "Logic Signal"))
        elif "vl53" in sens_id.lower() or "tof" in sens.name.lower():
            p_sda, p_scl = ("GPIO 21 (SDA)", "GPIO 22 (SCL)") if is_esp32 else ("Pin A4 (SDA)", "Pin A5 (SCL)")
            connections.append(WireConnection(ctrl.name, p_sda, sens.name, "SDA", "I2C"))
            connections.append(WireConnection(ctrl.name, p_scl, sens.name, "SCL", "I2C"))
        elif "tcrt5000" in sens_id.lower() or "line" in sens.name.lower():
            channels = int(sens.spec_value("channels") or 5)
            if is_esp32:
                esp_pins = ["GPIO 34", "GPIO 35", "GPIO 36 (VP)", "GPIO 39 (VN)", "GPIO 4"]
                for i in range(min(channels, len(esp_pins))):
                    connections.append(WireConnection(ctrl.name, esp_pins[i], sens.name, f"OUT{i+1}", "Logic Signal"))
            else:
                uno_pins = ["Pin A0", "Pin A1", "Pin A2", "Pin A3", "Pin D2"]
                for i in range(min(channels, len(uno_pins))):
                    connections.append(WireConnection(ctrl.name, uno_pins[i], sens.name, f"OUT{i+1}", "Logic Signal"))

    # Assembly steps
    assembly_steps = [
        "1. Mount motors into the chassis brackets and snap wheels onto the motor shafts.",
        "2. Mount the motor driver, controller, and battery pack securely on the chassis deck.",
        "3. Wire Motor Driver OUT terminals to Left & Right motor lead wires.",
        "4. Wire Battery (+) to Driver VCC (install an SPST power toggle switch in series for safety).",
        "5. Wire Battery (-) to Driver GND, and connect Driver GND to Controller GND (Common Ground).",
        "6. Connect Controller logic/PWM pins to Driver IN/PWM pins as mapped in the table.",
        "7. Connect Sensor VCC, GND, and signal pins to the Controller.",
        "8. Double check with a multimeter that logic voltages match before turning on battery power."
    ]

    # Mermaid diagram string
    mermaid = f"""flowchart TD
    BAT["Battery: {bat.name if bat else 'Pack'}"]
    DRV["Driver: {drv.name if drv else 'Driver'}"]
    CTRL["Controller: {ctrl.name if ctrl else 'MCU'}"]
    SENS["Sensor: {sens.name if sens else 'Sensor'}"]
    ML["Left Motor"]
    MR["Right Motor"]

    BAT -->|"Power (+)"| DRV
    BAT -->|"GND (-)"| DRV
    BAT -.->|"Vin Power"| CTRL
    CTRL <-->|"Common GND"| DRV
    CTRL -->|"Control / PWM"| DRV
    DRV -->|"Motor Drive"| ML
    DRV -->|"Motor Drive"| MR
    CTRL -->|"Power & Signals"| SENS
"""

    return WiringPlan(
        connections=connections,
        common_ground_required=True,
        warnings=warnings,
        assembly_steps=assembly_steps,
        mermaid_diagram=mermaid
    )
