# R07 managed-data continuation — 2026-10-30

R07 is complete at implementation/fixture scope, with native Linux host gates
still open. No commit, push, live-provider or native application delivery claim.

Implemented a versioned offline managed-data directory bundle and CLI:
`orion data export`, `orion data import`, `orion data retain --keep N`.
Export holds the runtime lease, snapshots SQLite online, preserves managed blobs
and protected provider credential records, then publishes a private bundle with
strict inventory, schema digest, byte sizes and SHA256. Import checks SQLite
integrity/foreign keys, live blob references, stored credentials, platform and
privacy, and restores only into a new directory. Retention validates all candidate
bundles before deleting exact known files; unrelated data and failed staging
directories remain. See DATA_LIFECYCLE.md for the managed/external boundary.

LocalBlobStore now rejects linked/reparse/hardlinked paths and changed roots,
protects legacy UUID children when opening the store and makes new files private
before writing. Windows private-file helpers verify the resulting protected DACL
by reading it back; the benign Windows auto-inherited control flag is normalized,
but extra or inherited ACEs are rejected.

E5 dependencies moved to the optional `semantic` extra. Both source and release
installers default to no model provisioning; `--with-embeddings`/`-WithEmbeddings`
explicitly installs the extra and provisions the pinned model. Smoke definitions
and operation documentation were synchronized; native installer/package smoke
has not been rerun here. A subprocess fixture blocks semantic-package imports
with ModuleNotFoundError and verifies startup, lexical search, export and import.
Openpyxl's optional NumPy probe legitimately catches this missing-package error.

Focused data/blob/optional-dependency tests: 27 passed, one symlink privilege skip;
the Windows junction and ACL tests execute natively. First full run is retained in
R07_DATA_CHECKS_2026-10-30.json: 1396 passed, eight failed, seven skipped and 23
subtests. Six failures are Linux installer host cases (the prior four cases now
include parameterized default/embedding opt-in coverage); two exposed Project API
management using a fabricated session incompatible with the new session guard.
The first harness also used an unsupported OpenAPI flag and a nonexistent audit
test directory; those command errors are retained rather than reported as passes.
The completed R07_DATA_REPAIRED_2026-10-30.json reports 1400 passed, six Linux-host
failures, seven skipped and 23 subtests passed, without deselection. Source hashes
were unchanged throughout the run. All remaining failures are the Linux installer
cases above; there is no claim of a fully green native Linux backend run.

The direct Device Chat service reproduction (`ready`, one visible document) was
fixed: uploads are rejected before blob creation, and legacy attachment data is
not visible through list/search/read/status/delete/metadata. Forged principal,
workspace, Project and endpoint identity tests now cover every knowledge entry
point. Project operator management has dedicated membership-checked methods;
model-callable tools still require an actual session, including when a fake
`project-document-management` ID is supplied. The unused API helper constructing
that pseudo-session was removed after checking all callers.

The pre-migration backup now closes its SQLite connection explicitly. The remote
auth restart test now closes its old ASGITransport-owned store before starting the
replacement runtime; it had previously opened two owners, which the new lease
correctly rejects. No authorization guard was weakened. Focused API/auth/knowledge/
endpoint/restart regression passed 84 tests after these repairs.

Full-backend formatting found four preexisting unformatted R01/R07 files; their
formatting was repaired. Full mypy was then run with the backend configuration and
its declared types-openpyxl dev stub installed in the external test toolchain.
The callback-finalizer annotation, platform-specific URL opener typing and worker
message TypeAdapter alias were made explicit without changing runtime semantics.
Full mypy now passes 107 source files; Linux-platform static typing passes nine
affected source files. This is not Linux execution evidence.

The repaired run also passes full backend Ruff/format (199 Python files),
architecture, OpenAPI, 13 audit tests, PowerShell installer parse checks and Git
whitespace. Windows ACL/junction/DPAPI fixtures execute on this host. Symlink
creation requiring unavailable account privilege is skipped; junction/hardlink
coverage is separate. Native Linux, provisioned E5, browser/desktop and other
platform skips retain their actual reasons in pytest evidence.

Graphify local code-only updates succeeded with 5415 nodes/16712 edges. Queries
narrowed blob and E5 callers; conclusions above come from inspected source/tests.
No cloud/semantic extraction or labeling was invoked.
