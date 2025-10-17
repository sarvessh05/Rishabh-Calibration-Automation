# decoder.py

# Utility functions for decoding and organizing raw byte data from meter hardware.
# Provides:
#   - 5E escape sequence decoding
#   - Splitting a byte stream using CR (carriage return)
#   - Assigning data segments to meters using byte markers

import config


# ------------------------------------
# 5E Escape Sequence Decoding Function
# ------------------------------------

def process_hex_data(data_str: str) -> str:
    """
    Decodes a contiguous hex string containing 5E escape sequences.
    Returns a continuous hex string (no spaces).
    """
    s = data_str.upper()
    hex_pairs = [s[i:i + 2] for i in range(0, len(s), 2)]
    result = []
    i = 0
    while i < len(hex_pairs):
        if hex_pairs[i] == '5E' and i + 1 < len(hex_pairs):
            val = int(hex_pairs[i + 1], 16) - 0x40
            result.append(f"{max(val, 0):02X}")
            i += 2
        else:
            result.append(hex_pairs[i])
            i += 1
    print(''.join(result))
    return ''.join(result)   # continuous string


# ------------------------------------
# Split Raw Byte Stream by Carriage Return
# ------------------------------------

def split_segments_by_CR(raw_bytes: bytes) -> list[str]:
    """
    Splits a raw byte stream into hex string segments, dividing at 0x0D (CR).

    Args:
        raw_bytes (bytes): The raw stream returned by meter hardware.

    Returns:
        list[str]: List of hex string segments separated by CR.
    """
    segments = []
    buf = raw_bytes
    while True:
        idx = buf.find(b'\x0D')
        if idx == -1:
            break
        segment = buf[:idx]
        buf = buf[idx + 1:]
        if segment:
            hex_str = ''.join(f"{b:02X}" for b in segment)
            segments.append(hex_str)
    print(segments)
    return segments


# ------------------------------------
# Assign Hex Segments to Meter Channels
# ------------------------------------

def process_by_second_marker(segments: list[str]) -> tuple[dict, list]:
    """
    Assigns each hex segment to its meter, using the marker in the second byte.

    - Skips first 2 bytes and 5 bytes thereafter (wrapper bytes).
    - Maps according to meter count from config.

    Args:
        segments (list[str]): Hex segments, e.g. ['0031AA...', '0032BB...']

    Returns:
        (dict, list):
            - Mapping meter channel name (e.g., 'meter 1') to list of hex tokens
            - List of segments that weren't assigned
    """
    final = {f"meter {i}": [] for i in range(1, config.METER_COUNT + 1)}
    unassigned = []
    for seg in segments:
        if len(seg) >= 4:
            marker = seg[2:4]  # 2nd byte (positions 2 and 3)
            valid_markers = [f"{x:02X}" for x in range(0x31, 0x31 + config.METER_COUNT)]
            if marker in valid_markers:
                meter_number = int(marker, 16) - 0x30
                tokens = [seg[i:i + 2] for i in range(4, len(seg), 2)]
                # Skip first 5 payload bytes which are wrappers
                tokens = tokens[5:]
                if 1 <= meter_number <= config.METER_COUNT:
                    final[f"meter {meter_number}"].extend(tokens)
                else:
                    unassigned.append(seg)
            else:
                unassigned.append(seg)
        else:
            unassigned.append(seg)
    print(final)
    print(unassigned)
    return final, unassigned


# ------------------------------------
# Full Decoding Pipeline
# ------------------------------------

def decode_raw_bytes(raw_bytes: bytes) -> tuple[dict, list]:
    """
    Complete pipeline to convert raw byte stream from meters into organized data.

    Steps:
        1. Split raw stream into segments using CR (0x0D)
        2. Apply 5E escape decoding to each segment
        3. Assign decoded segments to meters

    Args:
        raw_bytes (bytes): Stream received from device

    Returns:
        tuple:
            - Mapping of meter names to decoded token lists
            - List of segments not mapped to any meter
    """
    segments = split_segments_by_CR(raw_bytes)
    decoded_segments = [process_hex_data(seg) for seg in segments]
    final_map, unassigned = process_by_second_marker(decoded_segments)
    print(final_map, unassigned)
    return final_map, unassigned