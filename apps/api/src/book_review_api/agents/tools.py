"""Tools của research agent (ngày 8).

Mỗi tool là một hàm thường trả `dict` JSON-được; lỗi trả `{error_code, message}` thay vì ném
exception để agent tự xử lý (mục 3.2 plan v5). Phụ thuộc ngoài (tìm web, tải trang, LLM, DB,
Store) đi qua `ToolContext` nên test thay bằng mock được, không cần mạng hay DB.
"""

import ipaddress
import json
import logging
import re
import socket
import urllib.request
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from difflib import get_close_matches
from typing import Any, Protocol
from urllib.parse import urlparse, urlunparse

import trafilatura
from langchain_core.language_models import BaseChatModel
from langchain_core.tools import BaseTool, StructuredTool
from langgraph.store.base import BaseStore
from pydantic import BaseModel

from book_review_api.errors import ERROR_SPECS, ErrorCode
from book_review_api.graph.nodes.precheck import find_excluded_keyword, fold
from book_review_api.rag.ingest import Document, IngestError, extract_html, ingest_text
from book_review_api.rag.retrieve import Chunk

log = logging.getLogger(__name__)

MAX_PAGE_CHARS = 20_000
MAX_SEARCH_RESULTS = 8

# Thể loại bị loại trừ chỉ có tên thể loại (tên sách đã có `precheck`).
EXCLUDED_GENRES: dict[str, str] = {
    "tien hiep": "tiên hiệp",
    "kiem hiep": "kiếm hiệp",
    "vo hiep": "võ hiệp",
    "huyen huyen": "huyền huyễn",
    "tu tien": "tu tiên",
    "tu chan": "tu chân",
    "xianxia": "tiên hiệp",
    "wuxia": "võ hiệp",
    "cultivation": "tu tiên",
}

DEFAULT_PREFERENCES: dict[str, Any] = {
    "voice": "default",
    "image_style": "default",
    "length_minutes": 3,
    "no_spoiler": True,
    "tone": "neutral",
}

Event = dict[str, Any]


# --- Giao diện provider ---------------------------------------------------------


@dataclass(frozen=True)
class SearchResult:
    url: str
    title: str
    snippet: str = ""


class SearchProvider(Protocol):
    """Tách riêng để đổi Gemini grounding sang Tavily mà không đụng agent."""

    def search(self, query: str) -> list[SearchResult]: ...


class GeminiSearchProvider:
    """Gemini có Google Search grounding: nguồn lấy từ `grounding_metadata` của câu trả lời."""

    def __init__(self, model: BaseChatModel) -> None:
        self.model = model.bind_tools([{"google_search": {}}])

    def search(self, query: str) -> list[SearchResult]:
        reply = self.model.invoke(f"Tìm thông tin web về: {query}")
        meta = getattr(reply, "response_metadata", {}) or {}
        chunks = (meta.get("grounding_metadata") or {}).get("grounding_chunks") or []
        snippet = reply.content if isinstance(reply.content, str) else ""
        results: list[SearchResult] = []
        for c in chunks:
            web = c.get("web") or {}
            if web.get("uri"):
                results.append(SearchResult(web["uri"], web.get("title") or "", snippet[:300]))
        return results


class TavilySearchProvider:
    """Tavily search API: không phụ thuộc quota Google Search grounding của Gemini."""

    def __init__(self, api_key: str, timeout: float = 20.0) -> None:
        self.api_key = api_key
        self.timeout = timeout

    def search(self, query: str) -> list[SearchResult]:
        body = json.dumps({"query": query, "max_results": MAX_SEARCH_RESULTS}).encode()
        req = urllib.request.Request(
            "https://api.tavily.com/search",
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:  # noqa: S310
            data = json.load(resp)
        return [
            SearchResult(r["url"], r.get("title") or "", (r.get("content") or "")[:300])
            for r in data.get("results", [])
            if r.get("url")
        ]


def _is_public_http_url(url: str) -> bool:
    """Chỉ http(s) tới host công khai: agent không được đọc mạng nội bộ qua `fetch_page`."""
    parts = urlparse(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return False
    try:
        addrs = {ai[4][0] for ai in socket.getaddrinfo(parts.hostname, None)}
    except OSError:
        return True  # không phân giải được thì để bước tải báo lỗi mạng
    return all(ipaddress.ip_address(a).is_global for a in addrs)


@dataclass
class ToolContext:
    """Mọi phụ thuộc của tool. Trường bắt buộc tối thiểu là `search`; còn lại thiếu thì tool
    tương ứng trả `PROVIDER_UNAVAILABLE`."""

    search: SearchProvider | None = None
    fetch: Callable[[str], str | None] = trafilatura.fetch_url
    url_allowed: Callable[[str], bool] = _is_public_http_url
    # Nạp chunk vào kho vector (phạm vi công khai); trả số chunk mới thêm.
    index: Callable[[Sequence[Document]], int] | None = None
    # Truy xuất chunk theo câu hỏi cho sách đang làm (đã gắn book_id/engine).
    retrieve: Callable[[str], list[Chunk]] | None = None
    # LLM xác định sách; trả văn bản JSON `{"candidates": [...]}`.
    identity_model: BaseChatModel | None = None
    store: BaseStore | None = None
    book_id: str | None = None
    user_id: str | None = None
    emit: Callable[[Event], None] | None = None
    # URL đã thấy trong kết quả tìm và trang đã tải; dùng để sửa URL model chép sai.
    known_urls: set[str] = field(default_factory=set)


# --- Tiện ích -------------------------------------------------------------------


def tool_error(code: ErrorCode, message: str | None = None) -> dict[str, Any]:
    return {"error_code": code.value, "message": message or ERROR_SPECS[code].message_vi}


def _emit(ctx: ToolContext, event: Event) -> None:
    """Sự kiện tiến độ cho UI; lỗi của listener không được làm hỏng tool."""
    if ctx.emit is None:
        return
    try:
        ctx.emit(event)
    except Exception:  # noqa: BLE001
        log.exception("emit event thất bại")


_URL_NOISE = " \t\r\n\"'<>()[].,;"
# Ngưỡng giống nhau tối thiểu để coi URL model đưa là bản chép sai của một URL đã biết.
URL_MATCH_CUTOFF = 0.93


def _url_key(url: str) -> str:
    p = urlparse(url)
    return urlunparse((p.scheme.lower(), p.netloc.lower(), p.path.rstrip("/"), "", p.query, ""))


def canonical_url(ctx: ToolContext, url: str, fuzzy: bool = False) -> str:
    """Đưa URL model chép lại về URL thật đã biết: bỏ ký tự thừa, khác hoa/thường ở host,
    dấu `/` cuối, fragment. `fuzzy` thêm so khớp gần đúng cho lỗi chép sai ký tự; chỉ bật khi URL
    chắc chắn phải là một URL đã biết (nạp nguồn vừa đọc), vì trang khác chỉ lệch một ký tự là
    trang hợp lệ khác. Không khớp gì thì giữ nguyên."""
    plain = url.strip()
    cleaned = plain.strip(_URL_NOISE)
    if plain in ctx.known_urls:
        return plain
    if cleaned in ctx.known_urls:
        return cleaned
    by_key = {_url_key(u): u for u in ctx.known_urls}
    if (hit := by_key.get(_url_key(cleaned))) is not None:
        return hit
    if not fuzzy:
        return plain
    close = get_close_matches(_url_key(cleaned), list(by_key), n=1, cutoff=URL_MATCH_CUTOFF)
    return by_key[close[0]] if close else plain


def _unavailable(what: str) -> dict[str, Any]:
    return tool_error(ErrorCode.PROVIDER_UNAVAILABLE, f"Chưa cấu hình {what}.")


# --- Tools ----------------------------------------------------------------------


def web_search(ctx: ToolContext, query: str) -> dict[str, Any]:
    if not query.strip():
        return tool_error(ErrorCode.VALIDATION_ERROR, "Câu tìm kiếm trống.")
    if ctx.search is None:
        return _unavailable("web search")
    try:
        found = ctx.search.search(query)
    except Exception:  # noqa: BLE001 - lỗi provider -> lỗi có cấu trúc
        log.exception("web_search thất bại")
        return tool_error(ErrorCode.PROVIDER_UNAVAILABLE)
    results, seen = [], set()
    for r in found:
        if r.url in seen:
            continue
        seen.add(r.url)
        ctx.known_urls.add(r.url)
        results.append({"url": r.url, "title": r.title, "snippet": r.snippet})
        _emit(ctx, {"type": "source_found", "url": r.url, "title": r.title})
        if len(results) >= MAX_SEARCH_RESULTS:
            break
    return {"query": query, "results": results}


def fetch_page(ctx: ToolContext, url: str) -> dict[str, Any]:
    url = canonical_url(ctx, url)
    if not ctx.url_allowed(url):
        return tool_error(ErrorCode.VALIDATION_ERROR, "URL không hợp lệ hoặc không được phép.")
    try:
        html = ctx.fetch(url)
    except Exception:  # noqa: BLE001
        log.exception("fetch_page thất bại")
        return tool_error(ErrorCode.PROVIDER_UNAVAILABLE, "Không tải được trang.")
    if not html:
        return tool_error(ErrorCode.NOT_FOUND, "Không tải được trang.")
    try:
        text, title = extract_html(html, url)
    except IngestError as e:
        return tool_error(ErrorCode.NOT_FOUND, str(e))
    ctx.known_urls.add(url)
    _emit(ctx, {"type": "source_read", "url": url, "title": title})
    return {
        "url": url,
        "title": title,
        "text": text[:MAX_PAGE_CHARS],
        "truncated": len(text) > MAX_PAGE_CHARS,
    }


def ingest_source(ctx: ToolContext, url: str, text: str) -> dict[str, Any]:
    url = canonical_url(ctx, url, fuzzy=True)
    if ctx.index is None or ctx.book_id is None:
        return _unavailable("kho tri thức")
    if not text.strip():
        return tool_error(ErrorCode.VALIDATION_ERROR, "Nội dung nguồn trống.")
    try:
        docs = ingest_text(text, url=url, book_id=ctx.book_id)
        added = ctx.index(docs)
    except IngestError as e:
        return tool_error(ErrorCode.VALIDATION_ERROR, str(e))
    except Exception:  # noqa: BLE001
        log.exception("ingest_source thất bại")
        return tool_error(ErrorCode.INTERNAL_ERROR)
    _emit(ctx, {"type": "source_ingested", "url": url, "chunks": len(docs)})
    return {"url": url, "chunks": len(docs), "added": added}


def search_knowledge(ctx: ToolContext, query: str) -> dict[str, Any]:
    if ctx.retrieve is None:
        return _unavailable("kho tri thức")
    try:
        chunks = ctx.retrieve(query)
    except Exception:  # noqa: BLE001
        log.exception("search_knowledge thất bại")
        return tool_error(ErrorCode.PROVIDER_UNAVAILABLE)
    return {
        "query": query,
        "results": [
            {
                "chunk_id": c.id,
                "content": c.content,
                "url": c.metadata.get("url"),
                "title": c.metadata.get("title"),
                "score": c.score,
            }
            for c in chunks
        ],
    }


_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


def _parse_candidates(raw: str) -> list[dict[str, Any]]:
    match = _JSON_RE.search(raw)
    data = json.loads(match.group(0)) if match else {}
    out: list[dict[str, Any]] = []
    for c in data.get("candidates", []):
        if isinstance(c, dict) and c.get("title"):
            out.append(
                {
                    "title": str(c["title"]),
                    "author": c.get("author"),
                    "year": c.get("year"),
                    "original_title": c.get("original_title"),
                }
            )
    return out


def lookup_book_identity(ctx: ToolContext, title: str, author: str | None = None) -> dict[str, Any]:
    if not title.strip():
        return tool_error(ErrorCode.VALIDATION_ERROR, "Thiếu tên sách.")
    if ctx.identity_model is None:
        return _unavailable("mô hình tra cứu sách")
    prompt = (
        "Xác định cuốn sách theo tên"
        + (f" và tác giả {author}" if author else "")
        + f": {title!r}. Liệt kê mọi cuốn sách thật có tên này. Chỉ trả JSON dạng "
        '{"candidates": [{"title": "", "author": "", "year": 0, "original_title": ""}]}; '
        'nếu không có cuốn nào thì {"candidates": []}. Không bịa.'
    )
    try:
        reply = ctx.identity_model.invoke(prompt)
        raw = reply.content if isinstance(reply.content, str) else json.dumps(reply.content)
        candidates = _parse_candidates(raw)
    except (ValueError, AttributeError):
        return tool_error(ErrorCode.PROVIDER_UNAVAILABLE, "Không đọc được kết quả tra cứu sách.")
    except Exception:  # noqa: BLE001
        log.exception("lookup_book_identity thất bại")
        return tool_error(ErrorCode.PROVIDER_UNAVAILABLE)
    if not candidates:
        return tool_error(ErrorCode.BOOK_NOT_FOUND)
    # Nhiều ứng viên -> UI hỏi người dùng chọn đúng cuốn.
    return {"candidates": candidates, "ambiguous": len(candidates) > 1}


def check_genre(ctx: ToolContext, genre: str) -> dict[str, Any]:
    if not genre.strip():
        return tool_error(ErrorCode.VALIDATION_ERROR, "Thiếu thể loại.")
    folded = fold(genre)
    matched = next((label for key, label in EXCLUDED_GENRES.items() if key in folded), None)
    matched = matched or find_excluded_keyword(genre)
    result: dict[str, Any] = {"genre": genre, "excluded": matched is not None}
    if matched:
        result["matched"] = matched
        result["error_code"] = ErrorCode.GENRE_EXCLUDED.value
        result["message"] = ERROR_SPECS[ErrorCode.GENRE_EXCLUDED].message_vi
    return result


def get_user_preferences(ctx: ToolContext) -> dict[str, Any]:
    prefs = dict(DEFAULT_PREFERENCES)
    if ctx.store is None or not ctx.user_id:
        return {"preferences": prefs, "source": "default"}
    try:
        item = ctx.store.get(("users", ctx.user_id, "preferences"), "default")
    except Exception:  # noqa: BLE001
        log.exception("get_user_preferences thất bại")
        return tool_error(ErrorCode.INTERNAL_ERROR)
    if item is None:
        return {"preferences": prefs, "source": "default"}
    prefs.update({k: v for k, v in item.value.items() if k in DEFAULT_PREFERENCES})
    return {"preferences": prefs, "source": "store"}


# --- LangChain tools ------------------------------------------------------------


def research_tools(ctx: ToolContext) -> list[BaseTool]:
    """7 tool gắn với `ctx`, dạng LangChain để đưa cho `create_agent` (ngày 9)."""
    return [
        StructuredTool.from_function(
            func=lambda query: web_search(ctx, query),
            name="web_search",
            description="Tìm trên web review, tóm tắt, thông tin tác giả của một cuốn sách.",
            args_schema=_Query,
        ),
        StructuredTool.from_function(
            func=lambda url: fetch_page(ctx, url),
            name="fetch_page",
            description="Tải một trang web và trả nội dung chính.",
            args_schema=_Url,
        ),
        StructuredTool.from_function(
            func=lambda url, text: ingest_source(ctx, url, text),
            name="ingest_source",
            description="Lưu nội dung một nguồn đáng tin vào kho tri thức để viết kịch bản.",
            args_schema=_Ingest,
        ),
        StructuredTool.from_function(
            func=lambda query: search_knowledge(ctx, query),
            name="search_knowledge",
            description="Tìm trong kho tri thức đã nạp để biết đã đủ thông tin chưa.",
            args_schema=_Query,
        ),
        StructuredTool.from_function(
            func=lambda title, author=None: lookup_book_identity(ctx, title, author),
            name="lookup_book_identity",
            description="Xác định tác giả, năm, tên gốc và các sách trùng tên.",
            args_schema=_Identity,
        ),
        StructuredTool.from_function(
            func=lambda genre: check_genre(ctx, genre),
            name="check_genre",
            description="Kiểm tra thể loại có bị loại trừ (tiên hiệp, kiếm hiệp) không.",
            args_schema=_Genre,
        ),
        StructuredTool.from_function(
            func=lambda: get_user_preferences(ctx),
            name="get_user_preferences",
            description="Đọc giọng đọc, phong cách, độ dài người dùng thường chọn.",
        ),
    ]


class _Query(BaseModel):
    query: str


class _Url(BaseModel):
    url: str


class _Ingest(BaseModel):
    url: str
    text: str


class _Identity(BaseModel):
    title: str
    author: str | None = None


class _Genre(BaseModel):
    genre: str
