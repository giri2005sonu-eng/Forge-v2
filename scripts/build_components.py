"""Generates data/components.json. Edit THIS file or the JSON directly; then run `python -m core.specification_validator`.
Only values with a field-level evidence entry are marked verified. Everything else is null."""
import json, pathlib
TODAY = "2026-10-17"
NANO_PDF = "https://docs.arduino.cc/resources/datasheets/A000005-datasheet.pdf"
ESP_GUIDE = "https://docs.espressif.com/projects/esp-idf/en/v5.1/esp32/hw-reference/esp32/get-started-devkitc.html"

def S(v, u): return {"value": v, "unit": u}
def ev(field, value, unit, url, title, section, note):
    return dict(field=field, value=value, unit=unit, source_url=url, document_title=title, section=section, retrieved=TODAY, status="verified", note=note)

def rec(id, name, cat, legacy, mfr=None, mpn=None, variant=None, desc="", specs=None, compat=None, evid=None, notes="", mapping="exact", datasheet=None):
    return dict(id=id, legacy_id=legacy, legacy_mapping=mapping, name=name, category=cat, manufacturer=mfr, manufacturer_part_number=mpn,
                model_variant=variant, description=desc, specifications=specs or {}, compatibility=compat or {}, datasheet_url=datasheet,
                specification_sources=evid or [], verification_status="unverified", last_verified=None, notes=notes)

NULL = lambda keys: {k: S(None, u) for k, u in keys.items()}
CTRL = dict(vin_min_v="V", vin_max_v="V", logic_v="V", wifi="bool", bluetooth="bool", supply_nominal_v="V", clock_mhz="MHz")
DRV = dict(supply_min_v="V", supply_max_v="V", continuous_current_a_per_channel="A", channels="count", drop_v="V")
MOT = dict(rated_voltage_min_v="V", rated_voltage_max_v="V", stall_current_a="A", no_load_rpm="rpm", stall_torque_kgcm="kg·cm")
BAT = dict(nominal_v="V", full_charge_v="V", capacity_mah="mAh", max_continuous_discharge_a="A")
SEN = dict(supply_min_v="V", supply_max_v="V", current_ma="mA")

R = []
nano_specs = NULL(CTRL) | dict(
    vin_min_v=S(7, "V"), vin_max_v=S(15, "V"), logic_v=S(5, "V"), clock_mhz=S(16, "MHz"),
    flash_kb=S(32, "kB"), sram_kb=S(2, "kB"), eeprom_kb=S(1, "kB"), digital_io_count=S(20, "count"), analog_inputs=S(8, "count"),
    pwm_channels=S(6, "count"), operating_temp_min_c=S(-40, "°C"), operating_temp_max_c=S(85, "°C"),
    typical_current_ma=S(None, "mA"), peak_current_ma=S(None, "mA"))
nano_ev = [
 ev("vin_min_v", 7, "V", NANO_PDF, "Arduino Nano User Manual (A000005)", "Features > Power", "'7-15V unregulated external power supply (pin 30)'"),
 ev("vin_max_v", 15, "V", NANO_PDF, "Arduino Nano User Manual (A000005)", "Features > Power", "'7-15V unregulated external power supply (pin 30)'"),
 ev("logic_v", 5, "V", NANO_PDF, "Arduino Nano User Manual (A000005)", "3.2 Processor", "'UART TTL (5V)'. Other pins' logic level is not stated in this document."),
 ev("clock_mhz", 16, "MHz", NANO_PDF, "Arduino Nano User Manual (A000005)", "Description / 3.2", "ATmega328 'clocked at a frequency of 16 MHz'"),
 ev("flash_kb", 32, "kB", NANO_PDF, "Arduino Nano User Manual (A000005)", "Features", "'32 kB of which 2 KB used by bootloader'"),
 ev("sram_kb", 2, "kB", NANO_PDF, "Arduino Nano User Manual (A000005)", "Features", "'2 kB internal SRAM'"),
 ev("eeprom_kb", 1, "kB", NANO_PDF, "Arduino Nano User Manual (A000005)", "Features", "'1 kB EEPROM'"),
 ev("digital_io_count", 20, "count", NANO_PDF, "Arduino Nano User Manual (A000005)", "Description / Features", "'20 digital input/output pins'. Other retailer pages say 14 plus analog pins; counts differ by how analog pins are counted."),
 ev("analog_inputs", 8, "count", NANO_PDF, "Arduino Nano User Manual (A000005)", "Features", "'8 analog pins'"),
 ev("pwm_channels", 6, "count", NANO_PDF, "Arduino Nano User Manual (A000005)", "Features", "'6 PWM Output'"),
 ev("operating_temp_min_c", -40, "°C", NANO_PDF, "Arduino Nano User Manual (A000005)", "2.1", "'Conservative thermal limits for the whole board: -40 °C 85 °C'"),
 ev("operating_temp_max_c", 85, "°C", NANO_PDF, "Arduino Nano User Manual (A000005)", "2.1", "same row"),
]
n = rec("ctrl_nano_a000005", "Arduino Nano (A000005)", "controller", "ctrl_nano", "Arduino S.r.l.", "A000005", "Nano 3.x, ATmega328",
        "ATmega328 8-bit AVR board, 5 V logic, no wireless interface listed in the datasheet.", nano_specs,
        dict(interfaces=["UART (5 V TTL)", "I2C", "SPI"], gpio_5v_tolerant=None), nano_ev,
        "Datasheet section 2.2 lists power consumption as 'TBC', so current stays null. The datasheet says Mini-B USB in Features but Micro-B in 4.1; unresolved. "
        "Wi-Fi/Bluetooth are not mentioned in the datasheet, so they stay null (unknown) rather than being recorded as false. Legacy FORGE seed used VIN max 12 V; the datasheet says 15 V.",
        datasheet=NANO_PDF)
R.append(n)

esp_specs = NULL(CTRL) | dict(supply_nominal_v=S(5, "V"), typical_current_ma=S(None, "mA"), peak_current_ma=S(None, "mA"), gpio_count=S(None, "count"), pwm_channels=S(None, "count"))
esp_ev = [ev("supply_nominal_v", 5, "V", ESP_GUIDE, "ESP32-DevKitC V4 Getting Started Guide", "Power Supply Options",
             "Power comes from the Micro USB port or the '5V and GND header pins'; use one option only. The guide documents a 5 V supply, not a wider VIN range.")]
e = rec("ctrl_esp32_devkitc_v4", "ESP32-DevKitC V4", "controller", "ctrl_esp32", "Espressif Systems", None, "ESP32-DevKitC V4 (module variant not fixed)",
        "Espressif ESP32 development board. Wireless, logic-level, GPIO and current figures are not yet verified here.", esp_specs,
        dict(interfaces=[], gpio_5v_tolerant=None), esp_ev,
        "FORGE's legacy part is a generic 'ESP32 DevKit V1' (different board from Espressif's DevKitC V4); mapping is APPROXIMATE. "
        "Chip-level ESP32 capabilities were deliberately not copied to this board record. Legacy seed assumed VIN 5-12 V; Espressif documents only a 5 V supply, "
        "so a 2S/3S battery must not be assumed to connect directly.", mapping="approximate", datasheet=ESP_GUIDE)
R.append(e)

R += [
 rec("drv_l298n_module", "L298N motor driver module", "driver", "drv_l298n", None, None, "Generic dual H-bridge module (L298N IC)", "Dual H-bridge module built on the ST L298N. Module-level limits unverified.", NULL(DRV), mapping="approximate"),
 rec("drv_tb6612fng", "TB6612FNG motor driver", "driver", "drv_tb6612", "Toshiba (IC)", "TB6612FNG", "Breakout board; vendor not fixed", "Dual MOSFET H-bridge driver IC on a breakout board. Unverified here.", NULL(DRV), mapping="approximate"),
 rec("mot_n20_6v", "N20 geared DC motor (6 V class)", "motor", "mot_n20", None, None, "Variant not fixed (RPM/gear ratio unknown)", "Small geared DC motor. Variants differ widely; no variant identified.", NULL(MOT), mapping="approximate"),
 rec("mot_tt_yellow", "TT yellow geared DC motor", "motor", "mot_tt", None, None, "Variant not fixed", "Common yellow gearbox motor. Unverified.", NULL(MOT), mapping="approximate"),
 rec("bat_1s_liion", "1S Li-ion cell (3.7 V nominal)", "battery", "bat_1s", None, None, "Cell not fixed", "Single lithium-ion cell. Capacity/discharge unknown.", NULL(BAT), mapping="approximate"),
 rec("bat_2s_liion", "2S Li-ion pack (7.4 V nominal)", "battery", "bat_2s", None, None, "Pack not fixed", "Two cells in series. Capacity, BMS and discharge limits unknown.", NULL(BAT), mapping="approximate"),
 rec("bat_3s_liion", "3S Li-ion pack (11.1 V nominal)", "battery", "bat_3s", None, None, "Pack not fixed", "Three cells in series. Capacity, BMS and discharge limits unknown.", NULL(BAT), mapping="approximate"),
 rec("sen_line5_array", "5-channel IR line sensor array", "sensor", "sen_line5", None, None, "Module not fixed", "Five IR reflectance channels. Output type and current unverified.", NULL(SEN) | dict(channels=S(5, "count")), mapping="approximate"),
 rec("sen_hcsr04", "HC-SR04 ultrasonic sensor", "sensor", "sen_hcsr04", None, None, "Generic HC-SR04", "Ultrasonic distance sensor. Unverified here.", NULL(SEN), mapping="approximate"),
]
# channels=5 on the line array is part of the product name, not a measured spec: keep it null-safe by moving it to notes
for r in R:
    if r["id"] == "sen_line5_array":
        r["specifications"]["channels"] = S(None, "count"); r["notes"] = "Channel count (5) comes from the product name only; not evidence-backed, so the field stays null."
    if r["specification_sources"]:
        r["verification_status"] = "partially_verified"; r["last_verified"] = TODAY
out = pathlib.Path(__file__).resolve().parent.parent / "data" / "components.json"
out.write_text(json.dumps(dict(schema_version=1, generated_by="scripts/build_components.py", components=R), indent=1, ensure_ascii=False))
print("wrote", out, len(R), "records")
