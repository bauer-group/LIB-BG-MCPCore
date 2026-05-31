# BG-MCPCore

> **BAUER GROUP MCP framework** — config-driven, pluggable REST-API MCP servers on [FastMCP](https://github.com/jlowin/fastmcp).

`bg-mcpcore` is the shared foundation for BAUER GROUP's fleet of
[Model Context Protocol](https://modelcontextprotocol.io) servers that bridge
REST APIs (Zammad, Shlink, and more to come). It turns "stand up a secure,
OAuth-gated MCP server for an API" from a multi-day clone-and-edit job into a
short declarative profile.

## The idea: config for the standard, code for the complex

A server is described by a **declarative JSON profile**. Standard behaviour —
identity, backend connection, inbound/outbound auth, rate limiting, observability,
health/branding routes, and OpenAPI-derived tools — needs **no Python**. The
genuinely complex parts (hand-written tools, per-user on-behalf-of token flows)
drop down to **Python escape hatches** the profile points at.

```jsonc
// profiles/mautic.json — a whole server, no Python
{
  "id": "mautic",
  "display_name": "BAUER GROUP Mautic",
  "backend": { "base_url": "${env:MAUTIC_URL}", "api_base_path": "/api" },
  "auth": {
    "inbound":  { "mode": "oidc" },
    "outbound": { "type": "bearer_env", "value_from_env": "MAUTIC_TOKEN" }
  },
  "tools": { "source": "openapi", "spec": { "source": "${env:MAUTIC_OPENAPI_URL}" } }
}
```

```python
# src/main.py — the entire entrypoint
from bg_mcpcore import load_profile, make_cli

app = make_cli(load_profile("profiles/mautic.json"))
if __name__ == "__main__":
    app()
```

## Install

```bash
pip install bg-mcpcore                         # lean core (hand-written-tool servers)
pip install "bg-mcpcore[openapi]"              # + OpenAPI-derived tools
pip install "bg-mcpcore[openapi,redis,tasks,oauth-providers]"   # the full Shlink-shaped server
```

| Extra | Adds |
|---|---|
| `openapi` | `tools.source: "openapi"` — generate the tool surface from an OpenAPI spec |
| `redis` | Redis-backed encrypted OAuth-state store (multi-replica deployments) |
| `oauth-providers` | Entra / Google inbound IdP modes |
| `tasks` | long-running task execution (bulk exports) |
| `testkit` | reusable pytest fixtures + stubs (pytest11 plugin) |

## Architecture

- **Pluggable via Python entry points** — new `auth_providers`, `tool_sources`,
  `auth_resolvers`, and `middleware` are pip-installable plugins, never core edits.
- **Central tool registry** — reusable tool building blocks live in the package
  and are referenced by name from any profile (`tools.source: "registry"`).
- **Fail-closed by design** — `AUTH_MODE=none` is forbidden in production and the
  JWT signing key is mandatory for any active mode; these invariants live in core
  and a profile cannot switch them off.

## Status

Beta. Built and consumed by [`bg-zammad-mcp`](https://github.com/bauer-group/ZAMMAD-MCPServer)
and [`bg-shlink-mcp`](https://github.com/bauer-group/IP-Shlink-MCPServer).

## License

MIT © BAUER GROUP
