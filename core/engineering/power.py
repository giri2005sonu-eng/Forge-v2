"""Power budget and battery discharge analysis module."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .selector import Build


@dataclass
class PowerAnalysis:
    controller_current_ma: float
    sensor_current_ma: float
    motor_qty: int
    motor_stall_current_per_motor_a: float
    motor_typical_current_per_motor_a: float
    system_idle_current_a: float
    system_typical_current_a: float
    system_peak_stall_current_a: float
    battery_capacity_mah: float
    battery_usable_mah: float
    battery_max_discharge_a: float
    battery_safety_margin_pct: float
    runtime_idle_h: float
    runtime_typical_h: float
    runtime_stall_min: float
    driver_voltage_drop_v: float
    driver_thermal_loss_w: float
    thermal_warning: Optional[str] = None


def analyze_power(build: Build, config: dict) -> Optional[PowerAnalysis]:
    ctrl = build.parts.get("controller")
    drv = build.parts.get("driver")
    mot = build.parts.get("motor")
    bat = build.parts.get("battery")
    sens = build.parts.get("sensor")

    if not (ctrl and drv and mot and bat):
        return None

    assumptions = config.get("assumptions", {})
    load_frac = float(assumptions.get("avg_load_fraction", 0.4))
    usable_frac = float(assumptions.get("battery_usable_fraction", 0.8))

    ctrl_a = float(ctrl.spec_value("current_a") or 0.05)
    sens_a = float(sens.spec_value("current_a") or 0.02) if sens else 0.0
    sens_qty = build.qty.get("sensor", 1)
    total_sens_a = sens_a * sens_qty

    motor_qty = build.qty.get("motor", 2)
    stall_a = float(mot.spec_value("stall_current_a") or 1.0)
    typical_motor_a = stall_a * load_frac

    idle_a = ctrl_a + total_sens_a + (0.1 * motor_qty)  # slight no-load motor bias
    typical_a = ctrl_a + total_sens_a + (typical_motor_a * motor_qty)
    peak_a = ctrl_a + total_sens_a + (stall_a * motor_qty)

    cap_mah = float(bat.spec_value("capacity_mah") or 2000.0)
    usable_mah = cap_mah * usable_frac
    bat_max_a = float(bat.spec_value("max_discharge_current_a") or 3.0)

    # Battery safety margin
    if bat_max_a > 0:
        margin_pct = max(0.0, (bat_max_a - peak_a) / bat_max_a * 100.0)
    else:
        margin_pct = 0.0

    # Runtimes
    runtime_idle_h = (usable_mah / 1000.0) / idle_a if idle_a > 0 else 0.0
    runtime_typical_h = (usable_mah / 1000.0) / typical_a if typical_a > 0 else 0.0
    runtime_stall_min = ((usable_mah / 1000.0) / peak_a * 60.0) if peak_a > 0 else 0.0

    # Driver thermal dissipation
    v_drop = float(drv.spec_value("voltage_drop_v") or 0.5)
    thermal_w = v_drop * (typical_motor_a * motor_qty)
    thermal_warning = None
    if thermal_w > 1.5:
        thermal_warning = f"High driver power dissipation ({thermal_w:.1f} W). Ensure a heatsink is attached to {drv.name}."

    return PowerAnalysis(
        controller_current_ma=ctrl_a * 1000.0,
        sensor_current_ma=total_sens_a * 1000.0,
        motor_qty=motor_qty,
        motor_stall_current_per_motor_a=stall_a,
        motor_typical_current_per_motor_a=typical_motor_a,
        system_idle_current_a=idle_a,
        system_typical_current_a=typical_a,
        system_peak_stall_current_a=peak_a,
        battery_capacity_mah=cap_mah,
        battery_usable_mah=usable_mah,
        battery_max_discharge_a=bat_max_a,
        battery_safety_margin_pct=margin_pct,
        runtime_idle_h=runtime_idle_h,
        runtime_typical_h=runtime_typical_h,
        runtime_stall_min=runtime_stall_min,
        driver_voltage_drop_v=v_drop,
        driver_thermal_loss_w=thermal_w,
        thermal_warning=thermal_warning,
    )
