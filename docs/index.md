# bg-mcpcore

Config-driven, pluggable REST-API MCP servers on [FastMCP](https://github.com/jlowin/fastmcp).

bg-mcpcore is the shared foundation for BAUER GROUP's fleet of
[Model Context Protocol](https://modelcontextprotocol.io) servers that bridge
REST APIs. A server is described by a **declarative JSON profile**; the genuinely
complex parts drop down to **Python escape hatches**.

## Why

The first two MCP servers (Zammad, Shlink) duplicated security-sensitive
infrastructure — encrypted OAuth-state storage, PII log redaction, rate
limiting, the OAuth-gated bootstrap — as drifting copies. bg-mcpcore gives that
code one audited, tested home, and turns a new REST-API MCP server into a
~15-line profile plus a 4-line entrypoint.

## Three complexity tiers

Pick the lowest tier that fits your backend — the [tier guide](tiers.md) walks
through each with a full profile + code.

| Tier | When | Effort |
|---|---|---|
| [**1 — pure config**](tiers.md#tier-1-pure-config) | backend ships a usable OpenAPI spec, standard auth | profile JSON only, no Python |
| [**2 — config + a little Python**](tiers.md#tier-2-config-a-little-python) | OpenAPI base + a few hand tools, or a custom resolver | profile + a `type: python` reference |
| [**3 — mostly Python**](tiers.md#tier-3-mostly-python) | no usable spec (e.g. Zammad) | `tools.source: python`; the profile still drives auth, rate-limit, identity, routes |

## Design pillars

- **Modular** — new auth modes / tool sources / resolvers are pip-installable
  plugins registered via Python entry points, never core edits.
- **Configurable** — every standard behaviour is an overridable profile default.
- **Stable** — the mandatory core depends only on fastmcp/pydantic/httpx/
  structlog/cryptography; volatile concerns live in optional extras.
- **Secure** — fail-closed auth invariants are enforced in core and a profile
  cannot switch them off.

## Where to go next

- [Quickstart](quickstart.md) — a running server in five minutes.
- [Usage & configuration](usage.md) — the settings/profile split, every env var,
  running, connecting a client, the request lifecycle.
- [The three tiers](tiers.md) — config vs. code, with a full example per tier.
- [Profile reference](profiles.md) — every field of the profile schema.
- [Writing plugins](plugins.md) — add auth modes, tool sources, resolvers.
- [Security model](security.md) — the fail-closed invariants.

Runnable end-to-end examples for every tier live in
[`examples/`](https://github.com/bauer-group/LIB-BG-MCPCore/tree/main/examples).
