"""Model providers. The agent needs one thing from a model: given a system
prompt, some content and one tool, return that tool's JSON input.

  anthropic  Claude over the Messages API (standard library only, no SDK)
  replay     recorded responses from a folder; used by the tests and for
             re-running a past run without a key
"""
from __future__ import annotations

import base64
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

API_URL = "https://api.anthropic.com/v1/messages"


class LLMError(RuntimeError):
    pass


class Provider:
    name = "base"
    model = ""

    def __init__(self) -> None:
        self.calls: list[dict] = []   # one entry per call: usage and timing

    def call_tool(self, system: str, text: str, tool: dict, pdf: bytes = b"") -> dict:
        raise NotImplementedError


class AnthropicProvider(Provider):
    name = "anthropic"

    def __init__(self, model: str, api_key: str | None = None, max_tokens: int = 16000) -> None:
        super().__init__()
        self.model = model
        self.max_tokens = max_tokens
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        if not self.api_key:
            raise LLMError("ANTHROPIC_API_KEY is not set. Set it, or use --provider replay.")

    def call_tool(self, system: str, text: str, tool: dict, pdf: bytes = b"") -> dict:
        content: list[dict] = []
        if pdf:  # documents go before the text
            content.append({"type": "document", "source": {
                "type": "base64", "media_type": "application/pdf",
                "data": base64.standard_b64encode(pdf).decode("ascii")}})
        content.append({"type": "text", "text": text})
        body = {
            "model": self.model, "max_tokens": self.max_tokens, "system": system,
            "messages": [{"role": "user", "content": content}],
            "tools": [tool], "tool_choice": {"type": "tool", "name": tool["name"]},
        }
        started = time.time()
        data = self._post(body)
        self.calls.append({"model": self.model, "seconds": round(time.time() - started, 1),
                           "usage": data.get("usage", {}), "stop_reason": data.get("stop_reason")})
        if data.get("stop_reason") == "max_tokens":
            raise LLMError("The model ran out of output tokens before finishing the chart; raise max_tokens.")
        for block in data.get("content", []):
            if block.get("type") == "tool_use" and block.get("name") == tool["name"]:
                return block["input"]
        raise LLMError(f"The model did not call {tool['name']} (stop_reason={data.get('stop_reason')}).")

    def _post(self, body: dict, attempts: int = 4) -> dict:
        req = urllib.request.Request(API_URL, data=json.dumps(body).encode("utf-8"), headers={
            "content-type": "application/json", "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01"})
        for attempt in range(attempts):
            try:
                with urllib.request.urlopen(req, timeout=600) as resp:
                    return json.loads(resp.read())
            except urllib.error.HTTPError as e:
                detail = e.read().decode("utf-8", "replace")[:500]
                if e.code in (429, 500, 502, 503, 529) and attempt < attempts - 1:
                    time.sleep(2 ** attempt * 2)
                    continue
                raise LLMError(f"API error {e.code}: {detail}") from None
            except urllib.error.URLError as e:
                if attempt < attempts - 1:
                    time.sleep(2 ** attempt * 2)
                    continue
                raise LLMError(f"Cannot reach the API: {e.reason}") from None
        raise LLMError("unreachable")


class ReplayProvider(Provider):
    """Returns 01.json, 02.json, ... from a folder, in order."""
    name = "replay"

    def __init__(self, folder: str | Path) -> None:
        super().__init__()
        self.files = sorted(p for p in Path(folder).glob("[0-9]*.json"))
        self.model = f"replay:{Path(folder).name}"
        if not self.files:
            raise LLMError(f"No recorded responses (NN.json) in {folder}")

    def call_tool(self, system: str, text: str, tool: dict, pdf: bytes = b"") -> dict:
        if len(self.calls) >= len(self.files):
            raise LLMError("The recording has no more responses.")
        path = self.files[len(self.calls)]
        self.calls.append({"model": self.model, "file": path.name})
        return json.loads(path.read_text(encoding="utf-8"))


def make_provider(kind: str, model: str = "", replay: str | None = None) -> Provider:
    if kind == "replay":
        if not replay:
            raise LLMError("--provider replay needs --replay <folder>")
        return ReplayProvider(replay)
    return AnthropicProvider(model)
