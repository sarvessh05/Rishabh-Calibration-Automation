#!/usr/bin/env python3
"""
quant_compensation_3p4w_parallel.py — Grouped, socket-aware calibration runner (final)

Behavior summary:
- Executes ONE calibration *group* per run (group = multiple STEPS).
- For the chosen calibration group it runs the group on each socket (transport) in sequence.
  Example: run group 1 on socket0 -> then group 1 on socket1 -> then script exits.
- After both sockets are done for that group it increments the bookmark (current_cal_group)
  so the next run will start the next calibration group.
- poll_ready_all has 2-phase timeout + elimination (marks problematic meters persistently by GLOBAL meter numbers).
- Progress stored at PROGRESS_FILE; problematic meters stored at PROBLEMATIC_FILE.
- IMPORTANT: MCW / Modbus slave IDs sent to a socket are rebased to that socket's local meter IDs
  (1..METERS_PER_SOCKET). Global meter numbers are used only for bookkeeping and problematic marking.
"""

import os
import time
import re
import json
from datetime import datetime
import config
import steps
from transport import get_transport

# ---------------- Constants ----------------
ADDR_9601 = 0x2580
REG_CAL_DONE = 0x17B8
SLAVE_ID = 1
READY_RESPONSE = "01030440000000EFF3"

# Logging / files
LOG_DIR = LOG_DIR = r"D:\DO_NOT_DELETE_TESTING_SCRIPTS\Logs"
LOG_FILE = os.path.join(LOG_DIR, "cal_log.txt")
PROGRESS_FILE = os.path.join(LOG_DIR, "progress.json")
PROBLEMATIC_FILE = os.path.join(LOG_DIR, "problematic_meters.json")

# Behavior tunables
METERS_PER_SOCKET = getattr(config, "METERS_PER_SOCKET", 10)
COMMAND_GAP = getattr(config, "COMMAND_GAP", 0.3)

# ---------------- Helpers: logging & JSON -----------------
def log(msg: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    os.makedirs(LOG_DIR, exist_ok=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")

def load_progress():
    if os.path.exists(PROGRESS_FILE):
        try:
            with open(PROGRESS_FILE, "r") as f:
                return json.load(f)
        except Exception:
            log("Warning: failed to parse progress.json, starting fresh")
    return {"current_cal_group": 1}

def save_progress(progress):
    os.makedirs(LOG_DIR, exist_ok=True)
    with open(PROGRESS_FILE, "w") as f:
        json.dump(progress, f, indent=2)

def load_problematic():
    if os.path.exists(PROBLEMATIC_FILE):
        try:
            with open(PROBLEMATIC_FILE, "r") as f:
                return set(int(x) for x in json.load(f))
        except Exception:
            log("Warning: failed to parse problematic_meters.json, starting empty")
            return set()
    return set()

def save_problematic(problematic_set):
    os.makedirs(LOG_DIR, exist_ok=True)
    lst = sorted(int(x) for x in problematic_set)
    with open(PROBLEMATIC_FILE, "w") as f:
        json.dump(lst, f, indent=2)
    log(f"Saved problematic meters: {lst}")

# ---------------- Decoder / comm utilities -----------------
def split_segments(raw_data):
    if isinstance(raw_data, bytes):
        raw_data = raw_data.decode("latin1", errors="ignore")
    return [seg for seg in raw_data.strip().split("\r") if seg.strip()]

def extract_meter_and_payload(segment: str):
    m = re.match(r"F(\d+),.*?,(.*)", segment)
    if m:
        return int(m.group(1)), m.group(2)
    return None, None

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
            match = re.match(r"<(\d{3})>", payload[i:])
            if match:
                value = int(match.group(1))
                if 128 <= value <= 255:
                    out.append(value)
                    i += len(match.group(0))
                    continue
        out.append(ord(payload[i]))
        i += 1
    return out.hex().upper()

def send_and_log(transport, mcw_cmd: str, description: str = "", local_meter_id: int | None = None, global_meter: int | None = None):
    """
    Sends an MCW command to the transport. local_meter_id is used for logging / building the
    MCW command context (MCW<local_id>). global_meter is only for logging/bookkeeping.
    """
    prefix = ""
    if global_meter is not None:
        prefix += f"G{global_meter} "
    if local_meter_id is not None:
        prefix += f"L{local_meter_id} "
    log(f"{prefix}SEND ({description}): {mcw_cmd}")
    transport.send_mcw(mcw_cmd)
    #time.sleep(COMMAND_GAP)

    raw = transport.recv_all(2.0)

    if not raw:
        log(f"{prefix}RECV: (no response)")
        return ""

    segments = split_segments(raw)
    decoded_segments = []

    for seg in segments:
        log(f"{prefix}RECV RAW: {seg}")
        meter_id, payload = extract_meter_and_payload(seg)
        if meter_id and payload:
            decoded = decode_escapes(payload)
            decoded_segments.append(decoded)
            log(f"{prefix}DECODED: {decoded}")

    return "".join(decoded_segments)

# ---------------- Command helpers (write/read) -----------------
def write_code_local(transport, local_id: int, code: int, wait_sec: int = 7):
    """
    Write modbus code to a meter using local meter id (1..N for that socket).
    """
    cmd = steps.build_modbus_write_multiple_float(local_id, SLAVE_ID, ADDR_9601, [code])
    send_and_log(transport, cmd, f"write code {code}", local_meter_id=local_id)
    if wait_sec > 0:
        log(f"L{local_id}: Waiting {wait_sec}s...")
        time.sleep(wait_sec)

def write_cal_done_local(transport, local_id: int):
    cmd = steps.build_modbus_write_multiple_float(local_id, SLAVE_ID, REG_CAL_DONE, [1])
    send_and_log(transport, cmd, "update calibration done status", local_meter_id=local_id)
    time.sleep(0.5)

def read_cal_status_local(transport, local_id: int):
    cmd = steps.build_modbus_read_cmd(local_id, SLAVE_ID, REG_CAL_DONE, 2)
    resp = send_and_log(transport, cmd, "read calibration status", local_meter_id=local_id)
    # Try to parse last 4 hex digits if present; if not, return -1
    try:
        if resp:
            # often response is hex string; parse last 4 digits if possible
            last4 = resp[-4:]
            return int(last4, 16)
    except Exception:
        pass
    return -1

# ---------------- Poll with elimination (accepts list of (global, local)) -----------------
def poll_ready_all_localpairs(transport, global_local_pairs, delay=1.2, first_phase=30, second_phase=40):
    """
    Poll until READY_RESPONSE is seen for each local meter.
    Accepts `global_local_pairs` = list of (global_meter_num, local_meter_id)
    Returns: set of problematic global meter numbers (those not ready after both phases).
    """
    start_time = time.time()
    pending = {local: global_ for (global_, local) in global_local_pairs}  # map local -> global
    problematic = set()

    total_timeout = first_phase + second_phase
    log(f"Start polling local meters {sorted(pending.keys())} (global mapping: {pending}) total timeout {total_timeout}s")

    while pending:
        elapsed = time.time() - start_time

        if elapsed > total_timeout:
            log(f"Timeout reached ({total_timeout}s). Remaining local IDs not ready: {sorted(pending.keys())}")
            problematic.update(pending.values())  # add remaining global numbers
            break
        elif elapsed > first_phase:
            log(f"Elimination mode for remaining local IDs: {sorted(pending.keys())} (extra {second_phase - (elapsed - first_phase):.1f}s left)")

        for local_id in list(pending.keys()):
            cmd = steps.build_modbus_read_cmd(local_id, SLAVE_ID, REG_CAL_DONE, 2)
            decoded = send_and_log(transport, cmd, "poll ready", local_meter_id=local_id, global_meter=pending[local_id])

            if READY_RESPONSE in decoded:
                log(f"L{local_id} (G{pending[local_id]}) ready.")
                pending.pop(local_id, None)
            else:
                log(f"L{local_id} (G{pending[local_id]}) still busy / no ready response.")
                time.sleep(1.0)

        if pending:
            time.sleep(delay)

    if problematic:
        log(f"Marked problematic (global) meters: {sorted(problematic)}")
    else:
        log("All local meters reported ready within allowed time.")

    return problematic

# ---------------- Calibration Steps -----------------
STEPS = [
    {"desc": "Change Connection per 3P3W", "code": None, "wait": 0, "input_change": False, "busy_poll": False},
    {"desc": "Turn ON Calmet - Input Step 1", "code": None, "wait": 0, "input_change": False, "busy_poll": False},
    {"desc": "Unlock Calibration", "code": 2023, "wait": 0, "input_change": False, "busy_poll": False},
    {"desc": "Import Energy Quantization", "code": 904, "wait": 1, "input_change": False, "busy_poll": True},
    {"desc": "Apply Input Step 2", "code": None, "wait": 0, "input_change": False, "busy_poll": False},
    {"desc": "Export Energy Quantization", "code": 905, "wait": 1, "input_change": False, "busy_poll": True},
    {"desc": "Apply Input Step 3", "code": None, "wait": 0, "input_change": False, "busy_poll": False},
    {"desc": "Import Current Quantization", "code": 906, "wait": 1, "input_change": False, "busy_poll": True},
    {"desc": "Apply Input Step 4", "code": None, "wait": 0, "input_change": False, "busy_poll": False},
    {"desc": "Export Current Quantization", "code": 907, "wait": 1, "input_change": False, "busy_poll": True},
    {"desc": "Export Voltage Quantization", "code": 908, "wait": 1, "input_change": False, "busy_poll": True},
    {"desc": "Save Coefficient in EEPROM", "code": 909, "wait": 2, "input_change": False, "busy_poll": False},
    # {"desc": "Update Calibration Done Status", "code": "cal_done", "wait": 0, "input_change": False, "busy_poll": False},
    # {"desc": "Read Calibration Status", "code": "read_status", "wait": 0, "input_change": False, "busy_poll": False},
]

# Groups
CAL_GROUPS = [
    STEPS[0:4],    # Group 1 (48,49,50)
    STEPS[4:6],    # Group 2 (51,52,53)
    STEPS[6:8],   # Group 3 (54,55,56,58)
    STEPS[8:12],
    # STEPS[11:12],    # Group 4 (59,60,61,62)
]

# ---------------- Helpers: sockets <-> meter ranges -----------------
def get_all_socket_entries():
    """Return list of socket tuples from config (ip,port)."""
    if hasattr(config, "METER_CONNECTIONS") and config.METER_CONNECTIONS:
        return list(config.METER_CONNECTIONS)
    return [(getattr(config, "SOCKET_IP", "192.168.100.100"),
             getattr(config, "SOCKET_PORT", 12345))]

def meters_for_socket_index(idx):
    """Return list of GLOBAL meter numbers assigned to socket index (0-based)."""
    total = getattr(config, "METER_COUNT", 0)
    start = idx * METERS_PER_SOCKET + 1
    end = min(total, start + METERS_PER_SOCKET - 1)
    if start > end:
        return []
    return list(range(start, end + 1))

# ---------------- Run one calibration group on one socket -----------------
def calibrate_group_on_socket(transport, socket_ip_port, group_steps, problematic_set):
    """
    Run group_steps on a single socket transport.
    - problematic_set contains GLOBAL meter numbers to skip.
    - All sends to transport use LOCAL meter IDs (1..N for that socket).
    Returns a set of newly discovered problematic GLOBAL meters.
    """
    sockets = get_all_socket_entries()
    ip, port = socket_ip_port
    idx = sockets.index((ip, port))
    global_meter_list = meters_for_socket_index(idx)
    if not global_meter_list:
        log(f"No meters assigned to socket {ip}:{port}")
        return set()

    # map global -> local (local numbering starts at 1)
    global_to_local = {g: (g - global_meter_list[0] + 1) for g in global_meter_list}
    active_pairs = [(g, global_to_local[g]) for g in global_meter_list if g not in problematic_set]

    if not active_pairs:
        log(f"All meters on {ip}:{port} are marked problematic or skipped; nothing to do.")
        return set()

    log(f"Running group on {ip}:{port} for global meters: {[g for g, _ in active_pairs]} (local IDs: {[l for _, l in active_pairs]})")
    new_problematic = set()

    for step in group_steps:
        log(f"Step: {step['desc']}")
        # input_change steps: operator must set Calmet properly BEFORE we proceed with this socket
        if step.get("input_change"):
            log("Please ensure Calmet is set as required for this step for this socket.")
            input("Press Enter to continue after setting Calmet input for this socket...")

        if step.get("busy_poll"):
            # busy_poll requires we first optionally send a code to all active local IDs (if step has code)
            if isinstance(step.get("code"), int):
                code = step["code"]
                for g, local in list(active_pairs):
                    send_and_log(transport, steps.build_modbus_write_multiple_float(local, SLAVE_ID, ADDR_9601, [code]),
                                 f"pre-busy write code {code}", local_meter_id=local, global_meter=g)
                    time.sleep(step.get("wait", 0))
            time.sleep(7)
            # Now poll until ready: we need to use list of (global, local)
            problematic_here = poll_ready_all_localpairs(transport, active_pairs)
            if problematic_here:
                new_problematic.update(problematic_here)
                # update active_pairs to remove newly problematic meters
                active_pairs = [(g, l) for (g, l) in active_pairs if g not in new_problematic]
        else:
            # Non-busy steps: either write code or nothing (apply input)
            code = step.get("code")
            wait = step.get("wait", 0)
            if isinstance(code, int):
                for g, local in list(active_pairs):
                    write_code_local(transport, local, code, wait_sec=wait)
            elif code is None:
                # input-change or purely operator step; nothing to send (we prompted above if input_change)
                pass

    return new_problematic

# ---------------- Main orchestration -----------------
def run_quant_compensation_3p4w():
    log("=== Starting 3P4W Quant Compensation Calibration (grouped per run) ===")

    sockets = get_all_socket_entries()
    if not sockets:
        raise RuntimeError("No METER_CONNECTIONS defined in config.")

    total_meters = getattr(config, "METER_COUNT", 0)
    if total_meters <= 0:
        raise RuntimeError("METER_COUNT not set or zero in config.")

    progress = load_progress()
    problematic = load_problematic()

    current_group = int(progress.get("current_cal_group", 1))
    if current_group < 1 or current_group > len(CAL_GROUPS):
        log("All calibration groups completed (or invalid bookmark). Resetting to group 1.")
        current_group = 1
        progress["current_cal_group"] = 1
        save_progress(progress)

    log(f"Resuming at calibration group {current_group} of {len(CAL_GROUPS)}")
    group_steps = CAL_GROUPS[current_group - 1]

    # Prompt operator once BEFORE opening transports if this group includes an initial input_change step.
    if any(s.get("input_change", False) for s in group_steps):
        log("This calibration group requires Calmet input change BEFORE running on sockets.")
        input("Apply Calmet input for this group now, then press Enter to continue...")

    per_socket_done_key = lambda ip, port, grp: f"group_{grp}_socket_{ip.replace('.','_')}_{port}_done"

    for (ip, port) in sockets:
        key = per_socket_done_key(ip, port, current_group)
        if progress.get(key):
            log(f"Skipping {ip}:{port} for group {current_group} (already done previously).")
            continue

        transport = None
        try:
            log(f"Opening transport {ip}:{port}")
            transport = get_transport(ip, port)
            new_problems = calibrate_group_on_socket(transport, (ip, port), group_steps, problematic)
            if new_problems:
                problematic.update(new_problems)
                save_problematic(problematic)
            # mark socket done for this group
            progress[key] = True
            save_progress(progress)
            log(f"Completed group {current_group} on {ip}:{port}")
        except Exception as exc:
            log(f"Error while processing {ip}:{port}: {exc}")
            # do not mark as done; operator can re-run later
        finally:
            if transport:
                try:
                    transport.close()
                except Exception:
                    pass

    # Check completion across all sockets
    done_flags = [progress.get(per_socket_done_key(ip, port, current_group)) for (ip, port) in sockets]
    if all(bool(f) for f in done_flags):
        # advance bookmark
        if current_group < len(CAL_GROUPS):
            progress["current_cal_group"] = current_group + 1
            save_progress(progress)
            log(f"Calibration group {current_group} completed across all sockets.")
            log(f"Please change Calmet input as per next group's requirements and re-run the script to continue (it will start group {current_group + 1}).")
        else:
            log("All calibration groups completed across all sockets.")
            log(f"Problematic meters (if any) saved at: {PROBLEMATIC_FILE}" if os.path.exists(PROBLEMATIC_FILE) else "No problematic meters recorded.")
            # Optionally keep progress or remove it — leaving it is safer.
        log("Exiting now. Restart the script after making the required Calmet changes.")
        raise SystemExit(0)
    else:
        log("Not all sockets completed for this group. Re-run the script to continue remaining sockets.")
        raise SystemExit(0)

if __name__ == "__main__":
    run_quant_compensation_3p4w()