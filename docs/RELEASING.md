# Releasing

1. Update `project.version`, `CHANGELOG.md`, and version-pinned examples/docs together. Run `uv lock` if project metadata or dependencies changed.
2. Run `uv sync --frozen`, `uv run --frozen ruff check src tests scripts`, `uv run --frozen pytest -q`, and `uv build`.
3. Run `uv run --frozen python scripts/check_dist.py`, then `uv run --frozen python scripts/verify_install.py --from dist/fudan_library_mcp-VERSION-py3-none-any.whl`. This launches the wheel in an isolated uv tool environment outside the source tree and checks MCP discovery.
4. Optionally run `uv run --frozen python scripts/live_smoke.py` for real-library verification; it makes a small number of requests and updates the dated report. Do not put online library tests into routine CI.
5. Commit, push, and wait for CI to pass on Windows/Linux with Python 3.11/3.13.
6. Create an annotated `vVERSION` tag at the reviewed commit and push it. The release workflow repeats tests, verifies tag/package version agreement, validates distribution contents, and creates a GitHub Release with wheel, sdist, and `SHA256SUMS`.
7. Verify the public installation with `uv run --frozen python scripts/verify_install.py --from git+https://github.com/LvDAO/fudan-library-mcp.git@vVERSION --live`. Do not move a published version tag; fix release problems in a new version.

GitHub Actions needs `contents: write` only in the release job, using its built-in token. No PyPI token is required. This repository does not currently publish to PyPI or the MCP Registry.
