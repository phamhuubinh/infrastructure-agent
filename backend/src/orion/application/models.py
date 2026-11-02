"""Read one saved profile and bind its credential before the model/tool loop."""

import hmac
import sqlite3
from dataclasses import dataclass
from typing import Any

from pydantic import SecretStr, ValidationError

from orion.contracts.profiles import ModelProfile
from orion.models.backend import (
    ModelBackendError,
    ModelBackendErrorKind,
    ModelSettings,
    ReasoningMode,
)
from orion.models.credential_store import StoredCredentialResolver
from orion.models.credentials import CredentialResolver
from orion.models.registry import ProviderRegistry
from orion.persistence.sqlite import SQLiteStore


@dataclass(frozen=True)
class CredentialMigrationResult:
    migrated: int
    changed_during_migration: int
    remaining: int


class ModelSettingsResolver:
    def __init__(self, registry: ProviderRegistry, credentials: CredentialResolver) -> None:
        self._registry = registry
        self._credentials = credentials

    def validate_profile(self, profile: ModelProfile, mode: ReasoningMode) -> ModelSettings:
        bound = self._registry.bind_profile(profile, self._credentials)
        if mode != ReasoningMode.AUTO and not profile.capabilities.reasoning_controls:
            raise ModelBackendError(
                "This profile does not support reasoning controls.",
                kind=ModelBackendErrorKind.UNSUPPORTED,
            )
        bound = bound.model_copy(update={"reasoning_mode": mode})
        self._registry.resolve(bound)
        return bound

    def resolve_binding(
        self, binding: tuple[dict[str, Any], ModelProfile | None] | None
    ) -> ModelSettings:
        try:
            if binding is None:
                raise ModelBackendError(
                    "No active model configuration.", kind=ModelBackendErrorKind.UNSUPPORTED
                )
            stored, profile = binding
            if profile is not None:
                if (
                    stored["model_config_id"] != profile.profile_id
                    or stored["provider_type"] != profile.provider_id
                    or str(stored["base_url"]).rstrip("/") != profile.endpoint.rstrip("/")
                    or stored["model_id"] != profile.model_id
                    or stored["api_key"] is not None
                    or stored.get("credential_ref") is not None
                ):
                    raise ModelBackendError(
                        "Stored model profile binding is invalid.",
                        kind=ModelBackendErrorKind.UNSUPPORTED,
                    )
                return self.validate_profile(profile, ReasoningMode(str(stored["reasoning_mode"])))
            reference = stored.get("credential_ref")
            values = {
                key: stored[key]
                for key in (
                    "provider_type",
                    "base_url",
                    "model_id",
                    "api_key",
                    "reasoning_mode",
                )
            }
            if reference is not None:
                if stored["api_key"] is not None:
                    raise ValueError("ambiguous credential binding")
                values["api_key"] = self._credentials.resolve(str(reference)).get_secret_value()
            settings = ModelSettings.model_validate(values)
            _, profile = self._registry.resolve(settings)
            if reference is not None:
                profile = profile.model_copy(update={"credential_ref": str(reference)})
            return settings.model_copy(update={"profile": profile})
        except (ValidationError, ValueError):
            raise ModelBackendError(
                "Stored model configuration is invalid.", kind=ModelBackendErrorKind.UNSUPPORTED
            ) from None


class ModelConfigurationService(ModelSettingsResolver):
    def __init__(
        self, store: SQLiteStore, registry: ProviderRegistry, credentials: CredentialResolver
    ) -> None:
        super().__init__(registry, credentials)
        self._store = store

    def store_credential(self, value: SecretStr) -> str:
        if not isinstance(self._credentials, StoredCredentialResolver):
            raise ModelBackendError(
                "Protected credential storage is unavailable.",
                kind=ModelBackendErrorKind.UNSUPPORTED,
            )
        try:
            reference = self._credentials.store.put(value)
            verified = self._credentials.resolve(reference)
            if not hmac.compare_digest(verified.get_secret_value(), value.get_secret_value()):
                raise ValueError("credential verification failed")
            return reference
        except (ValueError, OSError):
            raise ModelBackendError(
                "Protected credential storage failed.", kind=ModelBackendErrorKind.UNSUPPORTED
            ) from None

    def migrate_legacy_credentials(self) -> CredentialMigrationResult:
        """Verify the protected copy before a compare-and-swap SQLite update.

        On any uncertain persistence failure, retain the new protected record as
        well as the existing database state for recovery; never replay a request.
        This migrates logical values, not historical backup/WAL forensic bytes.
        """
        migrated = 0
        changed = 0
        for identity, key in self._store.legacy_model_credentials():
            reference = self.store_credential(SecretStr(key))
            try:
                if self._store.migrate_model_credential(identity, key, reference):
                    migrated += 1
                else:
                    changed += 1
            except sqlite3.Error:
                raise ModelBackendError(
                    "Credential migration could not be committed; protected copies were retained.",
                    kind=ModelBackendErrorKind.UNSUPPORTED,
                ) from None
        return CredentialMigrationResult(migrated, changed, self._store.legacy_credential_count())

    def delete_credential(self, reference: str) -> None:
        if not isinstance(self._credentials, StoredCredentialResolver):
            raise ModelBackendError(
                "Protected credential storage is unavailable.",
                kind=ModelBackendErrorKind.UNSUPPORTED,
            )
        try:
            if self._store.credential_in_use(reference):
                raise ModelBackendError(
                    "Credential is still referenced by a model configuration.",
                    kind=ModelBackendErrorKind.UNSUPPORTED,
                )
            self._credentials.store.delete(reference)
        except (ValueError, OSError, sqlite3.Error):
            raise ModelBackendError(
                "Stored credential could not be safely removed.",
                kind=ModelBackendErrorKind.UNSUPPORTED,
            ) from None

    def create_profile(self, profile: ModelProfile, mode: ReasoningMode) -> str:
        self.validate_profile(profile, mode)
        return self._store.create_model_config(
            profile.provider_id,
            profile.endpoint,
            profile.model_id,
            None,
            mode.value,
            profile=profile,
        )

    def update_profile(self, profile: ModelProfile, mode: ReasoningMode) -> bool:
        self.validate_profile(profile, mode)
        return self._store.update_model_profile(profile, mode.value)

    def active_settings(self) -> ModelSettings:
        try:
            return self.resolve_binding(self._store.active_model_binding())
        except (ValidationError, ValueError):
            raise ModelBackendError(
                "Stored model configuration is invalid.", kind=ModelBackendErrorKind.UNSUPPORTED
            ) from None
