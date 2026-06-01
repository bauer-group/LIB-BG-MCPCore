---
icon: material/home-variant
---

# MCP Core

Config-driven, pluggable REST-API MCP servers on [FastMCP](https://github.com/jlowin/fastmcp).

bg-mcpcore is the shared foundation for BAUER GROUP's fleet of
[Model Context Protocol](https://modelcontextprotocol.io) servers that bridge
REST APIs to AI clients. A server is described by a **declarative JSON profile**;
the genuinely complex parts drop down to small **Python escape hatches**.

!!! quote "The principle"
    **Config for the standard, code for the complex.** Everything most servers
    share — OAuth-gated auth, encrypted state, rate limiting, redacted logging —
    is one audited, tested home. A new REST-API MCP server becomes a ~15-line
    profile plus a 4-line entrypoint.

```python
from bg_mcpcore import load_profile, make_cli

app = make_cli(load_profile("profiles/myserver.json"), version="1.0.0")
if __name__ == "__main__":
    app()
```

<div class="grid cards" markdown>

-   :material-rocket-launch-outline:{ .lg .middle } __Fast to market__

    ---

    A clean OpenAPI backend becomes a complete, OAuth-protected MCP server with
    **zero tool code** — just a profile.

    [:octicons-arrow-right-24: Quickstart](quickstart.md)

-   :material-layers-triple-outline:{ .lg .middle } __Three complexity tiers__

    ---

    Pure config, config + a little Python, or mostly Python. Pick the lowest
    tier your backend allows — and mix freely.

    [:octicons-arrow-right-24: The three tiers](tiers.md)

-   :material-puzzle-outline:{ .lg .middle } __Pluggable, never forked__

    ---

    New auth modes, tool sources, and resolvers are pip-installable plugins via
    Python entry points — never a core edit.

    [:octicons-arrow-right-24: Writing plugins](plugins.md)

-   :material-shield-lock-outline:{ .lg .middle } __Secure by default__

    ---

    Fail-closed auth invariants, encrypted OAuth state at rest, PII log
    redaction, and a least-privilege tool context — enforced in core.

    [:octicons-arrow-right-24: Security model](security.md)

</div>

## :material-layers-triple:  Three complexity tiers

Pick the lowest tier that fits your backend — the [tier guide](tiers.md) walks
through each with a full profile + code.

| Tier | When | Effort |
|---|---|---|
| [**1 — pure config**](tiers.md#tier-1-pure-config) | backend ships a usable OpenAPI spec, standard auth | profile JSON only, no Python |
| [**2 — config + a little Python**](tiers.md#tier-2-config-a-little-python) | OpenAPI base + a few hand tools, or a custom resolver | profile + a `python` source/resolver reference |
| [**3 — mostly Python**](tiers.md#tier-3-mostly-python) | no usable spec (e.g. Zammad) | `tools.source: python`; the profile still drives auth, rate-limit, identity, routes |

## :material-pillar:  Design pillars

- **Modular** — new auth modes / tool sources / resolvers are pip-installable
  plugins registered via Python entry points, never core edits.
- **Configurable** — every standard behaviour is an overridable profile default.
- **Stable** — the mandatory core depends only on fastmcp/pydantic/httpx/
  structlog/cryptography; volatile concerns live in optional extras.
- **Secure** — fail-closed auth invariants are enforced in core and a profile
  cannot switch them off.

## :material-arrow-right-circle:  Where to go next

<div class="grid cards" markdown>

-   __Get started__

    ---

    [Installation](installation.md) · [Quickstart](quickstart.md) ·
    [Core concepts](concepts.md)

-   __Guides__

    ---

    [The three tiers](tiers.md) · [Configuration & settings](usage.md) ·
    [Authentication](authentication.md) · [Tool sources](tools.md) ·
    [Extensions](extensions.md) · [Observability & limits](observability.md) ·
    [Deployment](deployment.md)

-   __Reference__

    ---

    [Profile schema](profiles.md) · [Writing plugins](plugins.md) ·
    [Security model](security.md) · [API reference](api.md) ·
    [Changelog](changelog.md)

-   __Examples__

    ---

    Runnable servers for every tier live in
    [`examples/`](https://github.com/bauer-group/LIB-BG-MCPCore/tree/main/examples).

</div>
