# Recommendation Model Evaluation

Deterministic evaluation over 28 hand-authored personas and 300 seeded synthetic profiles.
v2 returns up to four readiness-gated picks; v1 returns five baseline ranks, so coverage is not a same-K comparison.
Difficulty violations use the same raw catalog difficulty threshold (estimated level + 1.5) for both versions.
Score gaps are omitted from the comparison because v1 uses a 0–100 scale and v2 uses normalized component scores.

| Metric | v1 | v2 |
|---|---:|---:|
| Candidate coverage | 46.06% | 32.73% |
| All-equal top picks | 0.91% | 0.0% |
| Budget perturbation Jaccard | 0.89 | 0.865 |
| Difficulty violations | 12.07% | 7.0% |
| Readiness violations | — | 0.0% |
| Cold-start profiles | — | 3.05% |

## Evaluation notes

- Deterministic: v1 `True`, v2 `True`.
- Persona expectation failures: v1 1; v2 0.
- v2 requested more profile context for 3.05% of profiles.
- v2 budget stability covers 283 profiles with at least one pick in a perturbed run.
- Catalog cost figures remain rough estimates; the evaluator does not fetch live prices.
- v1 remains the default unless explicit release acceptance targets pass.

## v2 persona outcomes

| Persona | Status | Top projects / missing context |
|---|---|---|
| blank cold start | More info | Needs more info: career direction or interests, experience, resume skills, or completed projects, budget, available tools, weekly hours and deadline |
| embedded beginner low budget | Ranked | rf_remote_switch, water_level_controller, stm32_bringup, opencv_color_tracker |
| robotics maker | Ranked | smart_dustbin, drone_sim_pid, parametric_enclosure, pan_tilt_mount |
| advanced firmware | Ranked | buildroot_linux_driver, lifi_link, esp_mini_drone, sound_localizer |
| resume-only skills | More info | Needs more info: career direction or interests, budget, available tools, weekly hours and deadline |
| three Arduino projects | Ranked | lifi_link, freertos_multitask_hub, led_matrix_display, solar_tracker |
| vision learner | Ranked | opencv_color_tracker, drone_sim_pid, smart_dustbin, stm32_bringup |
| IoT intern portfolio | Ranked | smart_light_wifi, stm32_bringup, water_level_controller, rf_remote_switch |
| sensing beginner | Ranked | smart_dustbin, drone_sim_pid, solar_phone_charger, parametric_enclosure |
| mechanics lab access | Ranked | servo_robotic_arm, imu_kalman_fusion, solar_tracker, esp_mini_drone |
| no tools laptop | Ranked | buildroot_linux_driver, led_matrix_display, imu_kalman_fusion, camera_doorbell |
| tight schedule | Ranked | smart_dustbin, parametric_enclosure, dc_motor_speed_pid, pan_tilt_mount |
| long schedule | Ranked | servo_robotic_arm, esp_mini_drone, solar_tracker, imu_kalman_fusion |
| competition team | Ranked | servo_robotic_arm, esp_mini_drone, solar_tracker, imu_kalman_fusion |
| ESP32 owner | Ranked | smart_light_wifi, esp32cam_stream, drone_sim_pid, rf_remote_switch |
| STM32 owner advanced | Ranked | led_matrix_display, freertos_multitask_hub, gsm_sms_alert, solar_tracker |
| ML with fabrication tools | Ranked | opencv_color_tracker, smart_dustbin, parametric_enclosure, drone_sim_pid |
| wireless interest | Ranked | rf_remote_switch, opencv_color_tracker, water_level_controller, smart_light_wifi |
| experienced robotics | Ranked | esp_mini_drone, servo_robotic_arm, imu_kalman_fusion, solar_tracker |
| power electronics | Ranked | rf_remote_switch, water_level_controller, stm32_bringup, opencv_color_tracker |
| FPGA learner | Ranked | buildroot_linux_driver, lifi_link, esp_mini_drone, led_matrix_display |
| aerospace enthusiast | Ranked | esp_mini_drone, servo_robotic_arm, solar_tracker, smart_irrigation |
| budget constrained maker | Ranked | ldr_light_tracker, drone_sim_pid, rf_remote_switch, buck_converter_diy |
| high budget final year | Ranked | opencv_color_tracker, smart_dustbin, parametric_enclosure, pan_tilt_mount |
| career undecided with IoT interest | Ranked | nrf24_long_range_rc, weather_station, camera_doorbell, rc_hovercraft |
| beginner no budget limit | Ranked | rf_remote_switch, water_level_controller, stm32_bringup, opencv_color_tracker |
| robotics moderate budget and time | Ranked | smart_dustbin, parametric_enclosure, pan_tilt_mount, drone_sim_pid |
| vision portfolio with lab | Ranked | opencv_color_tracker, rf_remote_switch, water_level_controller, stm32_bringup |

## Candidates never recommended

- v1: 89 of 165.
- v2: 111 of 165.
