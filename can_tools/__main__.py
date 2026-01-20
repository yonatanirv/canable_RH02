"""
CAN Tools - Main entry point.

Usage:
    python -m can_tools --com_port COM5 --role tx
    python -m can_tools --com_port COM8 --role rx
    python -m can_tools --com_port COM5 --role tx --status
    python -m can_tools -h
"""

import sys

from .cli import parse_args, print_banner
from .transmitter import run_transmitter
from .receiver import run_receiver


def main() -> int:
    """Main entry point."""
    args = parse_args()
    print_banner(args)

    if args.role == 'tx':
        # Calculate interval from rate if specified
        if args.rate:
            interval_ms = 1000.0 / args.rate
        else:
            interval_ms = args.interval
            
        return run_transmitter(
            port=args.com_port,
            bitrate=args.canbus_speed,
            serial_baud=args.serial_baud,
            can_id=args.can_id,
            interval_ms=interval_ms,
            extended_id=args.extended,
            show_status=args.status
        )
    else:  # rx
        return run_receiver(
            port=args.com_port,
            bitrate=args.canbus_speed,
            serial_baud=args.serial_baud,
            show_status=args.status
        )


if __name__ == '__main__':
    sys.exit(main())
