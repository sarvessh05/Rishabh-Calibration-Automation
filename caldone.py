#!/usr/bin/env python3
"""
caldone.py
==========
Writes "Cal Done = 1.0" only for meters that passed Key Test,
and skips any meters that show FAIL or out_of_range warnings in any of
the parameter summary JSON files (meter_params, 4WS*, 3WS*).
"""

import os
import time
import json
import struct
import re
from typing import Dict, Set

import config
from transport import get_transport
import steps


# ---------------- Helper functions ----------------

def split_segments(raw_bytes: bytes):
    ascii_data = raw_bytes.decode("latin1", errors="ignore")
    return [seg for seg in ascii_data.strip().split("\r") if seg.strip()]


def extract_meter_and_payload(segment: str):
    if segment.startswith("MCW"):
        return None, None
    m = re.match(r"F(\d+),.*?,(.*)", segment)
    return (int(m.group(1)), m.group(2)) if m else (None, None)


def decode_escapes(payload: str) -> bytes:
    out = bytearray()
    i = 0
    while i < len(payload):
        if payload[i] == '^':
            if payload[i:i+2] == '^h' and i + 3 < len(payload):
                try:
                    out.append(int(payload[i+2:i+4], 16))
                    i += 4
                    continue
                except ValueError:
                    pass
            if i + 1 < len(payload):
                out.append(ord(payload[i+1]) & 0x1F)
                i += 2
                continue
        elif payload[i] == '<':
            m = re.match(r"<(\d{3})>", payload[i:])
            if m:
                v = int(m.group(1))
                if 128 <= v <= 255:
                    out.append(v)
                    i += len(m.group(0))
                    continue
        out.append(ord(payload[i]))
        i += 1
    return bytes(out)


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
        if func != 3 or byte_count < 4:
            continue

        data = frame[3:3 + byte_count]
        res["data_hex"] = data.hex().upper()

        try:
            val = struct.unpack(">f", data[:4])[0]
            res["params"]["cal_status"] = {"value": val}
        except Exception as e:
            res["params"]["cal_status"] = {"error": str(e)}

        break

    if not res["params"]:
        res["error"] = "no_valid_frame"
        res["raw_hex"] = raw.hex()
    return res


# ---------------- Load key test + parameter validation ----------------

def load_passed_meters() -> Set[int]:
    """
    Load meters that passed Key Test only.
    """
    passed = set(range(1, config.METER_COUNT + 1))

    try:
        with open(os.path.join(config.RESULTS_DIR, 'key_test_log.json')) as f:
            data = json.load(f)
        key_pass = {
            int(m) for m, vals in data.items()
            if all(v == "PASS" for v in vals.values())
        }
        passed &= key_pass
        print(f"[INFO] Key Test passed meters: {sorted(key_pass)}")
    except Exception as e:
        print(f"[WARN] Could not load key_test_log.json: {e}")

    print(f"✅ Meters eligible (before param file check): {sorted(passed)}")
    return passed


def load_problematic_meters() -> Set[int]:
    """
    Load all meters that show 'FAIL' or 'out_of_range' warnings
    in any of the parameter JSON files.
    """
    files_to_check = [
        "meter_params.json",
        "4WS1.json", "4WS2.json",
        "3WS1.json", "3WS2.json", "3WS3.json", "3WS4.json"
    ]
    problematic = set()
    base = config.RESULTS_DIR

    for fname in files_to_check:
        fpath = os.path.join(base, fname)
        if not os.path.exists(fpath):
            continue

        try:
            with open(fpath) as f:
                data = json.load(f)

            if not isinstance(data, list):
                continue

            for entry in data:
                meter = entry.get("global_meter")
                params = entry.get("params", {})
                for pvals in params.values():
                    warn = pvals.get("warning")
                    pf = pvals.get("pass_fail")
                    # If even one parameter fails or has warning, mark as problematic
                    if warn == "out_of_range" or pf == "FAIL":
                        problematic.add(meter)
                        break
        except Exception as e:
            print(f"[WARN] Failed to parse {fname}: {e}")
            continue

    if problematic:
        print(f"⚠️ Problematic meters found in parameter JSONs: {sorted(problematic)}")
    else:
        print("[INFO] No problematic meters found.")
    return problematic


# ---------------- Summary Table ----------------

def print_summary_table(results: Dict[int, Dict]):
    print("\n+---------+----------+-----------+--------------+")
    print("| MeterID |  Write   |  ReadVal  |    Result    |")
    print("+---------+----------+-----------+--------------+")
    for meter in sorted(results.keys()):
        data = results[meter]
        write = data.get("write", "N/A")
        read_val = data.get("read_val", "N/A")
        result = data.get("result", "N/A")
        print(f"| {meter:<7} | {write:<8} | {str(read_val):<9} | {result:<12} |")
    print("+---------+----------+-----------+--------------+\n")


# ---------------- Main logic ----------------

def run_caldone():
    passed_meters = load_passed_meters()
    problematic_meters = load_problematic_meters()

    # Final eligible meters = passed key test AND not problematic
    eligible = passed_meters - problematic_meters
    print(f"✅ Final meters eligible for CAL DONE: {sorted(eligible)}")

    results = {}
    last_ip = None

    for global_meter in range(1, config.METER_COUNT + 1):
        if global_meter not in eligible:
            print(f"⚠️  Skipping meter {global_meter} (failed or problematic)")
            results[global_meter] = {'write': 'SKIPPED', 'result': 'TEST_FAIL'}
            continue

        ip_idx = 0 if global_meter <= 10 else 1
        ip, port = config.METER_CONNECTIONS[ip_idx]
        local_id = (global_meter - 1) % 10 + 1

        if ip != last_ip:
            if last_ip is not None:
                print(f"[INFO] Switching to {ip}, waiting 3 seconds...")
                time.sleep(3)
            last_ip = ip

        transport = get_transport(ip, port)
        try:
            # Write Cal Done = 1.0
            write_cmd = steps.build_modbus_write_multiple_float(
                meter_num=local_id, slave_id=1, start_addr=0x17B8, values=[1.0]
            )
            print(write_cmd)
            transport.send_mcw(write_cmd)
            transport.recv_all(timeout=2.0)
            results[global_meter] = {'write': 'OK'}

            time.sleep(3)

            # Verify
            read_cmd = steps.build_modbus_read_cmd(
                meter_num=local_id, slave_id=1, start_addr=0x17B8, reg_count=2
            )
            print(read_cmd)
            transport.send_mcw(read_cmd)
            raw_read = transport.recv_all(timeout=2.0)
            print(raw_read)
            parsed = parse_meter_response(raw_read, local_id, global_meter)

            if 'error' in parsed:
                results[global_meter].update({'read_val': 'ERROR', 'result': 'PARAM_FAIL'})
                print(f"⚠️  Meter {global_meter} parameter read failed")
            else:
                val = parsed["params"]["cal_status"]["value"]
                results[global_meter].update({'read_val': val})
                results[global_meter]['result'] = 'CAL_SUCCESS' if val == 10.0 else 'CAL_FAIL'

        finally:
            transport.close()

        time.sleep(0.25)

    os.makedirs(config.RESULTS_DIR, exist_ok=True)
    log_file = os.path.join(config.RESULTS_DIR, 'caldone_log.json')
    with open(log_file, 'w') as f:
        json.dump(results, f, indent=2)

    print_summary_table(results)
    print(f"✅ Cal Done session complete. Log saved to {log_file}")
    return results


if __name__ == '__main__':
    run_caldone()