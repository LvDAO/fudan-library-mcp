import copy

import httpx
import pytest
from pydantic import ValidationError

from fudan_library_mcp.models import DocumentRef, SearchRequest
from fudan_library_mcp.primo import (
    LibraryError,
    PrimoClient,
    Settings,
    clean,
    normalize_document,
    search_params,
    search_url,
)


def client(handler):
    return PrimoClient(Settings(request_interval=0), transport=httpx.MockTransport(handler))


def response(record, total=30, **info):
    return {"info": {"total": total, **info}, "docs": [record], "facets": []}


def test_evidence_and_links_are_not_misrepresented(record):
    doc = normalize_document(record, "2026-09-27T00:00:00+00:00")
    assert doc.title == "测试 Graph & Text"
    assert doc.abstract.text.endswith("x < 2.")
    assert doc.abstract.source_field == "pnx.addata.abstract"
    assert doc.description is None
    assert doc.snippets[0].kind == "search_snippet"
    assert doc.full_text_available and doc.open_access and doc.peer_reviewed
    assert not doc.full_text_retrieved
    assert {link.kind for link in doc.links} == {"pdf", "resolver", "doi"}
    assert all(not link.access_verified for link in doc.links)
    assert doc.authors == ["Li, A", "Wang, B"]
    assert doc.year == 2024


def test_missing_abstract_does_not_promote_description_or_snippet(record):
    del record["pnx"]["addata"]["abstract"]
    doc = normalize_document(record, "now")
    assert doc.abstract is None
    assert doc.description.kind == "description"
    assert doc.snippets
    assert doc.warnings
    record["delivery"] = {}
    record["pnx"]["facets"] = {}
    doc = normalize_document(record, "now")
    assert doc.full_text_available is None
    assert doc.open_access is None
    assert doc.peer_reviewed is None


def test_long_abstract_is_explicitly_truncated(record):
    record["pnx"]["addata"]["abstract"] = ["x" * 25000]
    doc = normalize_document(record, "now")
    assert len(doc.abstract.text) == 20000
    assert doc.abstract.truncated
    assert any("截断" in w for w in doc.warnings)


def test_clean_preserves_words_and_removes_executable_markup():
    assert clean("<script>bad()</script><p>A &amp; B</p><p>C</p>") == "A & B C"


def test_fulltext_and_availability_are_independent():
    fulltext = search_params(SearchRequest(query="中文 graph", field="fulltext"))
    available = search_params(SearchRequest(query="中文 graph", full_text_available_only=True))
    assert fulltext["q"] == "ftext,contains,中文 graph"
    assert fulltext["pcAvailability"] == "true"
    assert available["q"] == "any,contains,中文 graph"
    assert available["pcAvailability"] == "false"
    assert "online_resources" in available["qInclude"]
    assert "searchInFulltextUserSelection" not in fulltext


def test_filters_and_query_separators():
    request = SearchRequest(
        query='"Graph, text"; OR 中文',
        year_from=2020,
        year_to=2024,
        language="chi",
        peer_reviewed_only=True,
        resource_type="articles",
    )
    params = search_params(request)
    assert (
        params["q"] == 'any,contains,"Graph text" OR 中文;dr_s,exact,20200101;dr_e,exact,20241231'
    )
    assert (
        params["qInclude"]
        == "facet_tlevel,exact,peer_reviewed|,|facet_lang,exact,chi|,|facet_rtype,exact,articles"
    )
    assert "facet=lang%2Cinclude%2Cchi" in search_url(request, params)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"query": " "},
        {"query": "*"},
        {"query": "a\nb"},
        {"query": "q", "limit": 21},
        {"query": "q", "offset": 1999, "limit": 2},
        {"query": "q", "year_from": 2025, "year_to": 2020},
        {"query": "q", "field": "fulltext", "scope": "books_journals"},
    ],
)
def test_invalid_search_rejected(kwargs):
    with pytest.raises(ValidationError):
        SearchRequest(**kwargs)


@pytest.mark.parametrize(
    "record_id", ["../../secrets", "https://example.com", "id?token=1", "id%2Ftest"]
)
def test_external_urls_cannot_be_used_as_document_ids(record_id):
    with pytest.raises(ValidationError):
        DocumentRef(record_id=record_id)


async def test_anonymous_auth_search_cache_and_paging(record):
    requests = []

    def handler(request):
        requests.append(request)
        if "guestJwt" in request.url.path:
            assert "authorization" not in request.headers
            return httpx.Response(200, text="abc.def.ghi")
        assert request.headers["authorization"] == "Bearer abc.def.ghi"
        assert request.url.params["q"] == "ftext,contains,test"
        assert request.url.params["offset"] == "10"
        return httpx.Response(200, json=response(record))

    c = client(handler)
    try:
        req = SearchRequest(query="test", field="fulltext", offset=10, limit=1)
        a, b = await c.search(req), await c.search(req)
        assert a.returned == 1 and a.next_offset == 11
        assert a.retrieved_at == b.retrieved_at
        assert len(requests) == 2
        assert not a.partial
    finally:
        await c.aclose()


async def test_token_refresh_once_and_no_token_in_error():
    counts = {"guest": 0, "search": 0}

    def handler(request):
        if "guestJwt" in request.url.path:
            counts["guest"] += 1
            return httpx.Response(200, text="abc.def.secret")
        counts["search"] += 1
        return httpx.Response(403, text="abc.def.secret")

    c = client(handler)
    try:
        with pytest.raises(LibraryError) as exc:
            await c.search(SearchRequest(query="test"))
        assert counts == {"guest": 2, "search": 2}
        assert "secret" not in str(exc.value)
    finally:
        await c.aclose()


async def test_partial_results_are_marked_and_never_cached(record):
    calls = []

    def handler(request):
        if "guestJwt" in request.url.path:
            return httpx.Response(200, text="abc.def.ghi")
        calls.append(request)
        return httpx.Response(
            200, json=response(record, errorDetails={"errorMessages": ["Partial results"]})
        )

    c = client(handler)
    try:
        for _ in range(2):
            result = await c.search(SearchRequest(query="test"))
            assert result.partial and result.warnings
        assert len(calls) == 2
    finally:
        await c.aclose()


@pytest.mark.parametrize(
    "payload", [{}, {"info": {"total": 0}}, {"info": None, "docs": []}, {"errorsExist": True}]
)
async def test_invalid_response_is_not_zero_results(payload):
    c = client(
        lambda req: (
            httpx.Response(200, text="abc.def.ghi")
            if "guestJwt" in req.url.path
            else httpx.Response(200, json=payload)
        )
    )
    try:
        with pytest.raises(LibraryError):
            await c.search(SearchRequest(query="test"))
    finally:
        await c.aclose()


async def test_redirect_is_not_followed():
    hosts = []

    def handler(request):
        hosts.append(request.url.host)
        if "guestJwt" in request.url.path:
            return httpx.Response(200, text="abc.def.ghi")
        return httpx.Response(302, headers={"Location": "https://other.example/login"})

    c = client(handler)
    try:
        with pytest.raises(LibraryError, match="重定向"):
            await c.search(SearchRequest(query="test"))
        assert len(set(hosts)) == 1
    finally:
        await c.aclose()


async def test_transient_error_retries_without_suppressing_failure(monkeypatch, record):
    async def no_sleep(_):
        pass

    monkeypatch.setattr("fudan_library_mcp.primo.asyncio.sleep", no_sleep)
    count = 0

    def handler(request):
        nonlocal count
        if "guestJwt" in request.url.path:
            return httpx.Response(200, text="abc.def.ghi")
        count += 1
        return httpx.Response(503) if count == 1 else httpx.Response(200, json=response(record))

    c = client(handler)
    try:
        assert (await c.search(SearchRequest(query="test"))).returned == 1
        assert count == 2
    finally:
        await c.aclose()


async def test_bad_record_is_partial_and_actual_page_offset_is_preserved(record):
    malformed = copy.deepcopy(record)
    del malformed["pnx"]["control"]["recordid"]
    payload = {"info": {"total": 10}, "docs": [malformed, record]}
    searches = []

    def handler(req):
        if "guestJwt" in req.url.path:
            return httpx.Response(200, text="abc.def.ghi")
        searches.append(req)
        return httpx.Response(200, json=payload)

    c = client(handler)
    try:
        for _ in range(2):
            result = await c.search(SearchRequest(query="test", limit=2))
            assert result.partial and result.returned == 1 and result.next_offset == 2
        assert len(searches) == 2  # Parsing failures must not remain in the success cache.
    finally:
        await c.aclose()


async def test_detail_uses_context_and_full_record_id(record):
    def handler(request):
        if "guestJwt" in request.url.path:
            return httpx.Response(200, text="abc.def.ghi")
        assert request.url.path.endswith("/PC/TN_test_123")
        return httpx.Response(200, json=record)

    c = client(handler)
    try:
        doc = await c.get_document(DocumentRef(record_id="TN_test_123"))
        assert doc.abstract and doc.record_id == "TN_test_123"
    finally:
        await c.aclose()
