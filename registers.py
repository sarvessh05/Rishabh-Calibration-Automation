# registers.py

# This file provides named addresses ("registers") and a mapping
# for instrument parameters, making hardware interaction easier to understand.
# Each register is a memory location in the instrument storing a specific value.

# --- Named Register Addresses (edit only if actual meter hardware uses different map) ---

REG_SERIAL_HIGH = 6056  # Start address for serial number, uses two consecutive registers

REG_YYMM = 6054         # Address for manufacturing date (YYMM format, stored as a float)

# For additional addresses, add new lines below and update comments to clarify their purpose.
# Example:
# REG_ENERGY_TOTAL = 6060  # Address for total energy reading

# --- Parameter-to-Register Offset Mapping ---

# PARAM_MAP defines the offset in the register block for each electric parameter.
# These offsets are relative to some base address determined by the instrument.

PARAM_MAP = {
    "V_R": 0,    # Voltage for R phase (offset 0)
    "V_Y": 2,    # Voltage for Y phase (offset 2)
    "V_B": 4,    # Voltage for B phase (offset 4)
    "I_R": 6,    # Current for R phase (offset 6)
    "I_Y": 8,    # Current for Y phase (offset 8)
    "I_B": 10,   # Current for B phase (offset 10)
    "P_R": 12,   # Power for R phase (offset 12)
    "P_Y": 14,   # Power for Y phase (offset 14)
    "P_B": 16,   # Power for B phase (offset 16)
    "FREQ": 18,  # Frequency (offset 18)
    "PF": 20     # Power Factor (offset 20)
    # Add further mappings as per hardware protocol.
}

# --- Float Word Order Configuration ---

# Some meters store floating point values with swapped word order
# (word-swapping means two halves of 32-bit float are read in reverse).
# Set to True if hardware/meter requires word swap for correct float decoding.

SWAP_WORDS = True

# End of file. Add new registers or mapping keys above this line as needed.