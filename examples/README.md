# Examples

Each example is a complete, runnable bg-mcpcore server with its own README, and
together they cover all three complexity tiers (see the
[tier guide](../docs/tiers.md)). Pick the lowest tier that fits your backend.

| Example | Tier | Demonstrates |
|---|---|---|
| [`registry_server/`](registry_server/) | — (minimal) | backend-less server mounting reusable registry tools — no backend, no Python |
| [`openapi_server/`](openapi_server/) | **1** — pure config | tools generated from an OpenAPI spec; the surface shaped declaratively |
| [`openapi_with_python_tools/`](openapi_with_python_tools/) | **2** — config + a little Python | an OpenAPI surface PLUS a few hand-written composite tools (multi-source `tools`) |
| [`python_tools_server/`](python_tools_server/) | **3** — mostly Python | hand-written tools + a per-user on-behalf-of outbound resolver (fail-closed) — the Zammad shape |

## Running any example

```bash
pip install "bg-mcpcore[openapi]"   # [openapi] needed for tiers 1 & 2
export PUBLIC_BASE_URL=http://localhost:8000
export ENVIRONMENT=development
export AUTH_MODE=none                # dev only — forbidden in production
cd examples/<name> && python main.py
# -> serves MCP at http://localhost:8000/mcp, health at /healthz
```

Each example's own `README.md` lists the exact env vars it needs (e.g. a
backend token) and what tools it exposes. The backend URLs in the profiles are
placeholders — point `backend.base_url` at a real API to see upstream calls
return data. In production, set a real `AUTH_MODE` and `AUTH_JWT_SIGNING_KEY`
(`AUTH_MODE=none` is rejected outside development).
