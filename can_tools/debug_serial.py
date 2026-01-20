"""Debug script to find serial port access in python-can slcan"""

import can

PORT = 'COM5'  # Change this to your port
BITRATE = 500000

print(f"Connecting to {PORT}...")
bus = can.interface.Bus(interface='slcan', channel=PORT, bitrate=BITRATE)
print(f"Connected!")

print(f"\nBus type: {type(bus)}")
print(f"\nBus attributes:")
for attr in dir(bus):
    if not attr.startswith('__'):
        try:
            val = getattr(bus, attr)
            if not callable(val):
                print(f"  {attr}: {type(val).__name__} = {val}")
        except:
            print(f"  {attr}: (error reading)")

# Try to find serial
print("\n\nLooking for serial connection...")
for attr in ['_ser', 'ser', '_serial', 'serial', 'serialPortOrig', 'channel']:
    val = getattr(bus, attr, None)
    if val is not None:
        print(f"  Found: bus.{attr} = {type(val).__name__}")
        if hasattr(val, 'write'):
            print(f"    -> Has write() method - this is likely the serial port!")
            
            # Test it
            print(f"\n  Testing 'F' command...")
            val.reset_input_buffer()
            val.write(b'F\r')
            val.flush()
            
            import time
            time.sleep(0.2)
            if val.in_waiting:
                response = val.read(val.in_waiting)
                print(f"  Response: {response}")
            else:
                print(f"  No response")

bus.shutdown()
print("\nDone.")

