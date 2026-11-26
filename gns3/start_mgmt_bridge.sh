#!/usr/bin/env bash
set -e

sudo ip link add name mgmt0 type bridge 2>/dev/null || true
sudo ip addr replace 192.168.100.1/24 dev mgmt0
sudo ip link set mgmt0 up promisc on

sudo ip tuntap add dev tap0 mode tap user "$USER" 2>/dev/null || true
sudo ip link set tap0 up promisc on
sudo ip link set tap0 master mgmt0

sudo sysctl -w net.bridge.bridge-nf-call-iptables=0 >/dev/null 2>&1 || true
sudo iptables -C FORWARD -i mgmt0 -j ACCEPT 2>/dev/null || sudo iptables -I FORWARD -i mgmt0 -j ACCEPT
sudo iptables -C FORWARD -o mgmt0 -j ACCEPT 2>/dev/null || sudo iptables -I FORWARD -o mgmt0 -j ACCEPT
sudo iptables -C DOCKER-USER -i mgmt0 -j ACCEPT 2>/dev/null || sudo iptables -I DOCKER-USER -i mgmt0 -j ACCEPT 2>/dev/null || true
sudo iptables -C DOCKER-USER -o mgmt0 -j ACCEPT 2>/dev/null || sudo iptables -I DOCKER-USER -o mgmt0 -j ACCEPT 2>/dev/null || true

sudo ip route replace 192.168.10.0/24 via 192.168.100.10 dev mgmt0
echo "NetOps360 management bridge (mgmt0 + tap0) and route to 192.168.10.0/24 are UP."
