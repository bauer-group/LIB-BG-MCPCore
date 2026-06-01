<!-- AUTO-GENERATED FILE. DO NOT EDIT. Edit docs/README.template.MD instead. -->
<!-- Generated on 2026-06-01 14:53:31 UTC -->

# BAUER GROUP - BG-MCPCore

[![PyPI Version](https://badge.fury.io/py/bg-mcpcore.svg)](https://pypi.org/project/bg-mcpcore/)
[![Python Support](https://img.shields.io/pypi/pyversions/bg-mcpcore.svg)](https://pypi.org/project/bg-mcpcore/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![🧪 Tests](https://github.com/bauer-group/LIB-BG-MCPCore/actions/workflows/tests.yml/badge.svg)](https://github.com/bauer-group/LIB-BG-MCPCore/actions/workflows/tests.yml)

> **BAUER GROUP MCP framework** — config-driven, pluggable REST-API MCP servers on [FastMCP](https://github.com/jlowin/fastmcp).

`bg-mcpcore` is the shared foundation for BAUER GROUP's fleet of
[Model Context Protocol](https://modelcontextprotocol.io) servers that bridge
REST APIs (Zammad, Shlink, and more). It turns "stand up a secure, OAuth-gated
MCP server for an API" from a multi-day clone-and-edit job into a short
declarative profile.

**Repository Information:**

- **Version:** v1.2.0 (2026-06-01)
- **Repository:** [bauer-group/LIB-BG-MCPCore](https://github.com/bauer-group/LIB-BG-MCPCore)
- **Branch:** main
- **Architecture:** Config-driven, pluggable, secure-by-default

## The idea: config for the standard, code for the complex

A server is described by a **declarative JSON profile**. Standard behaviour —
identity, backend connection, inbound/outbound auth, rate limiting,
observability, health/branding routes, and OpenAPI-derived tools — needs **no
Python**. The genuinely complex parts (hand-written tools, per-user
on-behalf-of token flows) drop down to **Python escape hatches** the profile
points at.

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

Requires **Python 3.12, 3.13, or 3.14**.

### From PyPI

```bash
pip install bg-mcpcore
```

### Directly from GitHub

```bash
# Latest from main
pip install git+https://github.com/bauer-group/LIB-BG-MCPCore.git@main

# A specific released version/tag
pip install git+https://github.com/bauer-group/LIB-BG-MCPCore.git@v1.2.0

# With extras (any install method)
pip install "bg-mcpcore[openapi] @ git+https://github.com/bauer-group/LIB-BG-MCPCore.git@main"
```

### Optional extras

```bash
pip install "bg-mcpcore[openapi]"                               # + OpenAPI-derived tools
pip install "bg-mcpcore[openapi,redis,tasks,oauth-providers]"   # full Shlink-shaped server
```

| Extra | Adds |
|---|---|
| `openapi` | `tools.source: "openapi"` — generate the tool surface from an OpenAPI spec |
| `redis` | Redis-backed encrypted OAuth-state store (multi-replica deployments) |
| `oauth-providers` | Entra / Google + the spec-driven IdP modes (Auth0, Keycloak, GitHub, AWS Cognito, WorkOS, …) |
| `tasks` | long-running task execution (bulk exports) |
| `testkit` | reusable pytest fixtures + stubs (pytest11 plugin) |

## Architecture

- **Pluggable via Python entry points** — new `auth_providers`, `tool_sources`,
  `auth_resolvers` are pip-installable plugins, never core edits.
- **Central tool registry** — reusable tools (`bg.health`, …) referenced by name
  from any profile (`tools.source: "registry"`).
- **Fail-closed by design** — `AUTH_MODE=none` forbidden in production; the JWT
  signing key mandatory for any active mode; invariants live in core.

See the [documentation](docs/) for the profile schema reference, plugin
authoring guide, and security model.

## License

MIT © BAUER GROUP
