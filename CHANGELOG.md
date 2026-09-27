# Changelog

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
