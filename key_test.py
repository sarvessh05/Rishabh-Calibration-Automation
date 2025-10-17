# key_test.py
"""
Key Testing Module
==================
This script automates the "Key Test" procedure for all connected meters
using the MCW ASCII-over-TCP protocol.

Features
--------
- Broadcast (MCW0) sent once per IP to enter Key Test mode.
- Polling always uses MCW1 … MCW10 (local IDs only).
- Global numbering (1..METER_COUNT) preserved in logs.
- Proper response decoding (split + escape handling).
- After switching IP, waits 3 seconds before polling.
- Operator popup prompt to press UP, DOWN, ENTER.
- Results saved as JSON and displayed as an SQL-like table.

Output
------
1. key_test_log.json → JSON with full results
2. SQL-like table printed in terminal
"""

import os
import time
import json
import re
import tkinter as tk
from tkinter import messagebox

import config
from transport import get_transport
import steps


# ============================================================
# Helpers
# ============================================================

def split_segments(raw_bytes: bytes):
    ascii_data = raw_bytes.decode("latin1", errors="ignore")
    return [seg for seg in ascii_data.strip().split("\r") if seg.strip()]


def extract_meter_and_payload(segment: str):
    if segment.startswith("MCW"):
        return None, None
    m = re.match(r"F(\d+),.*?,(.*)", segment)
    return (int(m.group(1)), m.group(2)) if m else (None, None)


def decode_escapes(payload: str) -> str:
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
        elif payload[i] == "<":
            m = re.match(r"<(\d{3})>", payload[i:])
            if m:
                v = int(m.group(1))
                if 128 <= v <= 255:
                    out.append(v)
                    i += len(m.group(0))
                    continue
        out.append(ord(payload[i]))
        i += 1
    return out.hex().upper()


def parse_key_response(raw: bytes, ip: str, start_global: int) -> dict:
    results = {}
    for seg in split_segments(raw):
        meter_id, payload = extract_meter_and_payload(seg)
        if meter_id and payload:
            global_id = start_global + (meter_id - 1)
            results[global_id] = decode_escapes(payload)
    return results


def get_local_meter_num(global_meter: int) -> int:
    return ((global_meter - 1) % 10) + 1


def print_results_table(results: dict):
    headers = ["Meter", "UP", "DOWN", "ENTER"]
    print("\n+-------+-------+-------+--------+")
    print("| {:<5} | {:<5} | {:<5} | {:<6} |".format(*headers))
    print("+-------+-------+-------+--------+")

    for meter in sorted(results.keys()):
        row = results[meter]
        up = row.get("UP", "N/A")
        down = row.get("DOWN", "N/A")
        enter = row.get("ENTER", "N/A")
        if up == down == enter == "CAL_FAIL":
            print(f"| {meter:<5} | {'-':<5} | {'-':<5} | {'CAL_FAIL':<6} |")
        else:
            print(f"| {meter:<5} | {up:<5} | {down:<5} | {enter:<6} |")

    print("+-------+-------+-------+--------+\n")


# ============================================================
# Config
# ============================================================

ONLY_CALIBRATED = True
CAL_RESULTS_FILE = config.CAL_RESULTS_JSON
LOG_FILE = os.path.join(config.RESULTS_DIR, "key_test_log.json")

KEY_ADDRS = {
    "UP":    0x25BE,
    "DOWN":  0x25C0,
    "ENTER": 0x25C2,
}

VALID_HEX = {
    "3F800000", "40400000", "40800000",
    "40A00000", "40C00000", "40E00000", "41000000",
    "41100000", "41200000"
}


# ============================================================
# Routines
# ============================================================
def load_calibrated_meters():
    """
    Load calibration log and determine which meters to skip.
    Returns:
      - meters_to_poll: list of global IDs to actually poll
      - failed_cal: set of meters failed in calibration (skip comm)
    """
    all_meters = list(range(1, config.METER_COUNT + 1))
    failed_cal = set()
    meters_to_poll = set(all_meters)

    try:
        with open(CAL_RESULTS_FILE, "r") as f:
            data = json.load(f)
        for entry in data.get("meters", []):
            meter_name = entry.get("name", "")
            status = entry.get("status", "")
            if not meter_name.startswith("meter "):
                continue
            meter_id = int(meter_name.replace("meter ", ""))
            if status != "PASS":
                failed_cal.add(meter_id)
                meters_to_poll.discard(meter_id)

        print(f"[INFO] Loaded calibration results: {len(all_meters) - len(failed_cal)} pollable, {len(failed_cal)} skipped due to CAL_FAIL")
        return sorted(meters_to_poll), failed_cal

    except Exception as e:
        # If file missing, assume nothing is failed: poll all
        print(f"[WARN] Cannot load calibration results: {e}")
        print("[INFO] No meters are explicitly failed. Polling all meters.")
        return all_meters, set()

    except Exception as e:
        # If file missing, treat all meters as failed
        print(f"[WARN] Cannot load calibration results: {e}")
        print("[INFO] Marking all meters as failed.")
        return [], set(all_meters)

def show_key_prompt_popup():
    root = tk.Tk()
    root.withdraw()
    messagebox.showinfo(
        "Key Press Required",
        "Step 9:\n\nPress UP → DOWN → ENTER on all meters.\n\nClick OK to continue."
    )


def run_key_tests():
    passed_meters, failed_meters = load_calibrated_meters()
    all_meters = list(range(1, config.METER_COUNT + 1))
    print(f"\n--- Key Testing on {len(all_meters)} total meter(s) ---")

    results = {m: {} for m in all_meters}  # Pre-fill results

    # Step 8: Broadcast MCW0 to all IPs
    broadcast_cmd = steps.build_modbus_write_multiple_float(
        meter_num=0, slave_id=1, start_addr=0x2580, values=[2024]
    )

    for idx, (ip, port) in enumerate(config.METER_CONNECTIONS):
        t = get_transport(ip)
        try:
            t.send_mcw(broadcast_cmd)
            print(f"  Sent MCW0 on {ip}")
        finally:
            t.close()

    # Step 9: Operator presses keys
    if config.ALLOW_OPERATOR_PROMPTS:
        show_key_prompt_popup()

    # Step 10–12: Polling per port
    for idx, (ip, port) in enumerate(config.METER_CONNECTIONS):
        start_global = idx * 10 + 1
        print(f"\n--- Polling meters on {ip} ---")
        time.sleep(3.0)
        t = get_transport(ip)
        try:
            for offset in range(10):
                global_meter = start_global + offset
                if global_meter not in all_meters:
                    continue

                # Skip failed meters but record CAL_FAIL
                if global_meter in failed_meters:
                    results[global_meter] = {
                        "UP": "CAL_FAIL",
                        "DOWN": "CAL_FAIL",
                        "ENTER": "CAL_FAIL"
                    }
                    print(f"⚠️  Skipping meter {global_meter} (failed calibration).")
                    continue

                local_id = get_local_meter_num(global_meter)
                results[global_meter] = {}

                for key, addr in KEY_ADDRS.items():
                    cmd = steps.build_modbus_read_cmd(
                        meter_num=local_id, slave_id=1,
                        start_addr=addr, reg_count=2
                    )

                    status, attempt = "NO_DATA", 0
                    while attempt < 3:
                        t.send_mcw(cmd)
                        raw = t.recv_all(timeout=2.0)
                        parsed = parse_key_response(raw, ip, start_global)
                        hex_data = parsed.get(global_meter, "")

                        print(f"[DEBUG] Meter {global_meter} {key} decoded: {hex_data}")

                        if not hex_data:
                            status = "NO_DATA"
                        elif any(v in hex_data for v in VALID_HEX):
                            status = "PASS"
                            break
                        else:
                            status = "FAIL"

                        attempt += 1
                        time.sleep(0.3)

                    results[global_meter][key] = status
                    print(f"  Meter {global_meter}: {key} = {status}")
                    time.sleep(0.3)
        finally:
            t.close()

    # Save JSON log
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    with open(LOG_FILE, "w") as f:
        json.dump(results, f, indent=2)

    # Print SQL-like table
    print_results_table(results)

    print(f"✅ Key Test complete. Log saved to {LOG_FILE}")
    return results


# ============================================================
# Entry
# ============================================================

if __name__ == "__main__":
    run_key_tests()
