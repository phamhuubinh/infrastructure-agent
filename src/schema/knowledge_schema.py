from __future__ import annotations


def validate(
    arguments: dict[str, object],
) -> None:
    if "resources" not in arguments:
        raise ValueError("Missing resources.")

    resources = arguments["resources"]

    if not isinstance(resources, list):
        raise ValueError("Resources must be a list.")

    if not resources:
        raise ValueError("Resources must not be empty.")

    for resource in resources:
        if not isinstance(resource, str):
            raise ValueError("Each resource must be a string.")

        if not resource.strip():
            raise ValueError("Resource must not be empty.")
