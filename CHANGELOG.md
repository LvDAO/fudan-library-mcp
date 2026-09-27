# Changelog

## 0.1.1 — 2026-09-27

- Reject `.` and `..` record IDs to prevent path normalization outside the document endpoint.
- Limit each HTTP response to 4 MiB and each transfer to 30 seconds; reject unexpected compression before decoding.
- Bound the cache by both entry count and total source-response bytes (16 MiB).
- Filter credential-bearing, local-address, malformed, and nonstandard-port document links.
- Add security regression tests, dependency auditing, and Bandit checks to CI and releases.
- Reduce the homepage to badges, a short introduction, and one copyable instruction for an Agent; move details into dedicated documentation.

## 0.1.0 — 2026-09-27

Initial release of the Fudan Library MCP server (stdio).

- Search literature in Chinese or English by title, abstract, author, subject, or full-text index.
- Query the verified Primo `ftext` field with `search_fulltext`.
- Retrieve individual or batched records with available abstracts, DOI, provenance, and full-text links.
- Filter by date, language, resource type, peer review, and full-text availability; paginate results.
- Guide evidence-based screening with the `screen_literature` prompt.
- Use anonymous guest authentication, rate limiting, bounded retries, and bounded caching.
- Install from a versioned GitHub source or release wheel using `uvx`.

Full-text search queries the upstream index. This version does not download or read publisher full text.
