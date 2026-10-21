"""Human-editable role evidence checklists; update these as portfolio expectations evolve."""

ROLE_CHECKLISTS = {
    "embedded": [
        {"id": "mcu_peripherals", "label": "MCU peripherals", "tags": {"stm32", "embedded"}, "weight": 1.0},
        {"id": "rtos", "label": "RTOS and scheduling", "tags": {"rtos"}, "weight": 1.0},
        {"id": "comm_protocols", "label": "Communication protocols", "tags": {"can_bus", "bluetooth", "rf_comms", "wireless_other"}, "weight": 0.8},
        {"id": "pcb", "label": "PCB design", "tags": {"pcb_design"}, "weight": 0.8},
        {"id": "power", "label": "Power electronics", "tags": {"power_electronics"}, "weight": 0.6},
        {"id": "linux", "label": "Embedded Linux", "tags": {"embedded_linux"}, "weight": 0.6},
        {"id": "hdl", "label": "HDL and FPGA", "tags": {"fpga"}, "weight": 0.6},
        {"id": "motor_ctrl", "label": "Motor control", "tags": {"motor_control"}, "weight": 0.8},
    ],
    "robotics": [
        {"id": "ros", "label": "Robot middleware", "tags": {"ros"}, "weight": 1.0},
        {"id": "control", "label": "Control systems", "tags": {"control"}, "weight": 1.0},
        {"id": "actuation", "label": "Actuation and motor control", "tags": {"motor_control"}, "weight": 0.9},
        {"id": "sensing", "label": "Sensors and estimation", "tags": {"sensors", "signal_processing"}, "weight": 0.9},
        {"id": "mechanics", "label": "Mechanical design", "tags": {"mechanical_design", "cad"}, "weight": 0.8},
        {"id": "vision", "label": "Robot vision", "tags": {"vision", "ml"}, "weight": 0.7},
        {"id": "embedded", "label": "Embedded integration", "tags": {"embedded", "stm32"}, "weight": 0.7},
    ],
    "ml_vision": [
        {"id": "ml", "label": "Machine learning", "tags": {"ml"}, "weight": 1.0},
        {"id": "vision", "label": "Computer vision", "tags": {"vision"}, "weight": 1.0},
        {"id": "python", "label": "Python engineering", "tags": {"python"}, "weight": 0.8},
        {"id": "signal", "label": "Signal processing", "tags": {"signal_processing"}, "weight": 0.8},
        {"id": "embedded", "label": "Edge deployment", "tags": {"embedded", "esp32"}, "weight": 0.7},
        {"id": "robotics", "label": "Robotics integration", "tags": {"ros", "motor_control"}, "weight": 0.6},
    ],
    "hardware": [
        {"id": "pcb", "label": "PCB design", "tags": {"pcb_design"}, "weight": 1.0},
        {"id": "power", "label": "Power electronics", "tags": {"power_electronics"}, "weight": 1.0},
        {"id": "soldering", "label": "PCB assembly", "tags": {"pcb_soldering"}, "weight": 0.8},
        {"id": "fpga", "label": "FPGA / digital logic", "tags": {"fpga"}, "weight": 0.8},
        {"id": "mcu", "label": "Microcontroller design", "tags": {"stm32", "embedded"}, "weight": 0.8},
        {"id": "rf", "label": "RF and connectivity", "tags": {"rf_comms", "wireless_other"}, "weight": 0.6},
    ],
    "iot": [
        {"id": "connectivity", "label": "Connectivity", "tags": {"esp32", "iot_cloud", "rf_comms", "wireless_other", "bluetooth"}, "weight": 1.0},
        {"id": "embedded", "label": "Embedded firmware", "tags": {"embedded", "stm32"}, "weight": 0.9},
        {"id": "sensing", "label": "Sensor integration", "tags": {"sensors"}, "weight": 0.8},
        {"id": "power", "label": "Low-power design", "tags": {"power_electronics"}, "weight": 0.7},
        {"id": "cloud", "label": "Cloud / telemetry", "tags": {"iot_cloud", "python"}, "weight": 0.8},
        {"id": "pcb", "label": "Custom hardware", "tags": {"pcb_design", "pcb_soldering"}, "weight": 0.6},
    ],
}
