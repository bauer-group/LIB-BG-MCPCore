# Changelog

Releases are cut automatically by
[python-semantic-release](https://python-semantic-release.readthedocs.io/) from
[Conventional Commits](https://www.conventionalcommits.org/) on every push to
`main`:

- `feat:` → **minor** release
- `fix:` / `perf:` → **patch** release
- a `feat!:` subject or a `BREAKING CHANGE:` footer → **major** release
- `docs:` / `chore:` / `test:` / `ci:` / `refactor:` / `style:` → no release

Each published version updates the package, the git tag (`vX.Y.Z`), and the
PyPI release in one pipeline run.

## Full history

The complete, version-by-version history lives in
[`CHANGELOG.md`](https://github.com/bauer-group/LIB-BG-MCPCore/blob/main/CHANGELOG.md)
at the repository root, and every release is also published on the
[GitHub releases page](https://github.com/bauer-group/LIB-BG-MCPCore/releases)
and on [PyPI](https://pypi.org/project/bg-mcpcore/#history).
