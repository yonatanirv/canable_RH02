# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules

hiddenimports = ['gs_usb', 'gs_usb.gs_usb', 'gs_usb.gs_usb_frame', 'gs_usb.constants', 'usb', 'usb.core', 'usb.util', 'usb.backend', 'usb.backend.libusb1', 'usb._objfinalizer', 'usb._interop', 'libusb', 'cantools', 'cantools.database', 'cantools.database.can']
hiddenimports += collect_submodules('cantools')
hiddenimports += collect_submodules('gs_usb')


a = Analysis(
    ['main.py'],
    pathex=['.'],
    binaries=[('C:\\Users\\Ofer\\AppData\\Local\\Packages\\PythonSoftwareFoundation.Python.3.11_qbz5n2kfra8p0\\LocalCache\\local-packages\\Python311\\site-packages\\libusb\\_platform\\windows\\x86_64\\libusb-1.0.dll', '.')],
    datas=[],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='YonaCan',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='YonaCan',
)
