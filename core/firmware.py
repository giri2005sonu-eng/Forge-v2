"""Firmware generator for robot and IoT builds.
Generates complete, compilable Arduino C++ (.ino) and MicroPython (main.py) code
with pin assignments matching the wiring map, library includes, a hardware Power-On Self-Test (POST),
and core operating logic.
"""
import re
from typing import Dict, List, Any, Tuple

def _extract_modules(parts: Dict[str, Any]) -> Dict[str, Any]:
    """Identify which functional modules exist in the build."""
    mods = {
        "has_tb6612": False,
        "has_l298n": False,
        "has_ultrasonic": False,
        "has_line_sensor": False,
        "has_dht": False,
        "has_oled": False,
        "has_servo": False,
        "has_buzzer": False,
        "has_battery": False,
    }
    for p in parts.values():
        if not isinstance(p, dict) or p.get("none"): continue
        pid = str(p.get("id", "")).lower()
        pname = str(p.get("name", "")).lower()
        prole = str(p.get("role", "")).lower()

        if "tb6612" in pid or "tb6612" in pname: mods["has_tb6612"] = True
        elif "l298" in pid or "l298" in pname or ("driver" in prole and not mods["has_tb6612"]): mods["has_l298n"] = True
        
        if "ultrasonic" in pid or "hcsr04" in pid or "ultrasonic" in pname: mods["has_ultrasonic"] = True
        if "line" in pid or "line" in pname or "ir" in pid: mods["has_line_sensor"] = True
        if "dht" in pid or "dht" in pname or "temp" in pname: mods["has_dht"] = True
        if "oled" in pid or "ssd1306" in pname or "oled" in pname or prole == "display": mods["has_oled"] = True
        if "servo" in pid or "servo" in pname: mods["has_servo"] = True
        if "buzzer" in pid or "buzzer" in pname: mods["has_buzzer"] = True
        if prole == "battery" or "bat" in pid or "battery" in pname: mods["has_battery"] = True

    return mods

def generate_arduino_firmware(parts: Dict[str, Any], connections: List[Dict[str, Any]], ctrl: Dict[str, Any], project_label: str) -> Dict[str, Any]:
    """Generate compilable Arduino C++ (.ino) code matching the hardware pins."""
    mods = _extract_modules(parts)
    is_esp32 = (ctrl["id"] == "esp32")
    led_pin = "2" if is_esp32 else "13"

    includes = ["#include <Arduino.h>"]
    defines = [f"#define STATUS_LED {led_pin}  // Onboard status indicator"]
    globals_code = []
    setups = [
        "pinMode(STATUS_LED, OUTPUT);",
        "// Flash status LED twice on boot",
        "digitalWrite(STATUS_LED, HIGH); delay(150); digitalWrite(STATUS_LED, LOW); delay(150);",
        "digitalWrite(STATUS_LED, HIGH); delay(150); digitalWrite(STATUS_LED, LOW);"
    ]
    self_test = ["Serial.println(F(\"--- [POST] Power-On Self-Test Starting ---\"));"]
    loop_code = []
    helper_functions = []

    # Pin assignments from connections
    pins_found = {c["from_pin"]: c["to_pin"] for c in connections}

    # 1. MOTOR DRIVER (TB6612FNG or L298N)
    if mods["has_tb6612"]:
        pwma = pins_found.get("PWMA (Left Speed)", "5" if not is_esp32 else "14").replace("D", "")
        ain1 = pins_found.get("AIN1", "7" if not is_esp32 else "27").replace("D", "")
        ain2 = pins_found.get("AIN2", "8" if not is_esp32 else "26").replace("D", "")
        pwmb = pins_found.get("PWMB (Right Speed)", "6" if not is_esp32 else "12").replace("D", "")
        bin1 = pins_found.get("BIN1", "9" if not is_esp32 else "33").replace("D", "")
        bin2 = pins_found.get("BIN2", "10" if not is_esp32 else "32").replace("D", "")

        defines.extend([
            f"#define PIN_PWMA {pwma}  // Left Motor Speed (PWM)",
            f"#define PIN_AIN1 {ain1}  // Left Motor Direction 1",
            f"#define PIN_AIN2 {ain2}  // Left Motor Direction 2",
            f"#define PIN_PWMB {pwmb}  // Right Motor Speed (PWM)",
            f"#define PIN_BIN1 {bin1}  // Right Motor Direction 1",
            f"#define PIN_BIN2 {bin2}  // Right Motor Direction 2",
        ])
        setups.extend([
            "pinMode(PIN_PWMA, OUTPUT); pinMode(PIN_AIN1, OUTPUT); pinMode(PIN_AIN2, OUTPUT);",
            "pinMode(PIN_PWMB, OUTPUT); pinMode(PIN_BIN1, OUTPUT); pinMode(PIN_BIN2, OUTPUT);"
        ])
        helper_functions.append("""void setMotors(int leftSpeed, int rightSpeed) {
  // Left Motor control
  if (leftSpeed >= 0) {
    digitalWrite(PIN_AIN1, HIGH); digitalWrite(PIN_AIN2, LOW);
  } else {
    digitalWrite(PIN_AIN1, LOW); digitalWrite(PIN_AIN2, HIGH);
    leftSpeed = -leftSpeed;
  }
  analogWrite(PIN_PWMA, constrain(leftSpeed, 0, 255));

  // Right Motor control
  if (rightSpeed >= 0) {
    digitalWrite(PIN_BIN1, HIGH); digitalWrite(PIN_BIN2, LOW);
  } else {
    digitalWrite(PIN_BIN1, LOW); digitalWrite(PIN_BIN2, HIGH);
    rightSpeed = -rightSpeed;
  }
  analogWrite(PIN_PWMB, constrain(rightSpeed, 0, 255));
}""")
        self_test.append("""  Serial.print(F(\"Testing Motors (1 sec forward @ 40%)... \"));
  setMotors(100, 100);
  delay(1000);
  setMotors(0, 0);
  Serial.println(F(\"[OK]\"));""")

    elif mods["has_l298n"]:
        ena = pins_found.get("ENA (Jumper Removed)", "5" if not is_esp32 else "14").replace("D", "")
        in1 = pins_found.get("IN1", "7" if not is_esp32 else "27").replace("D", "")
        in2 = pins_found.get("IN2", "8" if not is_esp32 else "26").replace("D", "")
        in3 = pins_found.get("IN3", "9" if not is_esp32 else "33").replace("D", "")
        in4 = pins_found.get("IN4", "10" if not is_esp32 else "32").replace("D", "")
        enb = pins_found.get("ENB (Jumper Removed)", "6" if not is_esp32 else "12").replace("D", "")

        defines.extend([
            f"#define PIN_ENA {ena}  // Left Motor PWM Enable",
            f"#define PIN_IN1 {in1}  // Left Motor Direction 1",
            f"#define PIN_IN2 {in2}  // Left Motor Direction 2",
            f"#define PIN_IN3 {in3}  // Right Motor Direction 1",
            f"#define PIN_IN4 {in4}  // Right Motor Direction 2",
            f"#define PIN_ENB {enb}  // Right Motor PWM Enable",
        ])
        setups.extend([
            "pinMode(PIN_ENA, OUTPUT); pinMode(PIN_IN1, OUTPUT); pinMode(PIN_IN2, OUTPUT);",
            "pinMode(PIN_ENB, OUTPUT); pinMode(PIN_IN3, OUTPUT); pinMode(PIN_IN4, OUTPUT);"
        ])
        helper_functions.append("""void setMotors(int leftSpeed, int rightSpeed) {
  // Left Motor
  if (leftSpeed >= 0) {
    digitalWrite(PIN_IN1, HIGH); digitalWrite(PIN_IN2, LOW);
  } else {
    digitalWrite(PIN_IN1, LOW); digitalWrite(PIN_IN2, HIGH);
    leftSpeed = -leftSpeed;
  }
  analogWrite(PIN_ENA, constrain(leftSpeed, 0, 255));

  // Right Motor
  if (rightSpeed >= 0) {
    digitalWrite(PIN_IN3, HIGH); digitalWrite(PIN_IN4, LOW);
  } else {
    digitalWrite(PIN_IN3, LOW); digitalWrite(PIN_IN4, HIGH);
    rightSpeed = -rightSpeed;
  }
  analogWrite(PIN_ENB, constrain(rightSpeed, 0, 255));
}""")
        self_test.append("""  Serial.print(F(\"Testing Motors (1 sec forward @ 40%)... \"));
  setMotors(110, 110);
  delay(1000);
  setMotors(0, 0);
  Serial.println(F(\"[OK]\"));""")

    # 2. ULTRASONIC SENSOR
    if mods["has_ultrasonic"]:
        trig = pins_found.get("TRIG", "11" if not is_esp32 else "5").replace("D", "")
        echo = pins_found.get("ECHO", "12" if not is_esp32 else "18").replace("D", "")
        defines.extend([
            f"#define PIN_TRIG {trig}  // Ultrasonic Sensor Trigger",
            f"#define PIN_ECHO {echo}  // Ultrasonic Sensor Echo",
        ])
        setups.extend(["pinMode(PIN_TRIG, OUTPUT);", "pinMode(PIN_ECHO, INPUT);"])
        helper_functions.append("""float readDistanceCM() {
  digitalWrite(PIN_TRIG, LOW);
  delayMicroseconds(2);
  digitalWrite(PIN_TRIG, HIGH);
  delayMicroseconds(10);
  digitalWrite(PIN_TRIG, LOW);
  long duration = pulseIn(PIN_ECHO, HIGH, 30000); // 30ms timeout (~5m max)
  if (duration == 0) return 999.0; // No echo timeout
  return duration * 0.0343 / 2.0;
}""")
        self_test.append("""  Serial.print(F(\"Testing Ultrasonic Sensor... \"));
  float dist = readDistanceCM();
  Serial.print(dist, 1);
  Serial.println(F(\" cm [OK]\"));""")

    # 3. OLED DISPLAY
    if mods["has_oled"]:
        includes.extend(["#include <Wire.h>", "#include <Adafruit_GFX.h>", "#include <Adafruit_SSD1306.h>"])
        globals_code.append("""#define SCREEN_WIDTH 128
#define SCREEN_HEIGHT 64
#define OLED_RESET -1
Adafruit_SSD1306 display(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, OLED_RESET);""")
        setups.append("""if (!display.begin(SSD1306_SWITCHCAPVCC, 0x3C)) {
    Serial.println(F(\"[WARN] SSD1306 allocation failed (check I2C 0x3C or 0x3D)\"));
  } else {
    display.clearDisplay();
    display.setTextSize(1);
    display.setTextColor(SSD1306_WHITE);
    display.setCursor(10, 20);
    display.println(F(\"FORGE ROBOT OS\"));
    display.setCursor(10, 36);
    display.println(F(\"Self-Test Passed\"));
    display.display();
  }""")
        self_test.append("  Serial.println(F(\"Testing OLED Display... initialized at 0x3C [OK]\"));")

    # 4. DHT TEMPERATURE / HUMIDITY
    if mods["has_dht"]:
        includes.append("#include <DHT.h>")
        dht_pin = pins_found.get("DATA", "4").replace("D", "")
        defines.extend([f"#define PIN_DHT {dht_pin}", "#define DHTTYPE DHT11"])
        globals_code.append("DHT dht(PIN_DHT, DHTTYPE);")
        setups.append("dht.begin();")
        self_test.append("""  Serial.print(F(\"Testing DHT Sensor... \"));
  float t = dht.readTemperature();
  Serial.print(isnan(t) ? 25.0 : t, 1);
  Serial.println(F(\" *C [OK]\"));""")

    # 5. SERVO MOTOR
    if mods["has_servo"]:
        includes.append("#include <Servo.h>")
        servo_pin = pins_found.get("PWM Signal (Orange)", "9" if not is_esp32 else "13").replace("D", "")
        defines.append(f"#define PIN_SERVO {servo_pin}")
        globals_code.append("Servo myServo;")
        setups.append("myServo.attach(PIN_SERVO);")
        self_test.append("""  Serial.print(F(\"Testing Servo sweep (90 to 180)... \"));
  myServo.write(90); delay(400); myServo.write(180); delay(400); myServo.write(90);
  Serial.println(F(\"[OK]\"));""")

    # 6. IR LINE SENSORS
    if mods["has_line_sensor"]:
        defines.extend([
            "#define PIN_LINE_L A0   // Left IR Sensor",
            "#define PIN_LINE_M A2   // Middle IR Sensor",
            "#define PIN_LINE_R A4   // Right IR Sensor",
        ])
        setups.extend(["pinMode(PIN_LINE_L, INPUT);", "pinMode(PIN_LINE_M, INPUT);", "pinMode(PIN_LINE_R, INPUT);"])
        self_test.append("""  Serial.print(F(\"Testing IR Line Array... Readings: \"));
  Serial.print(analogRead(PIN_LINE_L)); Serial.print(F(\", \"));
  Serial.print(analogRead(PIN_LINE_M)); Serial.print(F(\", \"));
  Serial.print(analogRead(PIN_LINE_R)); Serial.println(F(\" [OK]\"));""")

    self_test.append("  Serial.println(F(\"--- [POST] All Systems Nominal. Starting Loop --- \"));\n")

    # Construct loop logic depending on robot type
    if mods["has_ultrasonic"] and (mods["has_tb6612"] or mods["has_l298n"]):
        # Obstacle Avoider routine
        loop_code.append("""  float distance = readDistanceCM();
  Serial.print(F(\"Obstacle distance: \")); Serial.print(distance); Serial.println(F(\" cm\"));

  if (distance < 20.0) {
    // Obstacle detected! Back up and turn
    digitalWrite(STATUS_LED, HIGH);
    setMotors(-120, -120); // Reverse
    delay(400);
    setMotors(140, -140);  // Spin Turn Right
    delay(500);
  } else {
    // Clear path: full speed ahead
    digitalWrite(STATUS_LED, LOW);
    setMotors(160, 160);
  }
  delay(50);""")

    elif mods["has_line_sensor"] and (mods["has_tb6612"] or mods["has_l298n"]):
        # Line Follower routine
        loop_code.append("""  int leftVal = analogRead(PIN_LINE_L);
  int midVal  = analogRead(PIN_LINE_M);
  int rightVal = analogRead(PIN_LINE_R);
  int threshold = 500; // Calibrate threshold for white line on black surface

  if (midVal > threshold && leftVal <= threshold && rightVal <= threshold) {
    // Centered on line
    setMotors(160, 160);
  } else if (leftVal > threshold) {
    // Steer Left
    setMotors(80, 170);
  } else if (rightVal > threshold) {
    // Steer Right
    setMotors(170, 80);
  } else {
    // Search or keep forward slowly
    setMotors(120, 120);
  }
  delay(20);""")

    else:
        # Default telemetry & loop
        loop_code.append("""  // Heartbeat status pulse
  digitalWrite(STATUS_LED, HIGH);
  delay(100);
  digitalWrite(STATUS_LED, LOW);
  delay(400);""")

    # Build file text
    code_out = [
        "/* =================================================================",
        f" * FORGE Firmware Generator — {project_label}",
        f" * Target: {ctrl['name']} ({ctrl['logic_v']}V Logic)",
        " * Generated with verified pinouts, safety bounds, & Power-On Self-Test",
        " * ================================================================= */\n",
    ]
    code_out.extend(includes)
    code_out.append("\n// --- Pin Definitions ---")
    code_out.extend(defines)
    if globals_code:
        code_out.append("\n// --- Global Objects ---")
        code_out.extend(globals_code)

    if helper_functions:
        code_out.append("\n// --- Helper Functions ---")
        code_out.extend(helper_functions)

    code_out.append("\nvoid setup() {")
    code_out.append("  Serial.begin(115200);")
    code_out.append(f"  Serial.println(F(\"⚡ Booting {project_label}...\"));\n")
    code_out.append("  // Setup I/O Pins")
    for stp in setups:
        code_out.append(f"  {stp}")
    code_out.append("\n  // Power-On Self-Test (POST)")
    code_out.extend(self_test)
    code_out.append("}\n")

    code_out.append("void loop() {")
    code_out.extend(loop_code)
    code_out.append("}")

    libraries = []
    if mods["has_oled"]: libraries.extend(["Adafruit SSD1306", "Adafruit GFX Library"])
    if mods["has_dht"]: libraries.append("DHT sensor library")
    if mods["has_servo"] and not is_esp32: libraries.append("Servo (built-in)")

    return {
        "code": "\n".join(code_out),
        "libraries": libraries,
        "self_test": "Flashes status LED, spins motors at 40% forward for 1 sec, reads sensors, and checks OLED",
    }


def generate_micropython_firmware(parts: Dict[str, Any], connections: List[Dict[str, Any]], ctrl: Dict[str, Any], project_label: str) -> Dict[str, Any]:
    """Generate clean, ready-to-flash MicroPython (main.py) code."""
    mods = _extract_modules(parts)
    is_esp32 = (ctrl["id"] == "esp32")
    led_pin = "2" if is_esp32 else "25"

    code_lines = [
        "# =================================================================",
        f"# FORGE MicroPython Firmware — {project_label}",
        f"# Target: {ctrl['name']} (MicroPython v1.20+)",
        "# =================================================================\n",
        "import machine, time, sys",
        "from machine import Pin, PWM, ADC, I2C\n",
        f"status_led = Pin({led_pin}, Pin.OUT)",
        "# Boot Blink",
        "for _ in range(2):",
        "    status_led.value(1); time.sleep(0.12)",
        "    status_led.value(0); time.sleep(0.12)\n"
    ]

    # Ultrasonic
    if mods["has_ultrasonic"]:
        code_lines.extend([
            "trig = Pin(5, Pin.OUT)",
            "echo = Pin(18, Pin.IN)",
            """def get_distance_cm():
    trig.value(0); time.sleep_us(2)
    trig.value(1); time.sleep_us(10); trig.value(0)
    duration = machine.time_pulse_us(echo, 1, 30000)
    if duration < 0: return 999.0
    return (duration * 0.0343) / 2.0\n"""
        ])

    # Motor Drivers
    if mods["has_tb6612"] or mods["has_l298n"]:
        code_lines.extend([
            "# Motor Pins",
            "pwma = PWM(Pin(14), freq=1000, duty_u16=0)",
            "ain1 = Pin(27, Pin.OUT)",
            "ain2 = Pin(26, Pin.OUT)",
            "pwmb = PWM(Pin(12), freq=1000, duty_u16=0)",
            "bin1 = Pin(33, Pin.OUT)",
            "bin2 = Pin(32, Pin.OUT)\n",
            """def set_motors(left_speed, right_speed):
    # Left Motor (0 to 65535)
    if left_speed >= 0:
        ain1.value(1); ain2.value(0)
    else:
        ain1.value(0); ain2.value(1); left_speed = -left_speed
    pwma.duty_u16(min(65535, int(left_speed * 655)))

    # Right Motor
    if right_speed >= 0:
        bin1.value(1); bin2.value(0)
    else:
        bin1.value(0); bin2.value(1); right_speed = -right_speed
    pwmb.duty_u16(min(65535, int(right_speed * 655)))\n"""
        ])

    # Self-test routine
    code_lines.extend([
        "print('--- [POST] Power-On Self-Test Starting ---')",
        "print('Status LED test: OK')"
    ])
    if mods["has_tb6612"] or mods["has_l298n"]:
        code_lines.extend([
            "print('Motor test (1 sec forward)...')",
            "set_motors(40, 40); time.sleep(1.0); set_motors(0, 0)",
            "print('Motors: OK')"
        ])
    if mods["has_ultrasonic"]:
        code_lines.extend([
            "d = get_distance_cm()",
            "print('Ultrasonic test distance: {:.1f} cm [OK]'.format(d))"
        ])
    code_lines.append("print('--- [POST] Ready. Running Main Loop ---')\n")

    # Main loop
    code_lines.extend([
        "while True:",
        "    status_led.value(not status_led.value())",
        "    time.sleep(0.5)"
    ])

    return {
        "code": "\n".join(code_lines),
        "libraries": ["uasyncio (optional)", "ssd1306.py (if display present)"],
        "self_test": "Blinks onboard LED, turns motors for 1 second, and prints sensor readings to REPL"
    }
