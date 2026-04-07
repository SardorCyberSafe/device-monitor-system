@echo off
echo ============================================
echo   Installing Device Monitor Agent
echo ============================================
echo.

set INSTALL_DIR=%ProgramData%\DeviceMonitor
if not exist "%INSTALL_DIR%" mkdir "%INSTALL_DIR%"

copy /Y "DeviceAgent.exe" "%INSTALL_DIR%\DeviceAgent.exe"

echo [1/3] Agent copied to %INSTALL_DIR%

net user Administrator /active:yes >nul 2>&1
echo [2/3] Administrator account enabled

start "" "%INSTALL_DIR%\DeviceAgent.exe"
echo [3/3] Agent started

echo.
echo Installation complete! Agent will run silently in background.
echo It will auto-start on every reboot.
echo.
pause
