# Security

This is an independent community project, not an official Fudan University service.

## Runtime boundaries

- Local stdio only: the entry point does not listen on an HTTP port. The five tools perform read-only queries; none executes shell commands, reads arbitrary local files, or downloads publisher documents.
- Outbound library requests use a fixed HTTPS origin and fixed endpoint families. Document IDs are validated, `.`/`..` are rejected, redirects are not followed, and TLS verification stays enabled.
- Guest tokens are obtained from the anonymous library endpoint and kept in memory. The server does not read browser cookies or school credentials. Authentication headers and raw error bodies are not returned to the model.
- Search terms and requested document IDs are sent to the library service. Use the service accordingly for confidential research topics. Environment proxies are opt-in via `FUDAN_LIBRARY_TRUST_ENV=true`.
- Requests are rate limited and retried at most three times per HTTP operation. Each transfer has a 30-second deadline and 4 MiB response limit; unexpected compression is rejected before decoding. Cache limits are 64 entries and 16 MiB measured as source-response bytes, not total Python process memory.
- Publisher links are **unverified source data**. Obvious local IPs/hostnames, credentials in URLs, malformed URLs, and nonstandard ports are filtered. The server never follows these links. DNS resolution and publisher redirects are not checked, so this filter is not an access guarantee.
- Literature titles, abstracts, descriptions, and snippets remain untrusted content. Server instructions and the screening prompt tell the calling Agent to treat them as evidence only, never as commands. This reduces exposure but cannot guarantee that every model/client resists prompt injection.

## Installation and release

The recommended Agent path uses a versioned source checkout with `uv sync --frozen --no-dev`, retaining audited dependency versions and hashes. The `uvx --from` convenience path pins server source but resolves transitive dependencies within declared ranges. Installing any MCP server runs local code; inspect the selected source and use a trusted runtime.

GitHub Actions are pinned to commit SHAs. CI and release build/test jobs have read-only repository permissions. A separate publish job downloads the built artifacts, checks their hashes, and uses repository write permission only to publish the release; it does not install or execute the Python package. Release artifacts include SHA-256 hashes; those are integrity checks, not independent signatures. Never move a published release tag.

## Review and reporting

The 2026-09-27 review covered source, locked runtime dependencies, repository credential patterns, installation guidance, and CI/release permissions. [Review results and reproduction steps](docs/security-review.md) describe exactly what was checked. CI and releases run dependency auditing and static analysis in addition to regression tests. A passing scan means no findings under those checks at that time, not proof of absence of vulnerabilities.

Report reproducible problems through [GitHub Issues](https://github.com/LvDAO/fudan-library-mcp/issues). Do not include passwords, tokens, private queries, or private document contents. For sensitive reports, use the repository's private vulnerability reporting option if available; do not post exploit details containing private data publicly.
