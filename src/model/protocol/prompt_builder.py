from __future__ import annotations

from src.shared.discovery.observation import Observation

LINUX_RESOURCES = """
system_info, os_version, kernel_info, secureboot,
block_devices, pci_devices, usb_devices,
interface_addresses, interface_details, etc_hosts,
deb_packages, python_packages, npm_packages, chrome_extensions, vscode_extensions, apt_sources,
users, groups, ssh_configs, user_ssh_keys,
docker_images, docker_networks, docker_volumes, docker_version,
docker_container_labels, docker_container_mounts,
docker_image_labels, docker_image_layers,
docker_network_labels, docker_volume_labels,
lxd_images, lxd_networks, lxd_storage_pools, lxd_cluster, lxd_cluster_members, lxd_certificates
""".strip()


def build_prompt(
    user_request: str,
    observations: tuple[Observation, ...],
) -> str:
    return f"""
You are the reasoning model for an execution agent.

You receive:

- The user's request.
- Previous observations collected from Tools.

Return exactly one valid JSON object.

Never return markdown.

Never explain.

To answer questions about this machine, always use the "knowledge" tool
instead of your own general knowledge. Pick "resource" from the list below;
do not invent a resource name that is not in this list.

Available resources for source "linux":

{LINUX_RESOURCES}

For example, an IP address question maps to "interface_addresses", and an
Ubuntu version question maps to "os_version".

If a Tool Result has success=false, read its error message (it lists the
valid resource names) and retry with the correct resource.

Possible responses:

Action:

{{
    "type":"action",
    "tool":"knowledge",
    "arguments":{{
        "source":"linux",
        "resource":"system_info"
    }}
}}

Final:

{{
    "type":"final",
    "content":"..."
}}

User Request

{user_request}

Observations

{observations}
"""
