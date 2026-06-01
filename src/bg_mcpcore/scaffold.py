"""Scaffolder for ``bg-mcpcore new <name>`` — generate a Tier-1 server skeleton.

Emits a minimal, working OpenAPI-backed MCP server: a declarative profile, a
4-line entrypoint, a tiny Settings subclass, a smoke test, and packaging that
pins bg-mcpcore to the *current* version (so the generated server is
reproducible). The operator fills in the spec source + a couple of overrides and
has a deployable server — no framework code to write.

Templates are plain in-code strings (no copier/cookiecutter dependency): the
scaffold is small and the zero-dependency path keeps `bg-mcpcore new` instant.
"""

from __future__ import annotations

import re
from importlib import resources
from pathlib import Path

from . import __version__

# Bundled brand assets (package data) reused verbatim so a generated server's
# landing page at / and icon at /logo.svg match the BAUER GROUP reference design
# exactly. index.html carries `__DISPLAY_NAME__` (baked at scaffold time) plus
# the $version/$environment/$auth_mode/$mcp_url/$protocol runtime placeholders
# that the server's index route fills via string.Template at boot.
_DISPLAY_TOKEN = "__DISPLAY_NAME__"


def _bundled(asset: str) -> str:
    # Anchor on the importable package and navigate into the data subdir, so
    # `_scaffold` needs no __init__.py and this works for wheel + editable installs.
    return resources.files(__package__).joinpath("_scaffold", asset).read_text(encoding="utf-8")

# A project slug: lowercase, starts with a letter, hyphen-separated. This becomes
# the profile id, the `bg-<slug>-mcp` package name, and (upper-snake) the env prefix.
_SLUG_RE = re.compile(r"^[a-z][a-z0-9]*(-[a-z0-9]+)*$")


class ScaffoldError(RuntimeError):
    """Raised when a target name is invalid or the destination is unusable."""


def _derive(slug: str) -> dict[str, str]:
    env_prefix = slug.upper().replace("-", "_")
    return {
        "slug": slug,
        "project": f"bg-{slug}-mcp",
        "env_prefix": env_prefix,
        "display": "BAUER GROUP " + slug.replace("-", " ").title(),
        "version": __version__,
    }


def _profile_json(v: dict[str, str]) -> str:
    return f"""{{
  "$schema": "https://raw.githubusercontent.com/bauer-group/LIB-BG-MCPCore/main/src/bg_mcpcore/profile/schema.json",
  "id": "{v['slug']}",
  "display_name": "{v['display']}",
  "instructions": "TODO: tell the AI what this server is for and how to use its tools.",
  "backend": {{
    "base_url": "${{env:{v['env_prefix']}_URL}}",
    "api_base_path": ""
  }},
  "auth": {{
    "outbound": {{ "type": "bearer_env", "value_from_env": "{v['env_prefix']}_TOKEN" }}
  }},
  "tools": {{
    "source": "openapi",
    "spec": {{ "source": "${{env:{v['env_prefix']}_OPENAPI_URL:-file:///app/openapi/{v['slug']}.json}}" }},
    "annotations": "by_http_method"
  }}
}}
"""


def _config_py(v: dict[str, str]) -> str:
    return f'''"""{v['display']} MCP Server configuration.

A bg-mcpcore ``BaseMcpSettings`` subclass: cross-cutting settings (environment,
transport, auth persistence, OIDC, rate limiting, observability) come from the
base; add any {v['slug']}-specific fields + per-mode credential checks here.
"""

from __future__ import annotations

from bg_mcpcore import BaseMcpSettings
from bg_mcpcore.settings import get_settings as _core_get_settings


class Settings(BaseMcpSettings):
    """{v['display']}-specific settings on top of the shared bg-mcpcore base."""

    # The base leaves this required so two deployments never share a name.
    mcp_display_name: str = "{v['display']}"

    # Add backend fields here, e.g.:
    #   {v['slug']}_url: HttpUrl = Field(default=...)
    # and narrow auth_mode to your supported set + implement validate_provider_auth.


def get_settings(force_reload: bool = False) -> Settings:
    return _core_get_settings(Settings, force_reload=force_reload)


__all__ = ["Settings", "get_settings"]
'''


def _main_py(v: dict[str, str]) -> str:
    return f'''"""{v['display']} MCP Server — CLI entrypoint (profile-driven via bg-mcpcore)."""

from __future__ import annotations

import sys
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version
from pathlib import Path

_SRC = Path(__file__).resolve().parent
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from bg_mcpcore import load_profile, make_cli  # noqa: E402

from config import Settings  # noqa: E402

try:
    _VERSION = _pkg_version("{v['project']}")
except PackageNotFoundError:
    _VERSION = "0.0.0+local"

app = make_cli(
    load_profile(str(_SRC / "profiles" / "{v['slug']}.json")),
    settings_cls=Settings,
    version=_VERSION,
    static_dir=str(_SRC / "static"),  # serves the landing page at / + /logo.svg
)

if __name__ == "__main__":
    app()
'''


def _pyproject(v: dict[str, str]) -> str:
    return f'''[build-system]
requires = ["hatchling>=1.27"]
build-backend = "hatchling.build"

[project]
name = "{v['project']}"
version = "0.1.0"
description = "{v['display']} MCP Server"
readme = "README.md"
license = {{ text = "MIT" }}
requires-python = ">=3.14"

dependencies = [
    # Shared framework, pulled from GitHub (internal projects do not use PyPI),
    # pinned to a release tag for reproducibility. Extras: [openapi] = the
    # OpenAPI tool source; [oauth-providers] = Entra/Google; [redis] = the Redis
    # OAuth-state store. Drop extras you do not use.
    "bg-mcpcore[openapi,oauth-providers,redis] @ git+https://github.com/bauer-group/LIB-BG-MCPCore.git@v{v['version']}",
]

[project.optional-dependencies]
test = [
    "pytest>=8.3.0,<10.0.0",
    "pytest-asyncio>=0.24.0,<2.0.0",
]

[project.scripts]
{v['project']} = "main:app"

# bg-mcpcore is a direct git reference; hatchling needs this opt-in.
[tool.hatch.metadata]
allow-direct-references = true

[tool.hatch.build.targets.wheel]
packages = ["src"]

[tool.hatch.build.targets.wheel.sources]
"src" = ""

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
'''


def _env_example(v: dict[str, str]) -> str:
    return f"""# Copy to .env and fill in. AUTH_MODE=none is dev-only (forbidden in production).
ENVIRONMENT=development
PUBLIC_BASE_URL=http://localhost:8000
AUTH_MODE=none

# Backend
{v['env_prefix']}_URL=https://api.example.com
{v['env_prefix']}_TOKEN=replace-me
# {v['env_prefix']}_OPENAPI_URL=file:///app/openapi/{v['slug']}.json

# When AUTH_MODE != none, set the IdP credentials + a signing key, e.g.:
# AUTH_JWT_SIGNING_KEY=<64 hex chars>
# ENTRA_CLIENT_ID=... ENTRA_CLIENT_SECRET=... ENTRA_TENANT_ID=...
"""


def _readme(v: dict[str, str]) -> str:
    return f"""# {v['display']} MCP Server

A Tier-1 bg-mcpcore server: tools are generated from an OpenAPI spec, the whole
surface is declared in [`src/profiles/{v['slug']}.json`](src/profiles/{v['slug']}.json).

## Fill in

1. **Spec** — point `{v['env_prefix']}_OPENAPI_URL` at the API's OpenAPI document
   (or bake one at `/app/openapi/{v['slug']}.json`).
2. **Backend** — set `{v['env_prefix']}_URL` and the `api_base_path` in the profile.
3. **Outbound auth** — the profile uses `Authorization: Bearer ${{{v['env_prefix']}_TOKEN}}`;
   change `auth.outbound` to `static_header` (e.g. `X-Api-Key`) if the API differs.
4. **Shape the tools** (optional) — add `name_overrides`, `descriptions`,
   `route_maps`, `normalize.strip_path_prefix` to the profile's `tools` block.
   See the [profile reference](https://github.com/bauer-group/LIB-BG-MCPCore/blob/main/docs/profiles.md).

## Run

```bash
pip install -e ".[test]"
cp .env.example .env   # then edit
python src/main.py     # MCP at /mcp · landing page at / · icon at /logo.svg · liveness at /healthz
```

The landing page (`src/static/index.html`) and icon (`src/static/logo.svg`) are
the BAUER GROUP reference design with this server's name baked in — rebrand by
editing those two files.

## Test

```bash
pytest -q
```
"""


def _smoke_test(v: dict[str, str]) -> str:
    return f'''"""Smoke test: the generated profile parses and Settings construct."""

from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))


def test_profile_is_valid() -> None:
    from bg_mcpcore import load_profile

    profile = load_profile(
        str(_SRC / "profiles" / "{v['slug']}.json"),
        env={{"{v['env_prefix']}_URL": "https://api.example.com"}},
    )
    assert profile.id == "{v['slug']}"
    assert profile.backend is not None


def test_settings_construct(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("PUBLIC_BASE_URL", "http://localhost:8000")
    monkeypatch.setenv("AUTH_MODE", "none")
    from bg_mcpcore.settings import reset_settings_cache

    reset_settings_cache()
    from config import Settings

    assert Settings().mcp_display_name == "{v['display']}"
'''


_FILES = {
    "pyproject.toml": _pyproject,
    "README.md": _readme,
    ".env.example": _env_example,
    "src/main.py": _main_py,
    "src/config.py": _config_py,
    "tests/test_smoke.py": _smoke_test,
}


def scaffold(name: str, target_dir: str | Path = ".", *, force: bool = False) -> Path:
    """Generate a Tier-1 server skeleton named ``name`` under ``target_dir``.

    Returns the created project directory. Raises :class:`ScaffoldError` on an
    invalid name or a non-empty destination (unless ``force``).
    """
    slug = name.strip().lower()
    if not _SLUG_RE.match(slug):
        raise ScaffoldError(
            f"Invalid name {name!r}: use a lowercase, hyphen-separated slug "
            "starting with a letter (e.g. 'mautic', 'my-api')."
        )

    v = _derive(slug)
    dest = Path(target_dir).expanduser().resolve() / slug
    if dest.exists() and any(dest.iterdir()) and not force:
        raise ScaffoldError(f"Destination {dest} exists and is not empty (use force=True to overwrite)")

    # The profile lives under src/profiles/<slug>.json (computed, not in _FILES).
    files = dict(_FILES)
    written: list[str] = []
    for rel, render in files.items():
        path = dest / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(render(v), encoding="utf-8", newline="\n")
        written.append(rel)

    profile_path = dest / "src" / "profiles" / f"{slug}.json"
    profile_path.parent.mkdir(parents=True, exist_ok=True)
    profile_path.write_text(_profile_json(v), encoding="utf-8", newline="\n")
    written.append(f"src/profiles/{slug}.json")

    # Brand assets: the full BAUER GROUP landing page (served at /) + the icon
    # (served at /logo.svg). index.html is the reference design verbatim with the
    # server name baked in; logo.svg is copied as-is.
    static_dir = dest / "src" / "static"
    static_dir.mkdir(parents=True, exist_ok=True)
    (static_dir / "index.html").write_text(
        _bundled("index.html").replace(_DISPLAY_TOKEN, v["display"]),
        encoding="utf-8",
        newline="\n",
    )
    (static_dir / "logo.svg").write_text(_bundled("logo.svg"), encoding="utf-8", newline="\n")
    written += ["src/static/index.html", "src/static/logo.svg"]

    return dest


__all__ = ["ScaffoldError", "scaffold"]
