"""Anonymous Primo Classic REST client. No account or browser state is read."""

import asyncio
import json
import os
import re
import time
from collections import OrderedDict
from dataclasses import dataclass
from datetime import UTC, datetime
from html.parser import HTMLParser
from ipaddress import ip_address
from typing import Any
from urllib.parse import quote, urlencode, urlsplit

import httpx

from .models import Document, DocumentLink, DocumentRef, EvidenceText, SearchRequest, SearchResult

ORIGIN = "https://fudan-primo.hosted.exlibrisgroup.com.cn"
REST = "/primo_library/libweb/webservices/rest"
SEARCH = REST + "/primo-explore/v1/pnxs"
SCOPES = {
    "articles": ("digital_tab", "article_scope"),
    "all": ("default_tab", "default_scope"),
    "books_journals": ("book_journal", "book_journal"),
}
FIELDS = {
    "all": "any",
    "title": "title",
    "abstract": "abstract",
    "author": "creator",
    "subject": "sub",
    "fulltext": "ftext",
}
SORTS = {
    "relevance": "rank",
    "newest": "date",
    "oldest": "date2",
    "title": "title",
    "author": "author",
}


class LibraryError(Exception):
    """Actionable, credential-free upstream error safe to return to an MCP client."""


@dataclass(frozen=True)
class Settings:
    timeout: float = 30.0
    request_interval: float = 1.0
    cache_ttl: float = 300.0
    trust_env: bool = False
    max_response_bytes: int = 4 * 1024 * 1024
    max_cache_bytes: int = 16 * 1024 * 1024

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(trust_env=os.getenv("FUDAN_LIBRARY_TRUST_ENV", "false").lower() == "true")


def now() -> str:
    return datetime.now(UTC).isoformat()


class _TextParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.hidden += 1
        elif tag in {"br", "p", "div", "li"}:
            self.parts.append(" ")

    def handle_endtag(self, tag):
        if tag in {"script", "style"}:
            self.hidden = max(0, self.hidden - 1)
        elif tag in {"p", "div", "li"}:
            self.parts.append(" ")

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def clean(value: str) -> str:
    parser = _TextParser()
    parser.feed(value)
    return re.sub(r"\s+", " ", "".join(parser.parts)).strip()


def strings(value: Any) -> list[str]:
    values = value if isinstance(value, list) else [value]
    return list(dict.fromkeys(clean(v) for v in values if isinstance(v, str) and clean(v)))


def first(value: Any) -> str | None:
    return next(iter(strings(value)), None)


def web_url(value: str) -> str | None:
    # These URLs are returned as unverified data, never fetched by this server.
    if len(value) > 8192 or re.search(r"[\s\\\x00-\x1f\x7f]", value):
        return None
    try:
        parsed = urlsplit(value)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.port not in {None, 80, 443}
        ):
            return None
        host = parsed.hostname.rstrip(".").lower()
        try:
            if not ip_address(host).is_global:
                return None
        except ValueError:
            if (
                "." not in host
                or host.endswith((".localhost", ".local", ".internal"))
                or not re.fullmatch(r"[a-z0-9.-]+", host)
                or all(re.fullmatch(r"(?:0x[0-9a-f]+|[0-9]+)", part) for part in host.split("."))
            ):
                return None
        return value
    except ValueError:
        pass
    return None


def evidence(values: Any, field: str, kind: str, max_chars: int) -> EvidenceText | None:
    text = "\n\n".join(strings(values))
    if not text:
        return None
    return EvidenceText(
        text=text[:max_chars], source_field=field, kind=kind, truncated=len(text) > max_chars
    )


def normalize_document(raw: dict, timestamp: str) -> Document:
    if not isinstance(raw, dict):
        raise LibraryError("图书馆返回的文献不是有效对象。")
    pnx = raw.get("pnx")
    if not isinstance(pnx, dict):
        raise LibraryError("图书馆返回了不兼容的文献数据（缺少 PNX）。")
    for section in (
        "display",
        "addata",
        "search",
        "control",
        "facets",
        "links",
        "sort",
        "delivery",
    ):
        if section in pnx and not isinstance(pnx[section], dict):
            raise LibraryError("图书馆文献字段格式发生变化。")
    if "delivery" in raw and not isinstance(raw["delivery"], dict):
        raise LibraryError("图书馆文献获取信息格式发生变化。")
    display, addata = pnx.get("display", {}), pnx.get("addata", {})
    search, control = pnx.get("search", {}), pnx.get("control", {})
    delivery, facets = raw.get("delivery", {}), pnx.get("facets", {})
    record_id = first(control.get("recordid"))
    title = first(display.get("title")) or first(addata.get("atitle"))
    if not record_id or not title:
        raise LibraryError("图书馆返回的文献缺少记录 ID 或题名。")
    context = raw.get("context") or ("PC" if record_id.startswith("TN_") else "L")
    if context not in {"PC", "L"}:
        raise LibraryError("图书馆返回了不支持的文献来源类型。")
    abstract = evidence(addata.get("abstract"), "pnx.addata.abstract", "abstract", 20000)
    description = evidence(
        display.get("description"), "pnx.display.description", "description", 20000
    )
    if not description and not abstract:
        description = evidence(
            search.get("description"), "pnx.search.description", "description", 20000
        )
    if abstract and description and abstract.text == description.text:
        description = None
    date = first(addata.get("date")) or first(pnx.get("sort", {}).get("creationdate"))
    year_match = re.match(r"\d{4}", date or "")
    doi = first(addata.get("doi"))
    if not doi:
        doi = next(
            (v[4:].strip() for v in strings(display.get("identifier")) if v.startswith("DOI:")),
            None,
        )
    levels = strings(facets.get("toplevel"))
    availability = strings(delivery.get("availability")) + strings(
        pnx.get("delivery", {}).get("fulltext")
    )
    links: list[DocumentLink] = []
    seen: set[str] = set()

    def add_link(url: str, kind: str, label: str):
        if web_url(url) and url not in seen:
            seen.add(url)
            links.append(DocumentLink(url=url, kind=kind, label=clean(label)))

    for field, kind in [
        ("linktopdf", "pdf"),
        ("linktohtml", "html"),
        ("linktorsrc", "source"),
        ("backlink", "source"),
    ]:
        for encoded in strings(pnx.get("links", {}).get(field)):
            found = re.search(r"\$\$U(.*?)(?:\$\$|$)", encoded)
            if found:
                add_link(found.group(1), kind, field)
    delivery_links = delivery.get("link") or []
    if not isinstance(delivery_links, list):
        raise LibraryError("图书馆文献链接格式发生变化。")
    for item in delivery_links:
        if not isinstance(item, dict):
            continue
        label = first(item.get("displayLabel")) or ""
        if "thumbnail" in label.lower():
            continue
        kind = "resolver" if "openurl" in label.lower() else "source"
        add_link(first(item.get("linkURL")) or "", kind, label)
    for url in strings(delivery.get("availabilityLinksUrl")):
        add_link(url, "resolver", "图书馆全文入口")
    if doi:
        add_link("https://doi.org/" + quote(doi, safe="/():.-_"), "doi", "DOI")

    warnings = []
    if not abstract:
        warnings.append("未提供明确的摘要字段；不能把检索片段或书目描述当作完整摘要。")
    if (abstract and abstract.truncated) or (description and description.truncated):
        warnings.append("长文本已截断，truncated=true；筛选时须注明证据不完整。")
    if "fulltext" in availability or "online_resources" in levels:
        available = True
    elif any(v in availability for v in ["no_fulltext", "no_fulltext_linktorsrc"]):
        available = False
    else:
        available = None
    source_url = (
        ORIGIN
        + "/primo-explore/fulldisplay?"
        + urlencode(
            {
                "docid": record_id,
                "context": context,
                "vid": "fdu",
                "lang": "zh_CN",
                "adaptor": "primo_central_multiple_fe"
                if context == "PC"
                else "Local Search Engine",
            }
        )
    )
    return Document(
        record_id=record_id,
        context=context,
        title=title,
        authors=strings(addata.get("au"))
        or strings(search.get("creator"))
        or strings(display.get("creator")),
        date=date,
        year=int(year_match.group()) if year_match else None,
        journal=first(addata.get("jtitle")),
        resource_type=first(display.get("type")),
        doi=doi,
        languages=strings(display.get("language")),
        subjects=strings(search.get("subject"))[:40],
        abstract=abstract,
        description=description,
        snippets=[
            evidence(v, "pnx.display.snippet", "search_snippet", 2500)
            for v in strings(display.get("snippet"))[:3]
        ],
        peer_reviewed=True if "peer_reviewed" in levels else None,
        full_text_available=available,
        open_access=True
        if "open_access" in levels
        or any(
            v.lower() in {"free_for_read", "open_access"}
            for v in strings(pnx.get("addata", {}).get("oa"))
        )
        else None,
        links=links[:12],
        source_url=source_url,
        sources=strings(display.get("source")),
        retrieved_at=timestamp,
        warnings=warnings,
    )


def search_params(request: SearchRequest) -> dict[str, str | int]:
    tab, scope = SCOPES[request.scope]
    # Commas and semicolons delimit the Primo query grammar, not query text.
    query = re.sub(r"\s+", " ", re.sub(r"[;,]", " ", request.query)).strip()
    clauses = [f"{FIELDS[request.field]},{request.match},{query}"]
    if request.year_from or request.year_to:
        start, end = request.year_from or 1000, request.year_to or 2100
        clauses.extend([f"dr_s,exact,{start}0101", f"dr_e,exact,{end}1231"])
    includes = []
    if request.peer_reviewed_only:
        includes.append("facet_tlevel,exact,peer_reviewed")
    if request.full_text_available_only:
        includes.append("facet_tlevel,exact,online_resources")
    if request.language:
        includes.append(f"facet_lang,exact,{request.language}")
    if request.resource_type:
        includes.append(f"facet_rtype,exact,{request.resource_type}")
    return {
        "vid": "fdu",
        "inst": "FDU",
        "tab": tab,
        "scope": scope,
        "lang": "zh_CN",
        "q": ";".join(clauses),
        "qInclude": "|,|".join(includes),
        "offset": request.offset,
        "limit": request.limit,
        "sort": SORTS[request.sort],
        "pcAvailability": str(not request.full_text_available_only).lower(),
    }


def search_url(request: SearchRequest, params: dict) -> str:
    pairs = [("query", clause) for clause in params["q"].split(";")]
    pairs.extend(
        (key, str(value))
        for key, value in {
            "vid": "fdu",
            "tab": params["tab"],
            "search_scope": params["scope"],
            "offset": request.offset,
            "lang": "zh_CN",
            "sortby": params["sort"],
            "pcAvailability": params["pcAvailability"],
        }.items()
    )
    for facet in params["qInclude"].split("|,|"):
        if facet:
            pairs.append(("facet", facet.removeprefix("facet_").replace(",exact,", ",include,")))
    return ORIGIN + "/primo-explore/search?" + urlencode(pairs)


class PrimoClient:
    def __init__(self, settings: Settings | None = None, *, transport=None):
        self.settings = settings or Settings.from_env()
        self.http = httpx.AsyncClient(
            base_url=ORIGIN,
            timeout=self.settings.timeout,
            trust_env=self.settings.trust_env,
            follow_redirects=False,
            transport=transport,
            headers={
                "User-Agent": "FudanLibraryMCP/0.1 (anonymous literature search)",
                "Accept": "application/json",
                "Accept-Encoding": "identity",
            },
        )
        self._token: str | None = None
        self._token_until = 0.0
        self._token_lock = asyncio.Lock()
        self._request_lock = asyncio.Lock()
        self._last_request = 0.0
        self._cache: OrderedDict[str, tuple[float, dict]] = OrderedDict()
        self._cache_bytes = 0

    async def aclose(self):
        await self.http.aclose()

    def _drop_cache(self, key: str):
        stored = self._cache.pop(key, None)
        if stored:
            self._cache_bytes -= stored[1]["size"]

    async def _bounded_get(self, path: str, params: dict, token: str | None) -> httpx.Response:
        # Bound total transfer time, including servers that drip small chunks forever.
        async with (
            asyncio.timeout(self.settings.timeout),
            self.http.stream(
                "GET",
                path,
                params=params,
                headers=({"Authorization": "Bearer " + token} if token else {}),
            ) as response,
        ):
            if response.headers.get("Content-Encoding", "identity").lower() != "identity":
                raise LibraryError("图书馆返回了不支持的压缩响应，已停止读取。")
            length = response.headers.get("Content-Length", "")
            maximum = self.settings.max_response_bytes
            if length.isdigit() and int(length) > maximum:
                raise LibraryError("图书馆响应超过安全大小上限，请缩小检索范围。")
            body = bytearray()
            async for chunk in response.aiter_bytes(chunk_size=65536):
                if len(body) + len(chunk) > maximum:
                    raise LibraryError("图书馆响应超过安全大小上限，请缩小检索范围。")
                body.extend(chunk)
            return httpx.Response(
                response.status_code,
                headers=response.headers,
                content=bytes(body),
                request=response.request,
            )

    async def _request(self, path: str, params: dict, *, token: str | None = None):
        for attempt in range(3):
            async with self._request_lock:
                delay = self.settings.request_interval - (time.monotonic() - self._last_request)
                if delay > 0:
                    await asyncio.sleep(delay)
                self._last_request = time.monotonic()
                try:
                    response = await self._bounded_get(path, params, token)
                except (httpx.RequestError, TimeoutError):
                    if attempt < 2:
                        continue
                    raise LibraryError(
                        "无法连接复旦资源发现系统。请检查网络；若需环境代理，设置 "
                        "FUDAN_LIBRARY_TRUST_ENV=true。未返回结果不代表没有文献。"
                    ) from None
            if response.status_code == 429 or response.status_code >= 500:
                if attempt < 2:
                    raw_delay = response.headers.get("Retry-After", "")
                    retry_delay = float(raw_delay) if raw_delay.isdigit() else 2**attempt
                    if retry_delay > 30:
                        raise LibraryError("图书馆要求较长时间后重试，请稍后再检索。")
                    await asyncio.sleep(max(1, retry_delay))
                    continue
                raise LibraryError("图书馆暂时限流或服务不可用，请稍后再检索。")
            return response
        raise LibraryError("图书馆请求失败。")  # defensive; loop always returns or raises

    async def _guest_token(self, rejected_token: str | None = None) -> str:
        async with self._token_lock:
            if rejected_token and rejected_token == self._token:
                self._token = None
            if self._token and time.monotonic() < self._token_until:
                return self._token
            response = await self._request(
                REST + "/v1/guestJwt/FDU", {"vid": "fdu", "lang": "zh_CN"}
            )
            self._check_status(response)
            token = response.text.strip().strip('"')
            if not re.fullmatch(r"[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+", token):
                raise LibraryError("图书馆未返回可用的匿名访客令牌。请检查网站服务状态。")
            self._token, self._token_until = token, time.monotonic() + 600
            return token

    @staticmethod
    def _check_status(response: httpx.Response):
        if response.status_code in {401, 403}:
            raise LibraryError(
                "图书馆拒绝匿名请求。可能需要校内网络或馆方授权；请打开来源链接核实。"
            )
        if response.status_code == 404:
            raise LibraryError("未找到文献或接口。请使用最新检索结果中的 record_id 和 context。")
        if response.is_redirect:
            raise LibraryError("图书馆返回重定向，可能要求登录；请在浏览器打开来源页面。")
        if response.is_error:
            raise LibraryError(f"图书馆返回 HTTP {response.status_code}，请稍后重试。")

    async def _json(self, path: str, params: dict, *, cache: bool = True) -> tuple[dict, str]:
        key = path + json.dumps(params, sort_keys=True, ensure_ascii=False)
        stored = self._cache.get(key) if cache else None
        if stored and time.monotonic() < stored[0]:
            self._cache.move_to_end(key)
            return stored[1]["data"], stored[1]["time"]
        if stored:
            self._drop_cache(key)
        token = await self._guest_token()
        response = await self._request(path, params, token=token)
        if response.status_code in {401, 403}:
            token = await self._guest_token(rejected_token=token)
            response = await self._request(path, params, token=token)
        self._check_status(response)
        try:
            data = response.json()
        except (ValueError, RecursionError):
            raise LibraryError("图书馆返回了非 JSON 页面（可能是登录或维护页面）。") from None
        if not isinstance(data, dict):
            raise LibraryError("图书馆响应格式发生变化。")
        if data.get("errorsExist") or data.get("errorCode") or data.get("error"):
            raise LibraryError("图书馆报告接口错误；请检查检索条件或稍后重试。")
        timestamp = now()
        # Cache only recognizable success envelopes, never partial/error pages.
        info = data.get("info")
        valid_search = isinstance(info, dict) and isinstance(data.get("docs"), list)
        cacheable = (
            valid_search
            and not info.get("errorDetails")
            or isinstance(data.get("pnx"), dict)
            or isinstance(data.get("primo-view"), dict)
        )
        size = len(response.content)
        if cache and cacheable and size <= self.settings.max_cache_bytes:
            self._drop_cache(key)
            self._cache[key] = (
                time.monotonic() + self.settings.cache_ttl,
                {"data": data, "time": timestamp, "size": size},
            )
            self._cache_bytes += size
            self._cache.move_to_end(key)
            while len(self._cache) > 64 or self._cache_bytes > self.settings.max_cache_bytes:
                self._drop_cache(next(iter(self._cache)))
        return data, timestamp

    async def search(self, request: SearchRequest) -> SearchResult:
        params = search_params(request)
        data, timestamp = await self._json(SEARCH, params)
        info, docs = data.get("info"), data.get("docs")
        if not isinstance(info, dict) or not isinstance(docs, list):
            raise LibraryError("图书馆检索响应缺少 info/docs，不能据此判断为零结果。")
        try:
            total = int(info["total"])
            if total < 0:
                total = None
        except (KeyError, ValueError, TypeError):
            total = None
        partial = bool(info.get("errorDetails"))
        warnings = []
        if partial:
            warnings.append("图书馆返回部分结果；总数与列表可能不完整，请稍后重试。")
        if re.search(r"[;,]", request.query):
            warnings.append("检索词中的半角逗号／分号已替换为空格，以避免 Primo 查询分隔符歧义。")
        documents = []
        for doc in docs:
            try:
                documents.append(normalize_document(doc, timestamp))
            except (LibraryError, TypeError, AttributeError, ValueError):
                partial = True
                warnings.append("有一条文献格式异常，已跳过；不能把当前列表视为完整结果。")
        if partial:
            # Parsing can reveal incomplete results even when info reports success.
            self._drop_cache(SEARCH + json.dumps(params, sort_keys=True, ensure_ascii=False))
        next_offset = request.offset + len(docs)
        if not docs or total is None or next_offset >= total or next_offset >= 2000:
            next_offset = None
        normalized_facets = {}
        for facet in data.get("facets") or []:
            if isinstance(facet, dict) and isinstance(facet.get("values"), list):
                normalized_facets[str(facet.get("name", "unknown"))] = [
                    {"value": v.get("value"), "count": v.get("count")}
                    for v in facet["values"][:10]
                    if isinstance(v, dict)
                ]
        if request.field == "fulltext":
            basis = "Primo ftext 全文索引检索；覆盖范围由数据库决定，不代表已读取原文。"
            warnings.append("片段的具体命中位置未经接口确认，不能将 search_snippet 称为正文引文。")
        else:
            basis = f"Primo {FIELDS[request.field]} 字段检索；all 为常规跨字段检索。"
        return SearchResult(
            query=request.query,
            effective_query=params["q"],
            field=request.field,
            scope=request.scope,
            search_basis=basis,
            full_text_available_only=request.full_text_available_only,
            total=total,
            offset=request.offset,
            limit=request.limit,
            returned=len(documents),
            next_offset=next_offset,
            partial=partial,
            documents=documents,
            facets=normalized_facets,
            source_url=search_url(request, params),
            retrieved_at=timestamp,
            warnings=list(dict.fromkeys(warnings)),
        )

    async def get_document(self, ref: DocumentRef) -> Document:
        # Construct the path from validated IDs; never fetch a model-supplied URL.
        path = SEARCH + "/" + ref.context + "/" + quote(ref.record_id, safe="")
        params = {"vid": "fdu", "inst": "FDU", "lang": "zh_CN"}
        data, timestamp = await self._json(path, params)
        try:
            document = normalize_document(data, timestamp)
        except (LibraryError, TypeError, AttributeError, ValueError):
            self._drop_cache(path + json.dumps(params, sort_keys=True, ensure_ascii=False))
            raise LibraryError("图书馆文献详情格式异常，请稍后重试或打开来源页面。") from None
        if document.record_id != ref.record_id:
            document.warnings.append("上游返回了合并后的记录 ID，与请求 ID 不同。")
        return document

    async def status(self) -> dict:
        data, timestamp = await self._json(
            REST + "/v1/configuration/fdu", {"vid": "fdu", "inst": "FDU", "lang": "zh_CN"}
        )
        if not isinstance(data.get("primo-view"), dict):
            raise LibraryError("无法识别图书馆配置响应。")
        return {
            "status": "ok",
            "library": "复旦大学图书馆 · 望道溯源",
            "authentication": "anonymous_guest",
            "source_url": ORIGIN + "/primo-explore/search?vid=fdu",
            "scopes": data["primo-view"].get("scopes", []),
            "retrieved_at": timestamp,
            "fulltext_search_field": "ftext",
            "page_size_max": 20,
            "retrieval_limit": 2000,
            "fulltext_download": False,
            "note": "可检索全文索引并返回摘要与全文入口；出版商原文访问仍取决于校内网络和订购权限。",
        }
