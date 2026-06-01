"""Generate the JSON Schemas shipped for editor validation.

These schemas are an EDITOR AID only — the loader validates with the pydantic
models, not the JSON Schema (and strips `$schema` before validation). They let
an IDE autocomplete + validate a profile / extensions catalogue against the
real model. Regenerate after changing the profile or extensions models:

    uv run python scripts/generate_schemas.py

The ``$id`` of each schema, and the ``$schema`` reference that profiles/
catalogues use, is the file's own public raw-GitHub URL — a real, fetchable
location (the repository is public), never an unhosted placeholder.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from bg_mcpcore.extensions.config import ExtensionsConfig
from bg_mcpcore.profile.models import Profile

_RAW_BASE = "https://raw.githubusercontent.com/bauer-group/LIB-BG-MCPCore/main/src/bg_mcpcore"
_META = "https://json-schema.org/draft/2020-12/schema"
_SRC = Path(__file__).resolve().parent.parent / "src" / "bg_mcpcore"


def _write(model: Any, rel: str) -> None:
    schema_id = f"{_RAW_BASE}/{rel}"
    body: dict[str, Any] = {"$schema": _META, "$id": schema_id}
    body.update(model.model_json_schema())
    path = _SRC / rel
    path.write_text(json.dumps(body, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {path}  (id={schema_id})")


def main() -> None:
    _write(Profile, "profile/schema.json")
    _write(ExtensionsConfig, "extensions/schema.json")


if __name__ == "__main__":
    main()
