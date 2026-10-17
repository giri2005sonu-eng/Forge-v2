"""Tests for core.wiring: pinout mapping, Wokwi diagram.json, and starter firmware generation."""
import json
import pytest
from core import wiring

def test_detect_controller():
    nano_parts = {"c": {"role": "controller", "name": "Arduino Nano", "id": "ctrl_nano"}}
    esp_parts = {"c": {"role": "controller", "name": "ESP32 DevKit v4", "id": "ctrl_esp32"}}
    uno_parts = {"c": {"role": "controller", "name": "Arduino Uno R3", "id": "ctrl_uno"}}
    
    assert wiring._detect_controller(nano_parts)[0] == "nano"
    assert wiring._detect_controller(esp_parts)[0] == "esp32"
    assert wiring._detect_controller(uno_parts)[0] == "uno"

def test_nano_motor_driver_wiring():
    parts = {
        "controller": {"role": "controller", "name": "Arduino Nano", "id": "ctrl_nano"},
        "driver": {"role": "driver", "name": "TB6612FNG driver", "id": "drv_tb6612"},
        "battery": {"role": "battery", "name": "2S Li-ion (7.4V)", "id": "bat_2s"},
    }
    res = wiring.generate_wiring(parts, "Line Follower")
    conns = res["connections"]
    
    # Verify driver connections
    driver_pins = {c["from_pin"] for c in conns if "TB6612" in c["from_part"]}
    assert "VM (Motor Power)" in driver_pins
    assert "VCC (Logic)" in driver_pins
    assert "PWMA (Left Speed)" in driver_pins
    assert "PWMB (Right Speed)" in driver_pins
    assert "GND" in driver_pins

    # Verify Wokwi structure
    diagram = res["wokwi_diagram"]
    assert diagram["version"] == 1
    assert "parts" in diagram and len(diagram["parts"]) >= 1
    assert "connections" in diagram

def test_esp32_i2c_and_ultrasonic_pinout():
    parts = {
        "controller": {"role": "controller", "name": "ESP32 DevKit", "id": "ctrl_esp32"},
        "display": {"role": "display", "name": "SSD1306 OLED", "id": "disp_oled"},
        "sensor": {"role": "sensor", "name": "HC-SR04 ultrasonic", "id": "sen_hcsr04"},
    }
    res = wiring.generate_wiring(parts, "Obstacle Avoider")
    conns = res["connections"]

    # Verify ESP32 hardware I2C pin mapping: SDA -> 21, SCL -> 22
    sda_conn = next(c for c in conns if c["from_pin"] == "SDA")
    scl_conn = next(c for c in conns if c["from_pin"] == "SCL")
    assert sda_conn["to_pin"] == "21"
    assert scl_conn["to_pin"] == "22"

    # Verify ultrasonic pins
    trig_conn = next(c for c in conns if c["from_pin"] == "TRIG")
    echo_conn = next(c for c in conns if c["from_pin"] == "ECHO")
    assert trig_conn["to_pin"] == "5"
    assert echo_conn["to_pin"] == "18"

def test_firmware_and_svg_generation():
    parts = {
        "controller": {"role": "controller", "name": "Arduino Nano", "id": "ctrl_nano"},
        "sensor": {"role": "sensor", "name": "HC-SR04 ultrasonic", "id": "sen_hcsr04"},
        "servo": {"role": "actuator", "name": "SG90 Micro Servo", "id": "act_servo"},
    }
    res = wiring.generate_wiring(parts, "Radar Scan")
    code = res["firmware_code"]
    svg = res["svg_canvas"]

    # Firmware check
    assert "#define TRIG_PIN" in code
    assert "#define ECHO_PIN" in code
    assert "#define SERVO_PIN" in code
    assert "void setup()" in code
    assert "void loop()" in code

    # SVG check
    assert svg.startswith("<svg")
    assert svg.endswith("</svg>")
    assert "Arduino Nano" in svg

def test_wokwi_json_validity():
    parts = {
        "controller": {"role": "controller", "name": "Arduino Nano", "id": "ctrl_nano"},
        "display": {"role": "display", "name": "SSD1306 OLED", "id": "disp_oled"},
    }
    res = wiring.generate_wiring(parts, "Smart Clock")
    parsed = json.loads(res["wokwi_json_str"])
    assert parsed["version"] == 1
    assert any(p["id"] == "nano" for p in parsed["parts"])
    assert any(p["id"] == "oled1" for p in parsed["parts"])
