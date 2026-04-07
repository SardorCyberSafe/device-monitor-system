@echo off
setlocal enabledelayedexpansion

:: ============================================================
::  DEVICE MONITOR — ONE-CLICK AUTO SETUP (Windows)
::  Bitta skript — hammasi avtomatik!
:: ============================================================

echo.
echo ============================================
echo   Device Monitor — Avtomatik O'rnatish
echo ============================================
echo.

cd /d "%~dp0"

:: ---- Step 1: Python check ----
echo [1/6] Python tekshirilmoqda...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [!] Python o'rnatilmagan! Python 3.10+ kerak.
    echo [!] https://www.python.org/downloads/
    pause
    exit /b 1
)
echo [+] Python topildi.

:: ---- Step 2: Install dependencies ----
echo.
echo [2/6] Kutubxonalar o'rnatilmoqda...
pip install -q -r server\requirements.txt
echo [+] Kutubxonalar tayyor.

:: ---- Step 3: Build client agent ----
echo.
echo [3/6] Client agent yasalmoqda...
if exist "client\dist\DeviceAgent.exe" (
    echo [+] DeviceAgent.exe allaqachon mavjud.
) else (
    echo [!] DeviceAgent.exe yo'q, yasalmoqda...
    pip install -q pyinstaller psutil requests
    cd client
    pyinstaller --onefile --noconsole --name=DeviceAgent --clean client.py
    cd ..
    if exist "client\dist\DeviceAgent.exe" (
        echo [+] DeviceAgent.exe yasaldi!
    ) else (
        echo [!] Build xato berdi. Qo'lda build.bat ni ishga tushiring.
    )
)

:: ---- Step 4: Copy agent to server dir ----
echo.
echo [4/6] Agent server papkasiga nusxalanmoqda...
if exist "client\dist\DeviceAgent.exe" (
    copy /Y "client\dist\DeviceAgent.exe" "server\DeviceAgent.exe" >nul 2>&1
    echo [+] Nusxalandi.
) else (
    echo [!] Agent topilmadi. Qo'lda nusxalash kerak.
)

:: ---- Step 5: Get local IP ----
echo.
echo [5/6] Server IP aniqlanmoqda...
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /c:"IPv4"') do (
    set SERVER_IP=%%a
    set SERVER_IP=!SERVER_IP: =!
    goto :ip_found
)
:ip_found
echo [+] Server IP: %SERVER_IP%

:: ---- Step 6: Update client SERVER_URL ----
echo.
echo [6/6] Client SERVER_URL yangilanmoqda...
powershell -Command "(Get-Content client\client.py) -replace 'SERVER_URL = \".*\"', 'SERVER_URL = \"http://%SERVER_IP%:5000/api/heartbeat\"' | Set-Content client\client.py"
powershell -Command "(Get-Content client\client.py) -replace 'COMMAND_RESULT_URL = \".*\"', 'COMMAND_RESULT_URL = \"http://%SERVER_IP%:5000/api/command_result\"' | Set-Content client\client.py"
echo [+] Yangilandi: http://%SERVER_IP%:5000

echo.
echo ============================================
echo   HAMMASI TAYYOR!
echo ============================================
echo.
echo   Server:  http://%SERVER_IP%:5000
echo   Clients: http://%SERVER_IP%:5000/api/heartbeat
echo   Telegram: Bot orqali boshqaring
echo.
echo   Avtomatik o'rnatish yoqish uchun:
echo   server\config.py da:
echo     AUTO_DEPLOY_ENABLED = True
echo     AUTO_DEPLOY_USERNAME = "Administrator"
echo     AUTO_DEPLOY_PASSWORD = "SizningParol"
echo.
echo ============================================
echo.

cd server
python app.py
