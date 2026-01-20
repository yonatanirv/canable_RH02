"""
Transmitter module - Generates continuous CAN stream.
"""

import time
import signal
import sys
from typing import Optional

from .can_device import CanDevice, CanFrame


class Transmitter:
    """
    Transmitter class for generating continuous CAN message streams.
    """

    def __init__(
        self,
        device: CanDevice,
        can_id: int = 0x123,
        interval_ms: float = 100,
        extended_id: bool = False,
        show_status: bool = False
    ):
        self.device = device
        self.can_id = can_id
        self.interval_ms = interval_ms
        self.extended_id = extended_id
        self.show_status = show_status
        self._running = False
        self._frame_count = 0
        self._error_count = 0

    def _get_status_str(self) -> str:
        """Get compact status string for inline display."""
        if not self.show_status:
            return ""
        
        status = self.device.get_status()
        if status is None:
            return " | Status: N/A"
        
        # Compact format: TEC:X REC:X [ERR]
        parts = [f"TEC:{status.tx_err_cnt}", f"REC:{status.rx_err_cnt}"]
        
        if status.last_error != 0:
            parts.append(f"Err:{status.last_error_str}")
        
        if status.bus_off:
            parts.append("[BUS-OFF]")
        elif status.error_passive:
            parts.append("[PASSIVE]")
        elif status.error_warning:
            parts.append("[WARN]")
        
        return " | " + " ".join(parts)

    def start(self) -> None:
        """Start transmitting CAN frames continuously."""
        self._running = True
        self._frame_count = 0
        self._error_count = 0
        self._consecutive_errors = 0

        original_handler = signal.signal(signal.SIGINT, self._signal_handler)

        print(f"\n[TX] Starting continuous transmission...")
        print(f"[TX] Flushing buffers...")
        self.device._flush_rx_buffer()  # Clear any pending data
        print(f"[TX] Press Ctrl+C to stop\n")
        print("-" * 80)

        try:
            while self._running:
                counter = self._frame_count % 256
                data = bytes([
                    counter,
                    (counter + 1) % 256,
                    (counter + 2) % 256,
                    (counter + 3) % 256,
                    (self._frame_count >> 24) & 0xFF,
                    (self._frame_count >> 16) & 0xFF,
                    (self._frame_count >> 8) & 0xFF,
                    self._frame_count & 0xFF,
                ])

                frame = CanFrame(
                    arbitration_id=self.can_id,
                    data=data,
                    is_extended_id=self.extended_id
                )

                try:
                    if self.device.send(frame):
                        self._frame_count += 1
                        self._consecutive_errors = 0
                        status_str = self._get_status_str()
                        print(f"[TX #{self._frame_count:6d}] {frame}{status_str}")
                    else:
                        self._error_count += 1
                        self._consecutive_errors += 1
                        status_str = self._get_status_str()
                        print(f"[TX ERROR] Send failed{status_str}")
                except Exception as e:
                    self._error_count += 1
                    self._consecutive_errors += 1
                    print(f"[TX ERROR] Exception: {e}")
                
                # If too many consecutive errors, try to recover
                if self._consecutive_errors >= 10:
                    print(f"\n[TX] Too many errors, attempting recovery...")
                    self._try_recovery()
                    self._consecutive_errors = 0

                time.sleep(self.interval_ms / 1000.0)

        finally:
            signal.signal(signal.SIGINT, original_handler)
            self._print_summary()

    def _try_recovery(self) -> None:
        """Attempt to recover from stalled state."""
        try:
            print("[TX] Closing and reopening connection...")
            self.device.disconnect()
            time.sleep(1.0)
            self.device.connect()
            print("[TX] Reconnected successfully!")
        except Exception as e:
            print(f"[TX] Recovery failed: {e}")
            print("[TX] You may need to unplug and replug the device.")

    def stop(self) -> None:
        self._running = False

    def _signal_handler(self, signum, frame) -> None:
        print("\n\n[TX] Stopping...")
        self._running = False

    def _print_summary(self) -> None:
        print("-" * 80)
        print(f"\n[TX] Summary: {self._frame_count} sent, {self._error_count} errors")
        
        # Final status
        if self.show_status:
            status = self.device.get_status()
            if status:
                print(f"[TX] Final Status: TEC:{status.tx_err_cnt} REC:{status.rx_err_cnt} LastErr:{status.last_error_str}")
        print()


def run_transmitter(
    port: str,
    bitrate: int,
    serial_baud: int,
    can_id: int,
    interval_ms: float,
    extended_id: bool,
    show_status: bool = False
) -> int:
    """Run transmitter with given configuration."""
    device = CanDevice(port=port, bitrate=bitrate, serial_baud=serial_baud)

    try:
        print(f"\n[*] Connecting to {port}...")
        device.connect()
        print(f"[+] Connected: {device}")

        tx = Transmitter(
            device=device,
            can_id=can_id,
            interval_ms=interval_ms,
            extended_id=extended_id,
            show_status=show_status
        )
        tx.start()
        return 0

    except ConnectionError as e:
        print(f"\n[ERROR] {e}")
        return 1

    except Exception as e:
        print(f"\n[ERROR] Unexpected error: {e}")
        return 1

    finally:
        device.disconnect()
        print("[*] Disconnected.")
