import platform
import psutil
import socket
import uuid

def get_system_info():
    print("=== THÔNG TIN HỆ THỐNG ===")
    print(f"Hệ điều hành: {platform.system()} {platform.release()}")
    print(f"Phiên bản Python: {platform.python_version()}")
    print(f"Tên máy: {socket.gethostname()}")
    print(f"Mã MAC: {':'.join([uuid.uuid1().hex[i:i+2] for i in range(0,12,2)])}")
    print("\n=== THÔNG TIN CPU ===")
    print(f"Số lõi CPU: {psutil.cpu_count(logical=False)}")
    print(f"Số luồng CPU: {psutil.cpu_count(logical=True)}")
    print(f"Tần suất CPU: {psutil.cpu_freq()} MHz")
    
    print("\n=== THÔNG TIN RAM ===")
    mem = psutil.virtual_memory()
    print(f"RAM tổng: {mem.total / (1024**3):.2f} GB")
    print(f"RAM trống: {mem.available / (1024**3):.2f} GB")
    print(f"RAM đang sử dụng: {mem.used / (1024**3):.2f} GB ({mem.percent}%)")
    
    print("\n=== THÔNG TIN Ổ ĐĨA ===")
    for partition in psutil.disk_partitions():
        usage = psutil.disk_usage(partition.mountpoint)
        print(f"Ổ đĩa: {partition.device}")
        print(f"Đường dẫn: {partition.mountpoint}")
        print(f"Loại: {partition.fstype}")
        print(f"Tổng: {usage.total / (1024**3):.2f} GB")
        print(f"Trống: {usage.free / (1024**3):.2f} GB")
        print(f"Đã dùng: {usage.used / (1024**3):.2f} GB ({usage.percent}%)")
        print()
    
    print("\n=== THÔNG TIN MẠNG ===")
    for interface, addrs in psutil.net_if_addrs().items():
        print(f"Giao diện: {interface}")
        for addr in addrs:
            print(f"  Địa chỉ: {addr.address} ({addr.family.name})")
            print(f"  Mô tả: {addr.broadcast} / {addr.netmask}")
        print()

if __name__ == "__main__":
    get_system_info()
