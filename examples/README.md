# Examples

Each example is a complete, runnable bg-mcpcore server. Run any of them with a
minimal dev environment:

```bash
pip install "bg-mcpcore[openapi]"
export PUBLIC_BASE_URL=http://localhost:8000
export ENVIRONMENT=development
export AUTH_MODE=none          # dev only - forbidden in production
cd examples/<name> && python main.py
# -> serves MCP at http://localhost:8000/mcp, health at /healthz
```

| Example | Tier | Demonstrates |
|---|---|---|
| `registry_server/` | — | backend-less server mounting reusable registry tools (no Python) |
| `openapi_server/` | 1 | tools generated from an OpenAPI spec, pure config |
| `python_tools_server/` | 3 | the `tools.source: python` escape hatch (hand-written tools) |
