"""
Receiver module - Receives and displays CAN frames.
"""

import time
import signal
from typing import Optional

from .can_device import CanDevice, CanFrame


class Receiver:
    """
    Receiver class for capturing and displaying CAN messages.
    """

    def __init__(self, device: CanDevice, timeout: float = 0.5, show_status: bool = False):
        self.device = device
        self.timeout = timeout
        self.show_status = show_status
        self._running = False
        self._frame_count = 0
        self._start_time: Optional[float] = None
        self._last_frame_time: Optional[float] = None
        self._stall_timeout = 30.0  # Seconds without frames before recovery attempt
        # Status queries corrupt frame reception in SLCAN (shared serial channel)
        # So we only show frame count inline, not device status
        self._last_status_time: Optional[float] = None
        self._status_interval = 5.0  # Show status summary every N seconds (when no frames)

    def _get_status_str(self) -> str:
        """Get compact status string for inline display.
        
        NOTE: For RX mode, we don't query device status inline because
        the SLCAN status query (F command) corrupts the receive buffer.
        We only show frame count here.
        """
        if not self.show_status:
            return ""
        
        # Don't query device status during active reception - it corrupts the buffer!
        # Just show that status display is enabled (actual status shown at summary)
        return ""

    def start(self) -> None:
        """Start receiving CAN frames continuously."""
        self._running = True
        self._frame_count = 0
        self._start_time = time.time()
        self._last_status_time = time.time()

        original_handler = signal.signal(signal.SIGINT, self._signal_handler)

        print(f"\n[RX] Listening for CAN frames...")
        if self.show_status:
            print(f"[RX] Status will be shown at summary (inline status disabled to avoid buffer corruption)")
        print(f"[RX] Press Ctrl+C to stop\n")
        print("-" * 80)
        header = f"{'#':>6}  {'Time':<10}  {'ID':<11}  {'DLC':<4}  {'Data':<24}"
        print(header)
        print("-" * 80)

        try:
            while self._running:
                try:
                    frame = self.device.receive(timeout=self.timeout)
                    
                    if frame is not None:
                        self._frame_count += 1
                        self._last_frame_time = time.time()
                        self._print_frame(frame)
                    else:
                        # Check for stall (no frames for too long after receiving some)
                        if self._last_frame_time is not None:
                            stall_duration = time.time() - self._last_frame_time
                            if stall_duration > self._stall_timeout:
                                print(f"\n[RX] No frames for {stall_duration:.0f}s, attempting recovery...")
                                self._try_recovery()
                                self._last_frame_time = time.time()
                                
                except Exception as e:
                    print(f"[RX ERROR] {e}")
                    time.sleep(0.5)

        finally:
            signal.signal(signal.SIGINT, original_handler)
            self._print_summary()

    def _print_frame(self, frame: CanFrame) -> None:
        """Print a received frame."""
        elapsed = time.time() - self._start_time
        id_str = f"0x{frame.arbitration_id:08X}" if frame.is_extended_id else f"0x{frame.arbitration_id:03X}"
        data_str = frame.to_hex_string()
        
        print(f"{self._frame_count:6d}  {elapsed:>8.3f}s  {id_str:<11}  {len(frame.data):<4}  {data_str:<24}")

    def _try_recovery(self) -> None:
        """Attempt to recover from stalled state."""
        try:
            print("[RX] Closing and reopening connection...")
            self.device.disconnect()
            time.sleep(1.0)
            self.device.connect()
            print("[RX] Reconnected successfully!")
        except Exception as e:
            print(f"[RX] Recovery failed: {e}")
            print("[RX] You may need to unplug and replug the device.")

    def stop(self) -> None:
        self._running = False

    def _signal_handler(self, signum, frame) -> None:
        print("\n\n[RX] Stopping...")
        self._running = False

    def _print_summary(self) -> None:
        duration = time.time() - self._start_time if self._start_time else 0
        rate = self._frame_count / duration if duration > 0 else 0

        print("-" * 80)
        print(f"\n[RX] Summary: {self._frame_count} frames in {duration:.2f}s ({rate:.1f} frames/sec)")
        
        # Final status - safe to query now that reception has stopped
        if self.show_status:
            # Small delay to let any pending data settle
            time.sleep(0.1)
            status = self.device.get_status()
            if status:
                print(f"[RX] Final Status: TEC:{status.tx_err_cnt} REC:{status.rx_err_cnt} LastErr:{status.last_error_str}")
            else:
                print(f"[RX] Final Status: Unable to query")
        print()


def run_receiver(
    port: str,
    bitrate: int,
    serial_baud: int,
    show_status: bool = False
) -> int:
    """Run receiver with given configuration."""
    device = CanDevice(port=port, bitrate=bitrate, serial_baud=serial_baud)

    try:
        print(f"\n[*] Connecting to {port}...")
        device.connect()
        print(f"[+] Connected: {device}")

        rx = Receiver(device=device, show_status=show_status)
        rx.start()
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
