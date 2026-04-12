@echo off
REM =============================================
REM  YonaCan Build Script
REM  Creates standalone Windows EXE
REM  Run this from the YonaCan directory
REM =============================================

echo ========================================
echo  YonaCan Windows Build
echo ========================================
echo.

REM -- Check Python --
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found in PATH!
    pause
    exit /b 1
)

REM -- Install / upgrade build dependencies --
echo [1/4] Checking dependencies...
pip show pyinstaller >nul 2>&1
if errorlevel 1 (
    echo       Installing PyInstaller...
    pip install pyinstaller
)
pip show gs_usb >nul 2>&1
if errorlevel 1 (
    echo       Installing gs_usb...
    pip install gs_usb
)
pip show cantools >nul 2>&1
if errorlevel 1 (
    echo       Installing cantools...
    pip install cantools
)

REM -- Locate libusb-1.0.dll --
echo [2/4] Locating libusb DLL...
set LIBUSB_DLL=
for /f "delims=" %%i in ('python -c "import libusb, os; p=os.path.join(libusb.__path__[0],'_platform','windows','x86_64','libusb-1.0.dll'); print(p) if os.path.exists(p) else print('')" 2^>nul') do set LIBUSB_DLL=%%i

if "%LIBUSB_DLL%"=="" (
    echo [WARNING] libusb-1.0.dll not found via pip package.
    echo          The EXE may not work without it.
    echo          Trying to continue anyway...
    set ADD_LIBUSB=
) else (
    echo       Found: %LIBUSB_DLL%
    set ADD_LIBUSB=--add-binary "%LIBUSB_DLL%;."
)

REM -- Build the EXE --
echo [3/4] Building executable...
echo.
pyinstaller --noconfirm ^
    --onedir ^
    --windowed ^
    --name "YonaCan" ^
    --paths "." ^
    %ADD_LIBUSB% ^
    --hidden-import "gs_usb" ^
    --hidden-import "gs_usb.gs_usb" ^
    --hidden-import "gs_usb.gs_usb_frame" ^
    --hidden-import "gs_usb.constants" ^
    --hidden-import "usb" ^
    --hidden-import "usb.core" ^
    --hidden-import "usb.util" ^
    --hidden-import "usb.backend" ^
    --hidden-import "usb.backend.libusb1" ^
    --hidden-import "usb._objfinalizer" ^
    --hidden-import "usb._interop" ^
    --hidden-import "libusb" ^
    --hidden-import "cantools" ^
    --hidden-import "cantools.database" ^
    --hidden-import "cantools.database.can" ^
    --collect-submodules "cantools" ^
    --collect-submodules "gs_usb" ^
    main.py

if errorlevel 1 (
    echo.
    echo ========================================
    echo  BUILD FAILED!
    echo ========================================
    pause
    exit /b 1
)

REM -- Copy libusb DLL to dist (belt-and-suspenders) --
echo [4/4] Finalizing...
if not "%LIBUSB_DLL%"=="" (
    copy "%LIBUSB_DLL%" "dist\YonaCan\" /Y >nul 2>&1
    echo       libusb DLL copied to dist.
)

REM -- Copy default DBC files if present --
if exist "DBCs" (
    if not exist "dist\YonaCan\DBCs" mkdir "dist\YonaCan\DBCs"
    xcopy "DBCs\*.*" "dist\YonaCan\DBCs\" /Y /Q >nul 2>&1
    echo       DBC files copied to dist.
)

REM -- Copy README --
if exist "README.txt" (
    copy "README.txt" "dist\YonaCan\README.txt" /Y >nul 2>&1
    echo       README.txt copied to dist.
)

echo.
echo ========================================
echo  Build complete!
echo  Output: dist\YonaCan\YonaCan.exe
echo ========================================
echo.
echo  To distribute, zip the entire
echo  dist\YonaCan\ folder.
echo.

pause
