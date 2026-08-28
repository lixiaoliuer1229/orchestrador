"""Bounded Tavily search adapter."""

from __future__ import annotations

import asyncio
import hashlib
import os
from datetime import datetime, timezone
from typing import Any, Protocol
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from langchain_tavily import TavilySearch

from app.research.models import SearchItem, SourceDocument


def _env_int(name: str, default: int, maximum: int) -> int:
    raw = os.getenv(name, str(default))
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer") from exc
    if value <= 0 or value > maximum:
        raise RuntimeError(f"{name} must be between 1 and {maximum}")
    return value


def _env_choice(name: str, default: str, choices: set[str]) -> str:
    value = os.getenv(name, default).lower()
    if value not in choices:
        raise RuntimeError(f"{name} must be one of: {', '.join(sorted(choices))}")
    return value


class Searcher(Protocol):
    async def search(self, item: SearchItem) -> list[SourceDocument]: ...


def _canonical_url(value: str) -> str:
    parts = urlsplit(value.strip())
    filtered = [
        (key, item)
        for key, item in parse_qsl(parts.query, keep_blank_values=True)
        if not key.lower().startswith("utm_")
        and key.lower() not in {"fbclid", "gclid"}
    ]
    return urlunsplit(
        (
            parts.scheme.lower(),
            parts.netloc.lower(),
            parts.path or "/",
            urlencode(sorted(filtered)),
            "",
        )
    )


class TavilySearcher:
    def __init__(self) -> None:
        self.timeout = _env_int("RESEARCH_SEARCH_TIMEOUT_SECONDS", 20, 60)
        self.retries = _env_int("RESEARCH_SEARCH_RETRIES", 2, 4)
        self.source_chars = _env_int("RESEARCH_SOURCE_CHARS", 6_000, 20_000)
        max_results = _env_int("RESEARCH_RESULTS_PER_QUERY", 5, 10)
        search_depth = _env_choice(
            "RESEARCH_SEARCH_DEPTH",
            "advanced",
            {"basic", "advanced", "fast", "ultra-fast"},
        )
        self.tool = TavilySearch(
            max_results=max_results,
            search_depth=search_depth,
            include_raw_content="markdown",
        )

    async def search(self, item: SearchItem) -> list[SourceDocument]:
        error: Exception | None = None
        for attempt in range(self.retries):
            try:
                payload = await asyncio.wait_for(
                    self.tool.ainvoke({"query": item.query, "topic": item.topic}),
                    timeout=self.timeout,
                )
                if not isinstance(payload, dict):
                    raise RuntimeError("search provider returned an invalid payload")
                if payload.get("error"):
                    raise RuntimeError("search provider request failed")
                return self._sources(item, payload.get("results", []))
            except Exception as exc:
                error = exc
                if attempt + 1 < self.retries:
                    await asyncio.sleep(0.25 * (2**attempt))
        raise RuntimeError("search failed after retries") from error

    def _sources(
        self, item: SearchItem, results: list[dict[str, Any]]
    ) -> list[SourceDocument]:
        retrieved_at = datetime.now(timezone.utc)
        sources: list[SourceDocument] = []
        for result in results:
            url = str(result.get("url") or "").strip()
            title = str(result.get("title") or "").strip()
            if not url or not title:
                continue
            raw = result.get("raw_content") or result.get("content") or ""
            raw_content = str(raw).strip()
            content = raw_content[: self.source_chars]
            if not content:
                continue
            canonical_url = _canonical_url(url)
            source_id = hashlib.sha256(canonical_url.encode("utf-8")).hexdigest()[:24]
            content_hash = hashlib.sha256(raw_content.encode("utf-8")).hexdigest()
            score = result.get("score")
            sources.append(
                SourceDocument(
                    source_id=source_id,
                    canonical_url=canonical_url,
                    title=title,
                    publisher=urlsplit(canonical_url).netloc,
                    content=content,
                    content_hash=content_hash,
                    queries=[item.query],
                    score=float(score) if score is not None else None,
                    retrieved_at=retrieved_at,
                    metadata={"provider": "tavily"},
                )
            )
        return sources
