---
icon: material/layers-triple
---

# The three tiers: config vs. code

bg-mcpcore is built on one principle — **config for the standard, code for the
complex**. A server is described by a declarative JSON *profile*; the parts that
genuinely differ between backends drop down to small Python *escape hatches* the
profile points at.

How much Python a given server needs falls into three tiers. Pick the lowest
tier that fits your backend — you can always mix (a single profile can combine
an OpenAPI tool source with a few hand-written tools).

```text
Does the backend ship a usable OpenAPI spec?
├─ yes ──> Do you need a handful of bespoke tools / a custom outbound credential?
│          ├─ no  ──> TIER 1  (pure config)
│          └─ yes ──> TIER 2  (config + a little Python)
└─ no  ─────────────> TIER 3  (mostly Python: hand-written tools)
```

| Tier | Backend shape | Python you write | Example |
|---|---|---|---|
| **1** | Clean OpenAPI spec, standard inbound auth | none | `examples/openapi_server` |
| **2** | OpenAPI spec + a few bespoke tools, or a custom outbound credential | ~10–30 lines | `examples/openapi_with_python_tools` |
| **3** | No usable spec (hand-written tools), per-user on-behalf-of auth | the tool surface + a resolver | `examples/python_tools_server` |

Everything below the tier-specific parts — OAuth-gated inbound auth, encrypted
OAuth-state storage, rate limiting, structured logging with PII redaction, the
`/healthz` + branded `/` routes, dual-stack HTTP — is provided by the framework
in **every** tier. You never re-implement it.

---

## :material-numeric-1-circle: Tier 1 — pure config { #tier-1-pure-config }

**When:** the backend publishes a usable OpenAPI 3 spec and you want every
operation exposed as a tool, with standard inbound auth (OIDC / Entra / Google /
one of the first-class providers).

**You write:** a profile JSON + a 4-line `main.py`. No tool code.

```jsonc
// profiles/mautic.json
{
  "$schema": "https://schemas.bauer-group.com/mcp-profile/v1.json",
  "id": "mautic",
  "display_name": "BAUER GROUP Mautic",
  "instructions": "Marketing automation via the Mautic REST API.",
  "backend": { "base_url": "${env:MAUTIC_URL}", "api_base_path": "/api" },
  "auth": {
    "inbound":  { "mode": "oidc" },
    "outbound": { "type": "bearer_env", "value_from_env": "MAUTIC_TOKEN" }
  },
  "tools": {
    "source": "openapi",
    "spec": { "source": "${env:MAUTIC_OPENAPI_URL}" },
    "annotations": "by_http_method"
  }
}
```

```python
# src/main.py
from bg_mcpcore import load_profile, make_cli

app = make_cli(load_profile("profiles/mautic.json"), version="1.0.0")
if __name__ == "__main__":
    app()
```

The `openapi` tool source ([openapi] extra) calls `FastMCP.from_openapi`. You
shape the generated surface declaratively in the `tools` block — none of it is
Python:

- `route_maps` — turn paths into resources or exclude them
  (`[{ "pattern": "^/health$", "type": "resource" }, { "pattern": "^/admin", "type": "exclude" }]`).
- `name_overrides` — `{ "POST /short-urls": "create_short_url" }` renames the
  verbose `operationId` the LLM sees.
- `descriptions` — override an unhelpful spec `summary`.
- `annotations: "by_http_method"` — apply MCP safety hints (GET = read-only;
  POST/PUT/PATCH/DELETE = destructive) so clients can gate auto-run.
- `normalize: { "strip_path_prefix": "/rest/v{version}" }` — drop a version
  prefix that the backend's `api_base_path` already supplies.

This is the **Shlink shape**: a static `X-Api-Key` outbound (`static_header`) +
an OpenAPI spec → a complete server with zero tool code.

---

## :material-numeric-2-circle: Tier 2 — config + a little Python { #tier-2-config-a-little-python }

**When:** you have an OpenAPI spec but also need (a) a few bespoke convenience
tools the spec can't express, or (b) a custom outbound credential the built-in
`static_header` / `bearer_env` resolvers don't cover.

**You write:** the profile (as Tier 1) plus a small Python module the profile
references via an escape hatch.

### (a) Extra hand-written tools alongside the OpenAPI surface

`tools` accepts a **list** of sources — mount the OpenAPI surface AND a `python`
source that adds a couple of tools:

```jsonc
"tools": [
  { "source": "openapi", "spec": { "source": "${env:API_OPENAPI_URL}" } },
  { "source": "python", "register": "my_tools:register_extras" }
]
```

```python
# my_tools.py — ~10 lines
def register_extras(mcp, ctx) -> int:
    @mcp.tool
    async def summarise_account(account_id: str) -> dict:
        """A composite the raw API doesn't expose: fetch + shape an account."""
        resp = await ctx.request("GET", f"/accounts/{account_id}")
        data = resp.json()
        return {"id": data["id"], "name": data["name"], "open_tickets": data["stats"]["open"]}
    return 1
```

The `ctx` is a capability-scoped `ToolContext` (an authenticated `client` + a
logger); `ctx.request(...)` routes through the same outbound auth as the
generated tools.

### (b) A custom outbound resolver

If the backend needs a credential shape the built-ins don't cover (e.g. a signed
header), set `auth.outbound.type: "python"`:

```jsonc
"auth": { "outbound": { "type": "python", "resolver": "my_auth:make_resolver" } }
```

```python
# my_auth.py
class SignedHeaderResolver:
    def __init__(self, cfg): self._cfg = cfg
    def default_headers(self) -> dict[str, str]:
        return {"X-Signature": _sign(...)}     # static, applied at client construction
    async def auth_headers(self, ctx) -> dict[str, str]:
        return {}                              # nothing per-call

def make_resolver(cfg):
    return SignedHeaderResolver(cfg)
```

---

## :material-numeric-3-circle: Tier 3 — mostly Python { #tier-3-mostly-python }

**When:** the backend has no usable OpenAPI spec (so tools are hand-written), and
/or it uses **per-user on-behalf-of** auth where each MCP user's own upstream
token is forwarded per call.

**You write:** the tool surface (hand-written), an outbound resolver (the OBO
token logic), and — if the backend is its own IdP — a custom inbound provider
registered via an entry point. The profile still drives auth-core, rate limiting,
identity, routes, and observability.

This is the **Zammad shape**.

```jsonc
// profiles/zammad.json
{
  "id": "zammad",
  "display_name": "BAUER GROUP Zammad",
  "instructions": "Helpdesk: tickets, articles, users, organizations.",
  "backend": { "base_url": "${env:ZAMMAD_URL}", "api_base_path": "/api/v1" },
  "auth": {
    "inbound":  { "mode": "zammad" },                       // custom provider (entry point)
    "outbound": { "type": "python", "resolver": "zammad.auth:make_obo_resolver" }
  },
  "tools": { "source": "python", "register": "zammad.tools:register_all" }
}
```

```python
# zammad/auth.py — per-user on-behalf-of, FAIL-CLOSED
class OnBehalfOfResolver:
    def default_headers(self) -> dict[str, str]:
        return {}                                  # nothing static
    async def auth_headers(self, ctx) -> dict[str, str]:
        token = await _resolve_user_token()        # from the validated inbound session
        if not token:
            raise PermissionError("no upstream token for this user")  # never inherit a default
        return {"Authorization": f"Bearer {token}"}

def make_obo_resolver(cfg):
    return OnBehalfOfResolver()
```

Three escape hatches, each a documented seam:

1. **Inbound provider** — a non-standard IdP (opaque tokens, custom verification)
   registers a builder as a `bg_mcpcore.auth_providers` entry point in the
   server's own `pyproject.toml`, so `AUTH_MODE=zammad` resolves it. (Standard
   OIDC IdPs need no code — use `mode: oidc`.)
2. **Outbound resolver** — `auth.outbound.type: python` for per-user OBO. It must
   **raise** when no credential is available, never fall back to a static default.
3. **Access control** — a role-gate middleware (e.g. "Agents only") is added via
   `make_cli(..., extra_middleware=[...])` or a `bg_mcpcore.auth_middleware`
   entry point keyed on the mode.

```toml
# the server's pyproject.toml
[project.entry-points."bg_mcpcore.auth_providers"]
zammad = "zammad.auth:build_zammad_provider"
```

See [Writing plugins](plugins.md) for the provider/resolver/middleware contracts.

---

## :material-shuffle-variant: Mixing tiers

Tiers are not exclusive. A real server often combines them: an OpenAPI surface
(Tier 1) + two composite hand-written tools (Tier 2) + a per-user resolver
(Tier 3). The profile's `tools` list and the `auth` block compose freely — start
at the lowest tier and add code only where the backend forces it.
