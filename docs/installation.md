# Installation

`bg-mcpcore` is a normal Python package. The mandatory core is lean — install
only the optional extras a given server actually needs.

## Requirements

- **Python 3.12, 3.13, or 3.14.** The floor is 3.12 (lint + type-checks target
  it, so nothing uses newer syntax).
- A backend REST API your server will front (for any server that declares a
  `backend`).

## From PyPI

=== "pip"

    ```bash
    pip install bg-mcpcore                 # lean core
    pip install "bg-mcpcore[openapi]"      # + OpenAPI-derived tools
    ```

=== "uv"

    ```bash
    uv add bg-mcpcore
    uv add "bg-mcpcore[openapi]"
    ```

## Optional extras

The core depends only on `fastmcp`, `httpx`, `pydantic`, `pydantic-settings`,
`structlog`, `rich`, `cryptography`, `typer`, and the disk-backed encrypted state
store. Everything volatile or single-consumer lives in an extra, so a server
pays only for what it imports.

| Extra | Adds | Install when |
|---|---|---|
| `openapi` | `pyyaml` (YAML spec ingestion) | a profile uses `tools.source: openapi` |
| `redis` | `py-key-value-aio[redis]` | the OAuth-state store should live in Redis (multi-replica) |
| `oauth-providers` | *(marker — Entra/Google ship in FastMCP)* | the server opts into a cloud IdP inbound mode |
| `tasks` | `fastmcp[tasks]` (docket) | the server exposes long-running tasks (bulk exports) |
| `testkit` | `pytest`, `pytest-asyncio`, `respx` | running the reusable pytest fixtures in a consumer suite |
| `dev` | the full test + lint + build toolchain | contributing to the library itself |
| `docs` | `mkdocs`, `mkdocs-material`, `mkdocstrings` | building this documentation site |

Combine extras as needed — a typical production server:

```bash
pip install "bg-mcpcore[openapi,redis,oauth-providers,tasks]"
```

## Directly from GitHub

Install an unreleased revision or a specific tag without PyPI:

```bash
# Latest from main
pip install git+https://github.com/bauer-group/LIB-BG-MCPCore.git@main

# A specific released tag
pip install git+https://github.com/bauer-group/LIB-BG-MCPCore.git@v1.2.0

# With extras (any install method)
pip install "bg-mcpcore[openapi] @ git+https://github.com/bauer-group/LIB-BG-MCPCore.git@main"
```

## Development install

Working on the library itself? Clone and install editable with the `dev` extra.
The project uses [uv](https://docs.astral.sh/uv/) for fast, reproducible envs:

```bash
git clone https://github.com/bauer-group/LIB-BG-MCPCore.git
cd LIB-BG-MCPCore
uv sync --extra dev --extra openapi      # or: pip install -e ".[dev,openapi]"

uv run ruff check src tests              # lint
uv run mypy src/bg_mcpcore               # type-check (strict)
uv run pytest -q --cov=bg_mcpcore        # tests + coverage
uv run --extra docs mkdocs serve         # live docs preview
```

!!! tip "Cross-version checks"
    `uv run --python 3.12 pytest` / `--python 3.13` / `--python 3.14` runs the
    suite against each supported interpreter, mirroring the CI matrix.

## Verify the install

```bash
python -c "import bg_mcpcore; print(bg_mcpcore.__version__)"
python -c "from bg_mcpcore import build_app_from_profile, load_profile, make_cli; print('ok')"
```

Both should succeed with only the core installed — no extra is a hidden hard
dependency of the public API.

## Next

- [Quickstart](quickstart.md) — a running server in five minutes.
- [Core concepts](concepts.md) — the profile + settings + escape-hatch model.
- [The three tiers](tiers.md) — pick the lowest tier that fits your backend.
