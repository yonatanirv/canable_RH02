===============================================================================
  YonaCan - CAN Bus Analyzer for candleLight Devices
  Version 1.0.0
===============================================================================

  Table of Contents
  -----------------
  1. Overview
  2. System Requirements
  3. First-Time Setup (Fresh Windows PC)
  4. Running YonaCan
  5. Features
  6. Flashing candleLight Firmware (Hardware Setup)
  7. Troubleshooting
  8. License


===============================================================================
  1. OVERVIEW
===============================================================================

  YonaCan is a Windows CAN bus analyzer designed for candleLight / gs_usb
  compatible USB-CAN adapters. It supports:

    - Real-time CAN frame viewing (RX/TX)
    - DBC file loading and parsed signal viewer with live graphs
    - Offline log import viewer (CL2000 / CSV) with ISOBUS DDI dictionary
    - CAN frame transmission (single frames)
    - CAN signal simulator (sweep/static/random modes)
    - CAN bus error monitoring (TEC/REC counters)
    - CSV logging with auto-rotation

  Supported hardware:
    - candleLight          (STM32F072xB)
    - CANable / CANable Pro (STM32F042C6 / STM32F072xB)
    - CANtact              (STM32F042C6)
    - USB2CAN              (STM32F042x6)
    - CANAlyze             (STM32F042C6)
    - Any gs_usb-compatible adapter


===============================================================================
  2. SYSTEM REQUIREMENTS
===============================================================================

  Operating System : Windows 10 or Windows 11 (64-bit)
  USB              : One free USB port
  Hardware         : A candleLight / gs_usb compatible CAN adapter
  Disk Space       : ~150 MB (application folder)
  RAM              : 4 GB minimum recommended

  No Python installation is required - everything is bundled in the exe.


===============================================================================
  3. FIRST-TIME SETUP (FRESH WINDOWS PC)
===============================================================================

  Step 1: Install the WinUSB Driver (one-time, per device)
  --------------------------------------------------------
  candleLight devices need the WinUSB driver bound to them. On recent
  Windows 10/11 versions this may happen automatically. If the device
  is not recognized, use Zadig:

    a) Download Zadig from:  https://zadig.akeo.ie/
    b) Plug in your candleLight USB-CAN adapter.
    c) Open Zadig.
    d) In the menu bar, select Options > List All Devices.
    e) From the dropdown, select your device. It may appear as:
       - "candleLight USB to CAN adapter"
       - "CANable"  /  "CANtact"
       - "STM32 USB Device"  (if using gs_usb firmware)
    f) Set the target driver to "WinUSB" (on the right side).
    g) Click "Install Driver" (or "Replace Driver" if one exists).
    h) Wait for the installation to complete.
    i) Unplug and replug the device.

  NOTE: You only need to do this ONCE per device on each PC.

  Step 2: Verify Device Recognition
  ----------------------------------
    a) Open Device Manager (Win+X > Device Manager).
    b) Look under "Universal Serial Bus devices" for your device.
    c) If it shows with a yellow warning icon, repeat Step 1.

  Step 3: (Optional) Install Visual C++ Redistributable
  ------------------------------------------------------
  Most Windows PCs already have this. If YonaCan fails to start with
  a missing DLL error, install the VC++ 2015-2022 Redistributable:

    https://aka.ms/vs/17/release/vc_redist.x64.exe


===============================================================================
  4. RUNNING YONACAN
===============================================================================

  a) Extract the YonaCan zip file to any folder.
  b) Open the extracted folder.
  c) Double-click "YonaCan.exe" to launch.
  d) In the top connection bar:
     - Click "Scan" to detect connected CAN adapters.
     - Select your device from the dropdown.
     - Choose the CAN bitrate (default: 500 kbps).
     - Click "Connect".
  e) The status bar will show connection state and RX/TX counters.

  DBC Files:
  ----------
  A default J1939 DBC file is included in the "DBCs" subfolder.
  You can load your own .dbc files from the "CAN Simulator" or
  "Parsed Data Viewer" tabs.


===============================================================================
  5. FEATURES
===============================================================================

  Raw Data Viewer
  ---------------
  Real-time display of all CAN frames on the bus. Columns:
  Frame #, Timestamp, CAN ID, Direction (RX/TX), DLC, Data (hex), ASCII.

  Parsed Data Viewer
  ------------------
  Load a .dbc file to see decoded signal values. Select SPNs to plot
  live graphs (up to 5 simultaneous). Supports auto-scale, manual
  Y-axis limits, adjustable time window, and start/stop per graph.

  Log Import Viewer
  -----------------
  Analyze recorded CAN logs offline (no device connection required).
  Supported formats:
    - CSS Electronics CL2000 text export (.txt)
    - YonaCan CSV logs (.csv)
  Load a J1939 DBC for PGN/SPN names and decoding. The bundled
  ISOBUS/isobus_ddi.json dictionary (ISO 11783-11) provides DDI
  names and full definitions in DDI presentation mode.
  After loading a log or changing a dictionary, a summary shows how
  many PGNs were found and how many match the DBC / ISOBUS dictionary.
  Select a PGN to view SPN values and graph bytes, SPNs, or browse DDIs.

  CAN Simulator
  -------------
  Generate and transmit CAN signals based on a loaded DBC file.
  For each signal (SPN), configure:
    - Mode    : Sweep (triangle wave), Static, or Random
    - Step    : Value added/subtracted per tick
    - Tics/s  : Number of ticks (steps) per second
  Enable/disable individual signals with checkboxes.

  Transmit Frame
  --------------
  Send individual CAN frames manually. Enter CAN ID, DLC, and data.

  Logging
  -------
  Start/stop CSV logging from the menu. Logs are saved to:
    %USERPROFILE%\YonaCan_Logs\


===============================================================================
  6. FLASHING CANDLELIGHT FIRMWARE (HARDWARE SETUP)
===============================================================================

  If you have a blank or bricked adapter, or want to update firmware,
  follow these steps.

  What You Need:
  - An ST-Link V2 programmer (or STM32 Discovery board)
  - STM32CubeProgrammer (free from ST)
  - The correct firmware .bin file
  - 4 jumper wires (for SWD connection)

  Step 1: Install STM32CubeProgrammer
  ------------------------------------
    a) Download from: https://www.st.com/en/development-tools/stm32cubeprog.html
    b) Install with default settings.
    c) This also installs the necessary ST-Link USB drivers.

  Step 2: Connect ST-Link to the Target Board
  --------------------------------------------
  Wire the ST-Link to the CAN adapter's SWD header:

    ST-Link Pin     Target Board Pin
    -----------     ----------------
    SWDIO     <-->  SWDIO
    SWCLK     <-->  SWCLK
    GND       <-->  GND
    3.3V      <-->  3.3V  (to power the board from ST-Link)

  NOTE: Do NOT connect USB to the CAN adapter while using ST-Link
        power, unless the board supports it. Check your board docs.

  Step 3: Flash the Firmware
  --------------------------
  Using STM32CubeProgrammer GUI:

    a) Open STM32CubeProgrammer.
    b) On the right panel, select "ST-LINK" as the connection method.
    c) Click "Connect". The tool should detect the STM32 chip.
       - If not detected, check wiring and ensure ST-Link drivers
         are installed.
    d) Click the "Erasing & Programming" tab (download icon).
    e) In "File path", browse to the firmware .bin file:
       - For candleLight boards: candleLight_fw.bin
       - For CANable boards:     canable_fw.bin
       - For CANtact boards:     cantact_fw.bin
       (Pre-built binaries are in the "candleLight v2.0/bin/" folder
        of the source repository.)
    f) Set "Start address" to: 0x08000000
    g) Check "Verify programming".
    h) Click "Start Programming".
    i) Wait for "Download verified successfully".
    j) Disconnect ST-Link wires.
    k) Plug the CAN adapter into USB - it should enumerate as a
       candleLight / gs_usb device.

  Alternative: Flash via DFU (USB Bootloader)
  --------------------------------------------
  If your board has a BOOT jumper or button:

    a) Set the BOOT jumper (or hold the BOOT button while plugging in).
    b) The device appears as "STM32 BOOTLOADER" in Device Manager.
    c) Use STM32CubeProgrammer:
       - Select "USB" connection method (instead of ST-LINK).
       - Connect, then flash as described above.
    d) Remove the BOOT jumper and replug the device.

  Alternative: Flash via dfu-util (Command Line)
  -----------------------------------------------
    dfu-util -d 0483:df11 -c 1 -i 0 -a 0 -s 0x08000000:leave -D firmware.bin


===============================================================================
  7. TROUBLESHOOTING
===============================================================================

  Problem: YonaCan does not start / missing DLL error
  Solution: Install the Visual C++ 2015-2022 Redistributable (x64):
            https://aka.ms/vs/17/release/vc_redist.x64.exe

  Problem: "No devices found" when scanning
  Solution: 1. Check USB cable and connection.
            2. Open Device Manager and verify the device appears.
            3. Use Zadig to install/reinstall the WinUSB driver.
            4. Unplug and replug the device.

  Problem: Device connects but no RX data
  Solution: 1. Verify CAN bitrate matches the bus.
            2. Check CAN bus wiring (CANH, CANL).
            3. Ensure bus termination (120 ohm resistors).
            4. Confirm at least 2 active nodes on the bus.

  Problem: TX frames show errors / high TEC count
  Solution: 1. Verify bitrate matches all devices on the bus.
            2. Check CAN bus termination.
            3. Ensure the bus is not in bus-off state (disconnect
               and reconnect to reset).

  Problem: ST-Link cannot detect the chip
  Solution: 1. Check SWD wiring (SWDIO, SWCLK, GND, 3.3V).
            2. Hold RESET while connecting, then release.
            3. Try "Connect under reset" option in CubeProgrammer.
            4. Ensure ST-Link drivers are installed.


===============================================================================
  8. LICENSE
===============================================================================

  See LICENSE.md in the project repository.


===============================================================================
  YonaCan - Agromentum LTD
===============================================================================

