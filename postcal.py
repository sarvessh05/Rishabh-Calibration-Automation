#!/usr/bin/env python3
"""
postcal_modern_ui.py — Post-Calibration Programming with UI Prompts
(Existing docstring unchanged)
"""

import os
import time
import json
import struct
import tkinter as tk
from tkinter import simpledialog, messagebox
from transport import SocketTransport
import config  # Import METER_COUNT from your config.py

# -------------------------
# Configuration
# -------------------------
METER_COUNT = getattr(config, "METER_COUNT", 3)
MAX_RETRIES = 1
SOCKET_TIMEOUT = 2.0

RESULTS_DIR = r"C:\Users\rishabhd4\Desktop\Logs Sarvesh"
FILES_TO_CHECK = ["4W.json", "3W.json"]
CALDONE_LOG_PATH = os.path.join(RESULTS_DIR, "caldone_log.json")

MODEL_CODES = {
    "100A": {"2TS": 1200094, "MODBUS": 1200126, "MBUS": 1200222},
    "80A": {"2TS": 1200093, "MODBUS": 1200125, "MBUS": 1200221},
}

# -------------------------
# CRC16 and MCW Utilities
# -------------------------
def crc16_fn(data: bytes) -> int:
    crc = 0xFFFF
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return crc & 0xFFFF

def bytes_to_mcw_hex(byte_seq: bytes) -> str:
    return ''.join(f"^h{b:02X}" for b in byte_seq)

def build_simple_mcw(meter_num: int, raw_bytes: bytes) -> str:
    return f"MCW{meter_num},{bytes_to_mcw_hex(raw_bytes)}"

# -------------------------
# Modbus Float Writers
# -------------------------
def build_modbus_write_float(meter_num, slave_id, start_addr, value, fixed_crc=None):
    fbytes = struct.pack('>f', float(value))
    high_word, low_word = struct.unpack('>HH', fbytes)
    regs_bytes = struct.pack('>HH', high_word, low_word)
    reg_count = 2
    byte_count = reg_count * 2
    header = struct.pack('>B B H H B', slave_id, 0x10, start_addr, reg_count, byte_count)
    pdu = header + regs_bytes
    if fixed_crc is not None:
        pdu_full = pdu + struct.pack('<H', fixed_crc)
    else:
        crc = crc16_fn(pdu)
        pdu_full = pdu + struct.pack('<H', crc)
    return build_simple_mcw(meter_num, pdu_full)

# -------------------------
# Specific Commands
# -------------------------
def build_unlock_command(meter_num, addr, code=2121):
    return build_modbus_write_float(meter_num, 1, addr, float(code))

def build_serial_command(meter_num, serial):
    return build_modbus_write_float(meter_num, 1, 0x17A6, float(serial))

def build_yymm_command(meter_num, yymm_val=None):
    if yymm_val is None:
        t = time.localtime()
        yymm_val = (t.tm_year % 100) * 100 + t.tm_mon
    return build_modbus_write_float(meter_num, 1, 0x17A8, float(yymm_val))

def build_model_command(meter_num, code):
    return build_modbus_write_float(meter_num, 1, 0x17AE, float(code))

# -------------------------
# UI Helpers
# -------------------------
def prompt_serial_number():
    root = tk.Tk()
    root.withdraw()
    while True:
        serial = simpledialog.askstring("Serial Number", "Enter starting serial number (6 digits):")
        if serial and serial.isdigit() and len(serial) == 6:
            root.destroy()
            return int(serial)
        messagebox.showerror("Invalid Input", "Serial number must be 6 digits.")

def select_model_and_type():
    selection = {}

    def on_submit():
        selection['model'] = model_var.get()
        selection['type'] = type_var.get()
        top.destroy()

    top = tk.Tk()
    top.title("Select Model and Type")
    tk.Label(top, text="Select Model:").pack()
    model_var = tk.StringVar(value=list(MODEL_CODES.keys())[0])
    for m in MODEL_CODES:
        tk.Radiobutton(top, text=m, variable=model_var, value=m).pack(anchor='w')

    tk.Label(top, text="Select Type:").pack()
    type_var = tk.StringVar()
    type_buttons = []

    def rebuild_types(*args):
        for btn in type_buttons:
            btn.destroy()
        type_buttons.clear()
        for t in MODEL_CODES[model_var.get()]:
            btn = tk.Radiobutton(top, text=t, variable=type_var, value=t)
            btn.pack(anchor='w')
            type_buttons.append(btn)
        type_var.set(list(MODEL_CODES[model_var.get()].keys())[0])

    model_var.trace_add("write", rebuild_types)
    rebuild_types()
    tk.Button(top, text="Submit", command=on_submit).pack()
    top.mainloop()

    if selection.get('model') and selection.get('type'):
        return selection['model'], selection['type']
    else:
        messagebox.showerror("Error", "You must select model and type.")
        return select_model_and_type()

# -------------------------
# Utilities
# -------------------------
def send_with_delay(transport, cmd, delay=1.0):
    time.sleep(delay)
    transport.send_mcw(cmd)

def get_ip_for_meter(meter_id):
    if 1 <= meter_id <= 10:
        ip = "192.168.100.100"
    elif 11 <= meter_id <= 20:
        ip = "192.168.100.101"
    else:
        raise ValueError(f"Meter ID {meter_id} out of supported range")
    port = 12345
    return ip, port

def get_current_yymm_int():
    t = time.localtime()
    return (t.tm_year % 100) * 100 + t.tm_mon

def decode_response(raw):
    try:
        if raw is None:
            return None
        if isinstance(raw, bytes):
            raw = raw.hex()
        return raw[-8:]
    except Exception:
        return None

def save_logs(summary):
    with open("postcal_log.json", "w") as jf:
        json.dump(summary, jf, indent=2)
    with open("postcal_log.txt", "w") as tf:
        for entry in summary["meters"]:
            tf.write(f"{entry['name']}: {entry['status']} | Response: {entry.get('received')}\n")

def print_table(results):
    print("\n+-------+----------------------+------------------------------+")
    print("| Meter |       Status         |          Response            |")
    print("+-------+----------------------+------------------------------+")
    for e in results:
        meter_label = e.get("name", "meter ?")
        resp = e.get("received") or "N/A"
        display = (resp[:28] + "...") if len(resp) > 31 else resp
        print(f"| {meter_label:<5} | {e['status']:<20} | {display:<28} |")
    print("+-------+----------------------+------------------------------+\n")

# -------------------------
# NEW: Caldone Check Helper
# -------------------------
def load_caldone_success_meters():
    success_meters = set()
    if not os.path.exists(CALDONE_LOG_PATH):
        print(f"⚠️ caldone_log.json not found at {CALDONE_LOG_PATH}. All meters skipped.")
        return success_meters
    try:
        with open(CALDONE_LOG_PATH, "r") as f:
            data = json.load(f)
            if isinstance(data, dict):
                for k, v in data.items():
                    try:
                        if isinstance(v, dict) and v.get("result") == "CAL_SUCCESS":
                            success_meters.add(int(k))
                    except Exception:
                        continue
    except Exception as e:
        print(f"⚠️ Error reading caldone_log.json: {e}")
    return success_meters

# -------------------------
# Main Routine
# -------------------------
def run_post_calibration():
    caldone_success = load_caldone_success_meters()
    if not caldone_success:
        print("⚠️ No meters with CAL_SUCCESS found — skipping all operations.")
        return
    else:
        print(f"✅ Proceeding only for meters with CAL_SUCCESS: {sorted(caldone_success)}")

    serial_start = prompt_serial_number()
    model, meter_type = select_model_and_type()
    code = MODEL_CODES[model][meter_type]
    curr_serial = serial_start

    print("⏳ Waiting 5 seconds before starting writes...")
    time.sleep(5)

    results = []
    last_connection = None
    mcw_counter = 1  # MCW numbering per connection

    for meter_id in range(1, METER_COUNT + 1):
        if meter_id not in caldone_success:
            print(f"⚠️ Skipping meter {meter_id} (not CAL_SUCCESS).")
            results.append({
                "name": f"meter {meter_id}",
                "meter": meter_id,
                "received": "Skipped due to CAL_FAIL",
                "status": "SKIPPED_CAL_FAIL"
            })
            continue  # skip faulty but DO NOT increment serial

        # ✅ normal write for good meters only
        ip, port = get_ip_for_meter(meter_id)
        if last_connection != (ip, port):
            print(f"\n>> Meter {meter_id} targeting {ip}:{port}")
            print(" ⏳ New connection detected, waiting 3 seconds...")
            time.sleep(3)
            last_connection = (ip, port)
            mcw_counter = 1
        else:
            print(f"\n>> Meter {meter_id} targeting {ip}:{port}")

        entry = {"name": f"meter {meter_id}", "meter": meter_id, "received": "", "status": "COMM_ERROR"}

        try:
            for attempt in range(1, MAX_RETRIES + 1):
                cmd_unlock = build_unlock_command(mcw_counter, 0x17A6)
                send_with_delay(SocketTransport(ip, port, SOCKET_TIMEOUT), cmd_unlock)
                raw = SocketTransport(ip, port, SOCKET_TIMEOUT).recv_all(SOCKET_TIMEOUT)
                if decode_response(raw):
                    break
                time.sleep(0.3)

            for attempt in range(1, MAX_RETRIES + 1):
                cmd_write = build_serial_command(mcw_counter, f"{curr_serial:06d}")
                send_with_delay(SocketTransport(ip, port, SOCKET_TIMEOUT), cmd_write)
                raw = SocketTransport(ip, port, SOCKET_TIMEOUT).recv_all(SOCKET_TIMEOUT)
                if decode_response(raw):
                    entry["received"] += f"Serial {curr_serial:06d} written | "
                    entry["status"] = "PASS"
                    break
                time.sleep(0.3)
            curr_serial += 1  # ✅ increment serial only for successful meter

            for attempt in range(1, MAX_RETRIES + 1):
                cmd_unlock = build_unlock_command(mcw_counter, 0x17A8)
                send_with_delay(SocketTransport(ip, port, SOCKET_TIMEOUT), cmd_unlock)
                SocketTransport(ip, port, SOCKET_TIMEOUT).recv_all(SOCKET_TIMEOUT)
                time.sleep(0.3)

            yymm_val = get_current_yymm_int()
            for attempt in range(1, MAX_RETRIES + 1):
                cmd_write = build_yymm_command(mcw_counter, yymm_val)
                send_with_delay(SocketTransport(ip, port, SOCKET_TIMEOUT), cmd_write)
                SocketTransport(ip, port, SOCKET_TIMEOUT).recv_all(SOCKET_TIMEOUT)
                time.sleep(0.3)

            for attempt in range(1, MAX_RETRIES + 1):
                cmd_unlock = build_unlock_command(mcw_counter, 0x17AE)
                send_with_delay(SocketTransport(ip, port, SOCKET_TIMEOUT), cmd_unlock)
                SocketTransport(ip, port, SOCKET_TIMEOUT).recv_all(SOCKET_TIMEOUT)
                time.sleep(0.3)

            for attempt in range(1, MAX_RETRIES + 1):
                cmd_write = build_model_command(mcw_counter, code)
                send_with_delay(SocketTransport(ip, port, SOCKET_TIMEOUT), cmd_write)
                SocketTransport(ip, port, SOCKET_TIMEOUT).recv_all(SOCKET_TIMEOUT)
                time.sleep(0.3)

            mcw_counter += 1
            results.append(entry)

        except Exception as e:
            print(f"❌ Meter {meter_id} failed: {e}")
            results.append(entry)

    summary = {"run_time": time.ctime(), "meters": results}
    save_logs(summary)
    print_table(results)
    print("Post-calibration complete. Logs saved.")

if __name__ == "__main__":
    run_post_calibration()