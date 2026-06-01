# Writing plugins

bg-mcpcore is extended through Python **entry points** — a new capability is a
pip-installable package, never a core edit. Three groups:

| Group | Adds | Built-ins |
|---|---|---|
| `bg_mcpcore.tool_sources` | a `tools.source` value | `python`, `registry`, `openapi` |
| `bg_mcpcore.auth_providers` | an inbound `AUTH_MODE` | `none`, `oidc` |
| `bg_mcpcore.auth_resolvers` | an outbound `auth.type` | `none`, `static_header`, `bearer_env`, `python` |
| `bg_mcpcore.tools` | a named tool for `tools.source: registry` | `bg.ping`, `bg.health` |

## A new tool source

```python
# my_pkg/graphql.py
class GraphQLToolProvider:
    def __init__(self, cfg): self._cfg = cfg
    async def register(self, mcp, ctx) -> int:
        # add tools to `mcp`; use `ctx.client` / `ctx.request(...)` for upstream calls
        ...
        return count

def create_provider(cfg):   # cfg is the profile's ToolsConfig
    return GraphQLToolProvider(cfg)
```

```toml
# my_pkg/pyproject.toml
[project.entry-points."bg_mcpcore.tool_sources"]
graphql = "my_pkg.graphql:create_provider"
```

A provider implements **`ToolProvider`** (`async register(mcp, ctx) -> int`) to
add tools to an existing instance, or **`ConstructingToolProvider`**
(`async construct(*, name, instructions, auth, lifespan, icon_url, website_url, ctx) -> FastMCP`)
to build the instance itself (as the OpenAPI source does via `from_openapi`).

## A new auth provider / resolver

```python
def build_my_idp(settings): ...        # -> a FastMCP auth provider (or None)
def build_my_resolver(cfg): ...        # -> an AuthHeaderSource
```

```toml
[project.entry-points."bg_mcpcore.auth_providers"]
my-idp = "my_pkg.auth:build_my_idp"

[project.entry-points."bg_mcpcore.auth_resolvers"]
sigv4 = "my_pkg.auth:build_my_resolver"
```

## A reusable registry tool

```python
def register(mcp, ctx) -> None:
    @mcp.tool
    async def my_tool() -> str: ...
```

```toml
[project.entry-points."bg_mcpcore.tools"]
"acme.search" = "my_pkg.tools:register"
```

!!! warning "Least privilege"
    The OpenAPI/registry sources receive a capability-scoped `ToolContext`
    (a `client` + logger), not the full secret-bearing settings. Only the
    `python` escape hatch (the server's own trusted code) receives `settings`.
