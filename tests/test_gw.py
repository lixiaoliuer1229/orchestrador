"""Three-stage gateway sanity test.

Run with:
    python main.py run tests/test_gw.py
or:
    pytest tests/test_gw.py -v -s

What it does:
  1. Confirms `Settings` loaded your .env correctly (key & base_url non-empty,
     key does NOT start with "Bearer ").
  2. Probes the gateway by hand with `httpx` using Anthropic-protocol headers,
     prints HTTP status + body excerpt.
  3. Calls `ChatAnthropic.invoke("hello")` end-to-end through LangChain.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx

# Repo-root on path so `from src...` works regardless of how we were launched.
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.utils.config import settings  # noqa: E402


GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"
RESET = "\033[0m"


def _ok(label: str, detail: str = "") -> None:
    print(f"{GREEN}[OK]{RESET}   {label}  {detail}")


def _fail(label: str, detail: str = "") -> None:
    print(f"{RED}[FAIL]{RESET} {label}  {detail}", file=sys.stderr)


def _info(label: str, detail: str = "") -> None:
    print(f"{YELLOW}[INFO]{RESET} {label}  {detail}")


# --------------------------------------------------------------------------- #
# Stage 1 — config layer
# --------------------------------------------------------------------------- #
def stage1_config() -> bool:
    print("\n── Stage 1: Settings loaded from .env ──")
    key = settings.anthropic_api_key
    base = settings.anthropic_base_url
    model = settings.anthropic_model

    if not key:
        _fail("ANTHROPIC_API_KEY", "empty after Settings() — check .env")
        return False
    if key.startswith("Bearer "):
        _fail("ANTHROPIC_API_KEY", "starts with 'Bearer ' — strip the prefix")
        return False
    if not base:
        _fail("ANTHROPIC_BASE_URL", "empty")
        return False
    if not model:
        _fail("ANTHROPIC_MODEL", "empty")
        return False

    _ok("ANTHROPIC_API_KEY", f"len={len(key)}, preview={key[:6]}…{key[-4:]}")
    _ok("ANTHROPIC_BASE_URL", base)
    _ok("ANTHROPIC_MODEL", model)
    return True


# --------------------------------------------------------------------------- #
# Stage 2 — raw gateway probe (Anthropic protocol)
# --------------------------------------------------------------------------- #
def stage2_protocol_probe() -> bool:
    print("\n── Stage 2: Raw gateway probe (Anthropic /v1/messages) ──")
    base = settings.anthropic_base_url.rstrip("/")
    url = f"{base}/v1/messages"
    headers = {
        "x-api-key": settings.anthropic_api_key or "",
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
        # Some gateways forward the Authorization header from upstream SDKs.
        "Authorization": f"Bearer {settings.anthropic_api_key}",
    }
    body = {
        "model": settings.anthropic_model,
        "max_tokens": 32,
        "messages": [{"role": "user", "content": "ping"}],
    }

    _info("POST", url)
    try:
        r = httpx.post(url, headers=headers, json=body, timeout=30.0)
    except httpx.HTTPError as exc:
        _fail("transport", repr(exc))
        return False

    snippet = r.text[:300].replace("\n", " ")
    print(f"  HTTP {r.status_code}  body[:300]={snippet}")

    if r.status_code == 200:
        try:
            data = r.json()
            content = data.get("content", [])
            text = "".join(c.get("text", "") for c in content if c.get("type") == "text")
            _ok("protocol = anthropic", f"reply='{text[:80]}'")
            return True
        except Exception as exc:  # noqa: BLE001
            _fail("protocol = anthropic (200 but unparsable)", repr(exc))
            return False

    # Save full body for diagnosis
    Path(REPO_ROOT / "data" / "gateway_probe.txt").parent.mkdir(parents=True, exist_ok=True)
    (REPO_ROOT / "data" / "gateway_probe.txt").write_text(r.text)
    _info("full body saved", "data/gateway_probe.txt")

    # Common failure modes → actionable hints
    if r.status_code in (401, 403):
        _fail("auth", "key rejected by gateway — try OpenAI-protocol block instead")
    elif r.status_code == 404:
        _fail("path", f"{url} not served — gateway may only speak OpenAI; try /v1/chat/completions")
    elif r.status_code == 400:
        _fail("bad request", "check model name or model-vs-protocol mismatch")
    else:
        _fail("unexpected", f"status={r.status_code}")
    return False


# --------------------------------------------------------------------------- #
# Stage 3 — LangChain ChatAnthropic end-to-end
# --------------------------------------------------------------------------- #
def stage3_langchain() -> bool:
    print("\n── Stage 3: ChatAnthropic.invoke ──")
    try:
        from langchain_anthropic import ChatAnthropic
    except ImportError:
        _fail("import", "langchain-anthropic not installed")
        return False

    llm = ChatAnthropic(
        model=settings.anthropic_model,
        api_key=settings.anthropic_api_key,
        base_url=settings.anthropic_base_url,  # may be silently ignored — see note
        timeout=30,
        max_tokens=64,
    )
    try:
        msg = llm.invoke("Reply with the single word: pong")
    except Exception as exc:  # noqa: BLE001
        # Fallback: ChatAnthropic may reject the `base_url=` kwarg on older
        # versions. Retry without it but point the SDK at the gateway via env.
        _info("retry", "base_url= ignored or rejected; falling back to env")
        import os
        os.environ["ANTHROPIC_BASE_URL"] = settings.anthropic_base_url
        llm2 = ChatAnthropic(
            model=settings.anthropic_model,
            api_key=settings.anthropic_api_key,
            timeout=30,
            max_tokens=64,
        )
        try:
            msg = llm2.invoke("Reply with the single word: pong")
        except Exception as exc2:  # noqa: BLE001
            _fail("invoke", repr(exc2))
            return False

    _ok("ChatAnthropic.invoke", f"reply='{msg.content[:80]}'")
    return True


# --------------------------------------------------------------------------- #
def main() -> int:
    results = {
        "config": stage1_config(),
        "raw_probe": stage2_protocol_probe(),
        "langchain": stage3_langchain(),
    }
    print("\n── Summary ──")
    for name, ok in results.items():
        marker = f"{GREEN}PASS{RESET}" if ok else f"{RED}FAIL{RESET}"
        print(f"  {marker}  {name}")
    return 0 if all(results.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
