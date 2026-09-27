"""Verify an installed artifact through MCP, from outside the source checkout."""

import argparse
import asyncio
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

EXPECTED_TOOLS = {
    "search_literature",
    "search_fulltext",
    "get_document",
    "get_documents",
    "library_status",
}


async def verify(source: str, live: bool):
    if Path(source).is_file():
        source = str(Path(source).resolve())
    uvx = shutil.which("uvx")
    if not uvx:
        raise RuntimeError("Install uv and make uvx available on PATH first.")
    args = ["--no-config", "--from", source, "fudan-library-mcp"]
    report = {"checked_at": datetime.now(UTC).isoformat(), "source": source}
    with tempfile.TemporaryDirectory(prefix="fudan-mcp-install-") as directory:
        completed = await asyncio.to_thread(
            subprocess.run,
            [uvx, *args, "--version"],
            cwd=directory,
            env={**os.environ, "UV_PYTHON": sys.executable},
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=300,
            check=True,
        )
        report["version"] = completed.stdout.strip()
        params = StdioServerParameters(
            command=uvx, args=args, cwd=directory, env={"UV_PYTHON": sys.executable}
        )
        async with (
            stdio_client(params) as (read, write),
            ClientSession(read, write, read_timeout_seconds=timedelta(seconds=180)) as session,
        ):
            await session.initialize()
            tools = await session.list_tools()
            names = {tool.name for tool in tools.tools}
            if names != EXPECTED_TOOLS:
                raise RuntimeError(f"Unexpected tool list: {names}")
            if not all(tool.outputSchema and tool.annotations.readOnlyHint for tool in tools.tools):
                raise RuntimeError("Missing tool output schema or read-only annotation")
            prompt = await session.get_prompt(
                "screen_literature", {"research_question": "测试安装"}
            )
            if "测试安装" not in prompt.messages[0].content.text:
                raise RuntimeError("MCP prompt did not preserve Unicode")
            report["tools"] = sorted(names)
            report["prompt"] = "screen_literature"
            if live:
                checks = []
                for name, arguments in [
                    ("library_status", {}),
                    ("search_literature", {"query": "graph neural network", "limit": 2}),
                    ("search_fulltext", {"query": "graph neural network", "limit": 2}),
                ]:
                    result = await session.call_tool(name, arguments)
                    data = result.structuredContent
                    if result.isError or not isinstance(data, dict):
                        raise RuntimeError(f"{name} failed: {result.content}")
                    if name == "library_status":
                        if data.get("status") != "ok":
                            raise RuntimeError("Library connection not healthy")
                        checks.append({"tool": name, "status": "ok"})
                    else:
                        if data["partial"] or not data["documents"]:
                            raise RuntimeError(f"{name} did not return complete search results")
                        checks.append(
                            {
                                "tool": name,
                                "total": data["total"],
                                "effective_query": data["effective_query"],
                                "abstracts": sum(
                                    d["abstract"] is not None for d in data["documents"]
                                ),
                            }
                        )
                report["live_checks"] = checks
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from", dest="source", required=True, help="Wheel path or Git source URL")
    parser.add_argument("--live", action="store_true", help="Also query the real library")
    options = parser.parse_args()
    asyncio.run(verify(options.source, options.live))
