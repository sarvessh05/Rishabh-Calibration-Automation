# steps.py
# ============================================================
# Functions to build MCW commands for meters.
# - Handles CRC16 calculation
# - Converts payloads to ^hXX notation
# - Builds Modbus read/write commands
# - Special helpers for serial number and YYMM fields
#
# NOTE (for operator / non-tech person):
#   - Meters 1–10 are connected to first port (192.168.100.100).
#   - Meters 11–20 are connected to second port (192.168.100.101).
#   - You only need to set METER_COUNT in config.py.
#   - This file will automatically work with both groups.
# ============================================================

import struct
from datetime import datetime
import registers
import config  # For METER_COUNT, SIMULATE, etc.


# -------------------------------
# CRC16 Modbus calculation
# -------------------------------
def crc16_fn(data: bytes) -> int:
    """Compute Modbus CRC16 for a given byte stream."""
    crc = 0xFFFF
    for b in data:
        crc ^= b
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc & 0xFFFF


# -------------------------------
# Convert raw bytes to ^h notation
# -------------------------------
def bytes_to_mcw_hex(byte_seq: bytes) -> str:
    """Convert bytes to MCW ^hXX notation string."""
    return ''.join(f"^h{b:02X}" for b in byte_seq)


# -------------------------------
# Build MCW command string
# -------------------------------
def build_simple_mcw(meter_num: int, raw_bytes: bytes) -> str:
    """
    Build MCW command for a specific meter with raw bytes.
    - MCW0 = broadcast
    - MCW1..MCWn = individual meters
    - Meters 1–10 use first port, 11–20 use second port
      (handled later by transport.py)
    """
    if meter_num < 0 or meter_num > config.METER_COUNT:
        raise ValueError(f"Invalid meter_num {meter_num}. Must be 0..{config.METER_COUNT}")
    prefix = f"MCW{meter_num}"
    hex_part = bytes_to_mcw_hex(raw_bytes)
    return f"{prefix},{hex_part}"


# -------------------------------
# Build Modbus Read command
# -------------------------------
def build_modbus_read_cmd(meter_num: int, slave_id: int, start_addr: int, reg_count: int) -> str:
    """Build MCW command for Modbus Read Holding Registers."""
    pdu = struct.pack('>B B H H', slave_id, 0x03, start_addr, reg_count)
    crc = crc16_fn(pdu)
    pdu_full = pdu + struct.pack('<H', crc)
    return build_simple_mcw(meter_num, pdu_full)


# -------------------------------
# Build Modbus Write Multiple Registers (float values)
# -------------------------------
def build_modbus_write_multiple_float(meter_num: int, slave_id: int, start_addr: int, values: list) -> str:
    """Build MCW command for writing multiple IEEE 754 float values."""
    regs_bytes = b""
    for v in values:
        fbytes = struct.pack('>f', float(v))
        high_word, low_word = struct.unpack('>HH', fbytes)
        regs_bytes += struct.pack('>HH', high_word, low_word)

    reg_count = len(values) * 2
    byte_count = reg_count * 2
    header = struct.pack('>B B H H B', slave_id, 0x10, start_addr, reg_count, byte_count)
    pdu = header + regs_bytes
    crc = crc16_fn(pdu)
    pdu_full = pdu + struct.pack('<H', crc)
    return build_simple_mcw(meter_num, pdu_full)


# -------------------------------
# Build Serial Number write command
# -------------------------------
def build_serial_number_command(meter_num: int, serial_number_decimal_str: str) -> str:
    """Build MCW command to write serial number into a meter."""
    serial_float = float(serial_number_decimal_str)
    return build_modbus_write_multiple_float(meter_num, 1, registers.REG_SERIAL_HIGH, [serial_float])


# -------------------------------
# Build YYMM write command
# -------------------------------
def build_yymm_write_command(meter_num: int, yymm_int: int) -> str:
    """Build MCW command to write YYMM (year/month) into a meter."""
    yymm_float = float(yymm_int)
    return build_modbus_write_multiple_float(meter_num, 1, registers.REG_YYMM, [yymm_float])


# -------------------------------
# Get current YYMM as integer
# -------------------------------
def get_current_yymm_int() -> int:
    """Return current year/month as integer (YYMM)."""
    now = datetime.now()
    return int(now.strftime("%y%m"))

# -------------------------------
# Build Modbus Read Input Registers command
# -------------------------------
def build_modbus_read_input_registers(meter_num: int, slave_id: int, start_addr: int, reg_count: int) -> str:
    """Build MCW command for Modbus Read Input Registers (0x04)."""
    pdu = struct.pack('>B B H H', slave_id, 0x04, start_addr, reg_count)
    crc = crc16_fn(pdu)
    pdu_full = pdu + struct.pack('<H', crc)
    return build_simple_mcw(meter_num, pdu_full)


# -------------------------------
# Build Modbus Read Holding Registers command
# -------------------------------
def build_modbus_read_holding_registers(meter_num: int, slave_id: int, start_addr: int, reg_count: int) -> str:
    """Build MCW command for Modbus Read Holding Registers (0x03)."""
    pdu = struct.pack('>B B H H', slave_id, 0x03, start_addr, reg_count)
    crc = crc16_fn(pdu)
    pdu_full = pdu + struct.pack('<H', crc)
    return build_simple_mcw(meter_num, pdu_full)