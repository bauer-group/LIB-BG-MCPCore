---
icon: material/rocket-launch
---

# Quickstart

## :material-download:  Install

```bash
pip install "bg-mcpcore[openapi]"
```

## :material-layers-triple:  A Tier-1 server (pure config)

For a backend that ships a usable OpenAPI spec:

```jsonc
// profiles/mautic.json
{
  "id": "mautic",
  "display_name": "BAUER GROUP Mautic",
  "instructions": "Marketing automation via Mautic.",
  "backend": { "base_url": "${env:MAUTIC_URL}", "api_base_path": "/api" },
  "auth": {
    "inbound":  { "mode": "oidc" },
    "outbound": { "type": "bearer_env", "value_from_env": "MAUTIC_TOKEN" }
  },
  "tools": { "source": "openapi", "spec": { "source": "${env:MAUTIC_OPENAPI_URL}" } }
}
```

```python
# src/main.py
from bg_mcpcore import load_profile, make_cli

app = make_cli(load_profile("profiles/mautic.json"))
if __name__ == "__main__":
    app()
```

Run it:

```bash
export PUBLIC_BASE_URL=https://mcp.example.com
export AUTH_MODE=oidc OIDC_DISCOVERY_URL=... OIDC_CLIENT_ID=... OIDC_CLIENT_SECRET=...
export AUTH_JWT_SIGNING_KEY=$(python -c "import secrets;print(secrets.token_hex(32))")
export MAUTIC_URL=https://mautic.example.com MAUTIC_TOKEN=... MAUTIC_OPENAPI_URL=...
python src/main.py            # serves at /mcp, /healthz, /
```

## :material-format-list-bulleted:  A backend-less server (registry tools only)

```jsonc
{ "id": "demo", "display_name": "Demo",
  "tools": { "source": "registry", "include": ["bg.ping", "bg.health"] } }
```

## :material-cog:  Settings

Runtime values + secrets come from the environment via `BaseMcpSettings`
(`PUBLIC_BASE_URL`, `AUTH_MODE`, `AUTH_JWT_SIGNING_KEY`, OIDC creds, rate-limit,
Sentry, …). A server may subclass `BaseMcpSettings` to add backend-specific
fields and pass it via `make_cli(profile, settings_cls=MySettings)`.

The fail-closed invariants are enforced in core: `AUTH_MODE=none` is rejected in
production, and a JWT signing key is required for any active mode.

## :material-arrow-right-circle:  Next steps

- [Core concepts](concepts.md) — the profile + settings + escape-hatch model,
  the assembler spine, and the request lifecycle.
- [The three tiers](tiers.md) — pick the lowest tier that fits your backend;
  full profile + code for Tier 1 (pure config), Tier 2 (config + a little
  Python), and Tier 3 (mostly Python).
- [Configuration & settings](usage.md) — every setting, the profile/settings
  split, subclassing `BaseMcpSettings`, connecting an MCP client.
- Guides: [authentication](authentication.md), [tool sources](tools.md),
  [extensions](extensions.md), [observability & limits](observability.md),
  [deployment](deployment.md).
- Reference: [profile schema](profiles.md), [writing plugins](plugins.md),
  [security model](security.md), [API reference](api.md).
