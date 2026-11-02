"""One explicit registration source for service, CLI and provider diagnostics."""

from orion.models.backend import ModelBackend, ModelStreamSettings
from orion.models.providers.claude import ADAPTER_ID as CLAUDE_ADAPTER_ID
from orion.models.providers.claude import CLAUDE_OPTIONS, ClaudeBackend
from orion.models.providers.deepseek import ADAPTER_ID, DEEPSEEK_OPTIONS, DeepSeekBackend
from orion.models.providers.openai_compatible import OpenAICompatibleBackend
from orion.models.providers.openai_responses import ADAPTER_ID as RESPONSES_ADAPTER_ID
from orion.models.providers.openai_responses import RESPONSES_OPTIONS, OpenAIResponsesBackend
from orion.models.registry import AdapterRegistration, ProviderRegistry


def default_provider_registry(
    stream_settings: ModelStreamSettings | None = None,
    *,
    compatible_backend: ModelBackend | None = None,
) -> ProviderRegistry:
    return ProviderRegistry(
        (
            AdapterRegistration(
                adapter_id=RESPONSES_ADAPTER_ID,
                provider_id="openai",
                protocol="openai_responses",
                backend=OpenAIResponsesBackend(),
                option_schema=RESPONSES_OPTIONS,
            ),
            AdapterRegistration(
                adapter_id=CLAUDE_ADAPTER_ID,
                provider_id="claude",
                protocol="anthropic_messages",
                backend=ClaudeBackend(),
                option_schema=CLAUDE_OPTIONS,
            ),
            AdapterRegistration(
                adapter_id=ADAPTER_ID,
                provider_id="deepseek",
                protocol="chat_completions",
                backend=DeepSeekBackend(),
                option_schema=DEEPSEEK_OPTIONS,
            ),
            AdapterRegistration(
                adapter_id="openai_compatible.chat_completions.v1",
                provider_id="openai_compatible",
                protocol="chat_completions",
                backend=compatible_backend or OpenAICompatibleBackend(stream_settings),
                option_schema={"type": "object", "properties": {}, "additionalProperties": False},
            ),
        )
    )
