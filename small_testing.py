# # small_testing.py
# # Implements the "Small Testing" verification for 3P4W and 3P3W systems.
# # This runs after the main calibration sequence to verify accuracy.
#
# import time
# import struct
# import steps
# import config
# from transport import get_transport
# import ui_helpers  # GUI/console helpers
# import decoder
# from registers import PARAM_MAP,SWAP_WORDS
# import math
# # --- Configuration based on the document ---
#
# # Define the test steps for each system type
# TEST_STEPS_3P4W = [
#     {'step': 1, 'V': 230, 'I': 5, 'Angle': 0, 'Freq': 50},
#     {'step': 2, 'V': 230, 'I': 5, 'Angle': 60, 'Freq': 50},
# ]
#
# # Note: Step 4 must be repeated 5 times
# TEST_STEPS_3P3W = [
#     {'step': 1, 'V': 230, 'I': 5, 'Angle': 0, 'Freq': 50},
#     {'step': 2, 'V': 230, 'I': 5, 'Angle': 60, 'Freq': 50},
#     {'step': 3, 'V': 230, 'I': 1, 'Angle': 0, 'Freq': 50},
#     {'step': 4, 'V': 230, 'I': 1, 'Angle': 60, 'Freq': 50},
# ]
#
# # Define the error limits from the document
# ERROR_LIMITS = {
#     "voltage": 1.0,       # ±1% for phase-wise Voltage
#     "current": 1.0,       # ±1% for phase-wise Current
#     "active_power": 1.0,  # ±1% for phase-wise active power
#     "power_factor": 0.8,  # ±0.8% for power factor
#     "frequency": 0.2,     # ±0.2% for system frequency
# }
#
#
#
# # --- Helper Functions ---
#
# def _decode_parameter_response(raw_bytes: bytes, meter_num: int) -> dict:
#     """
#     Uses decoder.py to extract meter data and return a dictionary of parameters.
#     This replaces manual Modbus slicing — keeps one decoding logic for all scripts.
#     """
#     if not raw_bytes:
#         return {}
#
#     # Step 1: split into segments
#     segments = decoder.split_segments_by_CR(raw_bytes)
#
#     # Step 2: clean up each segment
#     processed_segments = [decoder.process_hex_data(seg).replace(" ", "") for seg in segments]
#
#     # Step 3: group by meter ID
#     final_map, _ = decoder.process_by_second_marker(processed_segments)
#
#     # Step 4: get this meter’s tokens
#     data_tokens = final_map.get(f"meter {meter_num}", [])
#     if not data_tokens:
#         return {}
#
#     # Step 5: rebuild a contiguous hex string
#     data_hex = ''.join(data_tokens)
#     data_bytes = bytes.fromhex(data_hex)
#
#
#     # Step 6: decode floats using register map
#     readings = {}
#     for name, word_index in PARAM_MAP.items():
#         base = word_index * 2
#         try:
#             hi = data_bytes[base:base+2]
#             lo = data_bytes[base+2:base+4]
#             if SWAP_WORDS:
#                 hi, lo = lo, hi
#             readings[name] = struct.unpack(">f", hi + lo)[0]
#         except Exception:
#             readings[name] = None
#
#     return readings
#
# def _decode_single_float(raw_bytes: bytes) -> float:
#     """Decodes a single 4-byte float from a Modbus response."""
#     if not raw_bytes or len(raw_bytes) < 7:
#         return 0.0
#     payload = raw_bytes[3:7]
#     return struct.unpack('>f', payload)[0]
#
# def _calculate_error(measured, expected):
#     """Calculates percentage error as per the formula."""
#     if expected == 0:
#         return float('inf') if measured != 0 else 0.0
#     # Formula: % Error = 100 * (Meter Reading - Applied Input) / (Applied Input)
#     return 100 * (measured - expected) / expected
#
# # --- Main Test Logic ---
#
# def _perform_test_step(transport, meter_num, step_config, check_pf=False):
#     """
#     Executes a single step of the small test for one meter.
#     Returns True if passed, False if failed.
#     """
#     print(f"\nMeter {meter_num}, Step {step_config['step']}: V={step_config['V']}V, I={step_config['I']}A, Angle={step_config['Angle']}°")
#     input(" -> Please apply the above inputs to the source and press Enter to continue...")
#
#     passed = True
#
#     # 1. Read first 40 parameters
#     cmd_params = steps.build_modbus_read_cmd(meter_num, 1, 0x0000, 40)
#     transport.send_mcw(cmd_params)
#     resp_params = transport.recv_all(timeout=3.0)
#
#     meter_readings = _decode_parameter_response(resp_params, meter_num)
#
#     if not meter_readings:
#         print("  ❌ ERROR: No valid data received for meter", meter_num)
#         return False
#
#     # 2. Validate Voltage, Current, Power
#     for param in ['V_R','V_Y','V_B','I_R','I_Y','I_B','P_R','P_Y','P_B']:
#         key = param.split('_')[0].lower()
#         param_type = "voltage" if key == 'v' else "current" if key == 'i' else "active_power"
#
#         measured = meter_readings.get(param, 0)
#
#         if param_type == "active_power":
#             expected = step_config['V'] * step_config['I'] * math.cos(math.radians(step_config['Angle']))
#         elif param_type == "voltage":
#             expected = step_config['V']
#         else:  # current
#             expected = step_config['I']
#
#         error = _calculate_error(measured, expected)
#         limit = ERROR_LIMITS[param_type]
#         status = "PASS" if abs(error) <= limit else "FAIL"
#         if status == "FAIL":
#             passed = False
#         print(f"  - {param}: Measured={measured:.2f}, Error={error:.3f}%, Limit=±{limit}%, Status: {status}")
#
#     # 3. Validate Frequency (from decoder)
#     freq_reading = meter_readings.get("FREQ", 0.0)
#     error = _calculate_error(freq_reading, step_config['Freq'])
#     limit = ERROR_LIMITS["frequency"]
#     status = "PASS" if abs(error) <= limit else "FAIL"
#     if status == "FAIL":
#         passed = False
#     print(f"  - Frequency: Measured={freq_reading:.3f}, Error={error:.3f}%, Limit=±{limit}%, Status: {status}")
#
#     # 4. Check Power Factor only for Step 2
#     if check_pf:
#         pf_reading = meter_readings.get("PF", 0.0)
#         expected_pf = math.cos(math.radians(step_config['Angle']))
#         diff = abs(pf_reading - expected_pf)
#         limit = ERROR_LIMITS["power_factor"] / 100.0  # 0.8% → 0.008
#         status = "PASS" if diff <= limit else "FAIL"
#         if status == "FAIL":
#             passed = False
#         print(f"  - Power Factor: Measured={pf_reading:.4f}, Expected={expected_pf:.4f}, Diff={diff:.4f}, Limit=±{limit}, Status: {status}")
#
#     return passed
#
# def run_small_tests(meters_to_test):
#     """
#     Main entry point to run the small testing sequence.
#     """
#     if not meters_to_test:
#         print("No meters to run small testing on.")
#         return {}
#
#     # Select test type (GUI/console prompt)
#     test_type = ui_helpers.select_small_test_type()
#     print(f"--- Starting Small Testing for {test_type} ---")
#
#     # Decide which steps to run
#     if test_type == "3P4W":
#         test_steps = TEST_STEPS_3P4W
#     elif test_type == "3P3W":
#         test_steps = TEST_STEPS_3P3W
#     else:
#         print("❌ Invalid test type selected.")
#         return {}
#
#     results = {m: {"status": "NOT_RUN", "details": []} for m in meters_to_test}
#     transport = get_transport()
#
#     try:
#         for meter in meters_to_test:
#             meter_passed_all_steps = True
#             for step_config in test_steps:
#                 # Repeat rule only applies for 3P3W step 4
#                 repeat_count = 5 if test_type == "3P3W" and step_config['step'] == 4 else 1
#
#                 for i in range(repeat_count):
#                     print(f"--- Running Test for Meter {meter} (Attempt {i+1}/{repeat_count}) ---")
#                     # Power factor is only checked at step 2
#                     check_power_factor = (step_config['step'] == 2)
#
#                     step_passed = _perform_test_step(transport, meter, step_config, check_pf=check_power_factor)
#
#                     if not step_passed:
#                         print(f"  ❌ Meter {meter} FAILED at step {step_config['step']}.")
#                         meter_passed_all_steps = False
#                         break  # stop testing this meter
#
#                 if not meter_passed_all_steps:
#                     break  # exit loop for this meter
#
#             results[meter]["status"] = "PASS" if meter_passed_all_steps else "FAIL"
#
#     finally:
#         transport.close()
#
#     print("\n--- Small Testing Complete ---")
#     print("Results:", results)
#     return results, test_type
