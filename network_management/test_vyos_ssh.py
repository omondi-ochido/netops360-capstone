from netmiko import ConnectHandler

main_rtr = {
    "device_type": "vyos",
    "host": "192.168.100.10",
    "username": "vyos",
    "password": "vyos",
    "port": 22,
}

print("Connecting to main-rtr (192.168.100.10) via Netmiko...")
with ConnectHandler(**main_rtr) as conn:
    hostname = conn.send_command("show host name")
    interfaces = conn.send_command("show interfaces")
    config = conn.send_command("show configuration commands")

    print("\n=== Connected Device ===")
    print(hostname.strip())

    print("\n=== Interface Status ===")
    print(interfaces)

    print("\n=== Config Backup Preview (First 10 Lines) ===")
    print("\n".join(config.splitlines()[:10]))
