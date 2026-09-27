"""Validated MCP input and compact, evidence-preserving output models."""

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SearchField = Literal["all", "title", "abstract", "author", "subject", "fulltext"]
SearchScope = Literal["articles", "all", "books_journals"]


class SearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=1000)
    field: SearchField = "all"
    scope: SearchScope = "articles"
    match: Literal["contains", "exact"] = "contains"
    offset: int = Field(default=0, ge=0, le=1999)
    limit: int = Field(default=10, ge=1, le=20)
    sort: Literal["relevance", "newest", "oldest", "title", "author"] = "relevance"
    year_from: int | None = Field(default=None, ge=1000, le=2100)
    year_to: int | None = Field(default=None, ge=1000, le=2100)
    peer_reviewed_only: bool = False
    full_text_available_only: bool = False
    language: str | None = Field(default=None, pattern=r"^[a-z]{3}$")
    resource_type: (
        Literal["articles", "books", "dissertations", "conference_proceedings", "journals"] | None
    ) = None

    @field_validator("query")
    @classmethod
    def valid_query(cls, value: str) -> str:
        value = value.strip()
        if not value or not re.search(r"\w", value):
            raise ValueError("请输入有意义的检索词，不能只含通配符或标点。")
        if any(ord(char) < 32 for char in value):
            raise ValueError("检索词不能包含换行或控制字符。")
        return value

    @model_validator(mode="after")
    def valid_ranges(self) -> "SearchRequest":
        if self.offset + self.limit > 2000:
            raise ValueError("Primo CDI 仅支持前 2000 条结果；请缩小检索范围。")
        if self.year_from and self.year_to and self.year_from > self.year_to:
            raise ValueError("year_from 不能大于 year_to。")
        if self.field == "fulltext" and self.scope == "books_journals":
            raise ValueError("全文检索请使用 articles 或 all 范围。")
        return self


class DocumentRef(BaseModel):
    model_config = ConfigDict(extra="forbid")
    record_id: str = Field(min_length=1, max_length=1000, pattern=r"^[A-Za-z0-9_.:-]+$")
    context: Literal["PC", "L"] = "PC"

    @field_validator("record_id")
    @classmethod
    def no_dot_segments(cls, value: str) -> str:
        if value in {".", ".."}:
            raise ValueError("record_id 不能是路径特殊段。")
        return value


class EvidenceText(BaseModel):
    text: str
    source_field: str
    kind: Literal["abstract", "description", "search_snippet"]
    truncated: bool = False


class DocumentLink(BaseModel):
    url: str
    kind: Literal["pdf", "html", "resolver", "source", "doi"]
    label: str
    access_verified: bool = False


class Document(BaseModel):
    record_id: str
    context: Literal["PC", "L"]
    title: str
    authors: list[str] = Field(default_factory=list)
    date: str | None = None
    year: int | None = None
    journal: str | None = None
    resource_type: str | None = None
    doi: str | None = None
    languages: list[str] = Field(default_factory=list)
    subjects: list[str] = Field(default_factory=list)
    abstract: EvidenceText | None = None
    description: EvidenceText | None = None
    snippets: list[EvidenceText] = Field(default_factory=list)
    peer_reviewed: bool | None = None
    full_text_available: bool | None = None
    open_access: bool | None = None
    full_text_retrieved: bool = False
    links: list[DocumentLink] = Field(default_factory=list)
    source_url: str
    sources: list[str] = Field(default_factory=list)
    retrieved_at: str
    warnings: list[str] = Field(default_factory=list)


class SearchResult(BaseModel):
    query: str
    effective_query: str
    field: SearchField
    scope: SearchScope
    search_basis: str
    full_text_available_only: bool
    total: int | None
    offset: int
    limit: int
    returned: int
    next_offset: int | None
    partial: bool
    documents: list[Document]
    facets: dict[str, list[dict]] = Field(default_factory=dict)
    source_url: str
    retrieved_at: str
    warnings: list[str] = Field(default_factory=list)


class BatchItem(BaseModel):
    ref: DocumentRef
    document: Document | None = None
    error: str | None = None


class BatchResult(BaseModel):
    items: list[BatchItem]
