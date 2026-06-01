# Minimal — backend-less registry tools

The smallest possible bg-mcpcore server: no backend, no Python, just a couple of
reusable tools mounted from the central registry. Useful as a smoke test and to
show that a profile alone produces a complete, OAuth-capable MCP server.

```jsonc
{ "id": "registry-demo", "display_name": "BG Registry Demo",
  "tools": { "source": "registry", "include": ["bg.ping", "bg.health"] } }
```

`bg.ping` returns `pong`; `bg.health` reports upstream reachability (here:
`no-backend`, since no `backend` block is configured). Add more named tools via
the `bg_mcpcore.tools` entry-point group — see [Writing plugins](../../docs/plugins.md).

## Files

| File | Role |
|---|---|
| [`profile.json`](profile.json) | a backend-less `registry` tool source |
| [`main.py`](main.py) | 4-line entrypoint |

## Run

```bash
pip install bg-mcpcore
export PUBLIC_BASE_URL=http://localhost:8000 ENVIRONMENT=development AUTH_MODE=none
cd examples/registry_server && python main.py
# -> serves bg.ping, bg.health at /mcp
```
