#!/bin/bash
# ============================================================
#  DEVICE MONITOR — ONE-CLICK AUTO SETUP (Linux/VPS)
#  Bitta buyruq — hammasi tayyor!
# ============================================================

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${CYAN}"
echo "============================================"
echo "  Device Monitor — Avtomatik O'rnatish"
echo "============================================"
echo -e "${NC}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ---- Step 0: Config check ----
echo -e "${YELLOW}[0/5] Sozlamalarni tekshirish...${NC}"

if grep -q 'BOT_TOKEN = ""' server/config.py 2>/dev/null; then
    echo -e "${RED}❌ server/config.py da BOT_TOKEN ni to'ldiring!${NC}"
    exit 1
fi

if grep -q 'AUTO_DEPLOY_USERNAME = ""' server/config.py 2>/dev/null; then
    echo -e "${YELLOW}⚠️  AUTO_DEPLOY yoqilmagan. /deploy buyrug'i bilan qo'lda o'rnating.${NC}"
    echo -e "${YELLOW}   Avtomatik o'rnatish uchun server/config.py ni tahrirlang:${NC}"
    echo -e "${YELLOW}   AUTO_DEPLOY_ENABLED = True${NC}"
    echo -e "${YELLOW}   AUTO_DEPLOY_USERNAME = \"Administrator\"${NC}"
    echo -e "${YELLOW}   AUTO_DEPLOY_PASSWORD = \"SizningParol\"${NC}"
fi

# ---- Step 1: Server dependencies ----
echo -e "${GREEN}[1/5] Server kutubxonalarini o'rnatish...${NC}"
pip install -q -r server/requirements.txt
echo -e "${GREEN}   ✅ Tayyor${NC}"

# ---- Step 2: Check if DeviceAgent.exe exists ----
if [ ! -f "server/DeviceAgent.exe" ]; then
    echo -e "${YELLOW}[2/5] DeviceAgent.exe topilmadi.${NC}"
    echo -e "${YELLOW}    Windows PC da build.bat ni ishga tushiring va .exe ni server/ papkasiga joylang.${NC}"
    echo -e "${YELLOW}    Hozircha server ishga tushadi, agent keyinroq o'rnatiladi.${NC}"
else
    echo -e "${GREEN}[2/5] DeviceAgent.exe topildi ✅${NC}"
fi

# ---- Step 3: Get server IP ----
SERVER_IP=$(hostname -I | awk '{print $1}')
echo -e "${GREEN}[3/5] Server IP: ${SERVER_IP}${NC}"

# ---- Step 4: Update client SERVER_URL if needed ----
if [ -f "client/client.py" ]; then
    sed -i "s|SERVER_URL = \".*\"|SERVER_URL = \"http://${SERVER_IP}:5000/api/heartbeat\"|g" client/client.py
    sed -i "s|COMMAND_RESULT_URL = \".*\"|COMMAND_RESULT_URL = \"http://${SERVER_IP}:5000/api/command_result\"|g" client/client.py
    echo -e "${GREEN}[4/5] Client SERVER_URL yangilandi → http://${SERVER_IP}:5000${NC}"
fi

# ---- Step 5: Setup auto-restart (systemd) ----
echo -e "${GREEN}[5/6] Svet o'chib yonganda avtomatik boshlash...${NC}"

SERVICE_FILE="device-monitor.service"
SYSTEMD_FILE="/etc/systemd/system/device-monitor.service"

# Fix paths in service file
sed "s|/opt/device-monitor|${SCRIPT_DIR}|g" server/${SERVICE_FILE} > /tmp/device-monitor.service

if command -v systemctl &> /dev/null && [ -w "/etc/systemd/system" ]; then
    cp /tmp/device-monitor.service ${SYSTEMD_FILE}
    systemctl daemon-reload
    systemctl enable device-monitor 2>/dev/null
    echo -e "${GREEN}   ✅ systemd service o'rnatildi — svet yonganda avto boshlanadi${NC}"
else
    echo -e "${YELLOW}   ⚠️  systemd topilmadi. run_server.sh ishlatiladi.${NC}"
fi

# ---- Step 6: Start server ----
echo -e "${GREEN}[6/6] Server ishga tushmoqda...${NC}"
echo ""
echo -e "${CYAN}============================================${NC}"
echo -e "${CYAN}  ✅ HAMMASI TAYYOR!${NC}"
echo -e "${CYAN}============================================${NC}"
echo ""
echo -e "  🌐 Server:  http://${SERVER_IP}:5000"
echo -e "  🤖 Telegram: Bot orqali boshqaring"
echo -e "  📡 Clients:  http://${SERVER_IP}:5000/api/heartbeat"
echo -e "  🔄 Auto-restart: ✅ Svet yonganda avto boshlanadi"
echo ""
echo -e "${CYAN}============================================${NC}"
echo ""

cd server/
bash run_server.sh
