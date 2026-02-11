"""
YonaCan - Simulator Device Driver
CandleLight/gs_usb device driver for CAN bus simulation (transmission).

Provides a lightweight wrapper around the gs_usb library focused on
transmitting CAN frames for simulation purposes. Does not start a
receive thread — this is a TX-only driver.
"""

import time
from typing import List, Optional

from can_interface import setup_libusb, CANDevice

# Ensure libusb is available
setup_libusb()


class SimulatorDevice:
    """
    CandleLight device driver for CAN bus simulation.

    Manages a dedicated gs_usb device for transmitting simulated CAN frames.
    Unlike CANInterface (which runs an RX thread), this driver is transmit-only.

    Usage:
        sim = SimulatorDevice()
        devices = sim.scan_devices()
        sim.connect(devices[0], bitrate=250000)
        sim.send(can_id=0x18FEF100, data=b'\\x01\\x02', extended=True)
        sim.disconnect()
    """

    def __init__(self):
        self._device = None
        self._running = False
        self._bitrate: int = 500000
        self._start_time: float = 0.0
        self._tx_count: int = 0
        self._error_count: int = 0

    # ------------------------------------------------------------------
    # Device scanning
    # ------------------------------------------------------------------

    @staticmethod
    def scan_devices() -> List[CANDevice]:
        """
        Scan for available candleLight / gs_usb devices.

        Returns:
            List of CANDevice objects found on the USB bus.
        """
        devices: List[CANDevice] = []
        try:
            from gs_usb.gs_usb import GsUsb
            gs_devices = GsUsb.scan()
            for i, dev in enumerate(gs_devices):
                devices.append(CANDevice(
                    name=str(dev),
                    device_id=f"gs_usb_{i}",
                    channel=i,
                    device_obj=dev
                ))
        except Exception as e:
            print(f"[SimDevice] Error scanning devices: {e}")
        return devices

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    def connect(self, device: CANDevice, bitrate: int = 500000) -> bool:
        """
        Connect to a candleLight device for simulation.

        Args:
            device:  CANDevice obtained from scan_devices().
            bitrate: CAN bus bitrate in bps (default 500 000).

        Returns:
            True on success, False on failure.
        """
        try:
            self._device = device.device_obj
            self._bitrate = bitrate

            if not self._device.set_bitrate(bitrate):
                raise RuntimeError("Failed to set bitrate")

            self._device.start()
            self._start_time = time.time()
            self._running = True
            self._tx_count = 0
            self._error_count = 0
            return True

        except Exception as e:
            print(f"[SimDevice] Connection error: {e}")
            self._device = None
            self._running = False
            return False

    def disconnect(self):
        """Disconnect from the device and release resources."""
        self._running = False
        if self._device:
            try:
                self._device.stop()
            except Exception:
                pass
            self._device = None

    # ------------------------------------------------------------------
    # Frame transmission
    # ------------------------------------------------------------------

    def send(self, can_id: int, data: bytes, extended: bool = False) -> bool:
        """
        Send a single CAN frame.

        Args:
            can_id:   CAN arbitration ID.
            data:     Payload bytes (0-8 bytes).
            extended: True for 29-bit extended ID, False for 11-bit.

        Returns:
            True if the frame was handed to the hardware, False on error.
        """
        if not self._device or not self._running:
            return False

        try:
            from gs_usb.gs_usb_frame import GsUsbFrame
            from gs_usb.constants import CAN_EFF_FLAG

            frame = GsUsbFrame()
            frame.can_id = can_id | (CAN_EFF_FLAG if extended else 0)
            frame.data = list(data)
            frame.can_dlc = len(data)

            self._device.send(frame)
            self._tx_count += 1
            return True

        except Exception as e:
            self._error_count += 1
            print(f"[SimDevice] Send error: {e}")
            return False

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def is_connected(self) -> bool:
        """True when a device is open and ready to transmit."""
        return self._device is not None and self._running

    @property
    def tx_count(self) -> int:
        """Total frames successfully queued for transmission."""
        return self._tx_count

    @property
    def error_count(self) -> int:
        """Total transmission errors since connect."""
        return self._error_count

    @property
    def bitrate(self) -> int:
        """Current CAN bitrate in bps."""
        return self._bitrate

    @property
    def elapsed_time(self) -> float:
        """Seconds elapsed since connect (0 if not connected)."""
        if self._start_time and self._running:
            return time.time() - self._start_time
        return 0.0

    def __str__(self) -> str:
        state = "connected" if self.is_connected else "disconnected"
        return f"SimulatorDevice({self._bitrate}bps, {state}, TX:{self._tx_count})"

