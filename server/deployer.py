"""
Remote Deployer — Deploys the client agent to Windows PCs via SMB + WMI.
Only deploys to IPs you explicitly specify. No self-replication.
"""

import os
import subprocess
import shutil
import time
import socket


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


def deploy_to_pc(ip, username, password, agent_path, use_psexec=False):
    """
    Full deployment to a single PC:
    1. Copy agent .exe
    2. Run it
    3. Create scheduled task for persistence
    """
    print(f"[*] Deploying to {ip}...")

    # Step 1: Copy agent
    print(f"  [1/3] Copying agent to {ip}...")
    if not copy_agent_to_remote(ip, username, password, agent_path):
        print(f"  [-] Failed to copy agent to {ip}")
        return False
    print(f"  [+] Agent copied")

    # Step 2: Run agent
    print(f"  [2/3] Starting agent on {ip}...")
    if use_psexec:
        success = deploy_via_psexec(ip, username, password, agent_path)
    else:
        success = deploy_via_wmi(ip, username, password, agent_path)

    if not success:
        print(f"  [-] Failed to start agent on {ip}")
        return False
    print(f"  [+] Agent started")

    # Step 3: Create persistence task
    print(f"  [3/3] Creating scheduled task on {ip}...")
    if create_remote_task(ip, username, password, agent_path):
        print(f"  [+] Persistence configured")
    else:
        print(f"  [-] Persistence task failed (agent will still run)")

    print(f"[+] Deployment to {ip} complete!")
    return True


def deploy_to_multiple(targets, username, password, agent_path, use_psexec=False):
    """Deploy to multiple PCs. targets = list of IPs."""
    results = {}
    for ip in targets:
        results[ip] = deploy_to_pc(ip, username, password, agent_path, use_psexec)
        time.sleep(1)

    success_count = sum(1 for v in results.values() if v)
    print(f"\n{'=' * 40}")
    print(f"Deployment complete: {success_count}/{len(targets)} successful")
    for ip, ok in results.items():
        status = "OK" if ok else "FAILED"
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
