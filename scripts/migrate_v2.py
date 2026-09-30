#!/usr/bin/env python3
"""Codemod for the mechanical half of the bg-mcpcore 1.x -> 2.0 migration.

Rewrites the HTTP types a server's tool code names, from `httpx` to the
`bg_mcpcore.http` re-exports. That is the one migration step that can fail
SILENTLY: httpx usually stays installed transitively, so `except httpx.X` around
a `ctx.request` call still imports and still type-checks after bg-mcpcore moved
to httpx2 — it simply never matches again.

Deliberately conservative. It only rewrites `httpx.<Name>` for names
`bg_mcpcore.http` actually re-exports, and only in files that reference
bg_mcpcore. It will not touch outbound httpx calls you make yourself with your
own client, which are unaffected by the migration and remain correct.

    python scripts/migrate_v2.py .            # report what it would change
    python scripts/migrate_v2.py . --write    # apply

Always review the diff. See docs/migration-v2.md for the steps this cannot do.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# The names bg_mcpcore.http re-exports. Anything else stays on httpx, because
# bg-mcpcore does not promise it.
REEXPORTED = (
    "Response",
    "Request",
    "HTTPError",
    "HTTPStatusError",
    "RequestError",
    "TransportError",
    "ConnectError",
    "ConnectTimeout",
    "TimeoutException",
)

_ATTR_RE = re.compile(r"\bhttpx\.(" + "|".join(REEXPORTED) + r")\b")
_PLAIN_IMPORT_RE = re.compile(r"^(?P<indent>[ \t]*)import httpx\s*$", re.MULTILINE)
_FROM_IMPORT_RE = re.compile(r"^(?P<indent>[ \t]*)from httpx import (?P<names>[^\n(]+)$", re.MULTILINE)
SKIP_DIRS = {".git", ".venv", "venv", "__pycache__", ".mypy_cache", ".ruff_cache", "node_modules", "build", "dist"}


def _iter_python_files(root: Path):
    for path in sorted(root.rglob("*.py")):
        if any(part in SKIP_DIRS or part.startswith(".venv") for part in path.parts):
            continue
        yield path


def _insertion_point(lines: list[str]) -> int:
    """First line after the module docstring and any __future__ import."""
    index = 0
    if lines and (lines[0].lstrip().startswith(('"""', "'''"))):
        quote = lines[0].lstrip()[:3]
        if lines[0].count(quote) >= 2 and len(lines[0].strip()) > 3:
            index = 1  # one-line docstring
        else:
            for i in range(1, len(lines)):
                if quote in lines[i]:
                    index = i + 1
                    break
    for i in range(index, min(index + 4, len(lines))):
        if "from __future__ import" in lines[i]:
            index = i + 1
            break
    while index < len(lines) and not lines[index].strip():
        index += 1
    return index


def _rewrite(source: str) -> tuple[str, list[str]]:
    notes: list[str] = []
    used: set[str] = set()

    def _sub_attr(match: re.Match[str]) -> str:
        name = match.group(1)
        used.add(name)
        return name

    new_source, count = _ATTR_RE.subn(_sub_attr, source)
    if count:
        notes.append(f"{count} httpx.<Type> reference(s) -> bg_mcpcore.http")

    # `from httpx import X, Y` -> keep only the names we do not re-export.
    def _sub_from(match: re.Match[str]) -> str:
        names = [n.strip() for n in match.group("names").split(",") if n.strip()]
        moved = [n for n in names if n in REEXPORTED]
        kept = [n for n in names if n not in REEXPORTED]
        if not moved:
            return match.group(0)
        used.update(moved)
        notes.append(f"from httpx import {', '.join(moved)} -> bg_mcpcore.http")
        if kept:
            return f"{match.group('indent')}from httpx import {', '.join(kept)}"
        return "\x00DROP\x00"

    new_source = _FROM_IMPORT_RE.sub(_sub_from, new_source)

    if not used:
        return source, []

    # Drop a now-unused `import httpx`.
    no_attrs_left = not re.search(r"\bhttpx\.\w+", new_source)
    if no_attrs_left and _PLAIN_IMPORT_RE.search(new_source):
        new_source = _PLAIN_IMPORT_RE.sub("\x00DROP\x00", new_source)
        notes.append("removed the now-unused `import httpx`")

    lines = [ln for ln in new_source.split("\n") if ln != "\x00DROP\x00"]

    # Add the bg_mcpcore.http import if it is not already there.
    existing = re.search(r"^from bg_mcpcore\.http import (?P<names>.+)$", "\n".join(lines), re.MULTILINE)
    if existing:
        have = {n.strip() for n in existing.group("names").split(",")}
        merged = sorted(have | used)
        lines = [
            (f"from bg_mcpcore.http import {', '.join(merged)}" if ln == existing.group(0) else ln)
            for ln in lines
        ]
    else:
        at = _insertion_point(lines)
        lines.insert(at, f"from bg_mcpcore.http import {', '.join(sorted(used))}")
        lines.insert(at + 1, "")
        notes.append("added the bg_mcpcore.http import")

    return "\n".join(lines), notes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("root", nargs="?", default=".", type=Path, help="directory to scan (default: .)")
    parser.add_argument("--write", action="store_true", help="apply the changes (default: report only)")
    args = parser.parse_args(argv)

    changed = 0
    for path in _iter_python_files(args.root):
        try:
            source = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if "httpx" not in source or "bg_mcpcore" not in source:
            continue
        new_source, notes = _rewrite(source)
        if not notes or new_source == source:
            continue
        changed += 1
        print(f"\n{path}")
        for note in notes:
            print(f"  - {note}")
        if args.write:
            path.write_text(new_source, encoding="utf-8")

    if not changed:
        print("Nothing to rewrite. Check the other steps in docs/migration-v2.md.")
        return 0

    print(f"\n{changed} file(s) {'rewritten' if args.write else 'would change'}.")
    if not args.write:
        print("Re-run with --write to apply.")
    else:
        print("Review the diff, then run your formatter/linter and the test suite.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
