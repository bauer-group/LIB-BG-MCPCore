# Tier 3 — mostly Python

**When:** the backend has no usable OpenAPI spec (tools are hand-written) and/or
it uses **per-user on-behalf-of** auth, where each MCP user's own upstream token
is forwarded per call. This is the **Zammad shape**.

The profile still drives auth-core, rate limiting, identity, routes, and
observability — you only hand-write the genuinely divergent parts:

```jsonc
"auth": {
  "inbound":  { "mode": "none" },                       // a real server: "zammad" (custom provider)
  "outbound": { "type": "python", "resolver": "my_auth:make_resolver" }
},
"tools": { "source": "python", "register": "my_tools:register" }
```

## Files

| File | Role |
|---|---|
| [`profile.json`](profile.json) | backend + `python` outbound + `python` tools |
| [`my_tools.py`](my_tools.py) | the hand-written tool surface; `whoami` calls `ctx.request` |
| [`my_auth.py`](my_auth.py) | the per-user OBO resolver — **fail-closed** (`auth_headers` raises when no token) |
| [`main.py`](main.py) | 4-line entrypoint |

The third Tier-3 escape hatch — a **custom inbound provider** (`AUTH_MODE=zammad`)
registered as a `bg_mcpcore.auth_providers` entry point — and a role-gate
middleware are covered in [Writing plugins](../../docs/plugins.md) and the
[tier guide](../../docs/tiers.md#tier-3-mostly-python).

## Run

```bash
pip install bg-mcpcore
export PUBLIC_BASE_URL=http://localhost:8000 ENVIRONMENT=development AUTH_MODE=none
cd examples/python_tools_server && python main.py
# -> serves greet, echo_setting, whoami at /mcp
```

`whoami` calls `https://api.example.com/api/v1/users/me` (a placeholder backend)
with the per-user token. Without `UPSTREAM_USER_TOKEN` set, the resolver raises
**fail-closed** — exactly as intended; the server never sends a shared credential.
