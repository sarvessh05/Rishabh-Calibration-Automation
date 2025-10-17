# ui_helpers.py
# Tkinter-based UI helpers for meter calibration scripts.
# Provides Yes/No prompts, serial number entry, and model/type selection.
# Falls back to console input if Tkinter unavailable or SIMULATE constraints.

import config  # Configuration for SIMULATE mode and operator prompts
try:
    import tkinter as tk
    from tkinter import ttk, messagebox
except Exception:
    tk = None  # Fallback if Tkinter not available

# -------------------------------
# Ask Yes/No (radio buttons or console)
# -------------------------------
def ask_yes_no(title="Confirm", question="Proceed?"):
    """
    Prompt user with Yes/No question.
    Returns True for Yes, False for No.
    Uses Tkinter radio buttons if available; otherwise console input.
    """
    if config.SIMULATE and not config.ALLOW_OPERATOR_PROMPTS:
        return False  # Skip prompt in simulation if operator prompts disabled
    if tk:
        val = {"ans": None}
        def submit():
            val["ans"] = (choice.get() == "Yes")
            win.destroy()
        win = tk.Tk()
        win.title(title)
        tk.Label(win, text=question).pack(padx=10, pady=8)
        choice = tk.StringVar(value="No")
        tk.Radiobutton(win, text="Yes", variable=choice, value="Yes").pack(anchor="w", padx=20)
        tk.Radiobutton(win, text="No", variable=choice, value="No").pack(anchor="w", padx=20)
        ttk.Button(win, text="OK", command=submit).pack(pady=8)
        win.mainloop()
        return val["ans"]
    # Console fallback
    return input(f"{question} (y/n): ").strip().lower().startswith("y")

# -------------------------------
# Prompt for starting serial number
# -------------------------------
def prompt_serial_number():
    """
    Prompt user to enter 6-digit start serial number.
    Returns string like '123456'.
    Uses Tkinter entry box if available; otherwise console input.
    """
    if config.SIMULATE and not config.ALLOW_OPERATOR_PROMPTS:
        return "123456"  # Default for simulation
    if tk:
        val = {"v": None}
        def submit():
            v = entry.get().strip()
            if v.isdigit() and len(v) == 6:
                val["v"] = v
                win.destroy()
            else:
                messagebox.showerror("Invalid", "Enter a 6-digit numeric serial.")
        win = tk.Tk()
        win.title("Enter Serial Number")
        ttk.Label(win, text="Enter 6-digit start serial:").pack(padx=10, pady=6)
        entry = ttk.Entry(win)
        entry.pack(padx=10, pady=6)
        entry.focus()
        ttk.Button(win, text="OK", command=submit).pack(pady=6)
        win.mainloop()
        return val["v"]
    # Console fallback loop
    while True:
        v = input("Enter 6-digit start serial (e.g. 123456): ").strip()
        if v.isdigit() and len(v) == 6:
            return v

# -------------------------------
# Select meter model and type
# -------------------------------
def select_model_and_type():
    """
    Prompt user to select meter model (100A/80A) and type (2TS/MODBUS/MBUS).
    Returns tuple (model, type).
    Uses Tkinter dropdowns if available; otherwise console input.
    """
    if config.SIMULATE and not config.ALLOW_OPERATOR_PROMPTS:
        return ("100A", "MODBUS")  # Default for simulation
    if tk:
        val = {"model": None, "type": None}
        def submit():
            m = combo_model.get().strip()
            t = combo_type.get().strip().upper()
            if m in ["100A", "80A"] and t in ["2TS", "MODBUS", "MBUS"]:
                val["model"] = m
                val["type"] = t
                win.destroy()
            else:
                messagebox.showerror("Invalid", "Select a valid model and type.")
        win = tk.Tk()
        win.title("Select Model & Type")

        # Model selection dropdown
        ttk.Label(win, text="Select meter model:").pack(padx=10, pady=4)
        combo_model = ttk.Combobox(win, values=["100A", "80A"], state="readonly")
        combo_model.pack(padx=10, pady=4)
        combo_model.current(0)

        # Type selection dropdown
        ttk.Label(win, text="Select meter type:").pack(padx=10, pady=4)
        combo_type = ttk.Combobox(win, values=["2TS", "MODBUS", "MBUS"], state="readonly")
        combo_type.pack(padx=10, pady=4)
        combo_type.current(1)

        ttk.Button(win, text="OK", command=submit).pack(pady=6)
        win.mainloop()
        return val["model"], val["type"]

    # Console fallback loop
    while True:
        m = input("Enter model (100A/80A) [100A]: ").strip().upper()
        if m == "": m = "100A"
        t = input("Enter meter type (2TS/MODBUS/MBUS) [MODBUS]: ").strip().upper()
        if t == "": t = "MODBUS"
        if m in ["100A", "80A"] and t in ["2TS", "MODBUS", "MBUS"]:
            return (m, t)


# -------------------------------
# Select meter wiring type via radio buttons
# -------------------------------
def select_meter_type_radio():
    """
    Prompt user to select meter wiring type using Tkinter radio buttons.
    Returns "3P4W" or "3P3W".
    Falls back to console input if Tkinter not available.
    """
    import config
    if config.SIMULATE and not config.ALLOW_OPERATOR_PROMPTS:
        return "3P4W"  # Default for simulation

    try:
        import tkinter as tk
        from tkinter import ttk
    except ImportError:
        tk = None

    if tk:
        val = {"type": None}

        def submit():
            val["type"] = choice.get()
            win.destroy()

        win = tk.Tk()
        win.title("Select Meter Wiring Type")
        tk.Label(win, text="Select meter wiring type:").pack(padx=10, pady=8)

        choice = tk.StringVar(value="3P4W")
        tk.Radiobutton(win, text="3P4W", variable=choice, value="3P4W").pack(anchor="w", padx=20)
        tk.Radiobutton(win, text="3P3W", variable=choice, value="3P3W").pack(anchor="w", padx=20)

        ttk.Button(win, text="OK", command=submit).pack(pady=8)
        win.mainloop()

        return val["type"]

    # Console fallback
    while True:
        t = input("Enter meter type (3P4W/3P3W) [3P4W]: ").strip().upper()
        if t == "": t = "3P4W"
        if t in ["3P4W", "3P3W"]:
            return t