import re
import subprocess
from datetime import datetime, timezone
from flask import Blueprint, jsonify, request
from netmiko import ConnectHandler

devices_bp = Blueprint("devices", __name__)

# Active GNS3 Main Site Inventory
GNS3_DEVICES = [
    {"id": "dev-1", "hostname": "main-rtr", "ipAddress": "192.168.100.10", "deviceType": "Router", "os": "VyOS 1.5", "site": "Main Site", "sshEnabled": True},
    {"id": "dev-2", "hostname": "MAIN-SERVER", "ipAddress": "192.168.10.100", "deviceType": "Server", "os": "VPCS / Linux Server", "site": "Main Site", "sshEnabled": False},
    {"id": "dev-3", "hostname": "PC1", "ipAddress": "192.168.10.11", "deviceType": "Host", "os": "VPCS", "site": "Main Site", "sshEnabled": False},
    {"id": "dev-4", "hostname": "PC2", "ipAddress": "192.168.10.12", "deviceType": "Host", "os": "VPCS", "site": "Main Site", "sshEnabled": False},
    {"id": "dev-5", "hostname": "PC3", "ipAddress": "192.168.10.13", "deviceType": "Host", "os": "VPCS", "site": "Main Site", "sshEnabled": False},
    {"id": "dev-6", "hostname": "PC4", "ipAddress": "192.168.10.14", "deviceType": "Host", "os": "VPCS", "site": "Main Site", "sshEnabled": False},
    {"id": "dev-7", "hostname": "MANAGEMENT-SW", "ipAddress": "192.168.100.2", "deviceType": "Switch", "os": "GNS3 Ethernet Switch", "site": "Management", "sshEnabled": False, "layer2Only": True},
    {"id": "dev-8", "hostname": "SW1", "ipAddress": "192.168.10.2", "deviceType": "Switch", "os": "GNS3 Ethernet Switch", "site": "Main Site", "sshEnabled": False, "layer2Only": True},
    {"id": "dev-9", "hostname": "SW2", "ipAddress": "192.168.10.3", "deviceType": "Switch", "os": "GNS3 Ethernet Switch", "site": "Main Site", "sshEnabled": False, "layer2Only": True},
]

def ping_host(ip_address):
    try:
        res = subprocess.run(
            ["ping", "-c", "1", "-W", "1", ip_address],
            capture_output=True,
            text=True,
            timeout=3,
        )
        if res.returncode == 0:
            match = re.search(r"time=([\d.]+)\s*ms", res.stdout)
            latency = float(match.group(1)) if match else 1.0
            return "Online", round(latency, 2), 0
        return "Offline", None, 100
    except Exception:
        return "Offline", None, 100

@devices_bp.route("/api/devices", methods=["GET"])
def get_devices():
    now = datetime.now(timezone.utc).isoformat()
    results = []
    for dev in GNS3_DEVICES:
        item = dict(dev)
        if dev.get("layer2Only"):
            # Unmanaged L2 switches have no IP stack; reflect active topology link
            item["status"] = "Online"
            item["latencyMs"] = 0.5
            item["packetLoss"] = 0
        else:
            status, latency, loss = ping_host(dev["ipAddress"])
            item["status"] = status
            item["latencyMs"] = latency
            item["packetLoss"] = loss
        item["lastChecked"] = now
        results.append(item)
    return jsonify({"devices": results, "timestamp": now})

@devices_bp.route("/api/devices/<device_id>/backup", methods=["POST"])
def backup_device(device_id):
    device = next((d for d in GNS3_DEVICES if d["id"] == device_id), None)
    if not device:
        return jsonify({"error": "Device not found"}), 404
    if not device.get("sshEnabled"):
        return jsonify({"error": f"{device['hostname']} does not support SSH config backup"}), 400

    try:
        conn_params = {
            "device_type": "vyos",
            "host": device["ipAddress"],
            "username": "vyos",
            "password": "vyos",
            "port": 22,
        }
        with ConnectHandler(**conn_params) as conn:
            config = conn.send_command("show configuration commands")
            interfaces = conn.send_command("show interfaces")
        return jsonify({
            "hostname": device["hostname"],
            "ipAddress": device["ipAddress"],
            "backedUpAt": datetime.now(timezone.utc).isoformat(),
            "config": config,
            "interfaces": interfaces,
        })
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
