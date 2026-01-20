"""
CanDevice - A wrapper class for CAN bus communication via SLCAN interface.
"""

import can
import serial
from typing import Optional, Callable
from dataclasses import dataclass

from .config import DEFAULT_SERIAL_BAUD, DEFAULT_CAN_BITRATE


# Last Error Code meanings
LEC_CODES = {
    0: "None",
    1: "Stuff Error",
    2: "Form Error", 
    3: "ACK Error (no acknowledgment)",
    4: "Bit Recessive Error",
    5: "Bit Dominant Error",
    6: "CRC Error",
    7: "Set by software",
}


@dataclass
class CanStatus:
    """CAN bus status information."""
    bus_state: bool        # True if on bus
    error_warning: bool    # Error warning flag (TEC or REC >= 96)
    error_passive: bool    # Error passive flag (TEC or REC >= 128)
    bus_off: bool          # Bus-off flag (TEC >= 256)
    last_error: int        # Last error code (0-7)
    tx_err_cnt: int        # Transmit error counter
    rx_err_cnt: int        # Receive error counter
    
    @property
    def last_error_str(self) -> str:
        """Get human-readable last error description."""
        return LEC_CODES.get(self.last_error, f"Unknown ({self.last_error})")
    
    @property
    def has_error(self) -> bool:
        """Check if any error condition exists."""
        return self.error_warning or self.error_passive or self.bus_off or self.last_error != 0
    
    def __str__(self) -> str:
        state = "ON BUS" if self.bus_state else "OFF BUS"
        status = f"[{state}] TEC:{self.tx_err_cnt} REC:{self.rx_err_cnt}"
        if self.last_error != 0:
            status += f" LastErr:{self.last_error_str}"
        if self.error_warning:
            status += " [WARNING]"
        if self.error_passive:
            status += " [PASSIVE]"
        if self.bus_off:
            status += " [BUS-OFF]"
        return status


@dataclass
class CanFrame:
    """Represents a CAN frame."""
    arbitration_id: int
    data: bytes
    is_extended_id: bool = False
    timestamp: float = 0.0

    def to_hex_string(self) -> str:
        """Return data as hex string."""
        return ' '.join(f'{b:02X}' for b in self.data)

    def __str__(self) -> str:
        id_str = f"0x{self.arbitration_id:08X}" if self.is_extended_id else f"0x{self.arbitration_id:03X}"
        return f"ID: {id_str}  Data: {self.to_hex_string()}  DLC: {len(self.data)}"


class CanDevice:
    """
    Wrapper class for CAN bus communication using SLCAN (CANable) interface.
    
    Example usage:
        device = CanDevice(port='COM5', bitrate=500000)
        device.connect()
        device.send(CanFrame(0x123, bytes([0x01, 0x02, 0x03])))
        frame = device.receive(timeout=1.0)
        status = device.get_status()
        device.disconnect()
    """

    def __init__(
        self,
        port: str,
        bitrate: int = DEFAULT_CAN_BITRATE,
        serial_baud: int = DEFAULT_SERIAL_BAUD
    ):
        """
        Initialize CAN device.
        
        Args:
            port: Serial port (e.g., 'COM5' on Windows, '/dev/ttyUSB0' on Linux)
            bitrate: CAN bus bitrate in bps (default: 500000)
            serial_baud: Serial communication baud rate (default: 115200)
        """
        self.port = port
        self.bitrate = bitrate
        self.serial_baud = serial_baud
        self._bus: Optional[can.interface.Bus] = None
        self._serial: Optional[serial.Serial] = None
        self._connected = False
        self._last_status: Optional[CanStatus] = None

    @property
    def is_connected(self) -> bool:
        """Check if device is connected."""
        return self._connected and self._bus is not None

    def connect(self) -> None:
        """
        Connect to the CAN device and open the bus.
        
        Raises:
            ConnectionError: If connection fails
        """
        if self._connected:
            return

        try:
            self._bus = can.interface.Bus(
                interface='slcan',
                channel=self.port,
                bitrate=self.bitrate,
                ttyBaudrate=self.serial_baud
            )
            self._connected = True
            
            # Try to get reference to the serial connection for status queries
            # python-can slcan uses _ser or serialPortOrig
            self._serial = getattr(self._bus, '_ser', None)
            if self._serial is None:
                self._serial = getattr(self._bus, 'serialPortOrig', None)
            if self._serial is None:
                # Try to access via the protocol
                protocol = getattr(self._bus, '_protocol', None)
                if protocol:
                    self._serial = getattr(protocol, '_ser', None)
                    
        except Exception as e:
            self._connected = False
            raise ConnectionError(f"Failed to connect to {self.port}: {e}")

    def disconnect(self) -> None:
        """Disconnect from the CAN device."""
        if self._bus:
            try:
                self._bus.shutdown()
            except Exception:
                pass  # Ignore errors during shutdown
            finally:
                self._bus = None
                self._connected = False

    def send(self, frame: CanFrame) -> bool:
        """
        Send a CAN frame.
        
        Args:
            frame: CanFrame to send
            
        Returns:
            True if sent successfully, False otherwise
        """
        if not self.is_connected:
            raise RuntimeError("Device not connected. Call connect() first.")

        try:
            msg = can.Message(
                arbitration_id=frame.arbitration_id,
                data=frame.data,
                is_extended_id=frame.is_extended_id
            )
            self._bus.send(msg)
            
            # Periodically flush receive buffer to prevent overflow
            self._tx_count = getattr(self, '_tx_count', 0) + 1
            if self._tx_count % 50 == 0:  # Every 50 frames (more aggressive)
                flushed = self._flush_rx_buffer()
                if flushed > 100:
                    print(f"\n[DEBUG] Flushed {flushed} bytes from buffer at frame {self._tx_count}")
                elif flushed < 0:
                    print(f"\n[DEBUG] Flush failed at frame {self._tx_count}!")
            
            return True
        except Exception as e:
            print(f"[TX ERROR] {e}")
            return False
    
    def _flush_rx_buffer(self) -> int:
        """Flush any pending data in receive buffer to prevent overflow.
        
        Returns:
            Number of bytes/messages flushed, or -1 if flush failed
        """
        flushed = 0
        try:
            # Method 1: Try to reset serial input buffer directly
            ser = self._serial
            if ser is None:
                ser = getattr(self._bus, '_ser', None)
            if ser and hasattr(ser, 'in_waiting'):
                pending = ser.in_waiting
                if pending > 0:
                    ser.reset_input_buffer()
                    flushed = pending
                return flushed
            
            # Method 2: Read and discard any pending CAN messages
            while True:
                msg = self._bus.recv(timeout=0.001)  # Very short timeout
                if msg is None:
                    break
                flushed += 1
            return flushed
        except Exception as e:
            return -1  # Indicate flush failed

    def receive(self, timeout: float = 1.0) -> Optional[CanFrame]:
        """
        Receive a CAN frame.
        
        Args:
            timeout: Timeout in seconds (default: 1.0)
            
        Returns:
            CanFrame if received, None if timeout
        """
        if not self.is_connected:
            raise RuntimeError("Device not connected. Call connect() first.")

        try:
            msg = self._bus.recv(timeout=timeout)
            if msg is not None:
                return CanFrame(
                    arbitration_id=msg.arbitration_id,
                    data=bytes(msg.data),
                    is_extended_id=msg.is_extended_id,
                    timestamp=msg.timestamp or 0.0
                )
            return None
        except Exception:
            return None

    def __enter__(self):
        """Context manager entry."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.disconnect()
        return False

    def get_status(self) -> Optional[CanStatus]:
        """
        Query CAN bus status from the device.
        
        Returns:
            CanStatus object or None if query fails
        """
        if not self.is_connected:
            return None
            
        try:
            # Try multiple ways to access the serial connection
            ser = self._serial
            if ser is None:
                ser = getattr(self._bus, '_ser', None)
            if ser is None:
                ser = getattr(self._bus, 'ser', None)
            if ser is None:
                # For newer python-can versions
                ser = getattr(self._bus, 'serialPortOrig', None)
            
            if ser is None:
                print(f"\n[DEBUG] Cannot access serial port for status query")
                return None
            
            # Check if serial port is still open
            if hasattr(ser, 'is_open') and not ser.is_open:
                print(f"\n[DEBUG] Serial port is closed!")
                return None
            
            # Check buffer state before query
            if hasattr(ser, 'in_waiting'):
                pending = ser.in_waiting
                if pending > 500:
                    print(f"\n[DEBUG] Large buffer pending before status: {pending} bytes")
            
            # Clear any pending data
            ser.reset_input_buffer()
            
            # Send status query command
            ser.write(b'F\r')
            ser.flush()
            
            # Read response (with timeout)
            import time
            start = time.time()
            response = b''
            while time.time() - start < 0.5:
                if ser.in_waiting:
                    response += ser.read(ser.in_waiting)
                    if b'\r' in response or b'\n' in response:
                        break
                time.sleep(0.01)
            
            # Parse response: F:bus,ewarn,epass,boff,lec,tec,rec
            response_str = response.decode('ascii', errors='ignore').strip()
            
            # Debug: show what we received if it's not a valid status
            if not response_str.startswith('F:'):
                # Only log occasionally to avoid spam
                self._status_fail_count = getattr(self, '_status_fail_count', 0) + 1
                if self._status_fail_count <= 3 or self._status_fail_count % 50 == 0:
                    preview = response_str[:50] if response_str else "(empty)"
                    print(f"\n[DEBUG] Status response #{self._status_fail_count}: '{preview}'")
                return None
            
            parts = response_str[2:].split(',')
            if len(parts) >= 7:
                self._status_fail_count = 0  # Reset on success
                self._last_status = CanStatus(
                    bus_state=bool(int(parts[0])),
                    error_warning=bool(int(parts[1])),
                    error_passive=bool(int(parts[2])),
                    bus_off=bool(int(parts[3])),
                    last_error=int(parts[4]),
                    tx_err_cnt=int(parts[5]),
                    rx_err_cnt=int(parts[6])
                )
                return self._last_status
            
            return None
            
        except Exception as e:
            print(f"\n[DEBUG] Status query exception: {e}")
            return None

    @property
    def last_status(self) -> Optional[CanStatus]:
        """Get the last queried status."""
        return self._last_status

    def __str__(self) -> str:
        status = "connected" if self.is_connected else "disconnected"
        return f"CanDevice({self.port}, {self.bitrate}bps, {status})"

    def __repr__(self) -> str:
        return self.__str__()

