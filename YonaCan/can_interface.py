"""
YonaCan - CAN Interface Module
Handles candleLight/gs_usb device communication.
"""

import os
import threading
import queue
import time
from dataclasses import dataclass
from typing import List, Optional, Callable
from enum import Enum


# Setup libusb for Windows
def setup_libusb():
    """Setup libusb DLL path for Windows."""
    try:
        import libusb
        pkg_path = libusb.__path__[0]
        dll_path = os.path.join(pkg_path, '_platform', 'windows', 'x86_64', 'libusb-1.0.dll')
        
        if os.path.exists(dll_path):
            dll_dir = os.path.dirname(dll_path)
            os.environ['PATH'] = dll_dir + os.pathsep + os.environ.get('PATH', '')
            if hasattr(os, 'add_dll_directory'):
                os.add_dll_directory(dll_dir)
            return True
    except Exception:
        pass
    return False


# Setup libusb on module import
setup_libusb()


class FrameDirection(Enum):
    RX = "RX"
    TX = "TX"


@dataclass
class CANFrame:
    """Represents a CAN frame with metadata."""
    timestamp: float
    can_id: int
    data: bytes
    dlc: int
    direction: FrameDirection
    is_extended: bool = False
    is_remote: bool = False
    is_error: bool = False
    
    @property
    def id_hex(self) -> str:
        """Get CAN ID as hex string."""
        if self.is_extended:
            return f"0x{self.can_id:08X}"
        return f"0x{self.can_id:03X}"
    
    @property
    def data_hex(self) -> str:
        """Get data as hex string."""
        return " ".join(f"{b:02X}" for b in self.data)
    
    @property
    def data_ascii(self) -> str:
        """Get data as ASCII string (printable chars only)."""
        return "".join(chr(b) if 32 <= b <= 126 else "." for b in self.data)


@dataclass 
class CANDevice:
    """Represents a detected CAN device."""
    name: str
    device_id: str
    channel: int
    device_obj: any = None
    
    def __str__(self):
        return f"{self.name} (Ch:{self.channel})"


class CANInterface:
    """
    CAN Interface for candleLight/gs_usb devices.
    """
    
    def __init__(self):
        self._device: Optional[any] = None
        self._running = False
        self._rx_thread: Optional[threading.Thread] = None
        self._rx_queue: queue.Queue = queue.Queue()
        self._frame_callback: Optional[Callable[[CANFrame], None]] = None
        self._start_time: float = 0
        self._frame_count: int = 0
        self._bitrate: int = 500000
        
    @staticmethod
    def scan_devices() -> List[CANDevice]:
        """Scan for available candleLight/gs_usb devices."""
        devices = []
        
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
            print(f"Error scanning devices: {e}")
        
        return devices
    
    def connect(self, device: CANDevice, bitrate: int = 500000) -> bool:
        """Connect to a CAN device."""
        try:
            self._device = device.device_obj
            self._bitrate = bitrate
            
            if not self._device.set_bitrate(bitrate):
                raise Exception("Failed to set bitrate")
            
            self._device.start()
            self._start_time = time.time()
            self._running = True
            self._frame_count = 0
            
            # Start receive thread
            self._rx_thread = threading.Thread(target=self._rx_loop, daemon=True)
            self._rx_thread.start()
            
            return True
            
        except Exception as e:
            print(f"Connection error: {e}")
            self._device = None
            return False
    
    def disconnect(self):
        """Disconnect from the CAN device."""
        self._running = False
        
        if self._rx_thread:
            self._rx_thread.join(timeout=1.0)
            self._rx_thread = None
        
        if self._device:
            try:
                self._device.stop()
            except Exception:
                pass
            self._device = None
    
    def send(self, can_id: int, data: bytes, extended: bool = False) -> bool:
        """Send a CAN frame."""
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
            
            # Create frame object for logging/display
            tx_frame = CANFrame(
                timestamp=time.time() - self._start_time,
                can_id=can_id,
                data=bytes(data),
                dlc=len(data),
                direction=FrameDirection.TX,
                is_extended=extended
            )
            self._frame_count += 1
            
            if self._frame_callback:
                self._frame_callback(tx_frame)
            
            return True
            
        except Exception as e:
            print(f"Send error: {e}")
            return False
    
    def set_frame_callback(self, callback: Callable[[CANFrame], None]):
        """Set callback for received frames."""
        self._frame_callback = callback
    
    def _rx_loop(self):
        """Receive loop running in background thread."""
        from gs_usb.gs_usb_frame import GsUsbFrame
        from gs_usb.constants import CAN_EFF_FLAG, CAN_RTR_FLAG, CAN_ERR_FLAG
        
        while self._running:
            try:
                # Non-blocking read with timeout
                frame = GsUsbFrame()
                if self._device.read(frame, timeout_ms=100):
                    # Parse frame
                    is_extended = bool(frame.can_id & CAN_EFF_FLAG)
                    is_remote = bool(frame.can_id & CAN_RTR_FLAG)
                    is_error = bool(frame.can_id & CAN_ERR_FLAG)
                    
                    can_id = frame.can_id & (0x1FFFFFFF if is_extended else 0x7FF)
                    
                    rx_frame = CANFrame(
                        timestamp=time.time() - self._start_time,
                        can_id=can_id,
                        data=bytes(frame.data[:frame.can_dlc]),
                        dlc=frame.can_dlc,
                        direction=FrameDirection.RX,
                        is_extended=is_extended,
                        is_remote=is_remote,
                        is_error=is_error
                    )
                    self._frame_count += 1
                    
                    if self._frame_callback:
                        self._frame_callback(rx_frame)
                        
            except Exception as e:
                if self._running:
                    print(f"RX error: {e}")
                    time.sleep(0.1)
    
    @property
    def is_connected(self) -> bool:
        return self._device is not None and self._running
    
    @property
    def frame_count(self) -> int:
        return self._frame_count
    
    @property
    def bitrate(self) -> int:
        return self._bitrate

