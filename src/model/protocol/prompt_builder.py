from __future__ import annotations

import json

from src.shared.discovery.observation import Observation

LINUX_RESOURCES = [
    "system_info",
    "os_version",
    "kernel_info",
    "secureboot",
    "block_devices",
    "pci_devices",
    "usb_devices",
    "interface_addresses",
    "interface_details",
    "etc_hosts",
    "deb_packages",
    "python_packages",
    "npm_packages",
    "chrome_extensions",
    "vscode_extensions",
    "apt_sources",
    "users",
    "groups",
    "ssh_configs",
    "user_ssh_keys",
    "docker_images",
    "docker_networks",
    "docker_volumes",
    "docker_version",
    "docker_container_labels",
    "docker_container_mounts",
    "docker_image_labels",
    "docker_image_layers",
    "docker_network_labels",
    "docker_volume_labels",
    "lxd_images",
    "lxd_networks",
    "lxd_storage_pools",
    "lxd_cluster",
    "lxd_cluster_members",
    "lxd_certificates",
]

RULES = [
    'Use "knowledge" instead of general knowledge for questions about this machine.',
    "Only use resource names listed in available_resources.",
    "Each entry in actions_taken is an Action already executed this "
    "session and its result -- do not repeat one.",
    "A failed entry's error lists valid resources; retry with one of those.",
    'A successful entry with empty data is itself a final answer (e.g. '
    '"not installed"), not a reason to retry.',
]

RESPONSE_SCHEMAS = {
    "action": {
        "type": "action",
        "tool": "knowledge",
        "arguments": {
            "source": "linux",
            "resource": "system_info",
        },
    },
    "final": {
        "type": "final",
        "content": "...",
    },
}


def _observation_to_dict(
    observation: Observation,
) -> dict[str, object]:
    entry: dict[str, object] = {
        "tool": observation.tool,
        "arguments": observation.arguments,
        "success": observation.success,
    }

    if observation.success:
        entry["data"] = observation.data
    else:
        entry["error"] = observation.error

    return entry


def build_prompt(
    user_request: str,
    observations: tuple[Observation, ...],
) -> str:
    payload = {
        "role": "reasoning model for an execution agent",
        "output_format": "exactly one JSON object, no markdown, no explanation",
        "response_schemas": RESPONSE_SCHEMAS,
        "rules": RULES,
        "available_resources": {
            "linux": LINUX_RESOURCES,
        },
        "user_request": user_request,
        "actions_taken": [
            _observation_to_dict(observation) for observation in observations
        ],
    }

    return json.dumps(payload)
