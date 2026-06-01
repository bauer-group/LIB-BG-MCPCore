# AGENTS.md — building MCP↔API servers with bg-mcpcore

Instructions for an AI agent (or a human in a hurry) tasked with **building a new
MCP server that bridges a REST API**, using this shared framework. Read this
first; it links to the deep docs under [`docs/`](docs/) for detail.

## What bg-mcpcore is — and the one principle

A framework for secure, OAuth-gated MCP servers on FastMCP. **Config for the
standard, code for the complex.** A server is a declarative JSON *profile*; the
genuinely-divergent parts drop to small Python *escape hatches* the profile
points at. Everything cross-cutting — inbound OAuth (OIDC/Entra/Google + more),
encrypted OAuth-state storage, rate limiting, PII-redacting logs, the `/healthz`
and branded `/` + `/logo.svg` routes, the retrying HTTP client, dual-stack
binding — is provided in **every** tier. **Never re-implement it.**

## The fast path — scaffold, don't hand-roll

```bash
bg-mcpcore new <slug>          # e.g. bg-mcpcore new mautic
```

Generates a runnable Tier-1 server: profile, 4-line `main.py`, a `Settings`
subclass, the full BAUER GROUP landing page + icon, `.env.example`, a smoke
test, and packaging pinned to the current bg-mcpcore. Then:

1. Point the profile's `tools.spec.source` at the backend's OpenAPI document.
2. Set `backend.base_url` / `api_base_path` and the outbound auth.
3. Shape the tool surface declaratively (overrides below).
4. `pip install -e ".[test]" && pytest -q && python src/main.py`.

Do **not** write a server from scratch, copy another server's tree, or
re-implement auth/storage/logging — scaffold and fill in.

## Pick the lowest tier that fits (see [docs/tiers.md](docs/tiers.md))

```text
Does the backend ship a usable OpenAPI spec?
├─ yes → need a few bespoke tools or a custom outbound credential?
│        ├─ no  → TIER 1  pure config (profile only)
│        └─ yes → TIER 2  config + a little Python (multi-source tools)
└─ no  ─────────→ TIER 3  mostly Python (hand-written tools + a resolver)
```

Tiers mix: one profile can combine an `openapi` source with a `python` source.

## Profile cheat-sheet (full reference: [docs/profiles.md](docs/profiles.md))

```jsonc
{
  "$schema": "https://raw.githubusercontent.com/bauer-group/LIB-BG-MCPCore/main/src/bg_mcpcore/profile/schema.json",
  "id": "mautic",
  "display_name": "BAUER GROUP Mautic",          // also the consent-screen name
  "instructions": "What the AI should know about this server.",
  "backend": {
    "base_url": "${env:MAUTIC_URL}",              // env interpolation, fail-closed
    "api_base_path": "/api"                        // appended to every call
  },
  "auth": {
    "inbound":  { "mode": "oidc" },               // ADVISORY — AUTH_MODE (env) is authoritative
    "outbound": { "type": "bearer_env", "value_from_env": "MAUTIC_TOKEN" }
  },
  "tools": {                                       // object OR array (multi-source)
    "source": "openapi",
    "spec": { "source": "${env:MAUTIC_OPENAPI_URL:-file:///app/openapi/mautic.json}" },
    "route_maps":     [{ "pattern": "^/health$", "type": "resource" }],
    "name_overrides": { "POST /contacts": "create_contact" },
    "descriptions":   { "list_contacts": "Better summary than the spec's." },
    "normalize":      { "strip_path_prefix": "/api/v{version}" },
    "annotations": "by_http_method"
  },
  "extensions": { "source": "file:///app/extensions/extensions.json" },  // prompts + resources
  "routes": { "healthz": true, "logo": true, "index": true }
}
```

Rules:

- **Env interpolation:** `${env:VAR}` (fail-closed if unset) or
  `${env:VAR:-default}` (default when unset/empty, override still wins). Use the
  default form for documented-but-optional knobs (spec source, extensions path).
- **Secrets never inline.** Outbound credentials are referenced by env-var name
  (`value_from_env`); they never enter the parsed profile.
- **Inbound `mode` is advisory** — the live mode is the `AUTH_MODE` env var,
  validated by `BaseMcpSettings`. The provider is resolved from it.

## Outbound auth (`auth.outbound.type`)

| type | use |
|---|---|
| `none` | upstream needs no auth |
| `static_header` | a fixed header, e.g. `X-Api-Key` (`header` + `value_from_env`) |
| `bearer_env` | `Authorization: Bearer <token>` from an env var |
| `python` | escape hatch: `resolver: "module:factory"` returning an `AuthHeaderSource` |

A per-call resolver MUST raise when it cannot produce a credential — never fall
back to a static default silently (fail-closed; see [docs/security.md](docs/security.md)).

## Escape hatches (when config is not enough)

- **Bespoke tools** → `tools: { "source": "python", "register": "server:register" }`;
  the dotted callable is `def register(mcp, ctx) -> int` (it gets a settings-bearing
  `ToolContext`; OpenAPI/registry sources get a settings-less one — least privilege).
- **Custom outbound credential** → `auth.outbound.type: "python"`.
- **Reusable central tools** → `tools: { "source": "registry", "include": ["bg.ping", …] }`.

## Extend without editing core (plugins — [docs/plugins.md](docs/plugins.md))

New capabilities are pip-installable, registered via entry-point groups — never a
core edit: `bg_mcpcore.tool_sources` (e.g. the built-in `openapi`),
`bg_mcpcore.auth_providers` (`entra-single`/`google`/…), `bg_mcpcore.auth_resolvers`,
`bg_mcpcore.auth_middleware`, `bg_mcpcore.tools` (registry). See
[`examples/example_plugin`](examples/example_plugin).

Compose several backends behind one endpoint with `build_gateway` —
[`examples/gateway_server`](examples/gateway_server).

## Security invariants — NON-NEGOTIABLE (never weaken)

1. **Fail-closed auth.** `AUTH_MODE=none` is rejected in production; an active
   mode requires the JWT signing key. `auth_mode` is a closed set — unknown → error.
2. **Secrets via env only.** Never inline a secret in a profile; never log one.
3. **Outbound never silently falls back.** A per-call resolver raises rather than
   inheriting a static default.
4. **Least privilege.** Only the `python` escape hatch receives settings (with
   secrets); OpenAPI/registry/third-party sources do not.
5. **Redis OAuth-state requires an encryption key** (no plaintext at rest).

These live in `BaseMcpSettings` + the assembler and cannot be switched off by a
profile. If a change would relax any of them, stop and ask.

## Verify + ship

- `pytest -q` (the scaffold ships a smoke test; add tests for any Python you write).
- `ruff check` + `mypy` clean.
- The Docker build is **test-gated** — a red test fails the image build.
- Commit per BAUER GROUP conventions: Conventional Commits, English, past-tense
  subject, a body explaining *what + why*; no AI attribution. Internal servers
  pin bg-mcpcore from its **GitHub tag**, never PyPI.

## Where to look

| Need | Doc |
|---|---|
| Tier decision + worked examples | [docs/tiers.md](docs/tiers.md) |
| Every profile field | [docs/profiles.md](docs/profiles.md) |
| Inbound auth modes + setup | [docs/authentication.md](docs/authentication.md) |
| Prompts + resources catalogue | [docs/extensions.md](docs/extensions.md) |
| Writing a plugin | [docs/plugins.md](docs/plugins.md) |
| Security model | [docs/security.md](docs/security.md) |
| Runnable examples (one per tier) | [`examples/`](examples/) |

Reference implementations: **bg-shlink-mcp** (Tier-1, production) and
**bg-zammad-mcp** (Tier-3, hand-written tools + per-user on-behalf-of auth).
