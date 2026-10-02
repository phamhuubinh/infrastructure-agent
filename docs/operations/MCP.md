# MCP v1 client/host

Orion is an MCP **client/host**: administrators configure external servers, and
allowlisted tools join the existing frozen canonical registry. The model sees them
on the first Chat/Project turn alongside built-in tools. MCP does not create another
agent, registry, model loop, authorization system, or knowledge pipeline. Orion is
not an MCP server. No MCP UI, marketplace or server installer is included.

Orion uses the official Python SDK, pinned to `mcp==2.0.0` (the stable v2 line).
External server runtimes and packages are the operator's responsibility. Installing
Orion does not install arbitrary MCP servers or add a Node/npm requirement to the
release installer. A configured server may independently require Node, Python, or
another executable.

## Local configuration

Set `ORION_MCP_CONFIG` to a readable local JSON file before starting `orion`.
Unset configuration or `{"servers": []}` keeps the built-in tool catalog. The
configuration is not persisted in the database, exposed to the model, or editable
through the public API. Keep the file under normal local administrative access.

Stdio example (replace the executable with your already installed server):

```json
{
  "servers": [
    {
      "server_id": "inventory",
      "transport": "stdio",
      "command": "inventory-mcp-server",
      "args": [],
      "env_from": {"INVENTORY_TOKEN": "ORION_INVENTORY_TOKEN"},
      "tools": {
        "read_item": {"operation_kind": "read"},
        "update_item": {"operation_kind": "mutation"}
      }
    }
  ]
}
```

Streamable HTTP example:

```json
{
  "servers": [
    {
      "server_id": "inventory",
      "transport": "streamable_http",
      "url": "https://inventory.example.com/mcp",
      "headers_from": {"Authorization": "ORION_INVENTORY_AUTH"},
      "tools": {
        "remote.read-item": {"alias": "read_item", "operation_kind": "read"}
      }
    }
  ]
}
```

`ORION_INVENTORY_AUTH` contains the complete header value, including `Bearer ` when
required. The JSON stores host environment **names**, never their resolved values.
Required variables must exist and be nonempty before startup. Header values must
not contain CR/LF; all mapped values reject NUL and have an 8 KiB bound. Secret values
must not appear in arguments, URLs, descriptions or schemas. Known mapped values in
the configuration fail startup. Stdio arguments containing credential flag names
(token, password, secret, API key, authorization) are rejected. Do not place any
other plaintext credentials in argv: argument strings cannot establish whether an
arbitrary literal is a password.

The only top-level field is `servers` (maximum 16). Each enabled entry requires
`server_id`, `transport`, and a nonempty `tools` mapping (maximum 128). There is no
implicit server enablement or discovery-based allowlist. Unknown fields, duplicate
JSON keys/IDs/aliases, wrong types and malformed files fail closed. The file is
bounded to 128 KiB. IDs and aliases match `[a-z][a-z0-9_]{0,19}`. Remote tool names
are bounded to 128 characters and use letters, digits, `_`, `.`, `:`, or `-`.
`alias` defaults to the remote name if it satisfies the local identifier grammar.
Environment names match `[A-Za-z_][A-Za-z0-9_]{0,127}`.

Every tool entry requires `operation_kind: "read" | "mutation"`; `alias` is its
only optional field. Remote read-only/destructive/idempotent annotations do not
change that local classification. Names are deterministic:
`mcp.<server_id>.<alias>`, at most 45 characters. Distinct server IDs separate
identical aliases; duplicate IDs or aliases and collisions with built-in names or
handler keys fail startup. There is no generic `mcp.call` bypass capability.

Transport fields are exclusive:

| Transport | Required | Optional |
| --- | --- | --- |
| `stdio` | `command` | `args`, `env_from`, `cwd`, `timeout_seconds` |
| `streamable_http` | `url` | `headers_from`, `timeout_seconds` |

Stdio executes an argv vector without a shell or interpolation. `cwd`, if used,
must be an existing absolute directory. The child gets the SDK's safe platform
environment and the explicit mapping; the full Orion environment is not copied.
Stderr is discarded into the null device so secrets cannot reach Orion logs or
protocol stdout. Executables/args/cwd are not returned by administration APIs.

HTTP requires an absolute `http` or `https` URL with a valid host/port, no userinfo,
query, fragment or whitespace. Headers may be `Authorization` or custom `X-*`
names; forwarded/protocol headers and duplicate case-insensitive names are rejected.
Header values always come from environment variables. TLS verification remains
on. Redirects are disabled, including redirects to another origin. Environment
proxy settings are not inherited. There is no global TLS bypass or legacy SSE-only
configuration transport.

`timeout_seconds` defaults to 30 and must be between 0.1 and 120. It bounds discovery
and calls; HTTP connect/write/pool/termination operations use at most 5 seconds.
Startup has an overall bound based on configured timeouts. These are local hang
protections, not product quotas or semantic routing limits.

## Schema and content boundaries

Only explicitly allowlisted discovered tools become canonical `ToolDefinition`s.
Missing tools, invalid names/descriptions and incompatible schemas fail startup.
Discovery is bounded to 256 tools per server and 17 pages; repeated cursors fail.
Remote names stay inside the integration except bounded administrative catalog
names. Tool descriptions remain untrusted capability metadata in provider schemas.

The v1 input-schema subset supports explicitly typed objects, arrays with a single
item schema, strings, integers, numbers, booleans and null; `required`, `enum`,
`const`, numeric bounds/multiples, string/array lengths and array uniqueness are
validated locally. Objects have finite declared properties and are closed at every
level; an omitted `additionalProperties` is made false. Open/freeform objects are
rejected. Required/optional fields and nested structure are preserved. `title` and
`default` are omitted. SDK output schemas are independently bounded to 32 KiB/16 levels and forbid
reference resolution before SDK result validation. Freeform output objects remain
data and cannot grant authority. The provider receives Orion's existing generic structural
projection; complete supported constraints remain in the registry's validator.

References/definitions, unions/combinators, patterns, formats, conditional schemas,
header annotations and unknown keywords are rejected instead of broadening
arguments. Schemas are bounded to 32 KiB, eight nested levels, 64 properties per
object, 64 characters per property name and 2,048 characters per description.
Authority fields (`principal_id`, `workspace_id`, `project_id`, `session_id`,
`mutation_mode`, `runtime_scope`, attachments and authorization policy fields) are
rejected recursively. Orion attaches the ordinary `RuntimeScope` locally and sends
only validated user-visible arguments to the server, without scope or authority
metadata. MCP does not select the session or Project, and Project knowledge remains
scoped by Orion's knowledge tools.

Server instructions, prompts, resources, roots, sampling and elicitation are not
added to Chat context or resolved as a second model loop. SDK compatibility
handshakes can read capabilities without granting them Orion authority. Server
catalog-change notifications never alter the live canonical registry. **Restart
Orion after configuration or server catalog changes** to create a newly validated
snapshot.

Successful tool results contain `data.text` (text blocks) and `data.structured`
(optional structured content). These are ordinary untrusted tool data returning to
the same model loop. Payloads are bounded to 64 KiB and 128 content blocks. Binary,
image, audio and resource blocks, malformed results and oversized content become
fixed bounded errors. Remote result metadata/annotations are not forwarded. MCP
results have `sources=[]`; external IDs are never invented as Orion `SourceRef`
citations. Resolved secret values are redacted recursively, including values from
environment names without words such as TOKEN or PASSWORD.

## Authorization, failures and lifecycle

MCP mutations pass through the existing `ToolRunner` server policy and conversation
permissions. `read_only` blocks them; `confirm` binds an exact request/session/call
and argument digest to the existing allow/deny flow; `auto` permits them only when
the local policy ceiling permits. A configured infrastructure `mutation_allowlist`
continues to block MCP mutations, just as it blocks local scheduler mutations.
Scheduler unattended requests are always forced read-only, regardless of the stored
session mode, and never ask for mutation confirmation.

MCP confirmation summaries show a fixed action label, configured server ID and
Orion-visible name. They do not echo arguments, remote descriptions/results,
headers or environment values. The existing pending-authorization target column
holds the safe local server ID; it does not confer target privileges.

Configuration/discovery/schema failures stop startup with safe category-only
administrative errors. A known unavailable connection fails before dispatch. Read
transport failures/timeouts return bounded errors for normal model recovery. A
mutation transport failure/timeout after dispatch returns `outcome_unknown`; a
malformed mutation result is also treated conservatively as unverifiable. Do not
repeat such mutations blindly. Orion performs no mutation retries or reconnects;
a failed transport remains unavailable until restart. User cancellation follows
the existing runtime boundary, which records mutation uncertainty when interrupted.

The composition root owns one SDK-client task on Orion's event loop. It connects
and discovers before building/freezing the one canonical registry and Chat runtime.
Scheduler starts after that snapshot is ready. The same owner enters/exits SDK
contexts once; failed startup closes already opened clients. Shutdown stops
Scheduler first, then releases HTTP clients and SDK subprocess trees with bounded
cleanup. No nested `asyncio.run()`, helper event loop or second registry exists.

## Safe inspection and troubleshooting

`GET /api/mcp/servers` is an administrative API protected by the existing Remote
Access inventory. It returns only configured server IDs, transport, state
(`connecting`, `connected`, `failed`, `closed`), discovered names, exposed Orion
names and `last_error` category. With no MCP configuration it returns `[]`.
No endpoint, argv, cwd, raw exception, prompt, header or environment values appear.
The API is available after successful startup; startup errors appear as bounded
administrative errors, without a partially serving application.

| Category | Operator action |
| --- | --- |
| `configuration` | Check strict JSON fields, transport shape, identifiers and bounds. |
| `missing_environment`, `invalid_environment` | Supply valid variables to Orion's launch environment. |
| `secret_in_configuration`, `secret_in_schema` | Remove plaintext values; use environment references. |
| `connection` | Check the executable/runtime or explicit endpoint, network and timeout. |
| `discovery`, `missing_tool`, `description`, `schema` | Check catalog names, allowlist and supported schema subset. |
| `composition` | Resolve canonical name/handler collisions or local policy errors. |
| `call_transport` | Inspect the external service independently; restart Orion after resolving failure. |
| `result` | Fix the server's bounded text/structured result contract. |

SDK wire/exception logs are suppressed while clients are owned because they can
contain full payloads or credentials. Use the safe API categories and the external
server's own administrative diagnostics. Do not paste credentials into Chat or
Orion issue reports.

Deterministic coverage lives in `backend/tests/test_mcp.py`, including an official
SDK Python subprocess fixture, in-process servers and a loopback-only HTTP server.
Linux CI and native Windows CI both execute the MCP tests; no public service or
third-party MCP server download is required during them.
