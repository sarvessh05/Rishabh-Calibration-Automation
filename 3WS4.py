#!/usr/bin/env python3
"""
Read Parameters Script (Full & Reliable)
========================================
- Connects to all configured meters (1..METER_COUNT).
- Skips meters that failed key test but logs them as "KEY_FAIL".
- Chooses IP based on global meter number:
    * 1–10  → 192.168.100.100
    * 11–20 → 192.168.100.101
- Always sends MCW1..10 (never MCW11+).
- Waits 3 seconds after switching IP/port.
- Decodes full 9-float frame per read (voltage, current, watt, etc.).
- Validates and saves results into a single JSON file (rewritten each run).
"""

import os
import re
import json
import time
import struct
from typing import Dict, List, Tuple

import config
from transport import get_transport
from steps import build_modbus_read_cmd

# ==========================================================
# Decoder helpers
# ==========================================================
def split_segments(raw_bytes: bytes) -> List[str]:
    ascii_data = raw_bytes.decode("latin1", errors="ignore")
    return [seg for seg in ascii_data.strip().split("\r") if seg.strip()]

def extract_meter_and_payload(segment: str) -> Tuple[int, str]:
    if segment.startswith("MCW"):
        return None, None
    m = re.match(r"F(\d+),.*?,(.*)", segment)
    return (int(m.group(1)), m.group(2)) if m else (None, None)

def decode_escapes(payload: str) -> bytes:
    out = bytearray()
    i = 0
    while i < len(payload):
        if payload[i] == "^":
            if payload[i:i+4].startswith("^h") and i + 3 < len(payload):
                try:
                    out.append(int(payload[i+2:i+4], 16))
                    i += 4
                    continue
                except ValueError:
                    pass
            elif i + 1 < len(payload):
                out.append(ord(payload[i+1]) & 0x1F)
                i += 2
                continue
        out.append(ord(payload[i]))
        i += 1
    return bytes(out)

# ==========================================================
# Parameter map
# ==========================================================
PARAM_REGS = [
    ("voltage_L1", 0x0000), ("voltage_L2", 0x0002), ("voltage_L3", 0x0004),
    ("current_L1", 0x0006), ("current_L2", 0x0008), ("current_L3", 0x000A),
    ("watt_sum",   0x0034), ("var_sum",    0x003C),
    ("frequency",  0x0046),
]


# ==========================================================
# Validation
# ==========================================================
def validate_value(name: str, value: float) -> bool:
    if value is None:
        return False
    if "voltage" in name and not (220.0 <= value <= 240.0):
        return False
    if "current" in name and not (4.0 <= value <= 5.5):
        return False
    if "watt" in name and not (0.0 <= value <= 1500.0):
        return False
    return True

# ==========================================================
# Read individual parameter
# ==========================================================
def read_single_param(transport, local_id: int, param_name: str, reg_addr: int, retries: int = 3) -> Dict:
    """
    Sends a separate read for a single parameter (float, 2 registers = 4 bytes)
    """
    cmd = build_modbus_read_cmd(local_id, 1, start_addr=reg_addr, reg_count=2)  # 2 registers = 1 float
    for attempt in range(retries):
        transport.send_mcw(cmd)
        raw = transport.recv_all(timeout=config.SOCKET_TIMEOUT)
        if raw:
            segments = split_segments(raw)
            for seg in segments:
                if seg.startswith(f"MCW{local_id}"):
                    continue
                m_id, payload = extract_meter_and_payload(seg)
                if m_id != local_id or not payload:
                    continue
                frame = decode_escapes(payload)
                if len(frame) < 7:  # slave + func + byte_count + 4 bytes float
                    continue
                byte_count = frame[2]
                if byte_count < 4:
                    continue
                data = frame[3:3+4]
                try:
                    val = struct.unpack(">f", data)[0]
                    if validate_value(param_name, val):
                        return {"value": val}
                    else:
                        return {"value": val, "warning": "out_of_range"}
                except Exception as e:
                    return {"value": None, "error": str(e)}
        time.sleep(0.2)
    return {"value": None, "error": "no_response"}

# ==========================================================
# Read all parameters individually
# ==========================================================
def read_meter(transport, local_id: int, global_id: int) -> Dict:
    res = {"global_meter": global_id, "local_meter": local_id, "params": {}}
    for param_name, reg_addr in PARAM_REGS:
        res["params"][param_name] = read_single_param(transport, local_id, param_name, reg_addr)
    return res

# ==========================================================
# IP mapping
# ==========================================================
def get_ip_and_local(global_meter: int):
    if global_meter <= 10:
        return "192.168.100.100", ((global_meter - 1) % 10) + 1
    return "192.168.100.101", ((global_meter - 1) % 10) + 1

# ==========================================================
# Load key test results
# ==========================================================
def load_key_test_results():
    try:
        with open(os.path.join(config.RESULTS_DIR, "key_test_log.json"), "r") as f:
            data = json.load(f)
        failed_meters = {int(m) for m, vals in data.items()
                         if any(v in ["CAL_FAIL", "FAIL", "NO_DATA"] for v in vals.values())}
        print(f"[INFO] Loaded key test results: {len(failed_meters)} meters failed key test.")
        return failed_meters
    except Exception as e:
        print(f"[WARN] Could not load key test results: {e}")
        return set()

# ==========================================================
# Calculate % error and pass/fail (with absolute limits for watt & var)
# ==========================================================
def calculate_errors(res: Dict, applied_inputs: Dict) -> None:
    """
    Adds % error and pass/fail for each parameter in res.
    Handles zero applied inputs safely.
    """
    for param, vals in res["params"].items():
        reading = vals.get("value")
        applied = applied_inputs.get(param)

        if reading is None or applied is None:
            vals["%error"] = None
            vals["pass_fail"] = "N/A"
            continue

        # Avoid division by zero
        if applied == 0:
            vals["%error"] = None
            vals["pass_fail"] = "N/A"
            vals["note"] = "applied_input_zero"
            continue

        # Absolute limits for watt & var
        if param == "watt_sum":
            vals["%error"] = None
            vals["pass_fail"] = "PASS" if 227 <= reading <= 232 else "FAIL"
        elif param == "var_sum":
            vals["%error"] = None
            vals["pass_fail"] = "PASS" if 394 <= reading <= 402 else "FAIL"
        # Voltage/current/frequency
        elif param.startswith(("voltage", "current", "frequency")):
            error = 100 * (reading - applied) / applied
            vals["%error"] = error
            if param.startswith("voltage") or param.startswith("current"):
                vals["pass_fail"] = "PASS" if abs(error) <= 1.0 else "FAIL"
            elif param == "frequency":
                vals["pass_fail"] = "PASS" if abs(error) <= 0.2 else "FAIL"
        else:
            vals["%error"] = None
            vals["pass_fail"] = "N/A"


# ==========================================================
# Save results
# ==========================================================
def save_results(results: List[Dict]):
    os.makedirs(config.RESULTS_DIR, exist_ok=True)
    out_file = os.path.join(config.RESULTS_DIR, "3WS4.json")
    with open(out_file, "w") as f:
        json.dump(results, f, indent=2)
    print(f"[INFO] Results saved to {out_file}")

# ==========================================================
# Main
# ==========================================================
def main(angle: int = 60):
    print(f"[START] Parameter read session (Angle = {angle}°)")
    all_results = []
    last_ip = None
    failed_key_meters = load_key_test_results()

    # Applied inputs per angle
    if angle == 60:
        applied_inputs = {
            "watt_sum": 230,
            "var_sum": 398,
            "voltage_L1": 398.36,
            "voltage_L2": 398.36,
            "voltage_L3": 398.36,
            "current_L1": 5.0,
            "current_L2": 5.0,
            "current_L3": 5.0,
            "frequency": 50.0
        }
    else:
        raise ValueError("Unsupported angle. Use 60.")

    # Read all meters
    for global_meter in range(1, config.METER_COUNT + 1):
        if global_meter in failed_key_meters:
            print(f"⚠️  Skipping meter {global_meter} (failed key test)")
            all_results.append({"global_meter": global_meter, "local_meter": None, "error": "KEY_FAIL"})
            continue

        ip, local_id = get_ip_and_local(global_meter)
        if ip != last_ip and last_ip is not None:
            print(f"[INFO] Switching to {ip}, waiting 3 seconds...")
            time.sleep(3)
        last_ip = ip

        print(f"\n=== Reading global meter {global_meter} (MCW{local_id} via {ip}) ===")
        transport = get_transport(ip=ip, port=config.PORT)
        try:
            res = read_meter(transport, local_id, global_meter)
            calculate_errors(res, applied_inputs)
            all_results.append(res)
        finally:
            try:
                transport.close()
            except Exception:
                pass
        time.sleep(0.25)

    # Save results once at the end
    save_results(all_results)
    print(f"[END] Parameter read session completed (Angle = {angle}°)")


if __name__ == "__main__":
    main()