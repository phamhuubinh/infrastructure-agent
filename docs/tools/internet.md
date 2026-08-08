# Internet Tool

`InternetTool` provides the bounded outbound path used by deterministic
external verification. It has two read-only capabilities:

| Capability | Purpose |
|---|---|
| `web_search` | Query a configured provider and return typed discovery results. |
| `web_fetch` | Fetch one public HTTP/HTTPS page and extract bounded text/JSON. |

Stable questions do not use the tool. Orion invokes it only when deterministic
request semantics require current external evidence, the user explicitly asks
to verify online, or the user supplies a public URL. The model does not choose
tools, rewrite arbitrary queries, or run a fetch loop.

## Search provider configuration

Keep the non-secret endpoint mapping in `tools.json` and the API credential in
the external secrets file (`/etc/orion/tool-credentials.json` by default, or
`ORION_SECRETS_PATH`). The configured endpoint must return JSON with a list of
results; common result fields `url`/`link`, `title`/`name`, and
`snippet`/`description` are recognized.

```json
// tools.json
{
  "internet": {
    "tool": "internet",
    "target": "internet",
    "search_endpoint": "https://search.example/api/search",
    "search_provider": "company-search",
    "search_query_parameter": "q",
    "search_locale_parameter": "locale",
    "search_results_field": "results",
    "timeout": 15
  }
}
```

```json
// /etc/orion/tool-credentials.json
{
  "internet": {
    "search_api_key": "replace-with-secret"
  }
}
```

`search_endpoint` is optional. Without it, `web_fetch` remains available for
an explicit URL, while `web_search` returns a typed configuration failure.
For a current-search request Orion then says that it could not verify the
current information; it never presents model memory as a verified result.

## Deterministic plan, cache, and limits

For a query-based request the reviewed plan is:

1. One provider search (up to five discovery results).
2. Deterministic URL canonicalization/deduplication with domain diversity.
3. At most three page fetches.
4. Normalize fetched pages into external evidence, Facts, retrieval timestamps,
   provider identity, and source URLs.
5. Give the evidence—not tool access—to the assessment model.

The default per-request envelope is one search, three fetches, 1 MiB total
page bytes, 25 seconds of network time, 15-second request timeout, 512 KiB
per page, and five redirects. Successful search/page observations are cached
briefly by provider/query-or-URL/freshness class. Failed, blocked, and missing
results are never cached as valid evidence.

## Security boundary

- Only public `http` and `https` URLs are allowed.
- Every fetch hop resolves and validates its destination before a socket is
  opened; loopback, RFC1918, link-local, metadata, reserved, and other
  non-global addresses are blocked.
- Redirect destinations are validated again, so a public URL cannot redirect
  into a private network.
- Credentials in URLs are rejected. Provenance redacts sensitive query
  parameters such as `token`, `api_key`, and `password`.
- No browser automation, JavaScript execution, authenticated arbitrary-site
  login, form submission, or unrestricted crawling is supported.

## Rollout switches

All GA1 routes are enabled by default. Operators can temporarily disable a
new layer with boolean environment variables:

- `ORION_GENERAL_AGENT_ROUTING_V1`
- `ORION_EXTERNAL_VERIFICATION_V1`
- `ORION_WEB_SEARCH_V1`
- `ORION_SOURCE_CONSTRAINTS_V1`

Disabling external verification or web search fails current-information
requests honestly; it does not restore an unbounded model/tool fallback.

## Troubleshooting

| Symptom | Meaning / action |
|---|---|
| “Search provider is not configured” | Set `search_endpoint`; add `search_api_key` only if the provider requires it. |
| “Could not verify current information” | Check endpoint reachability, outbound DNS/HTTPS policy, provider response shape, and request budget. |
| Private/localhost URL blocked | Expected SSRF protection; use a permitted public URL instead. |
| Source shown in answer but no current fact | The response was unavailable/partial; inspect safe trace fields and do not treat it as verified. |

The API response carries `trace_id` and credential-safe `execution_trace`; an
external-verification step reports call count, cache hits, byte use, failures,
retrieval time, truncation, and source URLs.
