# calibration.py
"""
Calibration runner (sequential, with proper decoder)
----------------------------------------------------
- Connects to meters sequentially (1..METER_COUNT).
- Picks IP based on meter number (1–10 → .100, 11–20 → .101).
- Always sends MCW1..10 (never MCW11+).
- After switching IP/port, waits 3 seconds before sending.
- Uses full decoder (split + escape decode) for responses.
- Compares decoded reply with expected.
- Saves JSON + TXT logs.
- Displays SQL-like table summary in terminal.
"""

import time
import json
import re
import config
from transport import SocketTransport  # your custom socket wrapper


# ==========================================================
# Calibration Commands
# ==========================================================
BASE_COMMANDS = [
    (
        "MCW{m},^h01^h10^h25^h80^h00^h02^h04^h44^hFC^hE0^h00^hC0^h5E",
        ["0110258000024B2C", "01900371C0"]
    )
]


# ==========================================================
# Decoder helpers
# ==========================================================
def split_segments(raw_bytes: bytes):
    """Split raw MCW ASCII response into segments by CR."""
    ascii_data = raw_bytes.decode("latin1", errors="ignore")
    return [seg for seg in ascii_data.strip().split("\r") if seg.strip()]


def extract_meter_and_payload(segment: str):
    """
    Extract meter ID and payload.
    - Skip echoes like 'MCW1,...'
    - Real responses: 'F<n>,MCW1,...'
    """
    if segment.startswith("MCW"):
        return None, None
    m = re.match(r"F(\d+),(?:MC\w+)?,(.*)", segment)
    if m:
        return int(m.group(1)), m.group(2)
    return None, None


def decode_escapes(payload: str) -> str:
    """
    Decode escape sequences:
    - ^hXX → hex byte
    - ^X   → control char (X & 0x1F)
    - <NNN> → byte 128–255
    Returns uppercase hex string.
    """
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
            match = re.match(r"<(\d{3})>", payload[i:])
            if match:
                val = int(match.group(1))
                if 128 <= val <= 255:
                    out.append(val)
                    i += len(match.group(0))
                    continue
        out.append(ord(payload[i]))
        i += 1
    return out.hex().upper()


def parse_response(raw: bytes, mcw_num: int):
    """
    Parse response for a single MCW<n> command.
    Debug prints raw data, segments, and decoded payloads.
    """
    if not raw:
        print(" ⚠ No raw data received.")
        return ""

    # Print raw bytes as hex
    print(" Raw bytes:", " ".join(f"{b:02X}" for b in raw))

    # Split into ASCII segments
    segments = split_segments(raw)
    print(" Segments:", segments)

    # Try extracting + decoding each segment
    for seg in segments:
        meter_id, payload = extract_meter_and_payload(seg)
        print(f"  → Segment: '{seg}' | MeterID={meter_id}, Payload={payload}")
        if not meter_id or not payload:
            continue

        decoded = decode_escapes(payload)
        print(f"    Decoded payload (hex): {decoded}")

        if meter_id == mcw_num:  # Only return for the matching MCW<n>
            return decoded

    return ""  # No matching segment found


# ==========================================================
# Helper: Pick IP based on meter ID
# ==========================================================
def get_ip_for_meter(meter_id: int):
    if meter_id <= 10:
        return config.METER_CONNECTIONS[0]
    else:
        return config.METER_CONNECTIONS[1]


# ==========================================================
# Logging
# ==========================================================
def save_run_log(summary):
    try:
        with open(config.RUN_JSON, "w") as jf:
            json.dump(summary, jf, indent=2)
        with open(config.RUN_LOG, "w") as tf:
            for entry in summary.get("meters", []):
                tf.write(
                    f"{entry['name']}: {entry['status']} | Response: {entry['received']}\n"
                )
    except Exception as e:
        print(f"⚠ Failed to save logs: {e}")


def print_results_table(meter_results):
    """
    Print calibration results in SQL-like table.
    Columns: Meter | Status | Response
    """
    print("\n+-------+--------+------------------+")
    print("| Meter | Status |     Response     |")
    print("+-------+--------+------------------+")
    for entry in meter_results:
        meter = entry["name"].replace("meter ", "")
        status = entry["status"]
        response = entry["received"] if entry["received"] else "N/A"
        print("| {:<5} | {:<6} | {:<16} |".format(meter, status, response))
    print("+-------+--------+------------------+\n")


# ==========================================================
# Main Calibration Routine
# ==========================================================
def run_calibration():
    passed, failed, skipped = [], [], []
    meter_results = []
    max_meters = config.METER_COUNT
    MAX_RETRIES = 3
    last_connection = None

    print("\n--- Calibration: Executing Commands ---")

    for meter_id in range(1, max_meters + 1):
        mcw_num = (meter_id - 1) % 10 + 1
        cmd_template, expected_resp = BASE_COMMANDS[0]
        cmd = cmd_template.format(m=mcw_num)
        ip, port = get_ip_for_meter(meter_id)

        print(f"\nMeter {meter_id} @ {ip}:{port}")
        transport = SocketTransport(ip=ip, port=port, timeout=config.SOCKET_TIMEOUT)

        if last_connection != (ip, port):
            print(" ⏳ New connection detected, waiting 3 seconds...")
            time.sleep(3)
            last_connection = (ip, port)

        print(f"Sending calibration command: {cmd}")
        status = "COMM_ERROR"
        received = None

        for attempt in range(1, MAX_RETRIES + 1):
            print(f" Attempt {attempt} of {MAX_RETRIES}")
            transport.send_mcw(cmd)
            raw = transport.recv_all(timeout=config.SOCKET_TIMEOUT)
            if not raw:
                print(" ❌ No response received.")
            else:
                decoded = parse_response(raw, mcw_num)
                print(f" Decoded response: {decoded}")

                if decoded:
                    received = decoded
                    if decoded in expected_resp:
                        status = "PASS"
                        time.sleep(0.3)  # short settle before break
                        break
                    else:
                        status = "FAIL"
                else:
                    status = "COMM_ERROR"

            time.sleep(0.3)

        if status == "PASS":
            passed.append(meter_id)
        elif status == "FAIL":
            failed.append(meter_id)
        else:
            skipped.append(meter_id)

        print(f"Meter {meter_id}: {status} | Received: {received}")
        meter_results.append({
            "name": f"meter {meter_id}",
            "status": status,
            "received": received,
            "command": cmd,
            "ip": ip,
        })
        transport.close()

    summary = {
        "run_time": time.ctime(),
        "meters": meter_results,
        "passed": sorted(set(passed)),
        "failed": sorted(set(failed)),
        "skipped": sorted(set(skipped)),
    }
    save_run_log(summary)

    # ✅ Print SQL-like table
    print_results_table(meter_results)

    return passed, failed, skipped


# ==========================================================
# Entry Point
# ==========================================================
if __name__ == "__main__":
    run_calibration()