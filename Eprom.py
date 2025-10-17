import socket
import time
import config

# List of target IPs
IPS = ["192.168.100.100", "192.168.100.101"]
PORT = 12345

# List of commands (without <cr>, will add \r automatically)
COMMANDS = [
    "MCW0,^h01^h10^h25^h80^h00^h02^h04^h44^hFC^hE0^h00^hC0^h5E",
    "MCW0,^h01^h10^h17^hD4^h00^h02^h04^h45^h04^h90^h00^h2C^h3D",
    "MCW0,^h01^h10^h17^hD4^h00^h02^h04^h47^hF1^h20^h00^h48^h77"
]

def send_commands(ip):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.connect((ip, PORT))
        print(f"Connected to {ip}:{PORT}")

        for cmd in COMMANDS:
            msg = (cmd + "\r").encode("ascii", errors="ignore")
            sock.sendall(msg)
            print(f">> Sent: {cmd}")
            time.sleep(3)  # 3 s delay

        print(f"✅ All commands sent to {ip}.\n")

def main():
    for ip in IPS:
        send_commands(ip)

if __name__ == "__main__":
    main()
