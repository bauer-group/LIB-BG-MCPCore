"""Backend-less registry server — the smallest possible bg-mcpcore server."""

from pathlib import Path

from bg_mcpcore import load_profile, make_cli

app = make_cli(load_profile(Path(__file__).parent / "profile.json"), version="0.1.0")

if __name__ == "__main__":
    app()
