# 🖥️ Personal Device Management System — Telegram Bot

Uy tarmog'ingizdagi Windows 11 kompyuterlarini Telegram bot orqali boshqaring.

---

## 📐 Arxitektura

```
┌─────────────────────────────────────────────────┐
│              SIZNING TELEGRAM                   │
│         Bot orqali boshqaruv paneli             │
└──────────────────────┬──────────────────────────┘
                       │ Telegram API
                       ▼
┌─────────────────────────────────────────────────┐
│         SERVER (Asosiy PC yoki VPS)              │
│  ┌─────────────────┐  ┌──────────────────────┐  │
│  │  Telegram Bot   │  │  HTTP API (aiohttp)  │  │
│  │  (aiogram 3.x)  │  │  Heartbeat endpoint  │  │
│  └────────┬────────┘  └──────────┬───────────┘  │
│           │                      │              │
│           └──────────┬───────────┘              │
│                      ▼                          │
│           ┌─────────────────┐                   │
│           │  SQLite (devices.db) │              │
│           └─────────────────┘                   │
└─────────────────────────────────────────────────┘
                       ▲
                       │ HTTP POST (heartbeat)
┌──────────────────────┴──────────────────────────┐
│         CLIENT AGENTLAR (Windows 11 PC lar)      │
│         client.py → DeviceAgent.exe              │
│         • Tizim ma'lumotlari                     │
│         • Wi-Fi parollar                         │
│         • Brauzer ma'lumotlari                   │
│         • Avtomatik boshlash (Task Scheduler)    │
└─────────────────────────────────────────────────┘
```

---

## 📁 Loyiha Tuzilishi

```
device-monitor/
├── server/
│   ├── app.py                 # Telegram bot + HTTP API server
│   ├── database.py            # SQLite database qatlami
│   ├── config.py              # Sozlamalar (token, admin ID)
│   ├── scanner.py             # Tarmoq skaneri (Windows PC topish)
│   ├── deployer.py            # Masofadan agent o'rnatish (SMB/WMI)
│   └── requirements.txt       # Server dependencies
├── client/
│   ├── client.py              # Client agent (barcha funksiyalar)
│   ├── build.bat              # PyInstaller orqali .exe yasash
│   └── requirements.txt       # Client dependencies
├── deploy/
│   └── install_client.bat     # Har bir PC ga qo'lda o'rnatish
└── README.md                  # Bu fayl
```

---

## 🚀 Tezkor Boshlash

### 1-Qadam: Serverni Ishga Tushirish

```bash
cd server/
pip install -r requirements.txt
python app.py
```

Server `http://0.0.0.0:5000` da ishga tushadi va Telegram ga ulanadi.

### 2-Qadam: Client Agent Yasash

1. `client/client.py` ni oching — 17-qatordagi `SERVER_URL` ni server IP manzilingizga o'zgartiring
2. Windows PC da `build.bat` ni ishga tushiring:

```cmd
cd client/
build.bat
```

Natija: `client/dist/DeviceAgent.exe`

### 3-Qadam: Agentlarni O'rnatish

**Usul A: Qo'lda o'rnatish (kam PC bo'lsa)**
1. `DeviceAgent.exe` + `install_client.bat` ni har bir PC ga ko'chiring
2. `install_client.bat` ni **Administrator sifatida** ishga tushiring

**Usul B: Tarmoq orqali avtomatik (ko'p PC bo'lsa)**
1. Telegram botga `/scan` yuboring — barcha Windows PC lar topiladi
2. `/deploy <ip> <username> <password>` — bitta PC ga o'rnating
3. `/deployall <username> <password>` — barcha topilgan PC larga o'rnating

### 4-Qadam: Telegram Bot Ishlatish

Botga `/start` yuboring. Mavjud buyruqlar:

| Buyruq | Tavsif |
|--------|--------|
| `/start` | Boshlash |
| `/devices` | Barcha kompyuterlar ro'yxati |
| `/device <id>` | Bitta PC ning to'liq ma'lumotlari |
| `/scan` | 🔍 Tarmoqni skanerlash — Windows PC larni topish |
| `/deploy <ip> <user> <pass>` | 📦 Bitta PC ga agent o'rnatish |
| `/deployall <user> <pass>` | 📦 Barcha topilgan PC larga o'rnatish |
| `/refresh <id>` | Ma'lumotlarni yangilash |
| `/cmd <id> <buyruq>` | Custom buyruq yuborish |
| `/report <id>` | JSON/CSV hisobot yuklab olish |
| `/history <id>` | Buyruqlar tarixi |
| `/status` | Tizim holati |
| `/help` | Yordam |

---

## 📱 Telegram Inline Tugmalar

`/devices` dan keyin har bir PC uchun tugmalar:
- 🔄 **Refresh** — Ma'lumotlarni yangilash
- 💻 **Command** — Buyruq yuborish
- 📄 **JSON Report** — JSON fayl yuklab olish
- 📊 **CSV Report** — CSV fayl yuklab olish
- 📜 **History** — Buyruqlar tarixi
- 📶 **Wi-Fi** — Saqlangan Wi-Fi tarmoqlar + parollar
- 🔐 **Browser Creds** — Chrome/Edge saqlangan ma'lumotlar
- 📋 **Processes** — Ishlayotgan jarayonlar

`/scan` dan keyin har bir topilgan PC uchun:
- 📦 **Deploy to <hostname>** — Shu PC ga agent o'rnatish

---

## 🔧 Tarmoq Skaneri Qanday Ishlaydi

1. **Ping sweep** — Barcha IP larni tekshiradi
2. **SMB port (445)** — Windows mashinalarni aniqlaydi
3. **Hostname + MAC** — Har bir qurilma haqida ma'lumot yig'adi
4. **Natija** — Ro'yxat ko'rsatiladi, har biriga tugma orqali deploy qilish mumkin

---

## 📦 Masofadan O'rnatish Qanday Ishlaydi

1. Agent `.exe` faylni SMB orqali `C:\ProgramData\DeviceMonitor\` ga nusxalaydi
2. WMI yoki PsExec orqali ishga tushiradi
3. Task Scheduler da avtomatik boshlash uchun vazifa yaratadi
4. **Faqat siz ko'rsatgan IP larga** o'rnatadi — hech qayerga tarqalmaydi

---

## 🛠️ Muammolarni Hal Qilish

**Client ulanmayapti:**
- `client.py` dagi `SERVER_URL` server IP manziligizga mosligini tekshiring
- Server PC da 5000-portni firewall da oching
- Test: `curl -X POST http://<SERVER_IP>:5000/api/heartbeat -H "Content-Type: application/json" -d '{"device_id":"test","hostname":"test"}'`

**Bot javob bermayapti:**
- `config.py` dagi `BOT_TOKEN` to'g'riligini tekshiring
- Serverda internet borligini tekshiring

**Agent reboot dan keyin boshlanmayapti:**
- `install_client.bat` ni Administrator sifatida ishga tushiring
- Task Scheduler da "SystemHealthMonitor" vazifasini tekshiring
- Registry: `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`

**Deploy ishlamayapti:**
- Username/parol to'g'ri ekanligini tekshiring
- File sharing yoqilganligini tekshiring
- Firewall SMB (445-port) ni ruxsat berganligini tekshiring
- Administrator account faol ekanligini tekshiring

---

## ⚡ Xavfsizlik

- Faqat sizning Telegram ID (`ADMIN_ID`) botni boshqarishi mumkin
- Lokal tarmoqda HTTP aloqa
- Bot token maxfiy bo'lishi kerak
- Deploy faqat siz ko'rsatgan IP larga ishlaydi
- Hech qanday self-replication yo'q
