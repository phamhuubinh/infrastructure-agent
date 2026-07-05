#!/usr/bin/env python3
"""
collect_osquery.py
-------------------
Goi truc tiep osqueryi de lay DUNG cac bang can thiet (khong dump toan bo
bang cua osquery), sau do ap dung quy tac lam sach:

  1. Chi lay cac bang trong danh sach TABLES.
  2. Trong moi object:
       - Xoa moi field co gia tri rong ("", [], {}, null).
       - Neu sau khi xoa field ma object rong thi xoa object do.
  3. Giu nguyen ten bang, ten field va gia tri (khong doi, khong merge,
     khong normalize).
  4. Khong doi cau truc JSON tong the (dict phang {ten_bang: [obj, ...]}).

Yeu cau: da cai osquery (co lenh `osqueryi` trong PATH).
    - Ubuntu/Debian : https://osquery.io/downloads/
    - macOS         : brew install osquery
    - Windows       : choco install osquery

Cach dung:
    python3 collect_osquery.py -o result.json
    python3 collect_osquery.py                     # in ra stdout
    python3 collect_osquery.py --workers 8 -o out.json
"""

import json
import shutil
import subprocess
import sys
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed

# ---------------------------------------------------------------------------
# Danh sach bang can lay (dung 48 bang theo yeu cau)
# ---------------------------------------------------------------------------
TABLES = [
    # He thong
    "system_info", "os_version", "kernel_info", "secureboot", "systemd_units",
    # Phan cung
    "block_devices", "pci_devices", "usb_devices", "memory_info",
    "interface_addresses", "interface_details",
    # Phan mem
    "deb_packages", "python_packages", "npm_packages",
    "chrome_extensions", "vscode_extensions", "apt_sources",
    # Mang
    "dns_resolvers", "etc_hosts", "routes", "listening_ports",
    # Nguoi dung & truy cap
    "users", "groups", "user_groups", "ssh_configs",
    "user_ssh_keys",
    # Docker
    "docker_containers", "docker_images", "docker_info", "docker_networks",
    "docker_version", "docker_volumes", "docker_container_labels",
    "docker_container_mounts", "docker_container_networks",
    "docker_container_ports", "docker_image_labels", "docker_image_layers",
    "docker_network_labels", "docker_volume_labels",
    # LXD
    "lxd_certificates", "lxd_cluster", "lxd_cluster_members", "lxd_images",
    "lxd_instance_config", "lxd_instance_devices", "lxd_instances",
    "lxd_networks", "lxd_storage_pools",
]


# ---------------------------------------------------------------------------
# Quy tac lam sach du lieu (giong filter_osquery.py)
# ---------------------------------------------------------------------------
def is_empty(value) -> bool:
    """Gia tri duoc coi la rong: "", [], {}, null (None)."""
    return value == "" or value == [] or value == {} or value is None


def clean_object(obj):
    """
    Xoa moi field co gia tri rong trong 1 object.
    Tra ve None neu object rong sau khi xoa.
    Khong doi ten field, khong doi gia tri con lai.
    """
    if not isinstance(obj, dict):
        return None if is_empty(obj) else obj

    cleaned = {k: v for k, v in obj.items() if not is_empty(v)}
    return cleaned if cleaned else None


def clean_table_value(value):
    """Ap dung quy tac cho gia tri (list[dict]) cua 1 bang."""
    if isinstance(value, list):
        result = []
        for item in value:
            cleaned = clean_object(item)
            if cleaned is not None:
                result.append(cleaned)
        return result

    if isinstance(value, dict):
        cleaned = clean_object(value)
        return cleaned if cleaned is not None else {}

    return value


# ---------------------------------------------------------------------------
# Goi osqueryi
# ---------------------------------------------------------------------------
def check_osquery_installed():
    if shutil.which("osqueryi") is None:
        print(
            "Loi: khong tim thay 'osqueryi' trong PATH.\n"
            "Cai osquery truoc: https://osquery.io/downloads/",
            file=sys.stderr,
        )
        sys.exit(1)


def query_table(table: str, timeout: int = 15):
    """
    Chay `osqueryi --json "SELECT * FROM <table>;"` cho 1 bang.
    Tra ve (table, data_da_loc, error).
    """
    query = f"SELECT * FROM {table};"
    try:
        proc = subprocess.run(
            ["osqueryi", "--json", query],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if proc.returncode != 0:
            return table, None, proc.stderr.strip() or "osqueryi tra ve loi"

        stdout = proc.stdout.strip()
        raw_data = json.loads(stdout) if stdout else []
        cleaned_data = clean_table_value(raw_data)
        return table, cleaned_data, None

    except subprocess.TimeoutExpired:
        return table, None, "timeout"
    except json.JSONDecodeError as e:
        return table, None, f"loi parse JSON: {e}"
    except FileNotFoundError:
        return table, None, "khong tim thay osqueryi"


def collect_all(tables: list, workers: int = 4):
    """
    Chay query song song cho tat ca bang trong danh sach.
    Chi giu lai bang lay thanh cong; bang loi duoc bao cao rieng qua stderr,
    khong dua vao ket qua JSON cuoi cung (dung quy tac "chi loc du lieu",
    khong them field/gia tri bao loi vao JSON dau ra).
    """
    result = {}
    errors = {}

    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_to_table = {executor.submit(query_table, t): t for t in tables}
        for future in as_completed(future_to_table):
            table = future_to_table[future]
            t, data, err = future.result()
            if err:
                errors[t] = err
            else:
                result[t] = data

    return result, errors


def main():
    parser = argparse.ArgumentParser(
        description="Lay truc tiep tu osquery, chi giu bang trong danh sach, xoa field/object rong."
    )
    parser.add_argument(
        "-o", "--output", default=None,
        help="Duong dan file JSON ket qua (mac dinh: in ra stdout)"
    )
    parser.add_argument(
        "--workers", type=int, default=4,
        help="So luong query chay song song (mac dinh: 4)"
    )
    args = parser.parse_args()

    check_osquery_installed()

    print("Dang lay du lieu tu osquery...", file=sys.stderr)
    result, errors = collect_all(TABLES, workers=args.workers)

    print(f"[OK] {len(result)}/{len(TABLES)} bang lay thanh cong", file=sys.stderr)
    if errors:
        print(f"[!!] {len(errors)} bang loi (khong dua vao ket qua):", file=sys.stderr)
        for t, msg in errors.items():
            print(f"    - {t}: {msg}", file=sys.stderr)

    # Giu dung thu tu theo TABLES cho de doc, chi voi cac bang lay thanh cong
    ordered_result = {t: result[t] for t in TABLES if t in result}

    output_json = json.dumps(ordered_result, ensure_ascii=False, indent=2)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output_json)
        print(f"\nDa luu: {args.output}", file=sys.stderr)
    else:
        print(output_json)


if __name__ == "__main__":
    main()
