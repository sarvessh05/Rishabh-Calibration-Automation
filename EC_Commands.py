import socket
import time

# Target connection
IP = ("192.168.100.101"
      "")
PORT = 12345

# List of commands (without <cr>, will add \r automatically)
EC_COMMANDS = [
    # "ECRES0,0;CTRES0,0;TIRES0,0;EHRES0;MCRES0",
    "ECRES0,0;CTRES0,0;TIRES0,0;EHRES0",  # Error counter reset, Pulse counter reset, Timer reset, EH reset
    "MODE1;VER;VER0;RTH",  # Mode 0 as compatibility mode
    "DITX0,2,",  # store text in memory position 2
    "DITX0,3,",  # store text in memory position 3
    "DISG0,L(H0,127,22)S",  # Draw Horizontal line
    "DIAG0,V1(C0,0,127,0,TX1)",  # draw vertical line
    "TIRES0,0",  # Timer reset
    "TIIN0,1,R",  # assign timer as a input source
    "TISP0,1,2,2",
    "TISP0,1,4,1",
    "TITR0,1,1,0",
    "TITR0,1,1,2.0",
    "TISU0,1,1",
    "TISTA0,1",
    "WRRES#,0",
    "WRIN#,1,F1",
    "OPO0,T1,0",
    "SU1",
    "MP",
    "MPI0",
    "INC*,F1,135000000,1",
    "WRNUL#,1",
    "WRSTA#,1",
    "INC*,F1,13500000,1",
    "WRNUL#,1",
    "WRSTA#,1",
    "DITX0, 1,RISHABH",
    "DITX0,2,\x1b5SSI400+",  # <esc> = \x1b
    # "DITX2,1,SSI400+",
    # "DITX2,2,\x1b5SSI400+",
    # "DITX3,1,SSI400+",
    # "DITX3,2,\x1b5SSI400+",
    # "DITX4,1,SSI400+",
    # "DITX4,2,\x1b5SSI400+",
    # "DITX5,1,SSI400+",
    # "DITX5,2,\x1b5SSI400+",
    # "DITX6,1,SSI400+",
    # "DITX6,2,\x1b5SSI400+",
    # "DITX7,1,SSI400+",
    # "DITX7,2,\x1b5SSI400+",
    # "DITX8,1,SSI400+",
    # "DITX8,2,\x1b5SSI400+",
    # "DITX9,1,SSI400+",
    # "DITX9,2,\x1b5SSI400+",
    # "DITX10,1,SSI400+",
    # "DITX10,2,\x1b5SSI400+",
    # "INC*,F1,135000000,1",
    "WRNUL#,1",
    "WRSTA#,1",
    "INC*,F1,33750,1",
    #"INC*,F1,16875,1",
    "WRNUL#,1",
    "WRSTA#,1",
    "ECL0,1,-0.8,0.8",
    "ECC1,1,1000,0",
    "ECC2,1,1000,0",
    "ECC3,1,1000,0",
    "ECC4,1,1000,0",
    "ECC5,1,1000,0",
    "ECC6,1,1000,0",
    "ECC7,1,1000,0",
    "ECC8,1,1000,0",
    "ECC9,1,1000,0",
    "ECC10,1,1000,0",
    "ECI$ffc,1,5,0",
    "DISG0,L(H0,127,22)S",
    "DISG$0,V1(C0,0,127,0,TX2)",
    "DIAG$ffc,L(H0,81,48)L(H81,127,35)L(V81,22,48)",
    "DIAG$ffc,R(0,0,EC1.2)",
    "DIAG$ffc,V1(r7,1,127,0,EC1.1:%.3s%%)",
    "DIAG$ffc,V2(R0,24,80,1,EC1.7:%u )",
    "DIAG$ffc,V3(R0,37,80,1,EC1.8:%u )",
    "DIAG$ffc,V4(R82,24,127,1,EC1.3:%u )",
    "WRNUL#,1",
    "WRSTA#,1",
    "ECRF*,1,F1",
    "ECIN$ffc,1,S1",
    "ECE0,1,2",
    "ECSP0,1,1,2",
    "ECSU$ffc,1,1",
    "ECSIN0,1,0",
    "WR?#,1,2",
    "ECSTA$ffc,1",
    "WR?#,1,2",
    # #"ECRES0,0",
    # #"EHRES0",
    # #"ECRES0,0",
    # #"EHRES0",
    # #"ECRES0,0;CTRES0,0;TIRES0,0;EHRES0;MCRES0",
    # #"DISG0,L(H0,127,22)S",
    # #"DISG$7fc,V1(C0,0,127,0,TX2)",
    # #"DIAG$8,V1(C0,0,127,0,TX1)",
    # #"WRNUL#,1",
    # #"WRSTA#,1",
    # #"WRSTA#,1",
]

def main():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.connect((IP, PORT))
        print(f"Connected to {IP}:{PORT}")

        for cmd in EC_COMMANDS:
            msg = (cmd + "\r").encode("ascii", errors="ignore")
            sock.sendall(msg)
            print(f">> Sent: {cmd}")
            time.sleep(0.1)  # 300 ms delay

        print("✅ All commands sent.")

if __name__ == "__main__":
    main()