# Tier 1 — pure config

**When:** the backend ships a usable OpenAPI spec and you want every operation
exposed as a tool, with standard inbound auth. **No Python tool code** — a
profile JSON plus a 4-line entrypoint.

The `openapi` tool source ([openapi] extra) calls `FastMCP.from_openapi` and you
shape the generated surface declaratively in the `tools` block:

```jsonc
"tools": {
  "source": "openapi",
  "spec": { "source": "petstore-mini.json" },
  "name_overrides": { "GET /pets": "list_pets", "POST /pets": "create_pet" },
  "annotations": "by_http_method"
}
```

Other declarative knobs: `route_maps` (exclude paths / turn them into resources),
`descriptions` (override an unhelpful spec summary), `normalize.strip_path_prefix`.
See the [profile reference](../../docs/profiles.md#tools).

## Files

| File | Role |
|---|---|
| [`profile.json`](profile.json) | the OpenAPI tool source + overrides (Tier-1 shape) |
| [`petstore-mini.json`](petstore-mini.json) | the demo OpenAPI spec |
| [`main.py`](main.py) | 4-line entrypoint |

## Run

```bash
pip install "bg-mcpcore[openapi]"
export PETSTORE_TOKEN=demo PUBLIC_BASE_URL=http://localhost:8000
export ENVIRONMENT=development AUTH_MODE=none   # dev only — forbidden in production
cd examples/openapi_server && python main.py
# -> serves list_pets, create_pet at /mcp
```

Need a couple of bespoke tools on top of the generated surface? That is
[Tier 2](../openapi_with_python_tools/).
