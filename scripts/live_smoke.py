"""Opt-in real MCP/stdio smoke test; performs a small number of anonymous searches."""

import asyncio
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main():
    report = {"checked_at": datetime.now(UTC).isoformat(), "checks": []}
    params = StdioServerParameters(command=sys.executable, args=["-m", "fudan_library_mcp"])
    async with (
        stdio_client(params) as (read, write),
        ClientSession(read, write, read_timeout_seconds=timedelta(seconds=180)) as session,
    ):
        await session.initialize()

        async def call(name, args):
            result = await session.call_tool(name, args)
            if result.isError:
                raise RuntimeError(result.content)
            data = result.structuredContent
            assert isinstance(data, dict), name
            return data

        status = await call("library_status", {})
        assert status["status"] == "ok"
        report["checks"].append({"tool": "library_status", "status": "ok"})
        query = "graph neural network"
        base = {"query": query, "limit": 2, "full_text_available_only": True}
        ordinary = await call("search_literature", base)
        fulltext = await call("search_fulltext", base)
        assert ordinary["documents"] and fulltext["documents"]
        assert not ordinary["partial"] and not fulltext["partial"]
        for name, data in [("regular", ordinary), ("fulltext", fulltext)]:
            report["checks"].append(
                {
                    "mode": name,
                    "query": query,
                    "total": data["total"],
                    "effective_query": data["effective_query"],
                    "abstracts": sum(d["abstract"] is not None for d in data["documents"]),
                    "source_url": data["source_url"],
                }
            )
        assert ordinary["total"] != fulltext["total"], "Full-text result sets need investigation"
        page2 = await call("search_literature", base | {"offset": 2})
        assert page2["documents"] and not page2["partial"]
        assert page2["documents"][0]["record_id"] != ordinary["documents"][0]["record_id"]
        report["checks"].append({"test": "pagination", "status": "ok"})
        refs = [
            {"record_id": d["record_id"], "context": d["context"]} for d in ordinary["documents"]
        ]
        single = await call("get_document", refs[0])
        assert single["abstract"] and single["record_id"] == refs[0]["record_id"]
        batch = await call("get_documents", {"references": refs})
        assert all(item["document"] for item in batch["items"])
        report["checks"].append(
            {
                "test": "single_and_batch_details",
                "status": "ok",
                "example_title": single["title"],
                "doi": single["doi"],
            }
        )
        chinese = await call("search_literature", {"query": "人工智能", "limit": 2})
        assert chinese["documents"] and not chinese["partial"]
        report["checks"].append({"test": "chinese", "total": chinese["total"]})
        filtered = await call(
            "search_literature",
            base
            | {
                "year_from": 2023,
                "year_to": 2024,
                "peer_reviewed_only": True,
                "sort": "newest",
                "language": "eng",
                "resource_type": "articles",
            },
        )
        assert filtered["documents"] and not filtered["partial"]
        assert all(
            2023 <= d["year"] <= 2024 and d["peer_reviewed"] and d["full_text_available"]
            for d in filtered["documents"]
        )
        assert filtered["documents"][0]["date"] >= filtered["documents"][-1]["date"]
        report["checks"].append(
            {
                "test": "filters",
                "total": filtered["total"],
                "years": [d["year"] for d in filtered["documents"]],
            }
        )
        empty = await call(
            "search_fulltext", {"query": "zzqxfudanvalidation0a9e8b7c6d5", "limit": 1}
        )
        assert empty["total"] == 0 and empty["documents"] == [] and not empty["partial"]
        report["checks"].append({"test": "fulltext_zero_results", "status": "ok"})
    Path("docs").mkdir(exist_ok=True)
    Path("docs/live-verification.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


asyncio.run(main())
