# Security model

bg-mcpcore enforces invariants that every downstream server inherits and cannot
relax. They were shaped by an adversarial security review during the design.

## Fail-closed auth (core-enforced)

`BaseMcpSettings` runs these BEFORE a subclass's per-mode checks:

- **`AUTH_MODE=none` is forbidden in production** (`ENVIRONMENT=production`).
- **`AUTH_JWT_SIGNING_KEY` is required** (and must not be a `CHANGE_ME`
  placeholder) for any active auth mode.
- **`AUTH_REDIS_URL` requires a valid Fernet `AUTH_STORAGE_ENCRYPTION_KEY`** — no
  plaintext OAuth state at rest.

A subclass adds per-mode credential checks via `validate_provider_auth()`; it
cannot remove the above.

## Closed-set auth modes

`build_auth_provider` raises on an unknown `AUTH_MODE` rather than silently
serving an unauthenticated endpoint. New modes are added by registering an
entry-point plugin, not by accepting arbitrary strings.

## Secrets never live in profiles

Profiles reference secrets by env-var name (`value_from_env`) or interpolate
non-secret config (`${env:VAR}`). The loader fails closed if a referenced
variable is unset, and credentials are never pulled into the parsed profile
object.

## Encrypted OAuth state at rest

DCR/token state is Fernet-encrypted (Redis or disk backend). The disk key is
derived from `AUTH_JWT_SIGNING_KEY` via HKDF with a salt that is **preserved by
default** so deployed state stays decryptable. A per-service salt is available
for a deliberate, signed-off crypto cutover. Redis mode **warns** when the
storage key reuses the JWT signing key — use a dedicated
`AUTH_STORAGE_ENCRYPTION_KEY`.

## Outbound auth is fail-closed

The `AuthHeaderSource` contract splits static credentials (`default_headers()`,
applied once at client construction) from per-call credentials
(`auth_headers(ctx)`). The two are mutually exclusive: a per-call (on-behalf-of)
resolver that cannot produce a credential **raises** rather than letting the
request inherit a static default. The credential-bearing client is not exposed
to spec-driven providers as a public attribute.

## Least-privilege tool context

Spec-driven / registry tool sources receive a capability-scoped `ToolContext`
(an authenticated `client` + logger), never the full settings object that holds
`SecretStr` fields. Only the `python` escape hatch — the server's own trusted
code — receives `settings`.

## Log redaction

A structured-logging processor masks values under sensitive-looking keys
(token, secret, authorization, x-api-key, …). Servers extend the fragment list
additively via `setup_logging(extra_sensitive_fragments=...)` for backend-specific
secret field names.

## FastMCP-version coupling

The core pins FastMCP for the fleet and binds to a few private FastMCP symbols
(e.g. `derive_jwt_key`). A security regression test guards the storage
key-derivation invariant so a FastMCP bump that changes it fails loudly.
Reporting: see [SECURITY.MD](https://github.com/bauer-group/LIB-BG-MCPCore/blob/main/SECURITY.MD).
