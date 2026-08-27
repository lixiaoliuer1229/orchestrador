"""Bounded Tavily search adapter."""

from __future__ import annotations

import asyncio
import hashlib
import os
from datetime import datetime, timezone
from typing import Any, Protocol

from langchain_tavily import TavilySearch

from app.graphs.research.models import SearchItem, Source


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
    async def search(self, item: SearchItem) -> list[Source]: ...


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

    async def search(self, item: SearchItem) -> list[Source]:
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

    def _sources(self, item: SearchItem, results: list[dict[str, Any]]) -> list[Source]:
        retrieved_at = datetime.now(timezone.utc)
        sources: list[Source] = []
        for result in results:
            url = str(result.get("url") or "").strip()
            title = str(result.get("title") or "").strip()
            if not url or not title:
                continue
            raw = result.get("raw_content") or result.get("content") or ""
            content = str(raw).strip()[: self.source_chars]
            if not content:
                continue
            source_id = hashlib.sha256(url.encode("utf-8")).hexdigest()[:20]
            score = result.get("score")
            sources.append(
                Source(
                    source_id=source_id,
                    query=item.query,
                    title=title,
                    url=url,
                    content=content,
                    score=float(score) if score is not None else None,
                    retrieved_at=retrieved_at,
                )
            )
        return sources
