# Authentication

Authentication in bg-mcpcore has two independent, orthogonal halves. Keeping
them separate is deliberate — the question "who may call this MCP server?" and
the question "how does this server prove itself to the upstream REST API?" have
different answers, different config sources, and different failure modes.

| Direction | Question | Mechanism | Config source |
|---|---|---|---|
| **Inbound** | Who may call this MCP server? | `AUTH_MODE` → a FastMCP auth provider that validates the caller's token | `settings`/env (`AUTH_*`, `OIDC_*`, `ENTRA_*`, `GOOGLE_*`) **or** the profile's `auth.inbound.config` (spec-driven providers) |
| **Outbound** | How does the server authenticate to the upstream API? | `auth.outbound.type` → an `AuthHeaderSource` resolver | the profile's `auth.outbound` block; secrets via `value_from_env` |

The inbound token is **never** forwarded upstream automatically. Even when both
halves use OAuth, they are wired separately: inbound establishes the caller's
identity; outbound is resolved independently by a resolver. The only way the
caller's identity reaches the upstream API is an explicit on-behalf-of resolver
(see [Outbound](#outbound-authenticating-to-the-upstream-api)).

!!! abstract "Where this fits"
    Inbound auth lives in [the three tiers](tiers.md) at the framework layer —
    you pick a mode, not write a verifier. Outbound auth is the one
    load-bearing per-server divergence. The full threat model and the
    invariants summarised below are in the [security model](security.md).

## Fail-closed invariants

These hold for **every** server and cannot be relaxed by a subclass. They run in
`BaseMcpSettings` *before* any per-mode credential check (`validate_provider_auth`),
so a server cannot accidentally weaken them.

!!! danger "Core-enforced, non-negotiable"
    - **`AUTH_MODE=none` is forbidden in production.** With
      `ENVIRONMENT=production`, booting unauthenticated raises at startup. Set
      `ENVIRONMENT=development` if running open is genuinely intentional.
    - **`AUTH_JWT_SIGNING_KEY` is required for any active (non-`none`) mode** and
      must not be a `CHANGE_ME` placeholder (the check strips whitespace and is
      case-insensitive). FastMCP-issued JWTs are signed with it, and the disk
      OAuth-state encryption key is derived from it.
    - **`AUTH_REDIS_URL` requires a valid Fernet `AUTH_STORAGE_ENCRYPTION_KEY`** —
      no plaintext OAuth state at rest.

A second guardrail lives in the inbound provider registry: `build_auth_provider`
enforces a **closed set** of modes. An unknown `AUTH_MODE` raises
`ProfileError` (listing the known modes) rather than silently booting an
unauthenticated endpoint. New modes are added by registering an entry-point
plugin — never by accepting an arbitrary string.

See the [security model](security.md) for the complete reasoning behind these.

## Inbound: who may call this server

`AUTH_MODE` (env, snake_case maps 1:1 to the `auth_mode` field) selects one
registered provider. The full catalogue:

| `AUTH_MODE` | Provider | Config source | Notes |
|---|---|---|---|
| `none` | *(unauthenticated)* | — | Forbidden in production |
| `oidc` | `OIDCProxy` / `OAuthProxy` | `settings`/env (`OIDC_*`) | Core built-in; any standard-OIDC IdP |
| `entra-single` | `AzureProvider` | `settings`/env (`ENTRA_*`) | One tenant (`[oauth-providers]`) |
| `entra-multi` | `AzureProvider` + tenant gate | `settings`/env (`ENTRA_*`) | Multi-tenant; needs allowlist (`[oauth-providers]`) |
| `google` | `GoogleProvider` | `settings`/env (`GOOGLE_*`) | Hosted-domain allowlist (`[oauth-providers]`) |
| `auth0` | `Auth0Provider` | profile `auth.inbound.config` | Spec-driven |
| `aws-cognito` | `AWSCognitoProvider` | profile `auth.inbound.config` | Spec-driven |
| `clerk` | `ClerkProvider` | profile `auth.inbound.config` | Spec-driven |
| `descope` | `DescopeProvider` | profile `auth.inbound.config` | Spec-driven |
| `discord` | `DiscordProvider` | profile `auth.inbound.config` | Spec-driven |
| `github` | `GitHubProvider` | profile `auth.inbound.config` | Spec-driven |
| `keycloak` | `KeycloakAuthProvider` | profile `auth.inbound.config` | Spec-driven |
| `oci` | `OCIProvider` | profile `auth.inbound.config` | Spec-driven |
| `propelauth` | `PropelAuthProvider` | profile `auth.inbound.config` | Spec-driven |
| `scalekit` | `ScalekitProvider` | profile `auth.inbound.config` | Spec-driven |
| `supabase` | `SupabaseProvider` | profile `auth.inbound.config` | Spec-driven |
| `workos` | `WorkOSProvider` | profile `auth.inbound.config` | Spec-driven |

The above is the *complete* registered list. `none` and `oidc` are core
built-ins; everything else is registered via the `bg_mcpcore.auth_providers`
entry-point group and ships in the `[oauth-providers]` extra. Three config
delivery styles are in play:

- **`oidc`, `entra-*`, `google`** read **cross-cutting, env-driven** settings off
  the server's `Settings` object. The profile's `mode` field is advisory; the
  authoritative mode is always `AUTH_MODE`.
- **The 12 spec-driven providers** read the profile's `auth.inbound.config`
  block, with secrets named by a `<key>_env` indirection (below).

!!! note "The profile `mode` is advisory"
    `auth.inbound.mode` documents intent and may differ from the live
    `AUTH_MODE`. The env var wins — it is held and validated by
    `BaseMcpSettings`. The profile's `auth.inbound.config` is the only part of
    the inbound block that carries operative values (and only for the
    spec-driven providers).

### Secrets are referenced by env-var name, never inlined

For spec-driven providers, any field marked secret is **not** read from the
profile directly. Instead the profile carries a `<key>_env` key naming an env
var, and the builder resolves it from `os.environ` at build time — so the secret
never lands in the parsed profile object. A field named `client_secret` is
supplied as `"client_secret_env": "AUTH0_CLIENT_SECRET"`, not as a literal
value.

Non-secret config values may use the profile loader's `${env:VAR}`
interpolation; secrets must use the `<key>_env` indirection.

### `oidc` — any standard-OIDC IdP

The core `oidc` mode wraps FastMCP's `OIDCProxy` (preferred) or `OAuthProxy`
(fallback). It works with anything that speaks standard OIDC — Authentik,
Keycloak, Zitadel, Auth0, Okta, Cognito, Microsoft Entra ID, Google Workspace,
and so on. Configuration is entirely env-driven via the `OIDC_*` settings:

| Env var | Field | Default | Role |
|---|---|---|---|
| `OIDC_CLIENT_ID` | `oidc_client_id` | — | **Required** (both paths) |
| `OIDC_CLIENT_SECRET` | `oidc_client_secret` | — | **Required** (both paths) |
| `OIDC_DISCOVERY_URL` | `oidc_discovery_url` | unset | Selects the discovery path when set |
| `OIDC_ISSUER` | `oidc_issuer` | unset | **Required** in explicit mode; optional override in discovery mode |
| `OIDC_AUTH_URI` | `oidc_auth_uri` | unset | Explicit mode: authorization endpoint |
| `OIDC_TOKEN_URI` | `oidc_token_uri` | unset | Explicit mode: token endpoint |
| `OIDC_JWKS_URI` | `oidc_jwks_uri` | unset | Explicit mode: JWKS endpoint |
| `OIDC_SCOPES` | `oidc_scopes` | `openid profile email` | Space-separated required scopes |
| `OIDC_USERNAME_CLAIM` | `oidc_username_claim` | `preferred_username` | Claim used as the username |

The mode chooses between two paths based on whether a discovery URL is set:

=== "Discovery (recommended)"

    Set `OIDC_DISCOVERY_URL` and the provider uses **`OIDCProxy`**: it
    auto-discovers all endpoints, picks up JWKS rotations, and reads the issuer
    from IdP metadata. The discovery document is validated **at boot** (it must
    expose `authorization_endpoint`, `token_endpoint`, `jwks_uri`, and `issuer`),
    so a misconfigured URL fails at startup rather than on the first login.

    ```bash
    AUTH_MODE=oidc
    OIDC_DISCOVERY_URL=https://idp.example.com/.well-known/openid-configuration
    OIDC_CLIENT_ID=mcp-server
    OIDC_CLIENT_SECRET=...                 # via secret manager
    OIDC_SCOPES="openid profile email"
    # OIDC_ISSUER optional here — taken from metadata unless you override it
    ```

=== "Explicit endpoints"

    For IdPs without a discovery document, set all three of `OIDC_AUTH_URI`,
    `OIDC_TOKEN_URI`, and `OIDC_JWKS_URI`; the provider falls back to the
    lower-level **`OAuthProxy`** with a `JWTVerifier`.

    ```bash
    AUTH_MODE=oidc
    OIDC_AUTH_URI=https://idp.example.com/oauth/authorize
    OIDC_TOKEN_URI=https://idp.example.com/oauth/token
    OIDC_JWKS_URI=https://idp.example.com/oauth/jwks
    OIDC_ISSUER=https://idp.example.com/realms/main   # REQUIRED
    OIDC_CLIENT_ID=mcp-server
    OIDC_CLIENT_SECRET=...
    ```

    !!! warning "Explicit mode requires `OIDC_ISSUER`"
        The issuer must match the token's `iss` claim exactly, and it **cannot
        be derived** from `OIDC_AUTH_URI` (a Keycloak authorize endpoint, for
        example, sits several path segments below the issuer). Omitting
        `OIDC_ISSUER` in explicit mode raises at boot rather than minting a
        verifier that silently rejects every token. The discovery path does not
        have this requirement — it reads the issuer from the IdP's metadata.

### `entra-single` / `entra-multi` — Microsoft Entra ID

Both modes use FastMCP's `AzureProvider`, configured from `ENTRA_*` settings on
the server's `Settings` subclass:

| Setting | Type | Role |
|---|---|---|
| `entra_client_id` | `str` | **Required** — app registration client ID |
| `entra_client_secret` | `SecretStr` | **Required** — client secret |
| `entra_tenant_id` | `str` | **Required** — tenant ID, or `common`/`organizations`/`consumers` for multi |
| `entra_api_scopes` | `list[str]` | **Required, non-empty** — custom API scope(s) from "Expose an API" (e.g. `access_as_user`) |
| `entra_extra_scopes` | `list[str]` | Additional authorize-time scopes |
| `entra_allowed_tenants` | `list[str]` | `tid`-claim allowlist (multi-tenant gate) |

The OIDC scopes `openid`, `profile`, `email` are always added at authorization
time (so the consent screen lists them) on top of `entra_api_scopes` and
`entra_extra_scopes`. `entra_api_scopes` must contain **at least one** custom API
scope or the provider raises — Microsoft's OIDC scopes never appear in the access
token's `scp` claim and therefore cannot be validated.

```bash
# Single-tenant: bound to one tenant, no allowlist needed.
AUTH_MODE=entra-single
ENTRA_CLIENT_ID=00000000-0000-0000-0000-000000000000
ENTRA_CLIENT_SECRET=...
ENTRA_TENANT_ID=11111111-1111-1111-1111-111111111111
ENTRA_API_SCOPES=access_as_user
```

```bash
# Multi-tenant: validates against Microsoft's multi-tenant JWKS, then gates tid.
AUTH_MODE=entra-multi
ENTRA_CLIENT_ID=00000000-0000-0000-0000-000000000000
ENTRA_CLIENT_SECRET=...
ENTRA_TENANT_ID=organizations
ENTRA_API_SCOPES=access_as_user
ENTRA_ALLOWED_TENANTS=11111111-1111-1111-1111-111111111111,22222222-2222-2222-2222-222222222222
```

!!! warning "`entra-multi` with no allowlist accepts every tenant"
    `AzureProvider` validates a token's **signature** against Microsoft's
    multi-tenant JWKS but does **not** by itself check **which** tenant issued
    it. That gate is the `tid`-claim allowlist, applied by the `entra-multi`
    auth middleware (wired config-driven via the `bg_mcpcore.auth_middleware`
    entry point; the middleware is only attached when `entra_allowed_tenants`
    is non-empty).

    With `entra_allowed_tenants` **empty**, tokens from *any* Entra tenant on
    earth are accepted. This is a deliberate "public multi-tenant app" option,
    so the server still boots — but it prints a **loud boot warning**
    (`WARNING: AUTH_MODE=entra-multi with no ENTRA_ALLOWED_TENANTS`) so it is
    never shipped unknowingly. Set `ENTRA_ALLOWED_TENANTS` to restrict access to
    your own tenant(s).

    Additionally, `entra-multi` with a *specific* `ENTRA_TENANT_ID` (not
    `common`/`organizations`/`consumers`) logs a hint, since that combination is
    usually a misconfiguration.

`entra-single` is bound to a single `ENTRA_TENANT_ID` and needs no allowlist.

### `google` — Google Workspace

FastMCP's `GoogleProvider`, configured from `GOOGLE_*` settings. The provider
handles the hosted-domain allowlist itself via `allowed_domains`.

| Setting | Type | Role |
|---|---|---|
| `google_client_id` | `str` | **Required** |
| `google_client_secret` | `SecretStr` | **Required** |
| `google_allowed_domains` | `list[str]` | Hosted-domain (`hd`) allowlist; omit to allow any Google account |

The required scopes are fixed to `openid`, `email`, `profile`.

```bash
AUTH_MODE=google
GOOGLE_CLIENT_ID=...apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=...
GOOGLE_ALLOWED_DOMAINS=bauer-group.com
```

### The 12 spec-driven providers

Each is described by a small declarative spec (its FastMCP class plus the
`auth.inbound.config` keys that map to constructor kwargs) and assembled by one
generic builder. `base_url` always comes from `public_base_url` (settings); a
`required_scopes` key in `config` is passed through if present. Two families:

- **DCR / OAuthProxy-style** providers also receive `client_storage` and
  `jwt_signing_key` from settings (marked **needs storage** below): `auth0`,
  `aws-cognito`, `clerk`, `discord`, `github`, `oci`, `workos`.
- **Token-verifier-style** providers validate externally-issued tokens and take
  **no** `client_storage`: `descope`, `keycloak`, `propelauth`, `scalekit`,
  `supabase`.

Required keys raise `ProfileError` if missing. Secret keys are supplied via the
`<key>_env` indirection; all others are plain `config` values (which may use
`${env:VAR}` interpolation).

| `AUTH_MODE` | Required config keys | Optional config keys | Secret (`<key>_env`) | Needs storage |
|---|---|---|---|---|
| `auth0` | `config_url`, `client_id`, `audience` | — | `client_secret` | Yes |
| `aws-cognito` | `user_pool_id`, `client_id` | `aws_region` | `client_secret` | Yes |
| `clerk` | `domain`, `client_id` | — | `client_secret` *(optional)* | Yes |
| `discord` | `client_id` | — | `client_secret` | Yes |
| `github` | `client_id` | — | `client_secret` | Yes |
| `oci` | `config_url`, `client_id` | `audience` | `client_secret` | Yes |
| `workos` | `client_id`, `authkit_domain` | — | `client_secret` | Yes |
| `keycloak` | `realm_url` | `audience` | — | No |
| `descope` | *(see note)* | `config_url`, `project_id`, `descope_base_url` | — | No |
| `propelauth` | `auth_url`, `introspection_client_id` | — | `introspection_client_secret` | No |
| `scalekit` | `environment_url`, `resource_id` | `client_id` | — | No |
| `supabase` | `project_url` | — | — | No |

!!! note "Descope requires one of two combinations"
    All three Descope keys are *optional* at the framework layer because
    `DescopeProvider` requires **either** `config_url` (new API) **or both**
    `project_id` + `descope_base_url` (legacy API). The provider itself
    validates the combination and raises a clear error if none is supplied.

Per-provider profile examples — `client_id`/`config_url`/etc. are non-secret
profile values; the `client_secret` is referenced by env-var name:

=== "Auth0"

    ```jsonc
    "auth": {
      "inbound": {
        "mode": "auth0",                          // advisory; AUTH_MODE=auth0 is authoritative
        "config": {
          "config_url": "https://tenant.eu.auth0.com",
          "client_id": "abc123",
          "audience": "https://mcp.example.com/api",
          "client_secret_env": "AUTH0_CLIENT_SECRET"
        }
      }
    }
    ```

=== "GitHub"

    ```jsonc
    "auth": {
      "inbound": {
        "mode": "github",
        "config": {
          "client_id": "Iv1.abc123",
          "client_secret_env": "GITHUB_CLIENT_SECRET"
        }
      }
    }
    ```

=== "Keycloak"

    ```jsonc
    // Token-verifier style: no client_storage, no secret.
    "auth": {
      "inbound": {
        "mode": "keycloak",
        "config": {
          "realm_url": "https://idp.example.com/realms/main",
          "audience": "mcp-server"
        }
      }
    }
    ```

=== "AWS Cognito"

    ```jsonc
    "auth": {
      "inbound": {
        "mode": "aws-cognito",
        "config": {
          "user_pool_id": "eu-central-1_AbCdEf",
          "client_id": "1example23client45id",
          "aws_region": "eu-central-1",
          "client_secret_env": "COGNITO_CLIENT_SECRET"
        }
      }
    }
    ```

=== "Supabase"

    ```jsonc
    // Single required key, no secret, no storage.
    "auth": {
      "inbound": {
        "mode": "supabase",
        "config": { "project_url": "https://abcdefgh.supabase.co" }
      }
    }
    ```

=== "WorkOS"

    ```jsonc
    "auth": {
      "inbound": {
        "mode": "workos",
        "config": {
          "client_id": "client_01ABC",
          "authkit_domain": "https://your-app.authkit.app",
          "client_secret_env": "WORKOS_CLIENT_SECRET"
        }
      }
    }
    ```

## Outbound: authenticating to the upstream API

The outbound resolver is how the MCP server presents itself to the REST API it
fronts. It is selected by `auth.outbound.type` in the profile and implements the
`AuthHeaderSource` protocol — two **mutually-exclusive** halves:

- **`default_headers()`** — STATIC credentials applied **once** at
  `AsyncClient` construction. Used by gateway-style servers where one shared
  service credential covers all callers (e.g. Shlink's `X-Api-Key`). These also
  cover FastMCP's bare-httpx-client path used by the OpenAPI tool source.
- **`auth_headers(ctx)`** — PER-CALL dynamic credentials resolved from the
  request context (e.g. a per-user bearer for on-behalf-of).

!!! danger "The fail-closed contract"
    The two halves are mutually exclusive. A static resolver returns `{}` from
    `auth_headers`, and a per-call resolver returns `{}` from
    `default_headers`. Critically, a **per-call resolver that cannot produce a
    credential MUST raise** rather than returning `{}` — otherwise the request
    would silently inherit a static default and defeat the fail-closed model.
    This is the entire point of an on-behalf-of resolver: no token, no request.

| `type` | Resolver | Required keys | Behaviour |
|---|---|---|---|
| `none` | `NoAuthResolver` | — | No outbound auth; both halves return `{}` |
| `static_header` | `StaticHeaderResolver` | `header` + (`value_from_env` \| `value`) | Static custom header at construction |
| `bearer_env` | `BearerEnvResolver` | `value_from_env` \| `value` | Static `Authorization: Bearer <token>` |
| `python` | *(your class)* | `resolver` (dotted `module:attr`) | Custom resolver, including per-call OBO |
| *(plugin)* | via `bg_mcpcore.auth_resolvers` | per plugin | Third-party resolver type |

For `static_header` and `bearer_env`, the secret is read from
`value_from_env` (an env-var name) at build time; an inline `value` is also
accepted but `value_from_env` is the secure default. If `value_from_env` names an
unset variable, the build raises `ProfileError`. Unknown `type` values raise
(listing the known types) — the same closed-set discipline as inbound.

=== "none"

    ```jsonc
    "auth": { "outbound": { "type": "none" } }
    ```

=== "static_header (Shlink)"

    The Shlink gateway shape — a fixed `X-Api-Key` applied at client
    construction, sourced from an env var:

    ```jsonc
    "auth": {
      "outbound": {
        "type": "static_header",
        "header": "X-Api-Key",
        "value_from_env": "SHLINK_API_KEY"
      }
    }
    ```

=== "bearer_env"

    A static bearer token, e.g. for a service account:

    ```jsonc
    "auth": {
      "outbound": {
        "type": "bearer_env",
        "value_from_env": "PETSTORE_TOKEN"
      }
    }
    ```

=== "python (Zammad OBO)"

    The Zammad per-user on-behalf-of shape — each MCP user's own upstream token
    is forwarded per call, never a shared service credential. `default_headers`
    sends nothing static; `auth_headers` resolves the per-user token and
    **raises** when none is available:

    ```jsonc
    "auth": {
      "outbound": {
        "type": "python",
        "resolver": "my_auth:make_resolver"
      }
    }
    ```

    ```python
    # my_auth.py
    from typing import Any


    class OnBehalfOfResolver:
        def default_headers(self) -> dict[str, str]:
            return {}  # never send a static/shared credential

        async def auth_headers(self, ctx: Any | None) -> dict[str, str]:
            token = resolve_user_token(ctx)  # from the validated inbound session
            if not token:
                # FAIL CLOSED: no token -> no request. Returning {} here would
                # let the call fall through unauthenticated.
                raise PermissionError("no upstream token for this user (fail-closed)")
            return {"Authorization": f"Bearer {token}"}


    def make_resolver(cfg: Any) -> OnBehalfOfResolver:
        """Factory referenced by auth.outbound.resolver; receives the OutboundAuthConfig."""
        return OnBehalfOfResolver()
    ```

!!! tip "Why this split exists"
    Outbound auth is the single load-bearing divergence between servers. A
    gateway like Shlink talks to its backend server-to-server with one API key
    (`static_header`); a per-user backend like Zammad must forward each caller's
    own identity (`python` + OBO). The `AuthHeaderSource` contract makes both
    expressible without special-casing either in core, while the fail-closed
    `auth_headers` raise guarantees a per-user server never leaks a shared
    credential.

## Adding a custom inbound provider or resolver

A non-standard or proprietary IdP (opaque tokens, a bespoke OAuth2 flow), or a
custom outbound scheme (e.g. AWS SigV4), is a pip-installable plugin — never a
core edit. Both seams are Python entry points:

```python
# my_pkg/auth.py
def build_my_idp(settings, inbound=None):   # -> a FastMCP auth provider (or None)
    ...

def build_my_resolver(cfg):                 # -> an AuthHeaderSource
    ...
```

```toml
# my_pkg/pyproject.toml
[project.entry-points."bg_mcpcore.auth_providers"]
my-idp = "my_pkg.auth:build_my_idp"

[project.entry-points."bg_mcpcore.auth_resolvers"]
sigv4 = "my_pkg.auth:build_my_resolver"
```

Once installed, `my-idp` becomes a valid `AUTH_MODE` and `sigv4` a valid
`auth.outbound.type` — and both join the closed set the registries enforce. An
inbound provider may also contribute post-auth middleware (as `entra-multi` does
with its tenant gate) via the `bg_mcpcore.auth_middleware` group. See
[plugins](plugins.md) for the full plugin surface and the `ToolContext`
least-privilege rules.

## See also

- [Security model](security.md) — the complete threat model and every invariant
- [Profile reference](profiles.md) — the `auth.inbound` / `auth.outbound` schema
- [Configuration](usage.md) — wiring settings, env vars, and profiles together
- [The three tiers](tiers.md) — where inbound and outbound auth sit in the stack
- [Plugins](plugins.md) — registering custom providers, resolvers, and middleware
