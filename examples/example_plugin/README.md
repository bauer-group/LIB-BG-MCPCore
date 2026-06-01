# Example plugin — a custom `echo` tool source

Proves the headline extensibility claim: **new tool sources are pip-installable
plugins, never core edits.** This package adds a `tools.source: "echo"` that
bg-mcpcore discovers through a Python entry point — exactly the mechanism the
`openapi` source itself uses.

## How it works

One declaration in [`pyproject.toml`](pyproject.toml):

```toml
[project.entry-points."bg_mcpcore.tool_sources"]
echo = "bg_mcpcore_echo:create_echo_source"
```

and one factory in [`src/bg_mcpcore_echo/__init__.py`](src/bg_mcpcore_echo/__init__.py)
returning a provider with `async def register(mcp, ctx) -> int`. That's the
whole contract — bg-mcpcore's `build_tool_provider` looks the name up in the
`bg_mcpcore.tool_sources` group when it sees `"source": "echo"` in a profile.

## Use it

```bash
pip install "bg-mcpcore" ./examples/example_plugin
```

```jsonc
// profile.json
{
  "id": "demo",
  "display_name": "Echo demo",
  "tools": { "source": "echo" }
}
```

```bash
ENVIRONMENT=development AUTH_MODE=none PUBLIC_BASE_URL=http://localhost:8000 \
  python -c "import asyncio; from bg_mcpcore import *; \
    asyncio.run(build_app_from_profile(load_profile('profile.json'), \
      get_settings(BaseMcpSettings)))"
# -> the server now exposes an `echo` tool, with zero changes to bg-mcpcore
```

The same pattern extends `bg_mcpcore.auth_providers` (new IdP), `auth_resolvers`
(new outbound auth), `auth_middleware`, and `bg_mcpcore.tools` (central registry
building blocks). See [docs/plugins.md](../../docs/plugins.md).
