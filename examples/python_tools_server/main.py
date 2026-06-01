"""Tier-3 server — hand-written tools via the python escape hatch.

Run from this directory (so `my_tools` is importable):
    export PUBLIC_BASE_URL=http://localhost:8000 ENVIRONMENT=development AUTH_MODE=none
    python main.py
"""

import os
import sys
from pathlib import Path

from bg_mcpcore import load_profile, make_cli

# Make `my_tools` importable and resolve the profile regardless of CWD.
_HERE = Path(__file__).parent
sys.path.insert(0, str(_HERE))
os.chdir(_HERE)

app = make_cli(load_profile("profile.json"), version="0.1.0")

if __name__ == "__main__":
    app()
