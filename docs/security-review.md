# Security review — 2026-09-27

Scope: version 0.1.1 runtime source, locked runtime dependencies, checked-in files, installation instructions, and GitHub CI/release workflows. This is a source review and automated scan, not a penetration test of Fudan's services.

## Findings addressed

| Finding | Change | Verification |
| --- | --- | --- |
| Record IDs allowed standalone `.` and `..`, which HTTP clients may normalize into other paths on the fixed host | Reject both special segments before a request | Input validation regression tests |
| HTTP response bodies had no byte cap; read timeouts alone allowed indefinite slow transfers | Stream with a 4 MiB cap and a 30-second total transfer deadline; request identity encoding and reject unexpected compression before reading | Oversized declared/chunked bodies, early close, compression, and slow-stream tests |
| Cache entry count alone did not bound large responses | Add a 16 MiB source-response-byte budget alongside the 64-entry limit | Eviction regression test |
| Unverified outgoing document links could include credentials or obvious local targets | Reject credential-bearing, local literal/hostname, malformed, and nonstandard-port links | URL validation regression tests |
| The release build shared a job with repository write permissions | Separate read-only build/test and write-enabled publish jobs | Workflow review; pinned action SHAs; checksum verification in publish job |
| Convenience `uvx` installs resolve dependency ranges again | Make versioned checkout plus frozen lockfile the default Agent installation path | Real stdio install verification using `--checkout` |

The original version already used a fixed HTTPS origin, disabled redirects, kept guest tokens in memory, provided read-only tools, and warned Agents to treat source content as untrusted data. These boundaries are retained.

## Scan results

- `pip-audit 2.10.1`: no known advisories in the 30 locked runtime packages applicable to the reviewed Windows environment, as of the review date. CI also checks the lockfile's runtime dependencies on Linux. No vulnerability IDs were suppressed.
- `bandit 1.9.4`: no findings in `src/`, with no scan exclusions or `nosec` suppressions.
- Tracked-file pattern review: no real GitHub tokens, private keys, AWS access keys, or machine-specific home paths found. Test authentication values are synthetic.
- 55 regression tests passed locally, including real MCP protocol discovery and malicious-input/resource-limit cases.
- A real library check and both ordinary/full-text-index searches passed after hardening, through the actual stdio client using the frozen checkout.

## Reproduce

```sh
uv sync --frozen --group security
uv run --frozen --group security bandit -r src
uv export --frozen --no-dev --no-emit-project --output-file runtime-requirements.txt
uv run --frozen --group security pip-audit -r runtime-requirements.txt --disable-pip --no-deps --require-hashes --strict
uv run --frozen pytest -q
```

The dependency audit needs network access to PyPI's advisory data. Scan dates and scope matter: an empty finding list cannot guarantee absence of vulnerabilities. Publisher links remain unverified; prompt-injection resistance also depends on the calling model/client. See [SECURITY.md](../SECURITY.md) for residual boundaries.
