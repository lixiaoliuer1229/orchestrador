#!/usr/bin/env python3
"""Probe OpenAI-compatible chat completions on the Norotech LLM gateway."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass

import requests


DEFAULT_BASE_URLS = (
    "https://llm-gateway.norotech.mx/v1",
    "https://llm-gateway.norotech.mx",
)
DEFAULT_MODELS = (
    "doubao-seed-2-lite",
    "deepseek-v4-flash",
    "doubao-seed-2-1-turbo",
    "minimax-m3",
    "glm-latest",
    "kimi-k2-7-code",
)


@dataclass
class Result:
    base_url: str
    model: str
    ok: bool
    status: int | None
    elapsed: float
    detail: str


def compact_detail(response: requests.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return response.text.strip().replace("\n", " ")[:240] or "empty response"

    if response.ok:
        try:
            content = body["choices"][0]["message"]["content"]
            return str(content).strip().replace("\n", " ")[:120] or "empty content"
        except (KeyError, IndexError, TypeError):
            return json.dumps(body, ensure_ascii=False)[:240]

    error = body.get("error", body) if isinstance(body, dict) else body
    if isinstance(error, dict):
        message = error.get("message") or error.get("detail") or error
    else:
        message = error
    return str(message).strip().replace("\n", " ")[:240]


def probe(
    base_url: str, model: str, api_key: str, timeout: float, max_tokens: int
) -> Result:
    endpoint = f"{base_url.rstrip('/')}/chat/completions"
    started = time.monotonic()
    try:
        response = requests.post(
            endpoint,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": [{"role": "user", "content": "Reply with exactly: OK"}],
                "max_tokens": max_tokens,
                "temperature": 0,
                "stream": False,
            },
            timeout=timeout,
        )
        return Result(
            base_url, model, response.ok, response.status_code,
            time.monotonic() - started, compact_detail(response),
        )
    except requests.RequestException as exc:
        return Result(
            base_url, model, False, None, time.monotonic() - started,
            f"{type(exc).__name__}: {exc}",
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", action="append", dest="base_urls")
    parser.add_argument("--model", action="append", dest="models")
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--max-tokens", type=int, default=128)
    args = parser.parse_args()

    api_key = os.getenv("NOROTECH_API_KEY") or os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("Set NOROTECH_API_KEY (or ANTHROPIC_API_KEY) before running.", file=sys.stderr)
        return 2

    results = [
        probe(base_url, model, api_key, args.timeout, args.max_tokens)
        for base_url in (args.base_urls or DEFAULT_BASE_URLS)
        for model in (args.models or DEFAULT_MODELS)
    ]

    print(f"{'BASE URL':42} {'MODEL':28} {'RESULT':9} {'TIME':>7}  DETAIL")
    print("-" * 112)
    for item in results:
        result = "OK" if item.ok else f"FAIL {item.status or '-'}"
        print(
            f"{item.base_url:42} {item.model:28} {result:9} "
            f"{item.elapsed:6.2f}s  {item.detail}"
        )

    passed = sum(item.ok for item in results)
    print(f"\nPassed {passed}/{len(results)} probes.")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
