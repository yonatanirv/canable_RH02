@echo off
REM YonaCan Build Script - Creates standalone Windows EXE
REM Run this from the YonaCan directory

echo ========================================
echo Building YonaCan...
echo ========================================

REM Check if PyInstaller is installed
pip show pyinstaller >nul 2>&1
if errorlevel 1 (
    echo Installing PyInstaller...
    pip install pyinstaller
)

REM Get libusb DLL path
for /f "delims=" %%i in ('python -c "import libusb, os; print(os.path.join(libusb.__path__[0], '_platform', 'windows', 'x86_64'))"') do set LIBUSB_DIR=%%i

echo LibUSB directory: %LIBUSB_DIR%

REM Build the EXE
echo.
echo Building executable...
pyinstaller --noconfirm ^
    --onedir ^
    --windowed ^
    --name "YonaCan" ^
    --icon "NONE" ^
    --add-data "%LIBUSB_DIR%\libusb-1.0.dll;." ^
    --hidden-import "gs_usb" ^
    --hidden-import "gs_usb.gs_usb" ^
    --hidden-import "gs_usb.gs_usb_frame" ^
    --hidden-import "gs_usb.constants" ^
    --hidden-import "usb" ^
    --hidden-import "usb.core" ^
    --hidden-import "usb.backend" ^
    --hidden-import "usb.backend.libusb1" ^
    main.py

if errorlevel 1 (
    echo.
    echo BUILD FAILED!
    pause
    exit /b 1
)

REM Copy libusb DLL to dist folder
echo.
echo Copying libusb DLL...
copy "%LIBUSB_DIR%\libusb-1.0.dll" "dist\YonaCan\" /Y

echo.
echo ========================================
echo Build complete!
echo Output: dist\YonaCan\YonaCan.exe
echo ========================================
echo.

pause

