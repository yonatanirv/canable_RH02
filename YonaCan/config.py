"""
YonaCan - Configuration and Constants
"""

import os

# Application Info
APP_NAME = "YonaCan"
APP_VERSION = "1.0.0"

# Default CAN Settings
DEFAULT_BITRATE = 500000
SUPPORTED_BITRATES = [
    10000, 20000, 50000, 100000, 125000,
    250000, 500000, 750000, 1000000
]

# Logging Settings
DEFAULT_LOG_DIR = os.path.join(os.path.expanduser("~"), "YonaCan_Logs")
DEFAULT_LOG_MAX_SIZE_MB = 10  # Max size before rotating to new file
DEFAULT_LOG_FORMAT = "csv"  # csv or txt

# UI Settings
WINDOW_MIN_WIDTH = 900
WINDOW_MIN_HEIGHT = 600
DATA_VIEWER_MAX_ROWS = 1000  # Max rows to display in real-time viewer
DATA_VIEWER_UPDATE_MS = 50   # Update interval in milliseconds

# Colors (Modern dark theme)
COLORS = {
    "bg_dark": "#1e1e1e",
    "bg_medium": "#252526",
    "bg_light": "#2d2d30",
    "fg_primary": "#ffffff",
    "fg_secondary": "#9d9d9d",
    "accent": "#007acc",
    "accent_hover": "#1c97ea",
    "success": "#4ec9b0",
    "warning": "#dcdcaa",
    "error": "#f14c4c",
    "can_tx": "#4fc1ff",
    "can_rx": "#4ec9b0",
}

# CAN Frame Display
FRAME_COLUMNS = ["#", "Time", "ID", "Dir", "DLC", "Data", "ASCII"]

