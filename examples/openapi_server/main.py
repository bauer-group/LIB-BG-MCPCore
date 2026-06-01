"""Tier-1 OpenAPI server — tools generated from a spec, pure config.

Run from this directory (so the relative spec path resolves):
    export PETSTORE_TOKEN=demo PUBLIC_BASE_URL=http://localhost:8000
    export ENVIRONMENT=development AUTH_MODE=none
    python main.py
"""

import os
from pathlib import Path

from bg_mcpcore import load_profile, make_cli

# Resolve the spec relative to this file regardless of the working directory.
os.chdir(Path(__file__).parent)

app = make_cli(load_profile("profile.json"), version="0.1.0")

if __name__ == "__main__":
    app()
