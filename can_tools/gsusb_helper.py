"""
Helper to setup libusb backend for gs_usb on Windows.
Import this BEFORE using gs_usb or python-can with gs_usb interface.
"""

import os
import sys


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
    except ImportError:
        print("Warning: libusb package not installed. Run: pip install libusb")
    except Exception as e:
        print(f"Warning: Failed to setup libusb: {e}")
    
    return False


# Auto-setup on import
_libusb_ready = setup_libusb()


def scan_devices():
    """Scan for candleLight/gs_usb devices."""
    from gs_usb.gs_usb import GsUsb
    return GsUsb.scan()


def send_test_frame(device, can_id=0x123, data=None):
    """Send a test frame."""
    from gs_usb.gs_usb_frame import GsUsbFrame
    
    frame = GsUsbFrame()
    frame.can_id = can_id
    frame.data = data or [0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08]
    frame.can_dlc = len(frame.data)
    
    device.send(frame)
    return frame


if __name__ == "__main__":
    print("Scanning for candleLight devices...")
    devs = scan_devices()
    
    if devs:
        print(f"Found {len(devs)} device(s):")
        for i, dev in enumerate(devs):
            print(f"  [{i}] {dev}")
    else:
        print("No devices found!")

