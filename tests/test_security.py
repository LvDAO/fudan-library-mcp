import asyncio
import json

import httpx
import pytest
from pydantic import ValidationError

from fudan_library_mcp.models import DocumentRef, SearchRequest
from fudan_library_mcp.primo import LibraryError, PrimoClient, Settings, web_url


@pytest.mark.parametrize("record_id", [".", ".."])
def test_dot_segments_cannot_escape_document_endpoint(record_id):
    with pytest.raises(ValidationError):
        DocumentRef(record_id=record_id)


@pytest.mark.parametrize(
    "url",
    [
        "javascript:alert(1)",
        "file:///etc/passwd",
        "https://@example.com/x",
        "https://user:password@example.com",
        "http://127.0.0.1/x",
        "http://[::1]/",
        "http://169.254.169.254/latest/meta-data",
        "http://10.0.0.1/",
        "http://localhost/",
        "http://service.internal/",
        "http://printer.local/",
        "https://example.com:bad/",
        "https://example.com:8080/",
        "https://example.com\\@localhost/",
        "https://example.com/\r\nx",
        "http://2130706433/",
        "http://0177.0.0.1/",
        "http://0x7f.0.0.1/",
    ],
)
def test_unsafe_links_are_not_exposed_as_document_links(url):
    assert web_url(url) is None


def test_publisher_links_remain_unmodified():
    url = "https://doi.org/10.1000/example?lang=en&source=library"
    assert web_url(url) == url


class ChunkStream(httpx.AsyncByteStream):
    def __init__(self, chunks):
        self.chunks = chunks
        self.closed = False
        self.read_count = 0

    async def __aiter__(self):
        for chunk in self.chunks:
            self.read_count += 1
            yield chunk

    async def aclose(self):
        self.closed = True


@pytest.mark.parametrize("with_length", [True, False])
async def test_oversized_body_stops_reading_and_closes_response(with_length):
    stream = ChunkStream([b"x" * 65536] * 3)
    headers = {"Content-Length": "196608"} if with_length else {}
    c = PrimoClient(
        Settings(request_interval=0, max_response_bytes=65536),
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, headers=headers, stream=stream)
        ),
    )
    try:
        with pytest.raises(LibraryError, match="大小上限"):
            await c.status()
        assert stream.closed
        assert stream.read_count == (0 if with_length else 2)
        assert not c._cache
    finally:
        await c.aclose()


async def test_unexpected_compression_rejected_before_decompression():
    stream = ChunkStream([b"not-a-gzip-file"])
    c = PrimoClient(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, headers={"Content-Encoding": "gzip"}, stream=stream)
        )
    )
    try:
        with pytest.raises(LibraryError, match="压缩"):
            await c.status()
        assert stream.closed and stream.read_count == 0
    finally:
        await c.aclose()


async def test_total_deadline_bounds_slow_stream():
    class SlowStream(ChunkStream):
        async def __aiter__(self):
            await asyncio.sleep(1)
            yield b"late"

    streams = []

    def handler(_):
        stream = SlowStream([])
        streams.append(stream)
        return httpx.Response(200, stream=stream)

    c = PrimoClient(
        Settings(timeout=0.02, request_interval=0), transport=httpx.MockTransport(handler)
    )
    try:
        with pytest.raises(LibraryError, match="无法连接"):
            await asyncio.wait_for(c.status(), timeout=1)
        assert len(streams) == 3 and all(s.closed for s in streams)
    finally:
        await c.aclose()


async def test_cache_byte_budget_evicts_old_searches(record):
    payload = {"info": {"total": 1}, "docs": [record]}
    size = len(json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode())
    calls = []

    def handler(req):
        if "guestJwt" in req.url.path:
            return httpx.Response(200, text="abc.def.ghi")
        calls.append(req)
        return httpx.Response(200, json=payload)

    c = PrimoClient(
        Settings(request_interval=0, max_cache_bytes=size + 1),
        transport=httpx.MockTransport(handler),
    )
    try:
        for query in ["first", "second", "first"]:
            await c.search(SearchRequest(query=query))
        assert len(calls) == 3
        assert len(c._cache) == 1 and c._cache_bytes <= size + 1
    finally:
        await c.aclose()
