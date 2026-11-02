from __future__ import annotations

import pytest
from pydantic import ValidationError

from orion.contracts import RuntimeScope
from orion.contracts.profiles import ModelCapabilities, ModelProfile
from orion.contracts.skills import SkillDescriptor


def profile(**changes):
    return ModelProfile(
        **{
            "profile_id": "configured",
            "provider_id": "claude",
            "protocol": "anthropic_messages",
            "endpoint": "https://provider.example/v1",
            "model_id": "owner-configured-model",
            "credential_ref": "credential-1",
            "capabilities": ModelCapabilities(),
            **changes,
        }
    )


@pytest.mark.parametrize(
    "provider,protocol",
    [
        ("deepseek", "chat_completions"),
        ("claude", "anthropic_messages"),
        ("openai", "openai_responses"),
        ("openai", "chat_completions"),
        ("openai_compatible", "chat_completions"),
    ],
)
def test_explicit_provider_protocol_and_configured_model(provider, protocol):
    value = profile(provider_id=provider, protocol=protocol)
    assert value.provider_id == provider
    assert value.model_id == "owner-configured-model"


@pytest.mark.parametrize(
    "changes",
    [
        {"protocol": "chat_completions"},
        {"provider_id": "unknown"},
        {"api_key": "not-a-credential-reference"},
        {"endpoint": "https://user:password@provider.example"},
        {"endpoint": "https://provider.example?token=secret"},
        {"endpoint": "file:///local"},
        {"endpoint": "https://provider.example/#fragment"},
        {"context_max_bytes": 262_145},
        {"request_timeout_seconds": 1},
        {"transport_timeout_seconds": float("nan")},
        {"safe_transport_retries": True},
        {"options": {"bad": float("nan")}},
        {"options": {"large": "秘" * 12_000}},
    ],
)
def test_profile_rejects_incoherent_or_secret_bearing_configuration(changes):
    with pytest.raises(ValidationError):
        profile(**changes)


def test_profile_options_snapshot_is_deeply_immutable():
    with pytest.raises(TypeError):
        profile().options["injected"] = True
    options = {"nested": {"items": ["original"]}}
    value = profile(options=options)
    options["nested"]["items"].append("changed")
    assert value.options["nested"]["items"] == ["original"]
    with pytest.raises(TypeError):
        value.options["nested"]["items"].append("changed")
    assert value.model_dump()["options"] == {"nested": {"items": ["original"]}}


def test_capabilities_do_not_infer_tool_or_boolean_support():
    assert not ModelCapabilities().tools
    with pytest.raises(ValidationError):
        ModelCapabilities(tool_result_continuation=True)
    with pytest.raises(ValidationError):
        ModelCapabilities(tools="yes")


def skill(**changes):
    return SkillDescriptor(
        **{
            "name": "project-research",
            "description": "Research project documents",
            "version": "1.0.0",
            "source": "project",
            "project_id": "project-a",
            "package_sha256": "a" * 64,
            **changes,
        }
    )


def test_project_guidance_cannot_apply_to_other_project_or_device_chat():
    common = {
        "session_id": "session-a",
        "principal_id": "principal-a",
        "workspace_id": "workspace-a",
    }
    descriptor = skill()
    assert descriptor.applies_to(RuntimeScope(**common, project_id="project-a"))
    assert not descriptor.applies_to(RuntimeScope(**common, project_id="project-b"))
    assert not descriptor.applies_to(RuntimeScope(**common))
    assert not descriptor.applies_to(
        RuntimeScope(**common, project_id="project-a", endpoint_id="b" * 32)
    )
    assert not skill(enabled=False).applies_to(RuntimeScope(**common, project_id="project-a"))


@pytest.mark.parametrize(
    "changes",
    [
        {"source": "bundled"},
        {"project_id": None},
        {"audience": "development"},
        {"required_capabilities": ("system.command.run", "system.command.run")},
        {"required_capabilities": ("*",)},
        {"package_sha256": "unpinned"},
    ],
)
def test_catalog_descriptor_rejects_invalid_trust_or_scope(changes):
    with pytest.raises(ValidationError):
        skill(**changes)
