---
icon: material/file-cog
---

# Profile reference

A profile is a JSON document validated against `mcp-profile/v1` (the schema is
shipped at `bg_mcpcore/profile/schema.json`). It describes **structure**, never
secrets: strings interpolate `${env:VAR}` (fail-closed if the variable is unset)
and outbound credentials are referenced by env-var name, never inlined.

For an optional knob with a sensible default, use shell-style `${env:VAR:-default}`:
the default applies when `VAR` is unset **or** empty, while an explicit value still
overrides it — so a documented-but-optional setting never silently becomes a no-op.
Defaults are literal and intended for **non-secret** config (URLs, paths) only;
secrets keep using `value_from_env` (no default, always fail-closed).

```jsonc
// unset SHLINK_OPENAPI_URL → the baked-in spec; set it → that override wins
"spec": { "source": "${env:SHLINK_OPENAPI_URL:-file:///app/openapi/shlink.json}" }
```

The top-level model is **strict** (`extra="forbid"`) so a typo'd key is a load
error; the source-specific sub-blocks (OpenAPI `spec`, `route_maps`, …) allow
extras so a profile stays valid before the relevant extra is installed.

## :material-format-list-bulleted-square:  Top-level fields

| Field | Type | Notes |
|---|---|---|
| `id` | string (required) | server id / log + namespace prefix |
| `display_name` | string (required) | profile-level name (settings `MCP_DISPLAY_NAME` overrides) |
| `instructions` | string | MCP server instructions for the LLM |
| `icon_url`, `website_url` | string | consent-screen branding (settings override) |
| `backend` | object | upstream connection; **omit for registry-only / backend-less servers** |
| `auth` | object | `inbound` + `outbound` (see below) |
| `tools` | object **or list** | one or more tool sources |
| `routes` | object | toggles for `healthz` / `logo` / `index` |
| `extensions` | object | optional declarative prompts + resources catalogue |
| `access_control` | object | optional role/claim gate (`roles_claim`) |
| `cache` | object | optional response-freshness hints (see below) |

## :material-server:  `backend`

The upstream REST API. Omit the whole block for a backend-less server (the
`ToolContext.client` is then `None` and `ctx.request(...)` raises).

```jsonc
"backend": {
  "base_url": "${env:SHLINK_URL}",   // required when backend is present
  "api_base_path": "/rest/v3",        // appended to base_url for every call (default "")
  "http_timeout": 30,                 // seconds, 1..300 (default 30)
  "verify_tls": true,                 // default true — never disable in production
  "user_agent": "bg-mcpcore"          // default "bg-mcpcore"
}
```

## :material-key:  `auth`

Two independent halves. `inbound` is who may call **this** MCP server; `outbound`
is how this server authenticates to the **upstream** API.

### `auth.inbound`

```jsonc
"inbound": {
  "mode": "oidc",            // advisory mirror of AUTH_MODE (env is authoritative)
  "config": { ... }          // provider-specific params for spec-driven IdPs
}
```

The authoritative inbound mode is the `AUTH_MODE` **environment variable**, held
and validated by `BaseMcpSettings` (closed set, fail-closed). `mode` here is an
advisory mirror for readability. `config` carries params for the spec-driven
providers (`auth0`/`keycloak`/`github`/…) — secrets referenced by a `<key>_env`
entry, never inlined:

```jsonc
"inbound": { "mode": "keycloak", "config": { "realm_url": "${env:KEYCLOAK_REALM_URL}" } }
"inbound": { "mode": "auth0",    "config": { "config_url": "...", "client_id": "...", "audience": "...", "client_secret_env": "AUTH0_SECRET" } }
```

`mode: oidc` (core built-in) covers any standard-OIDC IdP via discovery and needs
no `config`. See [plugins](plugins.md) for the full provider catalogue.

### `auth.outbound`

```jsonc
"outbound": { "type": "static_header", "header": "X-Api-Key", "value_from_env": "SHLINK_API_KEY" }
```

| `type` | Required keys | Credential shape |
|---|---|---|
| `none` | — | no outbound auth |
| `static_header` | `header` + `value_from_env` | a fixed header (Shlink's `X-Api-Key`) |
| `bearer_env` | `value_from_env` | `Authorization: Bearer <token>` |
| `per_user_token` | — (optional `static_fallback_env`) | **on-behalf-of**: the caller's upstream token, per request, fail-closed |
| `client_credentials` | `token_url` + `client_id_env` + `client_secret_env` | **service token**: OAuth2 client-credentials, minted and cached by the server itself |
| `entra_obo` | `scopes` (non-empty list) | **native Entra on-behalf-of** via azure-identity; prefer over `per_user_token` on the `entra-*` modes |
| `python` | `resolver` (dotted `module:attr`) | a custom `AuthHeaderSource` (bespoke signed headers) |
| *(plugin)* | per resolver | any `bg_mcpcore.auth_resolvers` entry point |

`per_user_token` resolves the upstream token from the access-token `claims`
(default `upstream_access_token` / `upstream_token`) then the OAuth-state storage
keyed by `jti`/`sub`, and applies it as `{scheme} <token>` on `header` (default
`Authorization` / `Bearer`). When none is found it raises — unless
`static_fallback_env` is set, then it applies that via `static_fallback_template`
(e.g. `"Token token={token}"`) or `{scheme} <token>`. Per-call only, so it needs a
python/request tool surface (the OpenAPI source uses the bare client). Optional
keys: `scheme`, `claims`, `storage_key_prefixes`, `static_fallback_env`,
`static_fallback_template`.

`entra_obo` is the better on-behalf-of path on `AUTH_MODE=entra-single` /
`entra-multi`. Instead of *finding* a token the IdP already issued, it *mints*
one: FastMCP's `EntraOBOToken` drives azure-identity's `OnBehalfOfCredential`,
with that SDK's own cache and refresh behind it. Because it is a supported API it
does not depend on the shape of FastMCP's OAuth-state storage, and it can request
scopes the caller's original token never carried. `scopes` is required, and every
scope must also appear in the provider's `additional_authorize_scopes` with admin
consent granted. Optional keys: `header`, `scheme`. Needs the
`[oauth-providers]` extra.

`client_credentials` is for an upstream that issues its own service tokens rather
than accepting a static key. The server authenticates as itself — no user, no
browser — against `token_url`, caches the token and re-mints it shortly before it
expires. The credential comes from the environment: `client_id_env` and
`client_secret_env` name the variables, and the resolver refuses to build if they
are unset. Optional keys: `scopes` (list, sent space-joined), `audience`,
`header` (default `Authorization`), `scheme` (default `Bearer`), `auth_style` —
`basic` (default, HTTP Basic on the token endpoint) or `post` (credentials in the
form body, required by endpoints that only accept `client_secret_post`) — and
`timeout` (seconds, default `30`).

```jsonc
"outbound": {
  "type": "client_credentials",
  "token_url": "https://idp.example.com/oauth/token",
  "client_id_env": "UPSTREAM_CLIENT_ID",
  "client_secret_env": "UPSTREAM_CLIENT_SECRET",
  "scopes": ["api.read"]
}
```

!!! warning "Per-call resolvers need a Python tool surface"
    `per_user_token`, `entra_obo` and `client_credentials` all resolve their
    credential **per request**, so `default_headers()` is empty by design and the
    OpenAPI tool source — which drives the bare client — is **not** covered by
    them. Pair them with a `python` tool source using `ctx.request` /
    `ctx.request_json`. All three fail closed: when no credential can be produced
    they raise rather than letting the request go out unauthenticated.

`value_from_env` names the env var holding the secret (resolved fail-closed at
boot); use `value` only for non-secret literals. A resolver splits credentials
into **static** `default_headers()` (applied once at client construction — this
also covers the bare httpx2 client the OpenAPI source drives) and **per-call**
`auth_headers(ctx)` (resolved per request; must **raise** when no credential is
available — never silently fall back to a static default). See the
[security model](security.md) and [Tier 3](tiers.md#tier-3-mostly-python).

## :material-wrench:  `tools`

A single source **or a list** of sources (they compose: at most one *constructing*
source — OpenAPI — builds the instance, the rest register onto it). Built-ins:

```jsonc
// hand-written tools (escape hatch) — the server's own code
{ "source": "python", "register": "myserver.tools:register_all_tools" }

// reusable tools from the central registry
{ "source": "registry", "include": ["bg.ping", "bg.health"] }

// paginated bulk export rendered as a CSV/JSON task ([tasks] extra)
{ "source": "export", "name": "export_short_urls", "endpoint": "/short-urls",
  "items_path": "shortUrls.data", "page_param": "page",
  "page_size_param": "itemsPerPage", "page_size": 200,
  "current_page_path": "shortUrls.pagination.currentPage",
  "total_pages_path": "shortUrls.pagination.pagesCount",
  "formats": ["csv", "json"], "task": { "mode": "required", "poll_interval_seconds": 2.0 } }

// OpenAPI-derived ([openapi] extra) — generalises Shlink's tool_mapper
{ "source": "openapi",
  "spec": { "source": "file:///app/openapi/shlink.json", "timeout": 30 },
  "normalize": { "strip_path_prefix": "/rest/v{version}" },
  "route_maps": [ { "pattern": "^/health$", "type": "resource" },
                  { "pattern": "^/rules", "type": "exclude" } ],
  "name_overrides": { "POST /short-urls": "create_short_url" },
  "descriptions": { "create_short_url": "Create a new short URL ..." },
  "annotations": "by_http_method" }
```

Mixing sources (the **Tier 2** pattern — an OpenAPI surface plus a couple of
hand-written tools):

```jsonc
"tools": [
  { "source": "openapi", "spec": { "source": "${env:API_OPENAPI_URL}" } },
  { "source": "python",  "register": "my_tools:register_extras" }
]
```

`annotations: "by_http_method"` applies MCP safety hints (GET = read-only;
POST/PUT/PATCH/DELETE = destructive) so clients can gate auto-run. The `python`
register callable receives `(mcp, ctx)`, may be sync or async, and returns the
count of tools it registered.

## :material-sign-direction:  `routes`

```jsonc
"routes": { "healthz": true, "logo": true, "index": true }
```

`healthz` is always mountable (no auth, for liveness probes). `logo`/`index` are
served only when the server passes a `static_dir` to `build_app_from_profile` /
`make_cli`.

## :material-puzzle:  `extensions`

Layer declarative prompts + resources on top of the tool surface (the loader is
pure core — no extra required). Points at a catalogue JSON:

```jsonc
"extensions": { "source": "file:///app/extensions/shlink.json", "required": false }
```

`required: true` makes a load failure fatal; `false` logs and continues.

## :material-account-key:  `access_control`

A coarse role/claim gate on every authenticated request (added after auth):

```jsonc
"access_control": { "roles_claim": "roles" }
```

Presence activates the gate; the allowlist + audit toggle are env-tunable via
`MCP_ALLOWED_ROLES` (CSV) and `MCP_ROLE_CHECK_AUDIT_ONLY`. Roles come from the
verified token's `roles_claim` (a list of strings or `{"name": ...}` objects,
case-insensitive). A present-but-non-matching role is denied (or audit-logged +
passed); an **absent** claim passes (a mode that carries no roles defers to the
upstream); an empty allowlist disables the gate. See [security model](security.md).

## :material-lightning-bolt:  `cache`

Response-freshness hints a caching client may honour instead of making another
round trip (FastMCP 4, SEP-2549):

```jsonc
"cache": { "ttl": 300, "scope": "public" }
```

`ttl` is in seconds (1–86400, required). FastMCP applies the hint to the results
the protocol treats as cacheable — `tools/list`, `prompts/list`,
`resources/list`, `resources/templates/list`, `server/discover` and
`resources/read`. Tool **calls** are never cached, so a tool always executes.
That makes the block worth setting on a server whose catalogue is stable and
whose clients re-list often, and on config-driven resources, whose reads go
through `resources/read`.

!!! danger "`scope` is the security-relevant half"
    `"public"` permits a **shared** cache — a proxy, a fleet-wide store — to hold
    the entry, so a result derived from one caller's identity or permissions
    could be served to another. The default is `"private"`; use `"public"` only
    for responses that are identical for every caller, such as a read-only
    reference catalogue. The hint says how *stale* an answer may be, never *who*
    may read it — it is not an authorization boundary.

## :material-file-document-check:  A complete annotated profile

```jsonc
{
  "$schema": "https://raw.githubusercontent.com/bauer-group/LIB-BG-MCPCore/main/src/bg_mcpcore/profile/schema.json",
  "id": "shlink",
  "display_name": "BAUER GROUP URL Shortener",
  "instructions": "Create and analyse short URLs via the Shlink REST API.",
  "backend": { "base_url": "${env:SHLINK_URL}", "api_base_path": "/rest/v3" },
  "auth": {
    "inbound":  { "mode": "oidc" },
    "outbound": { "type": "static_header", "header": "X-Api-Key", "value_from_env": "SHLINK_API_KEY" }
  },
  "tools": {
    "source": "openapi",
    "spec": { "source": "${env:SHLINK_OPENAPI_URL}" },
    "route_maps": [ { "pattern": "^/rest/health$", "type": "resource" } ],
    "name_overrides": { "POST /short-urls": "create_short_url" },
    "annotations": "by_http_method"
  },
  "routes": { "healthz": true, "logo": true, "index": true }
}
```

See [the three tiers](tiers.md) for when each shape applies, and
[usage](usage.md) for the settings that pair with a profile.
