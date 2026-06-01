# Usage & configuration

This page is the depth behind the [Quickstart](quickstart.md): how configuration
is split, every setting, how to run a server, and how a request flows.

## The mental model: profile + settings + escape hatches

A bg-mcpcore server is assembled from two inputs, plus optional Python:

| Input | Holds | Lives in | Changes per |
|---|---|---|---|
| **Profile** (JSON) | *structure*: backend shape, outbound-auth type, tool sources, route toggles, identity | a `.json` file in the repo | the server's design |
| **Settings** (env) | *runtime values + secrets*: inbound auth mode + credentials, public URL, rate-limit, Sentry, storage | environment variables | the deployment |
| **Escape hatches** (Python) | the genuinely-divergent logic: hand-written tools, custom resolvers/providers | the server's own modules | the backend's quirks |

Rule of thumb: **structure → profile, runtime/secret → env, complex behaviour →
Python.** Secrets never go in the profile — they are referenced by env-var name
(`value_from_env`, `<key>_env`) and resolved at boot.

`build_app_from_profile(profile, settings)` wires them together. `make_cli` wraps
that in a Typer CLI so a server's `main.py` is four lines.

## Settings reference (environment variables)

`BaseMcpSettings` reads these from the environment (`.env` is loaded too). Names
map 1:1 to upper-snake env vars (`public_base_url` ← `PUBLIC_BASE_URL`).

### General

| Env var | Default | Notes |
|---|---|---|
| `ENVIRONMENT` | `production` | `production` \| `staging` \| `development` |
| `PUBLIC_BASE_URL` | `http://localhost:8000` | public origin; **must** match the IdP's redirect-URI registration |
| `LOG_FORMAT` | `json` | `json` (prod) \| `console` (dev) |
| `LOG_LEVEL` | `INFO` | |

### Transport + identity

| Env var | Default | Notes |
|---|---|---|
| `MCP_TRANSPORT` | `streamable-http` | `streamable-http` \| `stdio` |
| `MCP_HOST` | `""` | empty = bind `::` (dual-stack v6+v4) |
| `MCP_PORT` | `8000` | |
| `MCP_DISPLAY_NAME` | *(required)* | consent-screen name; the server subclass sets a default |
| `MCP_ICON_URL` | unset | unset → `${PUBLIC_BASE_URL}/logo.svg` |
| `MCP_WEBSITE_URL` | `https://go.bauer-group.com/mcp-server` | |

### Auth (inbound + persistence)

| Env var | Default | Notes |
|---|---|---|
| `AUTH_MODE` | `none` | `none` \| `oidc` \| `entra-single`/`entra-multi` \| `google` \| `auth0` \| `keycloak` \| `github` \| `aws-cognito` \| `workos` \| … (see [tiers](tiers.md) / [plugins](plugins.md)) |
| `AUTH_JWT_SIGNING_KEY` | `""` | **required** for any active mode; not `CHANGE_ME` |
| `AUTH_REDIS_URL` | unset | set → Redis-backed encrypted OAuth state; unset → encrypted disk store |
| `AUTH_STORAGE_ENCRYPTION_KEY` | unset | **required** (valid Fernet key) when `AUTH_REDIS_URL` is set |
| `AUTH_DISK_STORAGE_PATH` | `/app/data/oauth-storage` | mount as a volume in production |
| `OIDC_DISCOVERY_URL` / `OIDC_CLIENT_ID` / `OIDC_CLIENT_SECRET` / `OIDC_*` | — | for `AUTH_MODE=oidc` |

### Rate limiting + observability

| Env var | Default | Notes |
|---|---|---|
| `RATE_LIMITER_ENABLED` | `true` | token-bucket per client |
| `RATE_LIMITER_MAX_REQUESTS_PER_SECOND` | `10` | sustained rate |
| `RATE_LIMITER_BURST_CAPACITY` | `2×` rate | |
| `RATE_LIMITER_GLOBAL` | `false` | one bucket for the whole server (DoS shield) |
| `RATE_LIMITER_TRUSTED_PROXY_HOPS` | `1` | reverse-proxy hops for X-Forwarded-For |
| `SENTRY_DSN` / `SENTRY_ENVIRONMENT` / `SENTRY_TRACES_SAMPLE_RATE` | unset / — / `0.05` | optional error tracking |

The **fail-closed invariants** are enforced in core and cannot be relaxed:
`AUTH_MODE=none` is rejected in production, the JWT signing key is mandatory for
any active mode, and `AUTH_REDIS_URL` requires a valid storage key. See the
[security model](security.md).

## Adding backend-specific settings

A server subclasses `BaseMcpSettings` to add its backend fields (which must NOT
live on the shared base) and per-mode credential checks:

```python
from bg_mcpcore import BaseMcpSettings
from bg_mcpcore.settings import get_settings

class MauticSettings(BaseMcpSettings):
    mcp_display_name: str = "BAUER GROUP Mautic"   # set a default for THIS server
    mautic_url: str = "http://mautic:8080"          # backend field (env: MAUTIC_URL)

    def validate_provider_auth(self) -> None:
        # Runs AFTER the core fail-closed invariants. Add per-mode checks here.
        if self.auth_mode == "oidc" and not self.oidc_client_id:
            raise ValueError("OIDC_CLIENT_ID is required for AUTH_MODE=oidc")

app = make_cli(load_profile("profiles/mautic.json"), settings_cls=MauticSettings, version="1.0.0")
```

`get_settings(MauticSettings)` is a per-class cached singleton.

## Running

```bash
export ENVIRONMENT=production PUBLIC_BASE_URL=https://mcp.example.com
export AUTH_MODE=oidc OIDC_DISCOVERY_URL=... OIDC_CLIENT_ID=... OIDC_CLIENT_SECRET=...
export AUTH_JWT_SIGNING_KEY=$(python -c "import secrets;print(secrets.token_hex(32))")
python src/main.py            # = `serve`
# overrides: python src/main.py serve --host 0.0.0.0 --port 9000 --transport stdio
```

The server exposes:

- `…/mcp` — the MCP endpoint (Streamable HTTP), OAuth-gated when a mode is set.
- `/healthz` — `200 OK` for container/k8s liveness probes (no auth).
- `/` — a human-readable status + quickstart page; `/logo.svg` — the brand icon.

## Connecting an MCP client

Point an MCP client (Claude Desktop, the MCP Inspector, an IDE) at
`https://mcp.example.com/mcp`. With an auth mode set, the client runs the OAuth
2.1 + PKCE consent flow against your IdP; bg-mcpcore (via FastMCP's OAuth proxy)
mints a session and persists the encrypted state so restarts don't log users out.

## Request lifecycle (what the framework does per call)

```text
inbound request
  → rate-limit middleware (cheapest rejection; keyed on OAuth subject or client IP)
  → auth-mode middleware (e.g. Entra tenant allowlist)        [if configured]
  → inbound auth validation (FastMCP OAuth provider)
  → tool dispatch
      → ToolContext.request(...) → UpstreamClient
          → outbound resolver: static default header + per-call auth_headers(ctx)
          → retry/backoff on transient upstream errors
  → response
```

Start with the [Quickstart](quickstart.md), then pick a [tier](tiers.md).
