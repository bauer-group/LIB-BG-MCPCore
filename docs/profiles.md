---
icon: material/file-cog
---

# Profile reference

A profile is a JSON document validated against `mcp-profile/v1` (the schema is
shipped at `bg_mcpcore/profile/schema.json`). It describes **structure**, never
secrets: strings interpolate `${env:VAR}` (fail-closed if the variable is unset)
and outbound credentials are referenced by env-var name, never inlined.

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
| `python` | `resolver` (dotted `module:attr`) | a custom `AuthHeaderSource` (per-user OBO, signed headers) |
| *(plugin)* | per resolver | any `bg_mcpcore.auth_resolvers` entry point |

`value_from_env` names the env var holding the secret (resolved fail-closed at
boot); use `value` only for non-secret literals. A resolver splits credentials
into **static** `default_headers()` (applied once at client construction — this
also covers the bare httpx client the OpenAPI source drives) and **per-call**
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

## :material-file-document-check:  A complete annotated profile

```jsonc
{
  "$schema": "https://schemas.bauer-group.com/mcp-profile/v1.json",
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
