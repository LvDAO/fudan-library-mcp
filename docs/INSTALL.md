# Install Fudan Library MCP

This guide is intended for people and coding agents. The server provides five read-only MCP tools over **stdio**. It uses Fudan Library's anonymous Primo interface. No university password, browser cookie, LLM key, or hosted server is needed.

## 1. Check prerequisites and prewarm the server

Install [uv](https://docs.astral.sh/uv/getting-started/installation/) and Git using their official installers if missing. `uvx` is included with uv. Python 3.11+ is required; uv can provision a compatible interpreter. Then run:

```sh
uvx --from git+https://github.com/LvDAO/fudan-library-mcp.git@v0.1.0 fudan-library-mcp --version
uvx --from git+https://github.com/LvDAO/fudan-library-mcp.git@v0.1.0 fudan-library-mcp --check
```

Expect version `0.1.0` and JSON with `"status": "ok"`. The first installation needs GitHub and PyPI access; the connection check needs access to `fudan-primo.hosted.exlibrisgroup.com.cn`. Run these commands before starting a client with a short startup timeout.

The version tag pins server source, not all transitive dependencies. For a dependency-locked deployment, see the source checkout option below.

## 2. Register with the selected MCP client

Preserve existing client settings and merge only the `fudan-library` entry. Do not install into unrelated clients or request credentials.

### Codex

```sh
codex mcp add fudan-library -- uvx --from git+https://github.com/LvDAO/fudan-library-mcp.git@v0.1.0 fudan-library-mcp
```

For configurable startup/tool timeouts, merge [examples/codex.toml](../examples/codex.toml) into your Codex MCP settings instead.

### Claude Desktop and Cursor

Merge [examples/mcp.json](../examples/mcp.json) into the client's MCP configuration:

```json
{
  "mcpServers": {
    "fudan-library": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/LvDAO/fudan-library-mcp.git@v0.1.0", "fudan-library-mcp"]
    }
  }
}
```

### VS Code

Merge [examples/vscode.mcp.json](../examples/vscode.mcp.json) into `.vscode/mcp.json`, or the client's user MCP configuration. It uses the `servers` key and `"type": "stdio"`.

For desktop apps, use the absolute path to `uvx` if PATH is not inherited. Find it with `Get-Command uvx` on PowerShell or `command -v uvx` on macOS/Linux. Restart or reload the client's MCP services after changing configuration. Do not add diagnostic flags (`--check`, `--search`, `--version`) to the server configuration.

## 3. Verify through MCP

The client must complete `initialize` and list these tools:

- `search_literature`
- `search_fulltext`
- `get_document`
- `get_documents`
- `library_status`

The `screen_literature` prompt is also available. Call `library_status`, then try `search_literature` with `{"query":"graph neural network","limit":2}` and `search_fulltext` with the same query. Verify that results include `source_url` and provenance; an absent abstract is `null`.

Example user request:

> 用复旦图书馆检索图神经网络用于分子性质预测的文献；用全文检索补充方法与数据集名称。根据真实摘要列出纳入／排除理由、DOI 和原文入口，证据不足的标为待核实。

Full-text search uses the upstream `ftext` index; it does **not** download or read publisher full text. Do not treat snippets, title matches, or full-text availability as proof that the paper was read.

## Alternative: install a release wheel without Git

Download the wheel and `SHA256SUMS` from the [v0.1.0 release](https://github.com/LvDAO/fudan-library-mcp/releases/tag/v0.1.0). Check its SHA-256 against the manifest (`Get-FileHash -Algorithm SHA256` on Windows; `sha256sum` on Linux; `shasum -a 256` on macOS), then run:

```sh
uvx --from ./fudan_library_mcp-0.1.0-py3-none-any.whl fudan-library-mcp --check
```

For MCP registration replace the `--from` value with the **absolute path** to the downloaded wheel. Keep the wheel at that path. Dependencies still come from PyPI. The checksum verifies release-file integrity; it is not a separate publisher signature.

## Alternative: source checkout with locked dependencies

```sh
git clone --branch v0.1.0 --depth 1 https://github.com/LvDAO/fudan-library-mcp.git
cd fudan-library-mcp
uv sync --frozen --no-dev
uv run --frozen --no-dev fudan-library-mcp --check
```

Configure `command` as `uv` and `args` as `["--directory", "/absolute/path/to/fudan-library-mcp", "run", "--frozen", "--no-dev", "fudan-library-mcp"]`. Substitute the actual checkout path, including on Windows.

## Updates and troubleshooting

- Upgrade by changing the version tag in `--from` after reviewing a release. Roll back by restoring the previous tag. A Git commit SHA can replace the tag for immutable source selection.
- Direct network access is the default. If your network requires an environment proxy, set `FUDAN_LIBRARY_TRUST_ENV=true` in the server's environment and configure `HTTPS_PROXY` as usual.
- Authentication or publisher access errors cannot be fixed by supplying a university password to this server. Publisher full text may require the user's campus access outside this MCP.
- A `partial=true` response is incomplete, not evidence of no matches. Retry later or narrow the query.
- This release is distributed through GitHub. It is not published to PyPI or registered in the MCP Registry; `uvx fudan-library-mcp` alone is not the supported installation command.

Distribution follows the [official MCP Git server's uvx approach](https://github.com/modelcontextprotocol/servers/tree/main/src/git) and [uv's tool source options](https://docs.astral.sh/uv/guides/tools/).
