"""Tests for core.firmware: compilable Arduino C++ and MicroPython boilerplate generation with self-tests."""
import pytest
from core import firmware, wiring

def test_arduino_motor_driver_and_self_test():
    parts = {
        "controller": {"role": "controller", "name": "Arduino Nano", "id": "ctrl_nano"},
        "driver": {"role": "driver", "name": "TB6612FNG driver", "id": "drv_tb6612"},
        "motor": {"role": "motor", "name": "N20 gear motor", "id": "mot_n20"},
        "battery": {"role": "battery", "name": "2S Li-ion (7.4V)", "id": "bat_2s"},
    }
    w = wiring.generate_wiring(parts, "Line Follower")
    ctrl = w["controller"]
    fw = firmware.generate_arduino_firmware(parts, w["connections"], ctrl, "Line Follower")
    code = fw["code"]

    # Motor pin definitions & controls
    assert "#define PIN_PWMA" in code
    assert "#define PIN_PWMB" in code
    assert "void setMotors(" in code

    # Power-On Self-Test (POST)
    assert "[POST] Power-On Self-Test" in code
    assert "Testing Motors (1 sec forward @ 40%)..." in code
    assert "setMotors(100, 100);" in code
    assert "delay(1000);" in code
    assert "setMotors(0, 0);" in code
    assert "STATUS_LED" in code

def test_arduino_ultrasonic_obstacle_avoidance():
    parts = {
        "controller": {"role": "controller", "name": "ESP32 DevKit", "id": "ctrl_esp32"},
        "driver": {"role": "driver", "name": "L298N driver", "id": "drv_l298n"},
        "sensor": {"role": "sensor", "name": "HC-SR04 ultrasonic", "id": "sen_hcsr04"},
    }
    w = wiring.generate_wiring(parts, "Obstacle Avoider")
    ctrl = w["controller"]
    fw = firmware.generate_arduino_firmware(parts, w["connections"], ctrl, "Obstacle Avoider")
    code = fw["code"]

    # Ultrasonic pins & logic
    assert "#define PIN_TRIG 5" in code
    assert "#define PIN_ECHO 18" in code
    assert "float readDistanceCM()" in code
    assert "Testing Ultrasonic Sensor..." in code
    assert "distance < 20.0" in code

def test_arduino_display_and_sensor_libraries():
    parts = {
        "controller": {"role": "controller", "name": "Arduino Nano", "id": "ctrl_nano"},
        "display": {"role": "display", "name": "SSD1306 OLED", "id": "disp_oled"},
        "sensor": {"role": "sensor", "name": "DHT11 sensor", "id": "sen_dht11"},
    }
    w = wiring.generate_wiring(parts, "Weather Station")
    ctrl = w["controller"]
    fw = firmware.generate_arduino_firmware(parts, w["connections"], ctrl, "Weather Station")
    code = fw["code"]

    # Library includes
    assert "#include <Wire.h>" in code
    assert "#include <Adafruit_SSD1306.h>" in code
    assert "#include <DHT.h>" in code
    assert "Adafruit SSD1306" in fw["libraries"]
    assert "DHT sensor library" in fw["libraries"]

def test_micropython_firmware():
    parts = {
        "controller": {"role": "controller", "name": "ESP32 DevKit", "id": "ctrl_esp32"},
        "driver": {"role": "driver", "name": "TB6612FNG driver", "id": "drv_tb6612"},
        "sensor": {"role": "sensor", "name": "HC-SR04 ultrasonic", "id": "sen_hcsr04"},
    }
    w = wiring.generate_wiring(parts, "Smart Bot")
    ctrl = w["controller"]
    mpy = firmware.generate_micropython_firmware(parts, w["connections"], ctrl, "Smart Bot")
    code = mpy["code"]

    assert "import machine, time" in code
    assert "from machine import Pin, PWM" in code
    assert "def set_motors" in code
    assert "def get_distance_cm" in code
    assert "[POST] Power-On Self-Test" in code
    assert "time.sleep(1.0)" in code
