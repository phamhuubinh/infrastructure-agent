# Internet Tool

> HTTP fetch tool with SSRF protection. **Opt-in only — never invoked automatically.**

## Overview

The Internet Tool performs HTTP GET requests to external URLs and returns extracted text content. It is **only invoked when the user explicitly requests it** — this is a permanent design constraint, not a temporary precaution.

## Capabilities

| Capability | Description |
|------------|-------------|
| `web_fetch` | Fetch and extract text content from a URL |

## Security

- **SSRF Protection**: Private IP ranges, loopback addresses, and link-local addresses are blocked at DNS resolution and connection time.
- **DNS Rebinding Guard**: Hostnames that resolve to private IPs after initial lookup are rejected.
- **Rate Limiting**: Each Internet Tool invocation is logged and counted.
- **Opt-in Only**: The tool never activates automatically — the user must explicitly request an internet lookup.

## Usage Examples

### Via CLI

```bash
orion run
> Fetch the status page from https://status.example.com
```

### Via API

```bash
curl -X POST http://localhost:61888/api/query \
  -H "Content-Type: application/json" \
  -d '{"question": "Check https://httpbin.org/status/200"}'
```

### Python

```python
from src.tool.internet_tool import InternetTool

tool = InternetTool()
result = tool.execute({"capability": "web_fetch", "url": "https://httpbin.org/json"})
print(result.data)
```

## Configuration

No authentication is required. The tool respects standard HTTP timeouts and retries.

## Limitations

- Only HTTP GET requests are supported.
- Response body is truncated to extract relevant text content; binary responses are not supported.
- JavaScript-rendered pages will not be properly extracted (no browser engine).
- Maximum response size is limited to prevent resource exhaustion.