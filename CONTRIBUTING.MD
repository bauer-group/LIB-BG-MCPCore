# Contributing to bg-mcpcore

Thanks for helping improve the BAUER GROUP MCP framework.

## Development setup

bg-mcpcore is pip-native (hatchling). Either pip or uv works locally; the repo
does not commit a lockfile (a library is consumed across environments).

```bash
git clone https://github.com/bauer-group/LIB-BG-MCPCore
cd LIB-BG-MCPCore
python -m pip install -e ".[dev,openapi,oauth-providers,tasks,testkit]"
pre-commit install
```

Requires **Python 3.14+**.

## Quality gates (must pass before a PR)

```bash
make lint        # ruff check
make type-check  # mypy --strict
make test        # pytest
# or: make all-checks
```

CI runs the same gates plus an extras-install matrix.

## Conventions

- **Conventional Commits** (English, past tense subject) — semantic-release
  derives the version and CHANGELOG from them. No AI attribution in commits.
- **Type everything** — `mypy --strict` is enforced; public functions take
  structural Protocols, not concrete settings (least privilege).
- **Security invariants are non-negotiable** — never weaken the fail-closed auth
  checks, the secret-redaction list, or the encrypted-storage path. Changes
  under `src/bg_mcpcore/auth/` and `settings/` require review.
- **Extend, don't edit** — new auth modes / tool sources / resolvers should ship
  as entry-point plugins, not core changes.

## Adding a new tool source / auth provider / resolver

Register an entry point in your package:

```toml
[project.entry-points."bg_mcpcore.tool_sources"]
graphql = "my_pkg.graphql:create_provider"
```

A `tool_sources` factory returns a `ToolProvider` (has `register(mcp, ctx)`) or a
`ConstructingToolProvider` (has `construct(...)`). See `docs/plugins.md`.

## Reporting security issues

See [SECURITY.MD](SECURITY.MD) — please use GitHub Security Advisories.
