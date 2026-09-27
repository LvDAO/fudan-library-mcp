# 功能与使用

[安装指南](INSTALL.md) · [安全说明](../SECURITY.md)

## 可以做什么

| MCP 工具 | 功能 |
| --- | --- |
| `search_literature` | 常规检索或按题名、摘要、作者、主题、全文索引检索；支持年份、语言、类型、同行评议、全文可用性过滤与分页 |
| `search_fulltext` | 使用 Primo 的 **`ftext` 全文字段**检索，查找正文中的具体术语、方法或数据集 |
| `get_document` | 根据检索返回的 `record_id` 和 `context` 获取单篇详情、可用摘要、DOI、全文入口 |
| `get_documents` | 批量获取最多 10 篇文献的详情；逐项返回成功或失败 |
| `library_status` | 检查匿名连接、检索范围和能力边界 |

另提供 `screen_literature` MCP 提示词，输入研究问题与纳入／排除标准，引导 LLM 完成“检索 → 全文索引补充 → 去重 → 摘要初筛 → 带来源的阅读清单”。相关性判断由调用方 LLM 完成，服务器不使用关键词分数冒充语义筛选。

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

服务器不读取浏览器 Cookie 或学校凭据；匿名访客令牌仅保存在内存中并自动刷新。请求至少间隔一秒，每次传输限时 30 秒、响应最多 4 MiB。相同成功结果缓存五分钟，最多 64 个响应且原始响应合计不超过 16 MiB；部分结果不缓存。遇到限流或临时服务错误有限重试，登录／重定向响应显式报错。

默认直连图书馆；如需使用 `HTTPS_PROXY` 等环境代理，在 MCP 服务器环境变量中设置 `FUDAN_LIBRARY_TRUST_ENV=true`。始终启用 TLS 证书验证。

## 验证与维护

```sh
git clone https://github.com/LvDAO/fudan-library-mcp.git
cd fudan-library-mcp
uv sync --frozen --group dev
uv run --frozen pytest -q
uv run --frozen ruff check src tests scripts
uv build
uv run --frozen python scripts/verify_install.py --from dist/fudan_library_mcp-0.1.1-py3-none-any.whl
uv run --frozen python scripts/live_smoke.py
```

pytest、ruff 和安装握手检查不访问图书馆；`live_smoke.py` 会通过真实 MCP stdio 客户端执行少量在线查询，生成 [`docs/live-verification.json`](live-verification.json)。当日核实普通检索和全文检索对同一个测试词分别返回 **128,376** 和 **469,266** 条（均使用有全文过滤）；这是历史验证记录，数量会随上游索引变化。

GitHub Actions 在 Windows 和 Linux 上测试 Python 3.11 / 3.13，并验证安装后的 wheel 能完成 MCP 握手。推送 `v*` 标签会构建 Release，附带 wheel、源码包与 SHA-256 校验文件。维护发布步骤见 [`docs/RELEASING.md`](RELEASING.md)。

文献检索和详情使用复旦现有 Primo Classic REST 服务。接口或索引发生变化时需要维护适配层；实现依据与端点说明见 [`docs/backend.md`](backend.md)。

本项目以 [MIT License](../LICENSE) 发布。软件许可证不改变文献、摘要及数据库内容的权利归属。
