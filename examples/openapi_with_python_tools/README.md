# Tier 2 — config + a little Python

**When:** the backend ships a usable OpenAPI spec (so most tools are generated)
but you also need a few bespoke tools the spec can't express — or a custom
outbound credential. Mostly config, a little code.

This server mounts **two tool sources** in one profile:

```jsonc
"tools": [
  { "source": "openapi", "spec": { "source": "petstore-mini.json" }, ... },  // generated: list_pets, create_pet
  { "source": "python",  "register": "extra_tools:register_extras" }          // hand-written: pet_count, find_pet_by_name
]
```

The assembler lets the **constructing** source (OpenAPI) build the FastMCP
instance, then the **registering** source (`python`) adds tools onto it. The
hand-written tools call the same backend via `ctx.request(...)`, so they inherit
the profile's outbound auth, base path, timeout, and retries — see
[`extra_tools.py`](extra_tools.py).

## Files

| File | Role |
|---|---|
| [`profile.json`](profile.json) | the two-source `tools` list (Tier-2 shape) |
| [`extra_tools.py`](extra_tools.py) | the hand-written composite tools |
| [`petstore-mini.json`](petstore-mini.json) | the demo OpenAPI spec |
| [`main.py`](main.py) | 4-line entrypoint |

## Run

```bash
pip install "bg-mcpcore[openapi]"
export PETSTORE_TOKEN=demo PUBLIC_BASE_URL=http://localhost:8000
export ENVIRONMENT=development AUTH_MODE=none   # dev only — forbidden in production
cd examples/openapi_with_python_tools && python main.py
# -> serves list_pets, create_pet (OpenAPI) + pet_count, find_pet_by_name (Python) at /mcp
```

The composite tools call `https://petstore.example.com` (a placeholder) — point
`backend.base_url` at a real Petstore to see them return data.

The alternative Tier-2 shape — a custom **outbound resolver** instead of extra
tools — is covered in the [tier guide](../../docs/tiers.md#tier-2-config-a-little-python).
