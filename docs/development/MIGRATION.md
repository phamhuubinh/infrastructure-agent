# Migration and cutover

This is a rebuild, but the repository contains existing users, data, and integrations. Migration exists to protect external behavior/data that matters, not to preserve obsolete internal abstractions.

## Rules

1. Identify externally observable contracts that must survive.
2. Build new contracts independently.
3. Write one-way adapters/migrations at the boundary when necessary.
4. Cut each entrypoint to the new runtime.
5. Delete the old path after cutover and validation.

## Persistence

For each stored type, choose explicitly:

- migrate;
- read-old/write-new temporarily;
- archive and reset;
- discard because it is internal/obsolete.

Never silently reinterpret incompatible old state as valid new authority/approval/evidence.

## Sessions

Historical chat text may be preserved as conversation data. Old hidden runtime/FSM state should not be resumed as new authority. New requests begin with new runtime state.

## Config

Migrate model connections and target/source definitions only after strict validation. Any ambiguous old default becomes an explicit migration error.

## Rollback

Use source-control checkpoints and data backups for destructive migrations. Do not maintain runtime fallback to old semantics as the rollback mechanism.
