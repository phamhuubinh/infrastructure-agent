# Internet Tool

`InternetTool` provides the bounded outbound path used by deterministic
external verification. It has two read-only capabilities:

| Capability | Purpose |
|---|---|
| `web_search` | Query a configured provider and return typed discovery results. |
| `web_fetch` | Fetch one public HTTP/HTTPS page and extract bounded text/JSON. |

Stable questions do not use the tool. In the Agent v2 controller, the model
can select a reviewed Internet action but never receives arbitrary HTTP
authority: the harness validates its typed query/URL input and executes it.

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

For the Agent v2 controller, the reviewed bounded flow is:

1. `internet.current` accepts one to three queries (the legacy single
   `query` field remains accepted), returning up to five result cards per
   query by default; the per-query hard maximum is ten.
2. Search snippets are discovery metadata only. The model explicitly selects
   a useful public URL in a later `internet.fetch_url` action.
3. One fetch normalizes readable public-page content into bounded evidence
   with final URL, title when available, content type, and truncation state.

Search usage is request-scoped: three queries are the visible soft budget and
six are the hard budget. Fetches have a hard budget of six attempted actions.
Crossing the soft search budget remains allowed; a query batch that would
cross the hard remaining budget is rejected before provider execution. These
Internet budgets are additional to—not replacements for—the controller's
global action/tool/model/token limits.

The transport envelope retains a 1 MiB aggregate legacy-verification byte
budget, 25 seconds of network time, 15-second request timeout, 512 KiB per
page, and five redirects. HTML extraction removes scripts, styles, navigation,
footers, and similar chrome; it preserves headings, paragraphs, lists, and
simple table rows, then bounds normalized text with explicit truncation.
Successful legacy search/page observations are cached briefly by
provider/query-or-URL/freshness class. Failed, blocked, and missing results
are never cached as valid evidence.

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
