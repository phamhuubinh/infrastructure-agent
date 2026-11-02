# R07 managed-data backup contract

The offline `orion data` commands acquire the same database runtime lease as
the application. Stop the server first. A SQLite online backup plus copied blobs
and protected provider-credential records form one versioned managed-data bundle.
No models, tools, migrations or scheduler jobs execute during export/import.

Bundles are private directories named `orion-backup-<UUID>`, published only after
all payloads and a manifest are durable. The v1 manifest records identity, UTC
creation time, platform, database schema digest and exact file sizes/SHA256.
Validation rejects extra/missing files, linked paths, hard links, traversal,
unknown versions, bad hashes, broken SQLite integrity/foreign keys, missing live
document blobs and unavailable stored credential references. Hashes detect damage;
they do not authenticate an untrusted publisher. Only import trusted local bundles.

All ordinary UUID blobs and all stored provider credential records are copied,
including currently unreachable records, so export never silently loses managed
bytes. Environment credential references are recorded as external requirements;
environment values are never exported. Windows DPAPI records remain bound to the
original OS account/machine. Cross-platform protected-credential restore is rejected.

Import validates into a private sibling staging directory, then publishes a new
data directory containing `orion.db`, `blobs/`, and `provider-credentials/` by rename.
The target must not exist; existing data is never replaced or merged. First startup
uses normal migrations and interrupted-request recovery, with no mutation replay.

This is a full backup of Orion's managed SQLite/blob/provider-credential stores,
not a system image: external SSH/tool/MCP configuration, environment secrets,
remote worker state, OS key material, models, logs, caches and app binaries are
outside the bundle. Reconfigure these explicitly after restore. Exported data may
contain secret-bearing historical database rows; filesystem privacy is mandatory.

Retention is explicit (`keep >= 1`), never automatic during export. It preflights
every matching bundle before deleting only validated payloads, manifest and known
empty directories. Unknown files, links, tampering or incomplete bundles fail
closed. It never deletes runtime data, migration snapshots, unrelated directories
or arbitrary archive files. Retention does not purge conversation history.

Filesystem checks defend against accidental redirection and other accounts;
a process already running as the same OS user can mutate its own files and is
outside this filesystem boundary. Keep all data/bundle parents owner-controlled.
