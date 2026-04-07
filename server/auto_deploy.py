"""
Auto Deploy — Server ishga tushganda avtomatik tarmoqni skanerlaydi
va barcha Windows PC larga agent o'rnatadi.
"""

import asyncio
import time
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from scanner import scan_network, get_local_ip
from deployer import deploy_to_pc, deploy_to_multiple, enable_administrator_remote
from config import (
    AUTO_SCAN_INTERVAL,
    AUTO_DEPLOY_ENABLED,
    AUTO_DEPLOY_USERNAME,
    AUTO_DEPLOY_PASSWORD,
    EXCLUDE_IPS,
    ADMIN_ID,
)


async def auto_deploy_loop(bot=None):
    """
    Har AUTO_SCAN_INTERVAL soniyada tarmoqni skanerlaydi.
    Yangi Windows PC topilsa — avtomatik agent o'rnatadi.
    """
    if not AUTO_DEPLOY_ENABLED:
        return

    if not AUTO_DEPLOY_USERNAME or not AUTO_DEPLOY_PASSWORD:
        if bot:
            await bot.send_message(
                ADMIN_ID,
                "⚠️ AUTO_DEPLOY yoqilgan, lekin username/password kiritilmagan.\n"
                "server/config.py da AUTO_DEPLOY_USERNAME va AUTO_DEPLOY_PASSWORD ni to'ldiring.",
            )
        return

    agent_path = os.path.join(os.path.dirname(__file__), "DeviceAgent.exe")
    if not os.path.exists(agent_path):
        if bot:
            await bot.send_message(
                ADMIN_ID,
                "❌ DeviceAgent.exe topilmadi!\n"
                "Agent .exe ni `server/` papkasiga joylang.",
            )
        return

    known_devices = set()

    while True:
        try:
            local_ip = get_local_ip()

            if bot:
                await bot.send_message(
                    ADMIN_ID,
                    f"🔍 Avtomatik skanerlash boshlandi... ({local_ip}/24)",
                )

            results = scan_network()

            new_devices = []
            for d in results:
                ip = d["ip"]
                if ip in known_devices:
                    continue
                if ip in EXCLUDE_IPS:
                    continue
                if " (this server)" in d.get("status", ""):
                    known_devices.add(ip)
                    continue

                new_devices.append(d)

            if new_devices:
                ips_to_deploy = [d["ip"] for d in new_devices]

                if bot:
                    names = ", ".join(
                        f"{d['hostname']} ({d['ip']})" for d in new_devices
                    )
                    await bot.send_message(
                        ADMIN_ID,
                        f"🆕 {len(new_devices)} ta yangi PC topildi:\n{names}\n\nO'rnatilmoqda...",
                    )

                deploy_results = deploy_to_multiple(
                    ips_to_deploy,
                    AUTO_DEPLOY_USERNAME,
                    AUTO_DEPLOY_PASSWORD,
                    agent_path,
                )

                for ip, result in deploy_results.items():
                    if isinstance(result, tuple):
                        success, used_user, _ = result
                    else:
                        success = result
                        used_user = AUTO_DEPLOY_USERNAME

                    if success:
                        known_devices.add(ip)
                        if bot:
                            await bot.send_message(
                                ADMIN_ID,
                                f"✅ Agent {ip} ga o'rnatildi! (user: {used_user})",
                            )
                    else:
                        if bot:
                            await bot.send_message(
                                ADMIN_ID,
                                f"❌ {ip} ga o'rnatish xato berdi.",
                            )

            else:
                if bot:
                    await bot.send_message(
                        ADMIN_ID,
                        f"✅ Skanerlash tugadi. Yangi PC topilmadi. "
                        f"Jami ma'lum: {len(known_devices)} ta.",
                    )

        except Exception as e:
            if bot:
                await bot.send_message(
                    ADMIN_ID,
                    f"⚠️ Avtomatik skanerlashda xato: {str(e)}",
                )

        await asyncio.sleep(AUTO_SCAN_INTERVAL)
