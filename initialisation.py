import socket
import time

def send_commands(host, port, commands):
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client_socket:
            client_socket.connect((host, port))
            print(f"✅ Connected to {host}:{port}")

            for cmd in commands:
                full_command = cmd + '\r'
                client_socket.sendall(full_command.encode('ascii'))
                print(f"➡️ Sent to {host}: {cmd}")
                time.sleep(0.05)

            print(f"✅ All commands sent to {host}:{port}\n")

    except Exception as e:
        print(f"❌ Error with {host}:{port} -> {e}")


def main():
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
        #("192.168.100.102", 12345),
    ]

    for host, port in targets:
        send_commands(host, port, commands)
       # time.sleep(1)


if __name__ == "__main__":
    main()
