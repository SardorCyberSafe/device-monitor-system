#!/bin/bash
# ============================================================
#  SERVER AUTO-RESTART — Svet o'chib yonganda avtomatik qayta boshlash
#  Bu skript doimiy ishlaydi, server tushsa qayta ko'taradi
# ============================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

LOG_FILE="server_autostart.log"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

log "========================================="
log "Server auto-restart boshlandi"
log "========================================="

while true; do
    log "Server ishga tushirilmoqda..."
    
    python app.py 2>&1 | tee -a "$LOG_FILE"
    
    EXIT_CODE=$?
    
    if [ $EXIT_CODE -eq 0 ]; then
        log "Server to'xtadi (exit 0). Qayta boshlanmoqda..."
    else
        log "Server xato bilan tushdi (exit $EXIT_CODE). 10 soniyada qayta boshlanadi..."
        sleep 10
    fi
    
    log "Qayta boshlanmoqda..."
    sleep 2
done
