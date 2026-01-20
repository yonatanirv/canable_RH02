"""
Default configuration values for CAN Tools.
"""

# Serial communication defaults
DEFAULT_SERIAL_BAUD = 115200

# CAN bus defaults
DEFAULT_CAN_BITRATE = 500000  # 500 kbps

# Common CAN bitrates (for validation)
VALID_CAN_BITRATES = {
    10000: "10 kbps",
    20000: "20 kbps",
    50000: "50 kbps",
    100000: "100 kbps",
    125000: "125 kbps",
    250000: "250 kbps",
    500000: "500 kbps",
    750000: "750 kbps",
    1000000: "1 Mbps",
}

# TX stream defaults
DEFAULT_TX_INTERVAL_MS = 100  # milliseconds between messages
DEFAULT_TX_CAN_ID = 0x123

