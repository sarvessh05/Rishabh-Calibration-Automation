# transport.py
"""
Transport layer for meter communication.

Provides:
- SimulatorTransport (fake data, useful for testing without hardware).
- SocketTransport (real TCP/IP device communication).

MCW protocol specifics:
- Commands must be ASCII with ^hXX escapes.
- Must be terminated with CR (sometimes CR+LF).
- After sending, device may need a short delay before replying.
"""

import config
import socket
import time
import random

# =========================================================
# Helpers
# =========================================================

CR = b"\x0D"  # Carriage return
CRLF = b"\x0D\x0A"  # Carriage return + line feed


def mcw_to_bytes(mcw: str, use_crlf: bool = False) -> bytes:
    """
    Convert MCW ASCII string to bytes with proper termination.
    - Default terminator = CR
    - If use_crlf=True, terminator = CRLF
    """
    terminator = CRLF if use_crlf else CR
    return mcw.encode("ascii") + terminator


# =========================================================
# Simulator Transport
# =========================================================
class SimulatorTransport:
    """
    Fake transport: generates deterministic payloads instead of using sockets.
    Useful for development & debugging.
    """

    def __init__(self, seed=42, meter_count=20):
        self.meter_count = meter_count
        random.seed(seed)
        self.payloads = {}
        for m in range(1, meter_count + 1):
            marker = f"{0x30 + m:02X}"  # embed meter ID
            payload = "".join(f"{(m * 7 + i) & 0xFF:02X}" for i in range(12))
            self.payloads[m] = "00" + marker + payload

    def send_mcw(self, mcw: str):
        # No-op in simulator
        pass

    def recv_all(self, timeout=config.SOCKET_TIMEOUT) -> bytes:
        # Random subset of simulated frames
        parts = []
        num = random.randint(0, max(1, self.meter_count // 2))
        chosen = random.sample(range(1, self.meter_count + 1), num)
        for m in chosen:
            seg_hex = self.payloads[m]
            parts.append(bytes.fromhex(seg_hex) + CR)
        return b"".join(parts)

    def close(self):
        pass


# =========================================================
# Real Socket Transport
# =========================================================
class SocketTransport:
    """
    TCP socket transport to talk to actual meters.
    Handles connection, sending MCW with CR termination,
    and reading until CR or timeout.
    """

    def __init__(self, ip=None, port=None, timeout=None, use_crlf=False, post_send_delay=0.1):
        self.ip = ip or config.SOCKET_IP
        self.port = port or config.SOCKET_PORT
        self.timeout = timeout or config.SOCKET_TIMEOUT
        self.use_crlf = use_crlf          # If device needs CR+LF instead of CR
        self.post_send_delay = post_send_delay
        self.sock = None

    def connect(self):
        """Establish TCP connection if not already connected."""
        if self.sock:
            return
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(self.timeout)
        s.connect((self.ip, self.port))
        self.sock = s

    def send_mcw(self, mcw: str):
        """Send MCW command terminated with CR or CRLF."""
        self.connect()
        b = mcw_to_bytes(mcw, use_crlf=self.use_crlf)
        self.sock.sendall(b)
        if self.post_send_delay > 0:
            time.sleep(self.post_send_delay)

    def recv_all(self, timeout=None) -> bytes:
        """
        Receive bytes until CR encountered or timeout.
        Returns whatever data was received.
        """
        self.connect()
        self.sock.settimeout(timeout or self.timeout)
        all_data = b""
        start = time.time()

        try:
            while True:
                chunk = self.sock.recv(4096)
                if not chunk:
                    break
                all_data += chunk

                # If CR found, do short extra read for trailing data
                if CR in chunk or CRLF in chunk:
                    time.sleep(0.5)
                    try:
                        self.sock.settimeout(0.2)
                        nxt = self.sock.recv(4096)
                        if nxt:
                            all_data += nxt
                    except socket.timeout:
                        pass
                    break

                if time.time() - start > (timeout or self.timeout):
                    break
        except socket.timeout:
            pass

        return all_data

    def close(self):
        """Close socket cleanly."""
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass
            self.sock = None


# =========================================================
# Factory
# =========================================================
def get_transport(ip=None, port=None, timeout=None):
    """
    Return a transport object based on config.SIMULATE.
    Allows overriding IP/port if provided.
    """
    if config.SIMULATE:
        return SimulatorTransport(seed=42, meter_count=config.METER_COUNT)
    else:
        return SocketTransport(
            ip=ip or config.SOCKET_IP,
            port=port or config.SOCKET_PORT,
            timeout=timeout or config.SOCKET_TIMEOUT,
        )