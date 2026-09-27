# 复旦大学图书馆 MCP

[![CI](https://github.com/LvDAO/fudan-library-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/LvDAO/fudan-library-mcp/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/LvDAO/fudan-library-mcp)](https://github.com/LvDAO/fudan-library-mcp/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

让支持 MCP 的 LLM 通过复旦图书馆「望道溯源」检索中英文文献，用真实摘要筛选论文，并使用全文索引补充检索。基于官方 Python MCP SDK，使用本地 **stdio** 传输。

**[Agent 安装指南 / Installation guide](docs/INSTALL.md)** · [版本记录](CHANGELOG.md) · [Release 安装包](https://github.com/LvDAO/fudan-library-mcp/releases)

An MCP server for searching Fudan Library, screening papers using source-provided abstracts, and expanding searches with the full-text index. Works with MCP clients such as Codex, Claude Desktop, Cursor, and VS Code. No API key required. This is an independent community project, not an official Fudan University product.

已于 **2026-09-27** 在复旦实际接口上通过 MCP 客户端验证；不是只生成网页搜索链接。当前匿名访客接口即可返回书目信息和可用摘要，无需提供学校账号、密码或 LLM API Key。

## 可以做什么

| MCP 工具 | 功能 |
| --- | --- |
| `search_literature` | 常规检索或按题名、摘要、作者、主题、全文索引检索；支持年份、语言、类型、同行评议、全文可用性过滤与分页 |
| `search_fulltext` | 使用 Primo 的 **`ftext` 全文字段**检索，查找正文中的具体术语、方法或数据集 |
| `get_document` | 根据检索返回的 `record_id` 和 `context` 获取单篇详情、可用摘要、DOI、全文入口 |
| `get_documents` | 批量获取最多 10 篇文献的详情；逐项返回成功或失败 |
| `library_status` | 检查匿名连接、检索范围和能力边界 |

另提供 `screen_literature` MCP 提示词，输入研究问题与纳入／排除标准，引导 LLM 完成“检索 → 全文索引补充 → 去重 → 摘要初筛 → 带来源的阅读清单”。相关性判断由调用方 LLM 完成，服务器不使用关键词分数冒充语义筛选。

## 快速安装

需要 [uv（包含 uvx）](https://docs.astral.sh/uv/getting-started/installation/) 和 Git。Python 要求 3.11+；uv 可在需要时自动安装兼容版本。首次安装需要连接 GitHub 和 PyPI，检索时需要能访问复旦 Primo 服务。

先执行一次连接检查，让依赖在 MCP 客户端启动前完成安装：

```sh
uvx --from git+https://github.com/LvDAO/fudan-library-mcp.git@v0.1.0 fudan-library-mcp --check
```

GitHub 标签固定服务器版本；依赖在声明的兼容范围内解析。需要完全锁定依赖的部署，可克隆对应标签后使用 `uv sync --frozen`，见[安装指南](docs/INSTALL.md)。本版本通过 GitHub 分发，尚未发布到 PyPI 或 MCP Registry。

### 接入 Codex

使用 CLI 注册：

```sh
codex mcp add fudan-library -- uvx --from git+https://github.com/LvDAO/fudan-library-mcp.git@v0.1.0 fudan-library-mcp
```

也可将 [`examples/codex.toml`](examples/codex.toml) 合并到 Codex MCP 配置：

```toml
[mcp_servers.fudan-library]
command = "uvx"
args = ["--from", "git+https://github.com/LvDAO/fudan-library-mcp.git@v0.1.0", "fudan-library-mcp"]
startup_timeout_sec = 120
tool_timeout_sec = 180
```

### Claude Desktop / Cursor / VS Code

Claude Desktop、Cursor 等使用 `mcpServers` 的客户端可合并 [`examples/mcp.json`](examples/mcp.json)。VS Code 使用 [`examples/vscode.mcp.json`](examples/vscode.mcp.json) 的 `servers` 结构。保留已有 MCP 配置，仅新增 `fudan-library` 条目。

如果桌面客户端找不到 `uvx`，将 `command` 改为本机 `uvx` 的绝对路径，随后重启客户端。MCP 启动参数不应包含 `--check` 或 `--search`；默认进程会等待 stdin/stdout 协议消息，没有交互菜单属于正常现象。

无 Git 的机器可直接从 [Release](https://github.com/LvDAO/fudan-library-mcp/releases/tag/v0.1.0) 安装 wheel；校验与完整步骤见[安装指南](docs/INSTALL.md)。

接入后可以直接对 LLM 说：

> 用复旦图书馆检索 2020—2025 年图神经网络用于分子性质预测的文献。先搜题名与摘要，再用全文检索补充。按摘要筛选出真正使用三维分子结构的方法，列出纳入理由、DOI 和原文入口；没有足够证据的标为待核实。

## 工具调用示例

普通主题检索（`search_literature`）：

```json
{
  "query": "graph neural network AND molecular property",
  "field": "all",
  "scope": "articles",
  "year_from": 2020,
  "year_to": 2025,
  "peer_reviewed_only": true,
  "limit": 10
}
```

全文检索（`search_fulltext`）：

```json
{
  "query": "\"QM9\" AND \"equivariant\"",
  "year_from": 2020,
  "limit": 10
}
```

批量详情（`get_documents`）：

```json
{
  "references": [
    { "record_id": "从检索结果复制的真实ID", "context": "PC" }
  ]
}
```

参数说明：

- `field`: `all` / `title` / `abstract` / `author` / `subject` / `fulltext`。`all` 是常规跨字段检索；`fulltext` 映射到 `ftext`，并非“只返回有全文的记录”。
- `scope=articles` 对应网页“文章”检索范围，包括 CDI 中的论文、图书、学位论文等；只要期刊论文时另设 `resource_type=articles`。`all` 包括本地电子书刊，`books_journals` 只查本地书刊。此项目不接入另一个 OPAC 门户的借阅／预约功能。
- `match=contains` 是上游检索引擎的检索语义；可使用引号短语或 `exact`。半角逗号和分号会替换为空格，并返回实际发送的 `effective_query`。
- `sort`: `relevance` / `newest` / `oldest` / `title` / `author`。
- `language`: 三字母代码，例如 `eng`、`chi`。
- `full_text_available_only=true` 筛选图书馆标记可获取全文的记录。默认 `false`，也发现没有订购全文的相关文献。
- 每页最多 20 条，使用 `next_offset` 翻页；上游 CDI 限制在前 2000 条内，需要更多结果时缩小检索范围。

## 证据与全文

每条文献带来源链接、抓取时间、DOI、摘要来源字段和可用性信息：

| 字段 | 含义 |
| --- | --- |
| `abstract` | 来源明确提供的 `pnx.addata.abstract`；缺失返回 `null` |
| `description` | 来源描述；不自动标成摘要 |
| `snippets` | 来源检索片段，可能来自摘要或其他字段；不保证是正文命中片段 |
| `truncated` | 文本超过输出上限时显式标记；单篇摘要最多 20,000 字符 |
| `full_text_available` | 图书馆记录中的全文可用性；不是一次实际下载验证 |
| `links` | PDF、HTML、图书馆解析器和 DOI 链接，均带 `access_verified=false` |
| `full_text_retrieved` | 此版本始终为 `false`，没有下载或读取出版社原文 |
| `partial` | 上游超时或异常导致结果不完整，不能据此判断没有文献 |

**全文检索利用的是上游全文索引，不等于获取整篇全文。** 该索引覆盖范围取决于各数据库和馆方配置，不能保证覆盖复旦全部资源。出版社原文仍可能要求校园网络或用户自行登录。MCP 提供全文入口，暂不自动下载 PDF 或对整篇原文做问答。

服务器不读取浏览器 Cookie 或学校凭据；匿名访客令牌仅保存在内存中并自动刷新。请求至少间隔一秒，相同成功结果缓存五分钟，最多缓存 64 个响应；部分结果不缓存。遇到限流或临时服务错误有限重试，登录／重定向响应显式报错。

默认直连图书馆；如需使用 `HTTPS_PROXY` 等环境代理，在 MCP 服务器环境变量中设置 `FUDAN_LIBRARY_TRUST_ENV=true`。始终启用 TLS 证书验证。

## 验证与维护

```sh
git clone https://github.com/LvDAO/fudan-library-mcp.git
cd fudan-library-mcp
uv sync --frozen --group dev
uv run --frozen pytest -q
uv run --frozen ruff check src tests scripts
uv build
uv run --frozen python scripts/verify_install.py --from dist/fudan_library_mcp-0.1.0-py3-none-any.whl
uv run --frozen python scripts/live_smoke.py
```

pytest、ruff 和安装握手检查不访问图书馆；`live_smoke.py` 会通过真实 MCP stdio 客户端执行少量在线查询，生成 [`docs/live-verification.json`](docs/live-verification.json)。当日核实普通检索和全文检索对同一个测试词分别返回 **128,376** 和 **469,266** 条（均使用有全文过滤）；这是历史验证记录，数量会随上游索引变化。

GitHub Actions 在 Windows 和 Linux 上测试 Python 3.11 / 3.13，并验证安装后的 wheel 能完成 MCP 握手。推送 `v*` 标签会构建 Release，附带 wheel、源码包与 SHA-256 校验文件。维护发布步骤见 [`docs/RELEASING.md`](docs/RELEASING.md)。

文献检索和详情使用复旦现有 Primo Classic REST 服务。接口或索引发生变化时需要维护适配层；实现依据与端点说明见 [`docs/backend.md`](docs/backend.md)。

本项目以 [MIT License](LICENSE) 发布。软件许可证不改变文献、摘要及数据库内容的权利归属。
