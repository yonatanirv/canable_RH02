#!/usr/bin/env python3
"""
YonaCan - CAN Bus Analyzer for candleLight Devices
Main entry point.

Usage:
    python main.py
    
Or run as module:
    python -m YonaCan
"""

import sys
import os

# Add script directory to path for imports (dev mode)
# In frozen exe, PyInstaller handles module paths automatically
if not getattr(sys, 'frozen', False):
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import main

if __name__ == "__main__":
    main()

