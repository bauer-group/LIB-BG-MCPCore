"""Tier-2 server — an OpenAPI surface PLUS a few hand-written composite tools.

Run from this directory (so the spec path resolves and `extra_tools` imports):
    export PETSTORE_TOKEN=demo PUBLIC_BASE_URL=http://localhost:8000
    export ENVIRONMENT=development AUTH_MODE=none
    python main.py
"""

import os
import sys
from pathlib import Path

from bg_mcpcore import load_profile, make_cli

# Make `extra_tools` importable and resolve the spec regardless of the CWD.
_HERE = Path(__file__).parent
sys.path.insert(0, str(_HERE))
os.chdir(_HERE)

app = make_cli(load_profile("profile.json"), version="0.1.0")

if __name__ == "__main__":
    app()
