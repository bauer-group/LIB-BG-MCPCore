# Multi-mount gateway — N backends, one endpoint

The optional **central tool availability** mode. Rather than running one server
per backend, `build_gateway` mounts several profiles under name prefixes on a
single FastMCP, so a client sees every backend's tools — `alpha_ping`,
`beta_ping`, … — behind one URL and one OAuth wall.

```python
from bg_mcpcore import build_gateway, load_profile, get_settings

gateway = await build_gateway(
    [("shlink", load_profile("shlink.json")), ("zammad", load_profile("zammad.json"))],
    get_settings(Settings),
)
```

Each sub-server's tools/resources/prompts are namespaced by its prefix, so two
backends never collide.

## Caveats

- All sub-servers share one `BaseMcpSettings` instance (bg-mcpcore has no
  `env_prefix`); per-backend secrets that collide on the same env var name need a
  bespoke settings type.
- Inbound auth belongs on the **parent** (the gateway's HTTP layer); build the
  sub-profiles with `AUTH_MODE` matching the gateway, or `none` behind a trusted
  proxy.

## Run

```bash
pip install "bg-mcpcore[openapi]"
export ENVIRONMENT=development AUTH_MODE=none PUBLIC_BASE_URL=http://localhost:8000
cd examples/gateway_server && python main.py
# -> serves alpha_ping, beta_ping at /mcp
```
