# readparameters.py
"""
Read Parameters Script with Key Test Integration
================================================
- Connects to all configured meters (1..METER_COUNT).
- Skips meters that failed key test but logs them as "KEY_FAIL".
- Chooses IP based on global meter number:
    * 1–10  → 192.168.100.100
    * 11–20 → 192.168.100.101
- Always sends MCW1..10 (never MCW11+).
- Waits 3 seconds after switching IP/port.
- Decodes full Modbus frame (9 floats = 36 bytes).
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
# Param register map
# ==========================================================
PARAM_REGS = [
    ("voltage_L1", 0x0000), ("voltage_L2", 0x0002), ("voltage_L3", 0x0004),
    ("current_L1", 0x0006), ("current_L2", 0x0008), ("current_L3", 0x000A),
    ("watt_L1",    0x000C), ("watt_L2",    0x000E), ("watt_L3",    0x0010),
]

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
# Response parser
# ==========================================================
def parse_meter_response(raw: bytes, local_id: int, global_id: int) -> Dict:
    res = {"global_meter": global_id, "local_meter": local_id, "params": {}}
    segments = split_segments(raw)
    for seg in segments:
        if seg.startswith(f"MCW{local_id}"):
            continue
        m_id, payload = extract_meter_and_payload(seg)
        if m_id != local_id or not payload:
            continue
        frame = decode_escapes(payload)
        if len(frame) < 5:
            continue
        slave, func, byte_count = frame[0], frame[1], frame[2]
        if func != 3 or byte_count < 36:
            continue
        data = frame[3:3 + byte_count]
        if len(data) < 36:
            continue
        for i, (name, _) in enumerate(PARAM_REGS):
            start, end = i * 4, (i + 1) * 4
            try:
                val = struct.unpack(">f", data[start:end])[0]
                if validate_value(name, val):
                    res["params"][name] = {"value": val}
                else:
                    res["params"][name] = {"value": val, "warning": "out_of_range"}
            except Exception as e:
                res["params"][name] = {"value": None, "error": str(e)}
        break
    if not res["params"]:
        res["error"] = "no_valid_frame"
        res["raw_hex"] = raw.hex()
    return res

# ==========================================================
# Meter read
# ==========================================================
def read_meter(transport, local_id: int, global_id: int, retries: int = 3) -> Dict:
    cmd = build_modbus_read_cmd(local_id, 1, start_addr=0x0000, reg_count=18)
    for attempt in range(retries):
        transport.send_mcw(cmd)
        raw = transport.recv_all(timeout=config.SOCKET_TIMEOUT)
        if raw:
            res = parse_meter_response(raw, local_id, global_id)
            if res.get("params"):
                return res
        time.sleep(0.2)
    return {"global_meter": global_id, "local_meter": local_id, "error": "no_response"}

# ==========================================================
# IP selector + local meter mapping
# ==========================================================
def get_ip_and_local(global_meter: int):
    if global_meter <= 10:
        return "192.168.100.100", ((global_meter - 1) % 10) + 1
    else:
        return "192.168.100.101", ((global_meter - 1) % 10) + 1

# ==========================================================
# Load key test results
# ==========================================================
def load_key_test_results():
    try:
        with open(os.path.join(config.RESULTS_DIR, "key_test_log.json"), "r") as f:
            data = json.load(f)
        failed_meters = {int(m) for m, vals in data.items()
                         if any(v == "CAL_FAIL" or v == "FAIL" or v == "NO_DATA" for v in vals.values())}
        print(f"[INFO] Loaded key test results: {len(failed_meters)} meters failed key test.")
        return failed_meters
    except Exception as e:
        print(f"[WARN] Could not load key test results: {e}")
        return set()

# ==========================================================
# Save results
# ==========================================================
def save_results(results: List[Dict]):
    os.makedirs(config.RESULTS_DIR, exist_ok=True)
    out_file = os.path.join(config.RESULTS_DIR, "meters_params.json")
    with open(out_file, "w") as f:
        json.dump(results, f, indent=2)
    print(f"[INFO] Results saved to {out_file}")

# ==========================================================
# Main
# ==========================================================
def main():
    print("[START] Parameter read session")
    all_results = []
    last_ip = None
    failed_key_meters = load_key_test_results()

    for global_meter in range(1, config.METER_COUNT + 1):
        if global_meter in failed_key_meters:
            print(f"⚠️  Skipping meter {global_meter} (failed key test)")
            all_results.append({
                "global_meter": global_meter,
                "local_meter": None,
                "error": "KEY_FAIL"
            })
            continue

        ip, local_id = get_ip_and_local(global_meter)
        if ip != last_ip:
            if last_ip is not None:
                print("[INFO] Switching to", ip, "waiting 3 seconds...")
                time.sleep(3)
            last_ip = ip

        print(f"\n=== Reading global meter {global_meter} "
              f"(MCW{local_id} via {ip}) ===")
        transport = get_transport(ip=ip, port=config.PORT)
        try:
            res = read_meter(transport, local_id, global_meter)
            all_results.append(res)
        finally:
            try:
                transport.close()
            except Exception:
                pass
        time.sleep(0.25)

    save_results(all_results)
    print("[END] Parameter read session completed.")

if __name__ == "__main__":
    main()