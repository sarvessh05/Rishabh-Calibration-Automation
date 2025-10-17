# ============================================================
# config.py
# Global configuration + automatic hardware initialization
# ============================================================

import os
import time
import socket
import tkinter as tk
from tkinter import simpledialog, messagebox

# ============================================================
# HARDWARE INITIALIZATION (auto-run on import)
# ============================================================

def initialize_hardware():
    """
    Sends basic initialization commands to all configured meter IPs.
    Runs automatically when this config is imported.
    """
    commands = [
        'VER',
        'MCO0,3',
        'MCP0,9600,N,8,1',
        'MCSP0,1,2',
        'MCSU0,1'
    ]

    targets = [
        ("192.168.100.100", 12345),
        ("192.168.100.101", 12345),
        # ("192.168.100.102", 12345),  # optional
    ]

    print("\n============================")
    print("🔧 Initializing hardware...")
    print("============================")

    for host, port in targets:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(3)
                s.connect((host, port))
                for cmd in commands:
                    s.sendall((cmd + '\r').encode('ascii'))
                    print(f"➡️ Sent to {host}: {cmd}")
                    time.sleep(0.05)
                print(f"✅ Initialization done for {host}:{port}\n")
        except Exception as e:
            print(f"⚠️ Could not initialize {host}:{port} -> {e}")

    print("✅ Hardware initialization complete.\n")
    time.sleep(0.5)


# ============================================================
# SINGLE-RUN PROTECTION (avoid re-running on re-import)
# ============================================================

if not globals().get("_HARDWARE_INIT_DONE", False):
    initialize_hardware()
    globals()["_HARDWARE_INIT_DONE"] = True


# ============================================================
# USER INPUT — METER COUNT PROMPT
# ============================================================

root = tk.Tk()
root.withdraw()

METER_COUNT = None
while METER_COUNT is None:
    try:
        value = simpledialog.askinteger(
            "Meter Setup",
            "Enter number of meters connected (1–20):",
            minvalue=1,
            maxvalue=20,
        )
        if value is None:
            messagebox.showerror("Error", "You must enter a value to continue.")
        else:
            METER_COUNT = value
    except Exception as e:
        messagebox.showerror("Error", f"Invalid input: {e}")
root.destroy()
print(f"✅ Meter count set to {METER_COUNT}")

# ============================================================
# GENERAL SETTINGS
# ============================================================

SIMULATE = False
USE_BROADCAST = False

METER_CONNECTIONS = [
    ("192.168.100.100", 12345),  # meters 1–10
    ("192.168.100.101", 12345),  # meters 11–20
]

PORT = 12345
SOCKET_PORT = PORT
SOCKET_TIMEOUT = 2.0
COMMAND_GAP = 0.1
READ_LOOP_TIMEOUT = 1.0

# ============================================================
# PATHS FOR LOGGING
# ============================================================

RESULTS_DIR = r"D:\DO_NOT_DELETE_TESTING_SCRIPTS\Logs"

CAL_RESULTS_JSON = os.path.join(RESULTS_DIR, "cal_results.json")
CAL_LOG = os.path.join(RESULTS_DIR, "cal_log.txt")
POSTCAL_LOG = os.path.join(RESULTS_DIR, "postcal_log.txt")
RUN_JSON = os.path.join(RESULTS_DIR, "run_results.json")
RUN_LOG = os.path.join(RESULTS_DIR, "run_log.txt")

ALLOW_OPERATOR_PROMPTS = True

# ============================================================
# EXPECTED RESPONSES
# ============================================================

standard_responses = {
    i: ("SKIP" if i <= 4 else "") for i in range(1, METER_COUNT + 1)
}