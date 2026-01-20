"""
Command-line interface for CAN Tools.
"""

import argparse
import sys

from .config import (
    DEFAULT_SERIAL_BAUD,
    DEFAULT_CAN_BITRATE,
    VALID_CAN_BITRATES,
    DEFAULT_TX_INTERVAL_MS,
    DEFAULT_TX_CAN_ID,
)


def parse_args(args=None) -> argparse.Namespace:
    """
    Parse command-line arguments.
    
    Args:
        args: List of arguments (default: sys.argv[1:])
        
    Returns:
        Parsed arguments namespace
    """
    parser = argparse.ArgumentParser(
        prog='can_tools',
        description='CAN bus testing utility for CANable devices',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  Transmit CAN frames:
    python -m can_tools --com_port COM5 --role tx
    python -m can_tools --com_port COM5 --role tx --canbus_speed 250000 --can_id 0x100
    
  Receive CAN frames:
    python -m can_tools --com_port COM8 --role rx
    python -m can_tools --com_port COM8 --role rx --canbus_speed 250000

Common CAN bus speeds:
  125000  - 125 kbps (common in industrial)
  250000  - 250 kbps (common in vehicles)
  500000  - 500 kbps (common in vehicles)
  1000000 - 1 Mbps (high speed)
'''
    )

    # Required arguments
    parser.add_argument(
        '--com_port',
        type=str,
        required=True,
        help='Serial port for CANable device (e.g., COM5, /dev/ttyUSB0)'
    )

    parser.add_argument(
        '--role',
        type=str,
        required=True,
        choices=['tx', 'rx'],
        help='Device role: tx (transmit stream) or rx (receive and print)'
    )

    # Optional arguments
    parser.add_argument(
        '--serial_baud',
        type=int,
        default=DEFAULT_SERIAL_BAUD,
        help=f'Serial baud rate (default: {DEFAULT_SERIAL_BAUD})'
    )

    parser.add_argument(
        '--canbus_speed',
        type=int,
        default=DEFAULT_CAN_BITRATE,
        help=f'CAN bus bitrate in bps (default: {DEFAULT_CAN_BITRATE})'
    )

    # TX-specific options
    parser.add_argument(
        '--can_id',
        type=lambda x: int(x, 0),  # Allows 0x prefix for hex
        default=DEFAULT_TX_CAN_ID,
        help=f'CAN ID for TX messages (default: 0x{DEFAULT_TX_CAN_ID:03X})'
    )

    parser.add_argument(
        '--interval',
        type=int,
        default=DEFAULT_TX_INTERVAL_MS,
        help=f'Interval between TX messages in ms (default: {DEFAULT_TX_INTERVAL_MS})'
    )

    parser.add_argument(
        '--rate',
        type=int,
        default=None,
        help='TX messages per second (overrides --interval if specified)'
    )

    parser.add_argument(
        '--extended',
        action='store_true',
        help='Use extended (29-bit) CAN IDs'
    )

    parser.add_argument(
        '--status',
        action='store_true',
        help='Show CAN bus status (error counters, last error) with each frame'
    )

    parsed = parser.parse_args(args)

    # Validate CAN bus speed
    if parsed.canbus_speed not in VALID_CAN_BITRATES:
        valid_speeds = ', '.join(str(s) for s in sorted(VALID_CAN_BITRATES.keys()))
        print(f"Warning: {parsed.canbus_speed} is not a standard CAN bitrate.")
        print(f"Valid bitrates: {valid_speeds}")

    return parsed


def print_banner(args: argparse.Namespace) -> None:
    """Print startup banner with configuration."""
    print("=" * 60)
    print("  CAN Tools - CANable Testing Utility")
    print("=" * 60)
    print(f"  Port:         {args.com_port}")
    print(f"  Role:         {args.role.upper()}")
    print(f"  CAN Bitrate:  {args.canbus_speed} bps")
    print(f"  Serial Baud:  {args.serial_baud}")
    if args.role == 'tx':
        id_format = f"0x{args.can_id:08X}" if args.extended else f"0x{args.can_id:03X}"
        print(f"  TX CAN ID:    {id_format}")
        if args.rate:
            interval_ms = 1000.0 / args.rate
            print(f"  TX Rate:      {args.rate} msg/sec ({interval_ms:.1f} ms interval)")
        else:
            print(f"  TX Interval:  {args.interval} ms ({1000/args.interval:.1f} msg/sec)")
        print(f"  Extended ID:  {args.extended}")
    print(f"  Show Status:  {args.status}")
    print("=" * 60)

