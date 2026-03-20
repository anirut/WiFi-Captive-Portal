#!/bin/bash
set -e
WAN_IF="${WAN_IF:-eth0}"

echo "Setting up tc HTB on $WAN_IF..."
# Remove existing
tc qdisc del dev $WAN_IF root 2>/dev/null || true

# Add HTB root qdisc (default class 999 = unlimited)
tc qdisc add dev $WAN_IF root handle 1: htb default 999

# Default unlimited class
tc class add dev $WAN_IF parent 1: classid 1:999 htb rate 1000mbit ceil 1000mbit

echo "tc HTB setup complete on $WAN_IF."
