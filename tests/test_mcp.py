import sys
from datetime import timedelta

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def test_stdio_handshake_schemas_prompt_and_invalid_call():
    params = StdioServerParameters(command=sys.executable, args=["-m", "fudan_library_mcp"])
    async with (
        stdio_client(params) as (read, write),
        ClientSession(read, write, read_timeout_seconds=timedelta(seconds=20)) as session,
    ):
        await session.initialize()
        result = await session.list_tools()
        tools = {tool.name: tool for tool in result.tools}
        assert set(tools) == {
            "search_literature",
            "search_fulltext",
            "get_document",
            "get_documents",
            "library_status",
        }
        assert all(t.annotations.readOnlyHint for t in tools.values())
        assert tools["search_literature"].inputSchema["properties"]["limit"]["maximum"] == 20
        assert "ctx" not in tools["search_literature"].inputSchema["properties"]
        assert tools["search_literature"].outputSchema
        assert tools["library_status"].outputSchema
        prompt = await session.get_prompt("screen_literature", {"research_question": "测试中文"})
        assert "测试中文" in prompt.messages[0].content.text
        result = await session.call_tool("search_literature", {"query": "test", "limit": 21})
        assert result.isError  # No network request for invalid arguments.
