#!/bin/bash
# 调整mac的网络设置
if [[ $# -ne 1 || ($1 != "auto" && $1 != "manual") ]]; then
    echo "Usage: $0 [auto|manual]"
    exit 1
fi

if [[ $1 == "auto" ]]; then
    networksetup -setdhcp Ethernet
    echo "Ethernet network is set to DHCP."
else
    networksetup -setmanual Ethernet 192.168.21.119 255.255.255.0 192.168.21.100
    echo "Ethernet network is set to manual mode."
fi
