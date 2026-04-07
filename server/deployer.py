"""
Remote Deployer — Deploys the client agent to Windows PCs via SMB + WMI.
Only deploys to IPs you explicitly specify. No self-replication.
"""

import os
import subprocess
import shutil
import time
import socket


def check_administrator_status(ip, username, password):
    """Check if built-in Administrator account is active on remote PC."""
    try:
        cmd = [
            "wmic",
            f"/node:{ip}",
            f"/user:{username}",
            f"/password:{password}",
            "path",
            "Win32_UserAccount",
            "where",
            "Name='Administrator'",
            "get",
            "Disabled",
            "/value",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        if "Disabled=FALSE" in result.stdout:
            return "active"
        elif "Disabled=TRUE" in result.stdout:
            return "disabled"
        return "unknown"
    except Exception:
        return "unknown"


def enable_administrator_remote(ip, username, password, new_password=None):
    """
    Enable built-in Administrator account on remote PC and optionally set password.
    Uses wmic to run net user command remotely.
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
            return True, new_password
        return False, None
    except Exception as e:
        return False, None


def check_credentials(username, password, ip):
    """Test if credentials work on a remote machine."""
    try:
        result = subprocess.run(
            ["net", "use", f"\\\\{ip}\\IPC$", password, f"/user:{username}"],
            capture_output=True,
            text=True,
            timeout=10,
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


def copy_agent_to_remote(ip, username, password, agent_path):
    """Copy the agent .exe to a remote PC via SMB."""
    agent_filename = os.path.basename(agent_path)
    remote_share = f"\\\\{ip}\\C$\\ProgramData\\DeviceMonitor"
    remote_path = f"{remote_share}\\{agent_filename}"

    try:
        subprocess.run(
            ["net", "use", remote_share, password, f"/user:{username}"],
            capture_output=True,
            text=True,
            timeout=15,
        )

        os.makedirs(remote_share, exist_ok=True)
        shutil.copy2(agent_path, remote_path)

        subprocess.run(
            ["net", "use", remote_share, "/delete"], capture_output=True, timeout=5
        )

        return True
    except Exception as e:
        return False


def deploy_via_psexec(ip, username, password, agent_path):
    """Deploy and run the agent using PsExec."""
    agent_filename = os.path.basename(agent_path)
    remote_exe = f"C:\\ProgramData\\DeviceMonitor\\{agent_filename}"

    try:
        psexec_path = os.path.join(os.path.dirname(__file__), "tools", "PsExec.exe")
        if not os.path.exists(psexec_path):
            psexec_path = "psexec.exe"

        cmd = [
            psexec_path,
            f"\\\\{ip}",
            "-u",
            username,
            "-p",
            password,
            "-s",
            "-d",
            "-h",
            remote_exe,
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return result.returncode == 0
    except Exception:
        return False


def deploy_via_wmi(ip, username, password, agent_path):
    """Deploy and run the agent using WMI (wmic)."""
    agent_filename = os.path.basename(agent_path)
    remote_exe = f"C:\\ProgramData\\DeviceMonitor\\{agent_filename}"

    try:
        cmd = [
            "wmic",
            f"/node:{ip}",
            f"/user:{username}",
            f"/password:{password}",
            "process",
            "call",
            "create",
            f'"{remote_exe}"',
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return "ReturnValue = 0" in result.stdout
    except Exception:
        return False


def create_remote_task(ip, username, password, agent_path):
    """Create a scheduled task on the remote PC for persistence."""
    agent_filename = os.path.basename(agent_path)
    remote_exe = f"C:\\ProgramData\\DeviceMonitor\\{agent_filename}"

    try:
        cmd = [
            "schtasks",
            "/Create",
            f"/S:{ip}",
            f"/U:{username}",
            f"/P:{password}",
            "/TN",
            "DeviceMonitorAgent",
            "/TR",
            f'"{remote_exe}"',
            "/SC",
            "ONLOGON",
            "/RL",
            "HIGHEST",
            "/F",
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return result.returncode == 0
    except Exception:
        return False


def deploy_to_pc(
    ip, username, password, agent_path, use_psexec=False, admin_password=None
):
    """
    Full deployment to a single PC:
    0. Check if Administrator is active, enable if needed
    1. Copy agent .exe
    2. Run it
    3. Create scheduled task for persistence
    """
    print(f"[*] Deploying to {ip}...")

    # Step 0: Check Administrator status
    print(f"  [0/4] Checking Administrator account on {ip}...")
    admin_status = check_administrator_status(ip, username, password)
    print(f"  [*] Administrator status: {admin_status}")

    deploy_user = username
    deploy_pass = password

    if admin_status == "disabled":
        print(f"  [!] Administrator disabled. Enabling...")
        enabled, new_pass = enable_administrator_remote(
            ip, username, password, admin_password
        )
        if enabled:
            print(f"  [+] Administrator enabled! Password: {new_pass}")
            deploy_user = "Administrator"
            deploy_pass = new_pass
        else:
            print(
                f"  [-] Failed to enable Administrator. Trying with provided credentials..."
            )

    # Step 1: Copy agent
    print(f"  [1/4] Copying agent to {ip}...")
    if not copy_agent_to_remote(ip, deploy_user, deploy_pass, agent_path):
        print(f"  [-] Failed to copy agent to {ip}")
        return False
    print(f"  [+] Agent copied")

    # Step 2: Run agent
    print(f"  [2/4] Starting agent on {ip}...")
    if use_psexec:
        success = deploy_via_psexec(ip, deploy_user, deploy_pass, agent_path)
    else:
        success = deploy_via_wmi(ip, deploy_user, deploy_pass, agent_path)

    if not success:
        print(f"  [-] Failed to start agent on {ip}")
        return False
    print(f"  [+] Agent started")

    # Step 3: Create persistence task
    print(f"  [3/4] Creating scheduled task on {ip}...")
    if create_remote_task(ip, deploy_user, deploy_pass, agent_path):
        print(f"  [+] Persistence configured")
    else:
        print(f"  [-] Persistence task failed (agent will still run)")

    # Step 4: Verify
    print(f"  [4/4] Verifying deployment...")
    time.sleep(3)
    if check_credentials(deploy_user, deploy_pass, ip):
        print(f"  [+] Connection verified")
    else:
        print(f"  [-] Verification failed (may still work)")

    print(f"[+] Deployment to {ip} complete!")
    return True, deploy_user, deploy_pass


def deploy_to_multiple(
    targets, username, password, agent_path, use_psexec=False, admin_password=None
):
    """Deploy to multiple PCs. targets = list of IPs."""
    results = {}
    for ip in targets:
        result = deploy_to_pc(
            ip, username, password, agent_path, use_psexec, admin_password
        )
        results[ip] = result
        time.sleep(1)

    success_count = sum(1 for v in results.values() if isinstance(v, tuple) and v[0])
    print(f"\n{'=' * 40}")
    print(f"Deployment complete: {success_count}/{len(targets)} successful")
    for ip, result in results.items():
        if isinstance(result, tuple):
            status = "OK" if result[0] else "FAILED"
            print(f"  {ip}: {status} (user: {result[1]})")
        else:
            status = "FAILED"
            print(f"  {ip}: {status}")

    return results


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 5:
        print(
            "Usage: python deployer.py <ip1,ip2,...> <username> <password> <agent_path>"
        )
        print(
            "Example: python deployer.py 192.168.1.10,192.168.1.11 Administrator Pass123 DeviceAgent.exe"
        )
        sys.exit(1)

    ips = sys.argv[1].split(",")
    username = sys.argv[2]
    password = sys.argv[3]
    agent_path = sys.argv[4]

    deploy_to_multiple(ips, username, password, agent_path)
