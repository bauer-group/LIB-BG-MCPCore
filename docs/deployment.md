---
icon: material/server-network
---

# Deployment

This guide covers running a `bg-mcpcore` server in production: choosing a transport, persisting the encrypted OAuth-state store, the environment a real deployment requires, reverse-proxy placement, health checks, and horizontal scaling.

For local setup and the dependency model see [installation](installation.md); for the profile and settings reference see [configuration](usage.md); for inbound identity providers see [authentication](authentication.md); for rate limiting and Sentry see [observability & limits](observability.md); for the trust boundaries see [security model](security.md).

## :material-package-variant:  1. Install for production

`bg-mcpcore` ships a lean mandatory core and pushes volatile or single-consumer dependencies into extras, so a server pays only for what it imports. The core already includes FastMCP, Pydantic, structlog, `cryptography`, Typer, and the **disk-backed** encrypted OAuth state store (`py-key-value-aio[disk]`).

### Extras matrix

| Extra | Adds | Install when |
| --- | --- | --- |
| `openapi` | `pyyaml` (the OpenAPI `$ref` resolver and `FastMCP.from_openapi` are core/stdlib) | the profile sets `tools.source = "openapi"` and ingests a **YAML** spec |
| `redis` | `py-key-value-aio[redis]` | you run more than one replica, or want the OAuth store on a shared, operator-keyed backend |
| `oauth-providers` | (marker extra — Entra and Google ship inside FastMCP) | the server opts into a cloud IdP inbound mode; kept explicit for clarity |
| `tasks` | `fastmcp[tasks]` (docket) | the server exposes long-running tasks such as bulk exports |
| `testkit` | `pytest`, `pytest-asyncio`, `respx` (exposed as a pytest11 plugin) | running the reusable test fixtures — **not** a runtime dependency |

!!! tip "Recommended production set"
    For a typical spec-driven, OAuth-protected, multi-replica server, install:

    ```bash
    pip install "bg-mcpcore[openapi,redis,oauth-providers,tasks]"
    ```

    Drop `openapi` if your tools come from a Python or registry source, drop `tasks` if you expose no long-running operations, and drop `redis` only for a deliberately single-instance deployment (see [section 4](#4-oauth-state-persistence-critical)).

### Supported Python

`bg-mcpcore` requires **Python 3.12+** and is tested and classified for **3.12, 3.13, and 3.14**. Lint and type-checks target the 3.12 floor, so nothing in the package uses syntax newer than 3.12.

## :material-cog:  2. Required environment for a real deployment

Environment variables map **1:1 to snake_case field names** — there is no env prefix — so `public_base_url` is set via `PUBLIC_BASE_URL`, `auth_jwt_signing_key` via `AUTH_JWT_SIGNING_KEY`, and so on. Settings load from the process environment and from a `.env` file (UTF-8, case-insensitive keys); unknown keys are ignored.

### The values that matter

- **`PUBLIC_BASE_URL`** — the public origin clients reach the server on. It is the origin used to build the OAuth **redirect URI** and the consent-screen icon URL (`${PUBLIC_BASE_URL}/logo.svg`). A trailing slash is normalised away internally (`https://mcp.example.com/` and `https://mcp.example.com` behave identically), but the value **must match what you registered as the redirect URI at your IdP**, or the OAuth flow fails. The MCP endpoint clients connect to is `${PUBLIC_BASE_URL}/mcp`.
- **`ENVIRONMENT`** — one of `production`, `staging`, `development` (default `production`). In `production`, `AUTH_MODE=none` is rejected at boot.
- **`AUTH_MODE`** — the inbound auth mode. The generic `oidc` mode covers any standards-compliant OIDC IdP via discovery; cloud modes (`entra-single`, `entra-multi`, `google`) and the spec-driven generic modes (`auth0`, `keycloak`, `workos`, `clerk`, …) are resolved through the provider registry. See [authentication](authentication.md).
- **A real auth mode's credentials** — for the generic `oidc` mode these are the `OIDC_*` fields: at minimum `OIDC_DISCOVERY_URL` (or the individual `OIDC_ISSUER` / `OIDC_AUTH_URI` / `OIDC_TOKEN_URI` / `OIDC_JWKS_URI` endpoints), `OIDC_CLIENT_ID`, and `OIDC_CLIENT_SECRET`. `OIDC_SCOPES` defaults to `openid profile email` and `OIDC_USERNAME_CLAIM` to `preferred_username`. Cloud modes read their own settings — consult [authentication](authentication.md) for the per-mode keys.
- **`AUTH_JWT_SIGNING_KEY`** — a 32-byte key used to sign FastMCP-issued JWTs. It is **mandatory for any active (non-`none`) auth mode** and must not be a `CHANGE_ME…` placeholder. In disk-storage mode it also seeds the storage encryption key (see [section 4](#4-oauth-state-persistence-critical)), which is why it must stay **stable** across restarts.

Generate the signing key:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

### Fail-closed boot checks

These universal invariants run in the core settings validator **before** any per-mode credential check, so a server subclass cannot relax them. Boot fails loudly (a `ValueError`) rather than starting in an insecure state:

1. `AUTH_MODE=none` is **forbidden when `ENVIRONMENT=production`**. (Set `ENVIRONMENT=development` if running unauthenticated is genuinely intentional.)
2. For any non-`none` mode, `AUTH_JWT_SIGNING_KEY` must be present and must not start with `CHANGE_ME`.
3. When `AUTH_REDIS_URL` is set, `AUTH_STORAGE_ENCRYPTION_KEY` must be present **and a valid Fernet key** (32 url-safe base64 bytes) — there is no plaintext OAuth state at rest.

!!! warning "`AUTH_MODE=none` is rejected in production"
    A server with `ENVIRONMENT=production` and `AUTH_MODE=none` will not start. This is deliberate: an unauthenticated MCP endpoint exposes your backend to anyone who can reach it. Use a real auth mode, or explicitly downgrade `ENVIRONMENT` for a sandbox.

### Copy-pasteable env block

```bash
# --- Identity / public origin -------------------------------------------------
PUBLIC_BASE_URL=https://mcp.example.com      # no trailing slash needed; must
                                             # match the IdP redirect URI
ENVIRONMENT=production

# --- Inbound auth (generic OIDC example) --------------------------------------
AUTH_MODE=oidc
OIDC_DISCOVERY_URL=https://idp.example.com/.well-known/openid-configuration
OIDC_CLIENT_ID=your-client-id
OIDC_CLIENT_SECRET=your-client-secret
# OIDC_SCOPES=openid profile email          # default
# OIDC_USERNAME_CLAIM=preferred_username     # default

# --- JWT signing (mandatory for any auth mode) --------------------------------
AUTH_JWT_SIGNING_KEY=<output of: python -c "import secrets; print(secrets.token_hex(32))">

# --- OAuth-state store: Redis (multi-replica) ---------------------------------
AUTH_REDIS_URL=redis://redis:6379/0
AUTH_STORAGE_ENCRYPTION_KEY=<output of: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())">

# --- OR single-instance disk mode (omit AUTH_REDIS_URL) -----------------------
# AUTH_DISK_STORAGE_PATH=/app/data/oauth-storage   # default; MUST be a volume

# --- Transport ----------------------------------------------------------------
# MCP_TRANSPORT=streamable-http              # default
# MCP_HOST=                                  # empty -> dual-stack "::"
MCP_PORT=8000

# --- Reverse proxy ------------------------------------------------------------
RATE_LIMITER_TRUSTED_PROXY_HOPS=1            # number of proxies in front
```

## :material-transit-connection-variant:  3. Transports

`bg-mcpcore` supports two MCP transports, selected by `MCP_TRANSPORT` (default `streamable-http`):

- **`streamable-http`** — the production transport. The server runs an HTTP listener and exposes the MCP endpoint at `${PUBLIC_BASE_URL}/mcp`, alongside the operational routes (see [section 5](#5-health-checks)). This is what a remote, OAuth-protected deployment uses.
- **`stdio`** — for embedding the server as a child process of a local MCP client over stdin/stdout. No network listener, no host/port. Not used for a hosted deployment.

Any other value raises `Unsupported transport` at startup.

### Binding and dual-stack

`MCP_HOST` defaults to **empty**, which means "any stack, any interface". An empty host binds `::`, and `bg-mcpcore` patches the socket layer (`patch_dual_stack_socket`, applied at process start) so that a single `::` listener accepts **both IPv6 and v4-mapped IPv4** — you do not need a second IPv4 listener. Pin the host explicitly to `0.0.0.0`, `::`, `127.0.0.1`, or `::1` if you need to constrain it. `MCP_PORT` defaults to `8000` (valid range 1–65535).

### The serve command

A profile-driven server exposes a `serve` command (it is also the default when invoked with no subcommand):

```bash
# Run with environment-driven config
your-mcp-server serve

# Override host / port / transport for this run
your-mcp-server serve --host 0.0.0.0 --port 9000 --transport streamable-http
```

The flags override `MCP_HOST`, `MCP_PORT`, and `MCP_TRANSPORT` respectively for that invocation; absent flags fall back to the environment.

## :material-database:  4. OAuth-state persistence (critical) { #4-oauth-state-persistence-critical }

FastMCP's OAuth providers persist five classes of server-side state: DCR client metadata, authorization codes + PKCE challenges, refresh-token-hash → upstream-token mappings, issued-JWT-JTI → upstream-token mappings, and in-flight OAuth transactions. Without an explicit store, FastMCP falls back to a `DiskStore` under `platformdirs.user_data_dir()` — which **inside a container is ephemeral**, so every restart wipes all of it and logs every user out.

`bg-mcpcore` therefore **always** supplies a durable, encrypted-at-rest backend. Which one you get depends on a single switch — whether `AUTH_REDIS_URL` is set.

!!! danger "The #1 production footgun: persist the OAuth store, or users get logged out on every restart"
    In **disk mode**, the *encryption key* is derived from `AUTH_JWT_SIGNING_KEY` and is therefore restart-stable on its own — but the encrypted **files** still live at `AUTH_DISK_STORAGE_PATH` (default `/app/data/oauth-storage`). If that path is **not mounted as a volume**, the files vanish when the container is recreated and every user must re-authenticate, regardless of the stable key. **Mount the disk path as a persistent volume, or use Redis.** This is the single most common deployment mistake.

### Redis vs. disk

| | **Redis** (`AUTH_REDIS_URL` set) | **Disk** (`AUTH_REDIS_URL` unset) |
| --- | --- | --- |
| Backend | `RedisStore`, Fernet-encrypted | `DiskStore` at `AUTH_DISK_STORAGE_PATH`, Fernet-encrypted |
| Encryption key | **operator-provided** `AUTH_STORAGE_ENCRYPTION_KEY` (required, validated Fernet key) | **derived** from `AUTH_JWT_SIGNING_KEY` via HKDF + fixed salt |
| Survives restart | Yes (state lives in Redis) | Only if the path is a mounted volume |
| Horizontal scaling | **Yes** — shared across replicas | **No** — single instance only |
| Recommended for | Production, especially > 1 replica | Single-instance / small deployments |

The encryption key must be **stable** across restarts in both modes — a changed key invalidates all stored state. In disk mode this is guaranteed automatically because the key is derived from the (fixed) `AUTH_JWT_SIGNING_KEY` plus a constant salt: identical inputs each boot yield an identical key. (There is intentionally no backward compatibility with FastMCP's historical DiskStore salt; a one-time re-authentication on cutover to `bg-mcpcore` is expected.)

Generate a Redis-mode storage key:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

!!! warning "Use a dedicated `AUTH_STORAGE_ENCRYPTION_KEY` — do not reuse the signing key"
    In Redis mode, if `AUTH_STORAGE_ENCRYPTION_KEY` equals `AUTH_JWT_SIGNING_KEY`, `bg-mcpcore` logs a warning at startup. Use a **separate** storage key so that a leaked signing key does not also compromise the encrypted OAuth state at rest. Keep the storage key as a discrete secret in your secret manager.

!!! note "Redis URLs are sanitised in logs"
    Credentials in `AUTH_REDIS_URL` (`redis://user:pass@host:6379/0`) are stripped before the URL is logged (`redis://***@host:6379/0`), so no Redis password leaks into structured logs.

## :material-heart-pulse:  5. Health checks { #5-health-checks }

The server mounts **`/healthz`**, which returns `200 OK` (`{"status": "ok"}`) as soon as the process is up. It is **unauthenticated** — it sits in front of the OAuth wall specifically so container and Kubernetes liveness/readiness probes can reach it without credentials. Point your container `HEALTHCHECK` and any k8s `livenessProbe` / `readinessProbe` at `/healthz`.

The server also serves `/logo.svg` and a human-readable status page at `/` from the configured `static_dir` (when those routes are enabled in the profile). The upstream backend's own health endpoint, if any, remains behind the OAuth wall and is not the same thing as `/healthz`.

## :material-router-network:  6. Reverse proxy

In production, terminate TLS at a reverse proxy (nginx, Traefik, Caddy, a cloud load balancer) and forward plain HTTP to the server's `MCP_PORT`. The proxy should:

- Terminate TLS and forward to the server port (default `8000`).
- Set `X-Forwarded-For` so the real client IP reaches the server.
- Forward the host so `PUBLIC_BASE_URL` continues to match the externally visible origin (and thus the IdP redirect URI).

Because the rate limiter keys on client IP, it must know how many proxy hops to trust when reading `X-Forwarded-For`. Set **`RATE_LIMITER_TRUSTED_PROXY_HOPS`** to the number of proxies in front of the server (default `1`, range 0–10) so a client cannot spoof its address by injecting forged `X-Forwarded-For` entries. See [observability & limits](observability.md) for the full rate-limiter configuration.

```nginx
location / {
    proxy_pass         http://mcp-server:8000;
    proxy_set_header   Host              $host;
    proxy_set_header   X-Forwarded-For   $proxy_add_x_forwarded_for;
    proxy_set_header   X-Forwarded-Proto $scheme;
    # Streamable HTTP keeps connections open; disable response buffering.
    proxy_buffering    off;
}
```

## :material-docker:  7. Containerisation

`bg-mcpcore` has no Dockerfile of its own (it is a library); a server that depends on it builds its own image. The following is a representative, production-credible Dockerfile grounded in the package — a supported Python base, an install with the recommended extras, the listen port exposed, a healthcheck hitting `/healthz`, and the disk-storage path declared as a volume.

```dockerfile
# Supported: 3.12, 3.13, or 3.14
FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    MCP_PORT=8000 \
    AUTH_DISK_STORAGE_PATH=/app/data/oauth-storage

WORKDIR /app

# Install your server (which depends on bg-mcpcore) with production extras.
COPY . /app
RUN pip install ".[openapi,redis,oauth-providers,tasks]"

# Encrypted OAuth state store (disk mode). Mount this as a volume in prod
# so OAuth state survives container recreation.
RUN mkdir -p /app/data/oauth-storage
VOLUME ["/app/data/oauth-storage"]

EXPOSE 8000

# Unauthenticated liveness probe.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz').status==200 else 1)"

CMD ["your-mcp-server", "serve"]
```

### docker run

```bash
docker run -d --name mcp-server \
  -p 8000:8000 \
  --env-file .env \
  -v mcp-oauth-storage:/app/data/oauth-storage \
  your-org/your-mcp-server:latest
```

### docker compose

```yaml
services:
  mcp-server:
    image: your-org/your-mcp-server:latest
    restart: unless-stopped
    ports:
      - "8000:8000"
    env_file: .env
    environment:
      MCP_PORT: "8000"
      # Single-instance disk mode: persist the encrypted store on a volume.
      AUTH_DISK_STORAGE_PATH: /app/data/oauth-storage
    volumes:
      - mcp-oauth-storage:/app/data/oauth-storage
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz').status==200 else 1)"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 10s

volumes:
  mcp-oauth-storage:
```

### Scaling beyond one replica

The disk store is **single-instance only** — each replica would hold its own private OAuth state, so a client whose login landed on replica A would fail on replica B. To run **more than one replica**, switch to the Redis store: set `AUTH_REDIS_URL` and a dedicated `AUTH_STORAGE_ENCRYPTION_KEY`, install the `redis` extra, and drop the per-replica volume. All replicas then share one durable, encrypted, restart-stable OAuth state store.

```yaml
services:
  mcp-server:
    image: your-org/your-mcp-server:latest
    restart: unless-stopped
    deploy:
      replicas: 3
    env_file: .env            # includes AUTH_REDIS_URL + AUTH_STORAGE_ENCRYPTION_KEY
    depends_on:
      - redis

  redis:
    image: redis:7-alpine
    restart: unless-stopped
    volumes:
      - redis-data:/data

volumes:
  redis-data:
```

!!! tip "Pre-flight checklist"
    - `PUBLIC_BASE_URL` matches the IdP redirect URI (trailing slash is harmless).
    - `ENVIRONMENT=production` with a real `AUTH_MODE` (never `none`).
    - `AUTH_JWT_SIGNING_KEY` generated and stable; not a `CHANGE_ME` value.
    - OAuth store persisted: Redis (multi-replica) **or** a mounted disk volume (single instance).
    - In Redis mode, `AUTH_STORAGE_ENCRYPTION_KEY` is a valid, **dedicated** Fernet key.
    - Reverse proxy terminates TLS and `RATE_LIMITER_TRUSTED_PROXY_HOPS` matches the hop count.
    - Probes hit `/healthz`.
