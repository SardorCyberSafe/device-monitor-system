@echo off
echo ============================================
echo   Building Device Monitor Client Agent
echo ============================================
echo.

echo [1/3] Installing dependencies...
pip install -r requirements.txt

echo.
echo [2/3] Building .exe with PyInstaller...
pyinstaller --onefile --noconsole --name=DeviceAgent --clean client.py

echo.
echo [3/3] Build complete!
echo.
echo Output: dist\DeviceAgent.exe
echo.
echo Copy DeviceAgent.exe to each PC and run install_client.bat
echo.
pause
