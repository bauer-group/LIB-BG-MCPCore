# Profile reference

A profile is a JSON document validated against `mcp-profile/v1` (the schema is
shipped at `bg_mcpcore/profile/schema.json`). Strings may interpolate
`${env:VAR}` (fail-closed if the variable is unset). Secrets are referenced by
env-var name, never inlined.

## Top-level fields

| Field | Type | Notes |
|---|---|---|
| `id` | string (required) | server id / log + namespace prefix |
| `display_name` | string (required) | profile-level name |
| `instructions` | string | MCP server instructions for the LLM |
| `icon_url`, `website_url` | string | consent-screen branding (settings override) |
| `backend` | object | upstream connection (omit for registry-only servers) |
| `auth` | object | `inbound` + `outbound` |
| `tools` | object or list | one or more tool sources |
| `routes` | object | toggles for `healthz` / `logo` / `index` |

## `backend`

```jsonc
"backend": {
  "base_url": "${env:SHLINK_URL}",
  "api_base_path": "/rest/v3",   // appended to base_url
  "http_timeout": 30,
  "verify_tls": true,
  "user_agent": "bg-mcpcore"
}
```

## `auth`

```jsonc
"auth": {
  "inbound":  { "mode": "oidc" },           // advisory; AUTH_MODE (env) is authoritative
  "outbound": { "type": "static_header", "header": "X-Api-Key", "value_from_env": "SHLINK_API_KEY" }
}
```

Outbound `type`: `none` · `static_header` (needs `header` + `value_from_env`) ·
`bearer_env` (needs `value_from_env`) · `python` (needs `resolver` dotted path) ·
or any plugin-registered resolver.

## `tools`

A single source or a list (multi-mount). Built-in sources:

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

`annotations: "by_http_method"` applies MCP safety hints (GET = read-only;
POST/PUT/PATCH/DELETE = destructive) so clients can gate auto-run.

## `routes`

```jsonc
"routes": { "healthz": true, "logo": true, "index": true }
```

`logo`/`index` are served only when the server passes a `static_dir` to
`build_app_from_profile` / `make_cli`.
