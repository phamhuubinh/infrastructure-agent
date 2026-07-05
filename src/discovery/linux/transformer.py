#!/usr/bin/env python3
"""
transformer.py
--------------------------
Transform raw Linux discovery data into Linux inventory.

Khac voi filter_osquery.py / collect_osquery.py (chi loc theo TEN BANG),
script nay loc sau hon: voi MOI bang, chi giu lai cac FIELD co gia tri
phan tich/nhan dien cao, bo cac field ky thuat thap (id noi bo, hash,
bien the signed/unsigned, timestamp cai dat, duong dan he thong...).

Muc dich: Stable Store se duoc nhieu tool khac nhau (khong chi osquery)
ghi vao, nen du lieu can gon, de doc, khong lan rac chi tiet ky thuat
khong can cho cau hoi nghiep vu (vd "may co cai Docker khong", "SSH dang
chay khong", "user nao ton tai").

Cach dung:
    python3 transformer.py \
        stable_store/linux/raw/osquery.json \
        -o stable_store/linux/inventory.json
"""

import argparse
import json
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Field can giu lai cho tung bang. Bang nao khong co trong dict nay se duoc
# GIU NGUYEN TOAN BO FIELD (fallback an toan, khong lam mat du lieu bat ngo
# neu sau nay them bang moi ma quen khai bao field-selection).
# ---------------------------------------------------------------------------
FIELD_SELECTION = {
    # --- He thong ---
    "system_info": [
        "hostname",
        "cpu_brand",
        "cpu_physical_cores",
        "cpu_logical_cores",
        "physical_memory",
    ],
    "os_version": ["name", "version", "codename", "arch"],
    "kernel_info": ["version"],
    "secureboot": ["secure_boot", "setup_mode"],
    # --- Phan cung ---
    "block_devices": ["name", "size"],
    "pci_devices": ["model", "vendor"],
    "usb_devices": ["model", "vendor"],
    "interface_addresses": ["interface", "address", "type"],
    "interface_details": ["interface", "mac", "link_speed"],
    # --- Phan mem cai dat ---
    "deb_packages": ["name", "version"],
    "python_packages": ["name", "version"],
    "npm_packages": ["name", "version"],
    "chrome_extensions": ["name", "version", "identifier"],
    "vscode_extensions": ["name", "version", "publisher"],
    "apt_sources": ["source", "release"],
    # --- Mang ---
    "etc_hosts": ["address", "hostnames"],
    # --- Nguoi dung & truy cap ---
    "users": ["username", "directory", "shell"],
    "groups": ["groupname"],
    "user_groups": ["uid", "gid"],
    "ssh_configs": ["block", "option"],
    "user_ssh_keys": ["path", "key_length"],
    # --- Docker (thuong rong tren may khong dung Docker, nhung khai bao san
    # de tu dong ap dung dung khi chay tren may co Docker) ---
    "docker_images": ["id", "tags", "size", "created"],
    "docker_networks": ["name", "driver"],
    "docker_volumes": ["name", "driver", "mount_point"],
    "docker_version": ["version", "api_version"],
    "docker_container_labels": ["id", "key", "value"],
    "docker_container_mounts": ["id", "source", "destination", "type", "rw"],
    "docker_image_labels": ["id", "key", "value"],
    "docker_image_layers": ["id", "layer_id"],
    "docker_network_labels": ["id", "key", "value"],
    "docker_volume_labels": ["name", "key", "value"],
    # --- LXD (tuong tu Docker) ---
    "lxd_images": ["fingerprint", "aliases", "architecture", "size"],
    "lxd_networks": ["name", "type", "managed"],
    "lxd_storage_pools": ["name", "driver", "source"],
    "lxd_cluster": ["server_name", "enabled"],
    "lxd_cluster_members": ["server_name", "status", "roles"],
    "lxd_certificates": ["name", "type"],
}


def is_empty(value) -> bool:
    """Gia tri duoc coi la rong: "", [], {}, null."""
    return value == "" or value == [] or value == {} or value is None


def select_fields(obj: dict, fields: list):
    """
    Chi giu lai cac field trong `fields` neu chung co mat va khong rong
    trong object. Khong doi ten field, khong doi gia tri.
    Tra ve None neu ket qua rong (de loai bo object).
    """
    result = {}
    for f in fields:
        if f in obj and not is_empty(obj[f]):
            result[f] = obj[f]
    return result if result else None


def clean_object_full(obj: dict):
    """Fallback: xoa field rong nhung giu toan bo field con lai (dung cho
    bang chua khai bao trong FIELD_SELECTION)."""
    if not isinstance(obj, dict):
        return None if is_empty(obj) else obj
    cleaned = {k: v for k, v in obj.items() if not is_empty(v)}
    return cleaned if cleaned else None


def build_table(table_name: str, value):
    """Ap dung field-selection (neu co) hoac fallback cho 1 bang."""
    fields = FIELD_SELECTION.get(table_name)

    if not isinstance(value, list):
        # Truong hop hiem: bang tra ve dict thay vi list
        if isinstance(value, dict):
            cleaned = (
                select_fields(value, fields) if fields else clean_object_full(value)
            )
            return cleaned if cleaned else {}
        return value

    result = []
    for item in value:
        if not isinstance(item, dict):
            if not is_empty(item):
                result.append(item)
            continue
        cleaned = select_fields(item, fields) if fields else clean_object_full(item)
        if cleaned is not None:
            result.append(cleaned)
    return result


EXCLUDED_TABLES = {
    "user_groups",
    "systemd_units",
    "memory_info",
    "dns_resolvers",
    "routes",
    "listening_ports",
    "docker_info",
    "docker_containers",
    "docker_container_networks",
    "docker_container_ports",
    "lxd_instances",
}


def build_knowledge_store(data: dict) -> dict:
    """
    Duyet toan bo bang trong data, ap dung build_table() cho tung bang
    (tru bang nam trong EXCLUDED_TABLES).
    Bang co gia tri rong sau khi loc se van giu key nhung gia tri la []
    (khong xoa hang loat de biet ro "da kiem tra, khong co gi").
    """
    result = {}
    for table_name, value in data.items():
        if table_name in EXCLUDED_TABLES:
            continue
        result[table_name] = build_table(table_name, value)
    return result


def main():
    parser = argparse.ArgumentParser(
        description="Transform Linux discovery data into inventory."
    )

    parser.add_argument(
        "input",
        help="Path to raw Linux discovery JSON.",
    )

    parser.add_argument(
        "-o",
        "--output",
        default=None,
        help="Output inventory JSON (default: stdout).",
    )

    args = parser.parse_args()

    input_path = Path(args.input)

    if not input_path.exists():
        print(
            f"Error: file not found: {input_path}",
            file=sys.stderr,
        )
        sys.exit(1)

    with input_path.open(
        "r",
        encoding="utf-8",
    ) as file:
        data = json.load(file)

    inventory = build_knowledge_store(data)

    undeclared = [
        table
        for table in data.keys()
        if table not in FIELD_SELECTION and table not in EXCLUDED_TABLES
    ]

    if undeclared:
        print(
            f"[i] {len(undeclared)} tables use fallback field selection: "
            + ", ".join(undeclared),
            file=sys.stderr,
        )

    output_json = json.dumps(
        inventory,
        ensure_ascii=False,
        indent=2,
    )

    if args.output:
        output_path = Path(args.output)

        with output_path.open(
            "w",
            encoding="utf-8",
        ) as file:
            file.write(output_json)

        print(
            f"Linux inventory saved: {output_path}",
            file=sys.stderr,
        )
    else:
        print(output_json)


if __name__ == "__main__":
    main()
