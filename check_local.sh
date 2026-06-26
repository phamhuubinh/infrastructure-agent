#!/bin/bash

# Script kiểm tra thông tin hệ thống cục bộ (Ubuntu 22.04/Server)
# Không sử dụng bất kỳ thư viện bên ngoài nào

echo "=== THÔNG TIN HỆ THỐNG ==="
echo "Hostname:"
hostnamectl

echo -e "\n=== CPU ==="
lscpu

echo -e "\n=== BỘ NHỚ ==="
free -h

echo -e "\n=== ĐĨA CỨNG ==="
echo "Thông tin đĩa:"
lsblk
echo -e "\nDung lượng phân vùng:"
df -h

echo -e "\n=== MẠNG ==="
echo "Địa chỉ IP:"
ip a show eth0 | grep "inet\b" | grep -v "127.0.0.1" | awk '{print $2}' | cut -d/ -f1
echo -e "\nThông tin mạng:"
ip -s link

echo -e "\n=== DỊCH VỤ ==="
echo "Dịch vụ đang chạy:"
systemctl list-units --type=service --state=running --no-pager

echo -e "\n=== LOG HỆ THỐNG ==="
echo "10 sự kiện gần nhất:"
journalctl -n 10

echo -e "\n=== DOCKER ==="
if command -v docker > /dev/null 2>&1; then
    echo "Thông tin Docker:"
    docker info
else
    echo "Docker không được cài đặt"
fi

echo -e "\n=== GPU ==="
if command -v nvidia-smi > /dev/null 2>&1; then
    echo "Thông tin GPU:"
    nvidia-smi
else
    echo "NVIDIA drivers không được cài đặt"
fi
