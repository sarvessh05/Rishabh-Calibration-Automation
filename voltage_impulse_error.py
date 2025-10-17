#!/usr/bin/env python3
"""
voltage_impulse_error.py — Post-calibration Error Measurement
-------------------------------------------------------------
- Performs voltage and impulse measurements for all meters.
- Uses in-house Modbus decoder (same as readparameters.py).
- Supports multiple sockets dynamically based on TOTAL_METERS.
"""

import os, time, json, struct, re
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import config, steps
from transport import get_transport

# ==========================
# Paths and Logging
# ==========================
LOGS_DIR = os.path.abspath(getattr(config, "RESULTS_DIR", "."))
STATE_FILE = os.path.join(LOGS_DIR, "error_progress.json")
LOG_FILE = os.path.join(LOGS_DIR, "combined_error_log.txt")
SOCKET_TIMEOUT = getattr(config, "SOCKET_TIMEOUT", 1.0)
COMMAND_GAP = getattr(config, "COMMAND_GAP", 0.3)
TOTAL_METERS = getattr(config, "METER_COUNT", 0)

# ==========================
# Meter Address Mapping
# ==========================
WRITE_ADDRS = {
    "unlock": 0x2580,
    "R_upf": 0x25CC, "R_lag": 0x25CE, "R_volt": 0x25D0,
    "Y_upf": 0x25D2, "Y_lag": 0x25D4, "Y_volt": 0x25D6,
    "B_upf": 0x25D8, "B_lag": 0x25DA, "B_volt": 0x25DC,
    "compute": 0x2580,
    "save_coeff": 0x17B8
}

PARAM_REGS = {"R": 0x0000, "Y": 0x0002, "B": 0x0004}
IMPULSE_KEYS = ["R_upf", "R_lag", "Y_upf", "Y_lag", "B_upf", "B_lag"]

IMPULSE_SETUP_COMMANDS = [
    "ECRES0,0;CTRES0,0;TIRES0,0;EHRES0",
    "MODE1;VER;VER0;RTH",
    "DITX0,2,", "DITX0,3,",
    "DISG0,L(H0,127,22)S",
    "DIAG0,V1(C0,0,127,0,TX1)",
    "TIRES0,0", "TIIN0,1,R",
    "TISP0,1,2,2", "TISP0,1,4,1",
    "TITR0,1,1,0", "TITR0,1,1,2.0",
    "TISU0,1,1", "TISTA0,1",
    "WRRES#,0", "WRIN#,1,F1",
    "OPO0,T1,0", "SU1", "MP", "MPI0",
    "INC*,F1,135000000,1", "WRNUL#,1", "WRSTA#,1",
    "INC*,F1,16875,1", "WRNUL#,1", "WRSTA#,1",
    "DITX0,1,RISHABH",
    "DITX0,2,\x1b5SSI400+",
    "ECL0,1,-0.8,0.8",
    "ECC1,1,1000,0","ECC2,1,1000,0","ECC3,1,1000,0","ECC4,1,1000,0",
    "ECC5,1,1000,0","ECC6,1,1000,0","ECC7,1,1000,0","ECC8,1,1000,0",
    "ECC9,1,1000,0","ECC10,1,1000,0",
    "ECI$ffc,1,5,0",
    "DISG0,L(H0,127,22)S",
    "DISG$0,V1(C0,0,127,0,TX2)",
    "DIAG$ffc,L(H0,81,48)L(H81,127,35)L(V81,22,48)",
    "DIAG$ffc,R(0,0,EC1.2)",
    "DIAG$ffc,V1(r7,1,127,0,EC1.1:%.3s%%)",
    "DIAG$ffc,V2(R0,24,80,1,EC1.7:%u )",
    "DIAG$ffc,V3(R0,37,80,1,EC1.8:%u )",
    "DIAG$ffc,V4(R82,24,127,1,EC1.3:%u )",
    "WRNUL#,1","WRSTA#,1",
    "ECRF*,1,F1","ECIN$ffc,1,S1",
    "ECE0,1,2","ECSP0,1,1,2",
    "ECSU$ffc,1,1","ECSIN0,1,0",
    "WR?#,1,2","ECSTA$ffc,1","WR?#,1,2"
]

# ==========================
# In-house Decoder
# ==========================
def split_segments(raw_bytes: bytes) -> List[str]:
    ascii_data = raw_bytes.decode("latin1", errors="ignore")
    return [seg for seg in ascii_data.strip().split("\r") if seg.strip()]

def extract_meter_and_payload(segment: str) -> Tuple[Optional[int], Optional[str]]:
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

def decode_modbus_response(raw: bytes, local_id: int) -> Optional[float]:
    for seg in split_segments(raw):
        m_id, payload = extract_meter_and_payload(seg)
        if m_id != local_id or not payload:
            continue
        frame = decode_escapes(payload)
        if len(frame) < 7:
            continue
        slave, func, byte_count = frame[0], frame[1], frame[2]
        if func != 3 or byte_count < 4:
            continue
        data = frame[3:3+4]
        try:
            return struct.unpack(">f", data)[0]
        except:
            pass
    return None

# ==========================
# State Helpers
# ==========================
def load_state() -> Dict:
    if os.path.exists(STATE_FILE):
        try:
            return json.load(open(STATE_FILE))
        except:
            pass
    return {"completed_step": 0, "results": {}, "steps": []}

def save_state(state: Dict):
    os.makedirs(LOGS_DIR, exist_ok=True)
    json.dump(state, open(STATE_FILE, "w"), indent=2)

def log_step(state: Dict, step_no: int, message: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    state.setdefault("steps", []).append({
        "step_no": step_no,
        "message": message,
        "timestamp": ts,
        "status": "pending"
    })
    save_state(state)
    log(f"Step {step_no}: {message}")

def complete_step(state: Dict, step_no: int):
    for s in state.get("steps", []):
        if s["step_no"] == step_no:
            s["status"] = "done"
            s["completed_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    state["completed_step"] = step_no
    save_state(state)
    log(f"Step {step_no} completed.")

def float_to_hex(val: Optional[float]) -> str:
    if val is None:
        return "N/A"
    try:
        return f"{struct.unpack('>I', struct.pack('>f', float(val)))[0]:08X}"
    except:
        return "N/A"

# ==========================
# Socket Management
# ==========================
_last_sock: Optional[Tuple[str, int]] = None
_socket_transports: dict[Tuple[str, int], object] = {}  # cache for transports

def _get_sockets() -> List[Tuple[str, int]]:
    if hasattr(config, "METER_CONNECTIONS") and config.METER_CONNECTIONS:
        return list(config.METER_CONNECTIONS)
    return [(getattr(config, "SOCKET_IP", "192.168.100.100"),
             getattr(config, "SOCKET_PORT", 12345))]

def build_socket_mapping(total_meters: int) -> dict[Tuple[str,int], range]:
    """
    Build socket-to-meter ranges dynamically based on TOTAL_METERS.
    Each socket handles 10 meters.
    """
    sockets = _get_sockets()
    meters_per_socket = 10
    mapping = {}
    remaining = total_meters
    current_meter = 1
    for sock in sockets:
        start = current_meter
        end = min(current_meter + meters_per_socket, total_meters + 1)
        mapping[sock] = range(start, end)
        current_meter = end
        if current_meter > total_meters:
            break
    return mapping

def _find_socket_for_meter(meter: int, socket_map: dict) -> Tuple[Tuple[str,int], int]:
    for sock, rng in socket_map.items():
        if meter in rng:
            local_meter = meter - rng.start + 1
            return sock, local_meter
    raise ValueError(f"No socket mapping found for meter {meter}")

def open_transport(ip: str, port: int):
    global _last_sock, _socket_transports
    sock_key = (ip, port)
    if _last_sock != sock_key:
        if _last_sock is not None:
            log(f"Switching socket from {_last_sock[0]}:{_last_sock[1]} to {ip}:{port}, wait 3s...")
            time.sleep(3)
        _last_sock = sock_key
    if sock_key not in _socket_transports:
        _socket_transports[sock_key] = get_transport(ip, port)
    return _socket_transports[sock_key]

def get_transport_for_meter(meter: int, socket_map: dict):
    sock, local_meter = _find_socket_for_meter(meter, socket_map)
    transport = open_transport(*sock)
    return transport, local_meter

# ==========================
# Voltage Measurement
# ==========================
def measure_voltage_phase_all_meters(phase: str, step_no: int):
    state = load_state()
    log_step(state, step_no, f"Voltage measurement for phase {phase}")
    socket_map = build_socket_mapping(TOTAL_METERS)
    reg_addr = PARAM_REGS[phase]

    for meter in range(1, TOTAL_METERS + 1):
        t, local_id = get_transport_for_meter(meter, socket_map)
        vals = []
        for _ in range(10):
            cmd = steps.build_modbus_read_cmd(local_id, 1, reg_addr, 2)
            t.send_mcw(cmd)
            raw = t.recv_all(SOCKET_TIMEOUT)
            val = decode_modbus_response(raw, local_id)
            if val is not None and 300 <= val <= 330:
                vals.append(val)
            time.sleep(COMMAND_GAP)
        avg = sum(vals)/len(vals) if vals else None
        err = (avg - 315.0)/315.0 if avg else None
        state["results"].setdefault(f"Voltage_{phase}", {})[f"meter_{meter}"] = {
            "values": vals, "average": avg, "error": err, "ieee": float_to_hex(err)
        }
        log(f"Meter {meter} phase {phase}: {vals}, avg={avg}, error={err}")

    for t in set(_socket_transports.values()):
        t.close()
    save_state(state)
    complete_step(state, step_no)

# ==========================
# Impulse Measurement
# ==========================
def measure_impulse_for_key(key: str, step_no: int):
    state = load_state()
    log_step(state, step_no, f"Impulse measurement for {key}")
    socket_map = build_socket_mapping(TOTAL_METERS)
    trans = {sock: open_transport(*sock) for sock in socket_map}
    collected = {m: None for m in range(1, TOTAL_METERS + 1)}

    try:
        for t in trans.values():
            for cmd in IMPULSE_SETUP_COMMANDS:
                t.send_mcw(cmd)
                time.sleep(0.025)

        start_time = time.time()
        timeout = 60

        while time.time() - start_time < timeout:
            for sock, t in trans.items():
                raw = t.recv_all(SOCKET_TIMEOUT)
                if not raw:
                    continue
                ascii_data = raw.decode("latin1", errors="ignore").strip()
                matches = re.findall(r"F(\d+),EC1\.1,(==\.==|[-\d.]+)", ascii_data)
                if not matches:
                    continue
                rng = socket_map[sock]
                for mcw_str, val_str in matches:
                    if val_str == "==.==":
                        continue
                    try:
                        mcw_num = int(mcw_str)
                        val = float(val_str)
                        meter = rng.start + mcw_num - 1
                        if meter in collected and collected[meter] is None:
                            collected[meter] = val
                            log(f"Meter {meter} ({sock[0]}:{sock[1]}) -> {val}")
                    except ValueError:
                        continue
            if all(collected[m] is not None for m in collected):
                break

        for meter, val in collected.items():
            state["results"].setdefault(key, {})[f"meter_{meter}"] = {
                "average": val, "ieee": float_to_hex(val) if val is not None else None
            }

        save_state(state)
        complete_step(state, step_no)

    finally:
        for t in trans.values():
            t.close()
        save_state(state)
        complete_step(state, step_no)

# ==========================
# Logging
# ==========================
def log(msg: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    os.makedirs(LOGS_DIR, exist_ok=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")

# ==========================
# Write Calibration
# ==========================
def write_three_measurement_cal(meter_num: int, errors: dict):
    socket_map = build_socket_mapping(TOTAL_METERS)
    sock, local_meter = _find_socket_for_meter(meter_num, socket_map)
    trans = open_transport(*sock)

    cmd_unlock = steps.build_modbus_write_multiple_float(local_meter, 1, WRITE_ADDRS["unlock"], [2023.0])
    trans.send_mcw(cmd_unlock)
    log(f"Meter {meter_num}: unlocked")
    time.sleep(1)

    for key in WRITE_ADDRS:
        if key in errors:
            cmd = steps.build_modbus_write_multiple_float(local_meter, 1, WRITE_ADDRS[key], [float(errors[key])])
            trans.send_mcw(cmd)
            log(f"Meter {meter_num}: Written {key} error {errors[key]}")
            time.sleep(1)

    cmd_compute = steps.build_modbus_write_multiple_float(local_meter, 1, WRITE_ADDRS["compute"], [900.0])
    trans.send_mcw(cmd_compute)
    log(f"Meter {meter_num}: Triggered coefficient computation")
    time.sleep(1)

    cmd_save = steps.build_modbus_write_multiple_float(local_meter, 1, WRITE_ADDRS["save_coeff"], [2.0])
    trans.send_mcw(cmd_save)
    log(f"Meter {meter_num}: Saved calibration coefficients")
    time.sleep(1)

    trans.close()
    log(f"✅ Meter {meter_num}: Three-Measurement Calibration done")

# ==========================
# Orchestrator
# ==========================
STEP_SEQUENCE = [
    ("voltage", "R", 1),
    ("voltage", "Y", 2),
    ("voltage", "B", 3),
    ("impulse", "R_upf", 4),
    ("impulse", "R_lag", 5),
    ("impulse", "Y_upf", 6),
    ("impulse", "Y_lag", 7),
    ("impulse", "B_upf", 8),
    ("impulse", "B_lag", 9),
    ("write_calibration", None, 10)
]


def main():
    state = load_state()
    completed = state.get("completed_step", 0)

    for typ, arg, step_no in STEP_SEQUENCE:
        if step_no <= completed:
            continue

        if typ == "voltage":
            measure_voltage_phase_all_meters(arg, step_no)

        elif typ == "impulse":
            measure_impulse_for_key(arg, step_no)

        elif typ == "write_calibration":
            log(f"WRITE_ADDRS keys: {list(WRITE_ADDRS.keys())}")
            log(f"Available results keys: {list(state['results'].keys())}")

            # --- Key aliases (voltage mapping only) ---
            alias = {
                "R_volt": "Voltage_R",
                "Y_volt": "Voltage_Y",
                "B_volt": "Voltage_B"
            }

            for meter in range(1, TOTAL_METERS + 1):
                errors = {}

                for key in WRITE_ADDRS:
                    lookup_key = alias.get(key, key)
                    meter_data = state["results"].get(lookup_key, {}).get(f"meter_{meter}", {})

                    # Prefer 'error', fallback to 'average' (impulse uses average as error)
                    err_val = meter_data.get("error", meter_data.get("average"))

                    if err_val is not None:
                        errors[key] = err_val
                        log(f"Meter {meter}: using {lookup_key} for {key} → error={err_val}")
                    else:
                        log(f"Meter {meter}: no error/avg found for {lookup_key}, skipping key {key}")

                if errors:
                    log(f"Meter {meter}: Writing calibration errors {errors}")
                    write_three_measurement_cal(meter, errors)
                else:
                    log(f"Meter {meter}: No calibration data available, skipping.")

        log(f"Step {step_no} done. Exiting for next run.")
        return  # exit after each step

if __name__ == "__main__":
    main()