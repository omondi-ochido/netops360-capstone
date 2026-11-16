#!/usr/bin/env bash
set -e

sudo ip link add name mgmt0 type bridge 2>/dev/null || true
sudo ip addr replace 192.168.100.1/24 dev mgmt0
sudo ip link set mgmt0 up

sudo ip tuntap add dev tap0 mode tap user "$USER" 2>/dev/null || true
sudo ip link set tap0 up
sudo ip link set tap0 master mgmt0

sudo iptables -C FORWARD -i mgmt0 -j ACCEPT 2>/dev/null || sudo iptables -I FORWARD -i mgmt0 -j ACCEPT
sudo iptables -C FORWARD -o mgmt0 -j ACCEPT 2>/dev/null || sudo iptables -I FORWARD -o mgmt0 -j ACCEPT

echo "Management bridge mgmt0 (192.168.100.1/24) + tap0 is UP."
