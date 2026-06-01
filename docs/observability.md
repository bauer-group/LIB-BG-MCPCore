# Observability & limits

`bg-mcpcore` ships a small, opinionated observability layer that every server inherits for free: structured logging with built-in PII/secret redaction, a startup banner with loud security warnings, optional Sentry error tracking, and a token-bucket rate limiter that runs as the first (cheapest) rejection path on every request.

All four are wired in a fixed order inside `build_app_from_profile`:

```text
setup_logging -> init_sentry -> inbound auth -> outbound client
  -> rate-limit middleware FIRST -> register tool sources
  -> healthz/logo/index routes -> banner
```

Logging is configured first so that everything after it — including Sentry's init log line and the rate limiter's `rate_limit.enabled` line — emits in the same structured shape. See [configuration](usage.md) for how settings are loaded and [deployment](deployment.md) for production wiring.

---

## Structured logging

Logging is built on [structlog](https://www.structlog.org/). structlog is the single source of truth: stdlib `logging` is routed through it as well, so third-party libraries (`httpx`, `fastmcp`, `uvicorn`) emit in the same shape as your own log lines. `setup_logging()` is idempotent — calling it twice is a no-op until `reset_logging()` is called (used only by tests).

### Two output modes

The output mode is selected by `LOG_FORMAT`:

| `LOG_FORMAT` | Renderer | Use |
| ------------ | -------- | --- |
| `json` | `JSONRenderer(sort_keys=True)` — one JSON object per line | Production / aggregator-ready (the default) |
| `console` | `ConsoleRenderer` — Rich-coloured, human-readable, `key=value` tail | Local development |

!!! note "JSON is the default"
    `LOG_FORMAT` defaults to `json`. Set `LOG_FORMAT=console` explicitly for readable local output.

`LOG_LEVEL` (default `INFO`) is resolved against the stdlib `logging` levels and applied both to the root logger and to structlog's filtering bound logger. A few notoriously chatty libraries are clamped to at least `WARNING` even when the root level is lower — `httpx`, `httpcore`, and `hpack` (the latter is pinned to `WARNING` outright).

### What gets logged and what it looks like

Every line carries a small, consistent envelope, regardless of format:

- an ISO-8601 UTC `timestamp` (key is literally `timestamp`, generated via `TimeStamper(fmt="iso", utc=True)`)
- the `level` and the `logger` name (e.g. `bg-mcpcore.app`, `bg-mcpcore.rate_limit`, `bg-mcpcore.sentry`, `bg-mcpcore.<profile-id>`)
- any context bound via `structlog.contextvars`
- the event name plus its structured key/value fields
- stack info / formatted exception info when present

A typical production (`json`) line — for example the `app.built` event emitted at the end of startup — looks like this:

```json
{
  "event": "app.built",
  "level": "info",
  "logger": "bg-mcpcore.app",
  "profile": "zammad",
  "tools_registered": 42,
  "constructing": true,
  "timestamp": "2026-06-01T09:15:42Z"
}
```

Get a logger anywhere in your server code with `get_logger`:

```python
from bg_mcpcore import get_logger

logger = get_logger("my-server.tools")
logger.info("ticket.created", ticket_id=123, queue="support")
```

`now_iso()` is also exported for the rare case where you need an ISO-8601 UTC timestamp string outside a structlog event.

### PII / secret redaction

A redaction processor runs in the shared processor chain, so it applies to **every** log line, in both `json` and `console` mode, for both your code and third-party libraries routed through structlog. It scans each event's keys: if a key (lowercased) contains any sensitive fragment as a substring, the value is replaced with `***`. Matching is by substring, so a key like `auth_token` or `X-Api-Key` is caught by `token` / `x-api-key` respectively.

The baseline fragment list is:

| Fragment | Fragment |
| -------- | -------- |
| `password` | `client_secret` |
| `secret` | `signing_key` |
| `token` | `encryption_key` |
| `api_key` | `x-api-key` |
| `apikey` | `bearer` |
| `authorization` | |

!!! tip "Add aggressively — false positives are cheap"
    A false positive just prints `***` instead of the value. There is no penalty for an over-broad fragment, so err on the side of masking.

**Before / after.** Given a call like:

```python
logger.info("upstream.auth", api_key="sk-live-abcd1234", queue="support")
```

the emitted line masks the secret but keeps the harmless field:

```json
{
  "event": "upstream.auth",
  "api_key": "***",
  "queue": "support",
  "level": "info",
  "logger": "my-server.tools",
  "timestamp": "2026-06-01T09:15:42Z"
}
```

#### Extending the fragment list additively

A server extends — never replaces — the baseline set by passing its own backend secret field names through `setup_logging(extra_sensitive_fragments=...)`. The extras are merged onto the built-in fragments:

```python
from bg_mcpcore import setup_logging

setup_logging(
    log_format="json",
    log_level="INFO",
    extra_sensitive_fragments=("fints_pin", "pat"),
)
```

When you build via `build_app_from_profile`, pass the same list as `extra_sensitive_fragments=` and core forwards it into `setup_logging` for you:

```python
mcp = await build_app_from_profile(
    profile,
    settings,
    version="1.2.3",
    extra_sensitive_fragments=("fints_pin", "pat"),
)
```

!!! note "Additive by design"
    `extra_sensitive_fragments` is concatenated onto the baseline tuple — your fragments are added, the built-in ones are never dropped. This is the intended way for a backend to mask its own secret field names (e.g. a banking `fints_pin`, a personal-access-token `pat`).

---

## Startup banner & loud warnings

After the server is fully assembled, `print_banner` prints a Rich-formatted boot banner. It is safe to call before logging is fully configured because it writes through the shared Rich `console` (with `force_terminal=True`, so colours survive in Docker logs that lack a real TTY).

The banner always shows the server display name and version, plus:

- `environment`
- `auth_mode`
- `public_url`

Backend-specific lines (for example a detected upstream URL and version) are appended verbatim via the `extra_lines` parameter; core itself passes none.

On top of the banner, three **loud** warnings exist for security-relevant misconfigurations. Each is a high-contrast, hard-to-miss console banner:

| Warning | Fires when | What it tells you |
| ------- | ---------- | ----------------- |
| `warn_no_auth()` | `AUTH_MODE=none` — emitted by `build_app_from_profile` immediately after the banner | The MCP endpoint is **unprotected**; only permitted in `ENVIRONMENT=development`, never deploy this way |
| `warn_entra_open_tenants()` | `AUTH_MODE=entra-multi` **and** no `ENTRA_ALLOWED_TENANTS` set — emitted while the Entra auth provider is built | Access tokens from **any** Microsoft Entra tenant are accepted; set `ENTRA_ALLOWED_TENANTS` to restrict to your own tenant(s) |
| `warn_role_audit_only()` | Role-check **audit-only** mode is enabled (denials logged via `auth.tenant_denied_audit_only_passing_through` but not enforced) | Use during rollout only; switch to enforcement once the allowlist is verified |

!!! warning "`AUTH_MODE=none` is development-only"
    `warn_no_auth()` prints a red-on-yellow banner because an unauthenticated MCP endpoint is wide open. It is only acceptable when `ENVIRONMENT=development`. The fail-closed persistence and auth invariants in core back this up — see the [security model](security.md).

!!! warning "Open multi-tenant Entra is rarely what you want"
    With `AUTH_MODE=entra-multi` and an empty allowlist, the JWT signature is still validated against Microsoft's multi-tenant JWKS, but the `tid` (tenant) claim is **not** gated — so any tenant on earth is accepted. The gate is otherwise silent, which is exactly why `warn_entra_open_tenants()` fires loudly. Set `ENTRA_ALLOWED_TENANTS`.

---

## Sentry error tracking

Sentry is fully optional and lazily wired. `init_sentry` activates **only** when a DSN is configured; `sentry-sdk` is imported lazily so it stays an optional runtime dependency.

Behaviour:

- **No DSN → no-op.** If `SENTRY_DSN` is falsy, `init_sentry` returns `False` and does nothing.
- **DSN set but `sentry-sdk` not installed** → logs `sentry.sdk_missing` (with a hint to install the SDK) and returns `False`.
- **DSN set and SDK installed** → initialises Sentry and logs `sentry.initialized`.
- **PII is never sent** — Sentry is initialised with `send_default_pii=False`.

The `environment` reported to Sentry is `SENTRY_ENVIRONMENT` if set, otherwise it falls back to the general `ENVIRONMENT` value. The `release` is the `version` string passed to `build_app_from_profile` (defaulting to `0.0.0`), so your deployments are release-tagged in Sentry automatically.

| Env var | Default | Purpose |
| ------- | ------- | ------- |
| `SENTRY_DSN` | _(unset)_ | Sentry project DSN. **Unset disables Sentry entirely.** |
| `SENTRY_ENVIRONMENT` | _(unset → falls back to `ENVIRONMENT`)_ | Environment tag in Sentry |
| `SENTRY_TRACES_SAMPLE_RATE` | `0.05` | Performance-tracing sample rate (validated to `0.0`–`1.0`) |

```bash
SENTRY_DSN=https://examplePublicKey@o0.ingest.sentry.io/0
SENTRY_ENVIRONMENT=production
SENTRY_TRACES_SAMPLE_RATE=0.05
```

!!! note "Release tagging comes from `version`"
    The Sentry `release` is whatever `version` you pass to `build_app_from_profile`. Wire your build/version string through so crashes are attributed to the correct release.

---

## Rate limiting

The rate limiter is a **token-bucket** built on FastMCP's `RateLimitingMiddleware`, wrapped with a client-identity resolver tailored for reverse-proxy deployments. It is added to the server **first**, ahead of auth-mode and tool middleware, because it is the cheapest rejection path under load — over-limit requests are dropped before any heavier work runs.

`build_rate_limit_middleware(settings)` returns `None` when `RATE_LIMITER_ENABLED` is false, in which case no rate-limit middleware is added at all (the disabled path). When enabled, it logs `rate_limit.enabled` with the effective parameters.

### Token bucket parameters

- **Sustained rate** — `RATE_LIMITER_MAX_REQUESTS_PER_SECOND` tokens refill per second per bucket.
- **Burst capacity** — `RATE_LIMITER_BURST_CAPACITY` is the bucket size. When unset, it defaults to `max(1, int(max_requests_per_second * 2))` — i.e. **2× the sustained rate**.

### Per-client vs global scope

`RATE_LIMITER_GLOBAL` selects the bucketing scope:

- **`false` (default) — per-client.** Each resolved client identity gets its own bucket.
- **`true` — global.** One bucket for the entire server, acting as a coarse DoS shield.

For per-client scope, the client identity is resolved by `resolve_client_id` with this precedence:

1. **Authenticated request → OAuth subject.** Keyed as `sub:<subject>`, taken from the access token's `sub` claim (falling back to `oid`). This is the most stable, least-forgeable identity: two parallel calls from the same user share one bucket regardless of source IP (mobile + desktop, IP roaming, NAT).
2. **Anonymous request behind a trusted proxy → forwarded IP.** Keyed as `ip:<address>` read from `X-Forwarded-For` (see below).
3. **Anonymous direct connection → source IP.** Keyed as `ip:<request.client.host>`.
4. **No identity at all →** the `ip:unknown` sentinel.
5. **Stdio transport** (no HTTP request) → the authenticated subject if present, otherwise the single `ip:local` sentinel, collapsing all stdio callers into one bucket.

### Trusted proxy hops & non-spoofable `X-Forwarded-For`

Behind a reverse proxy (e.g. Cloudflare → Traefik), `request.client.host` is always the proxy's IP — so without special handling every client would share one bucket. The limiter instead reads `X-Forwarded-For`, but only as far as it can trust it.

`RATE_LIMITER_TRUSTED_PROXY_HOPS` (default `1`, range `0`–`10`) is the number of reverse-proxy hops you actually run in front of the server. A trusting proxy like Traefik **prepends** to `X-Forwarded-For`, so the value at position `-trusted_proxy_hops` (counting from the right) is the outermost address **this server can verify** — anything further left was supplied by a proxy you do not control and is therefore treated as untrusted/forgeable. If the header has fewer hops than configured, resolution clips to the leftmost value observed (still a trusted-proxy view). Setting `trusted_proxy_hops` to `0` disables `X-Forwarded-For` parsing entirely and falls back to the direct connection IP.

!!! warning "Set `RATE_LIMITER_TRUSTED_PROXY_HOPS` to match your real proxy chain"
    This value must equal the number of proxies that actually prepend to `X-Forwarded-For` in front of the server.

    - **Too low** → you trust a client-supplied portion of `X-Forwarded-For`, letting a caller spoof their identity and dodge per-client limits.
    - **Too high** → you index past the real chain into a non-existent hop, so unrelated clients can collapse into the wrong bucket.

    Only when this matches the true hop count is the resolved client IP non-spoofable. Confirm your proxy topology in [deployment](deployment.md).

### Environment variables

| Env var | Default | Purpose |
| ------- | ------- | ------- |
| `RATE_LIMITER_ENABLED` | `true` | Master switch. `false` adds no rate-limit middleware at all. |
| `RATE_LIMITER_MAX_REQUESTS_PER_SECOND` | `10.0` | Sustained throughput per bucket (must be `> 0`). |
| `RATE_LIMITER_BURST_CAPACITY` | _(unset → 2× sustained rate)_ | Bucket size / max burst per bucket (`>= 1` when set). |
| `RATE_LIMITER_GLOBAL` | `false` | `true` = one server-wide bucket (DoS shield); `false` = per-client. |
| `RATE_LIMITER_TRUSTED_PROXY_HOPS` | `1` | Trusted reverse-proxy hops for `X-Forwarded-For` resolution (`0`–`10`). |

```bash
RATE_LIMITER_ENABLED=true
RATE_LIMITER_MAX_REQUESTS_PER_SECOND=10
RATE_LIMITER_BURST_CAPACITY=20
RATE_LIMITER_GLOBAL=false
RATE_LIMITER_TRUSTED_PROXY_HOPS=1
```

!!! tip "First and cheapest"
    Because the rate limiter is the first middleware added, it rejects over-limit requests before auth verification, tool dispatch, or any upstream call runs — keeping the server cheap to defend under load.

---

## See also

- [configuration](usage.md) — how settings and env vars are loaded
- [deployment](deployment.md) — production wiring, proxies, and the hop count
- [security model](security.md) — auth modes, fail-closed invariants, and the warnings above
