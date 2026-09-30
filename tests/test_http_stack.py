"""Guards on the HTTP stack: httpx2 everywhere, re-exported through bg_mcpcore.

FastMCP 4 replaced httpx with httpx2 across its whole stack. The dangerous part
of that swap is not the code that fails loudly — it is the code that keeps
importing and type-checking while silently never matching, because httpx usually
remains installed transitively. These tests pin the invariant so a stray
``import httpx`` cannot creep back into the library.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parent.parent / "src" / "bg_mcpcore"


def _library_modules() -> list[Path]:
    # testing/http.py is the one sanctioned httpx (v1) importer: respx models its
    # mocked responses with v1 objects even when patching httpx2 transports.
    return [p for p in SRC.rglob("*.py") if p.relative_to(SRC).as_posix() != "testing/http.py"]


@pytest.mark.parametrize("module", _library_modules(), ids=lambda p: p.relative_to(SRC).as_posix())
def test_no_httpx_v1_import_in_library(module: Path) -> None:
    """No library module may import httpx (v1) — the whole stack is httpx2."""
    tree = ast.parse(module.read_text(encoding="utf-8"))
    offenders: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            offenders += [a.name for a in node.names if a.name.split(".")[0] == "httpx"]
        elif isinstance(node, ast.ImportFrom) and node.module and node.module.split(".")[0] == "httpx":
            offenders.append(node.module)
    assert not offenders, f"{module.name} imports httpx (v1): {offenders} — use httpx2"


def test_no_bare_except_httpx_in_library() -> None:
    """``except httpx.X`` around FastMCP/httpx2 calls is dead code, not an error."""
    hits = [
        f"{p.relative_to(SRC).as_posix()}:{n}"
        for p in _library_modules()
        for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
        if re.search(r"except\s+\(?\s*httpx\.", line)
    ]
    assert not hits, f"httpx (v1) exception handlers never match httpx2 errors: {hits}"


def test_http_types_are_reexported_from_httpx2() -> None:
    """The public HTTP surface must be the real httpx2 types, not look-alikes."""
    import httpx2

    from bg_mcpcore import http

    for name in ("Response", "Request", "HTTPError", "HTTPStatusError", "RequestError",
                 "TransportError", "ConnectError", "ConnectTimeout", "TimeoutException"):
        assert getattr(http, name) is getattr(httpx2, name), name
        assert name in http.__all__


def test_http_types_resolve_through_the_lazy_top_level() -> None:
    """Downstream code imports these from bg_mcpcore directly; keep that working."""
    import bg_mcpcore

    for name in ("Response", "HTTPStatusError", "ConnectError", "TransportError"):
        assert name in bg_mcpcore.__all__
        assert getattr(bg_mcpcore, name) is getattr(bg_mcpcore.http, name)


def test_upstream_client_exposes_an_httpx2_client() -> None:
    """The client handed to FastMCP.from_openapi must be httpx2, not httpx."""
    import httpx2

    from bg_mcpcore.http import UpstreamClient

    client = UpstreamClient(base_url="https://api.test")
    assert isinstance(client.httpx_client, httpx2.AsyncClient)
