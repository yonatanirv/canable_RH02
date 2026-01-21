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

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import main

if __name__ == "__main__":
    main()

