"""Ollama client using the HTTP API directly (structured JSON output + token streaming)."""

from __future__ import annotations

import json
import os
import threading
from typing import Iterator

import httpx

from finadvisor.llm.base import Generation, JsonCache, ModelIdentity, timed


# Keep the model in memory between chats. Ollama's default unloads it after 5 idle minutes, so the next answer paid a
# several-second reload. Does not change outputs.
KEEP_ALIVE = "30m"

class OllamaLLM:
    def __init__(self, cfg: dict, base_url: str | None = None, timeout: float = 600.0, memo: bool = True):
        self.base_url = (base_url or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")).rstrip("/")
        model = cfg["model"]  # always from configs/models.yaml, so results record what actually ran
        opts = dict(cfg.get("options", {}))
        self.identity = ModelIdentity(
            provider="ollama", model=model, self_hosted=bool(cfg.get("self_hosted", True)),
            temperature=opts.get("temperature", 0.0), seed=opts.get("seed"), options=opts,
        )
        self._timeout = timeout
        self._cache = JsonCache() if memo else None   # memo off for replicate runs that measure variability
        self._described = False

    def describe(self) -> None:
        """Fill digest and quantisation from the server, once."""
        if self._described:
            return
        try:
            r = httpx.post(f"{self.base_url}/api/show", json={"model": self.identity.model}, timeout=10)
            r.raise_for_status()
            d = r.json()
            self.identity.quantization = d.get("details", {}).get("quantization_level")
            tags = httpx.get(f"{self.base_url}/api/tags", timeout=10).json().get("models", [])
            for t in tags:
                if t.get("name") in (self.identity.model, f"{self.identity.model}:latest"):
                    self.identity.digest = t.get("digest")
            self._described = True
        except httpx.HTTPError:
            pass

    def available(self) -> bool:
        try:
            return httpx.get(f"{self.base_url}/api/tags", timeout=3).status_code == 200
        except httpx.HTTPError:
            return False

    def json(self, system: str, prompt: str, schema: dict, *, purpose: str, template: str) -> tuple[dict, Generation]:
        self.describe()
        key = (system, prompt, json.dumps(schema, sort_keys=True))
        hit = self._cache.get(key) if self._cache else None
        if hit is not None:
            return hit, Generation(purpose, template, 0.0, hit, cached=True)
        body = {
            "model": self.identity.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            "format": schema,
            "stream": False,
            "options": self.identity.options,
            "keep_alive": KEEP_ALIVE,
        }

        def call():
            r = httpx.post(f"{self.base_url}/api/chat", json=body, timeout=self._timeout)
            r.raise_for_status()
            return r.json()

        data, dt = timed(call)
        content = data["message"]["content"]
        try:
            out = json.loads(content)
        except json.JSONDecodeError:
            out = {"_unparseable": content}
        if self._cache:
            self._cache.put(key, out)
        return out, Generation(purpose, template, round(dt, 3), out,
                               data.get("prompt_eval_count"), data.get("eval_count"))

    def stream(self, system: str, prompt: str, *, purpose: str, template: str,
               cancel: threading.Event | None = None) -> Iterator[str]:
        self.describe()
        body = {
            "model": self.identity.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            "stream": True,
            "options": self.identity.options,
            "keep_alive": KEEP_ALIVE,
        }
        with httpx.stream("POST", f"{self.base_url}/api/chat", json=body, timeout=self._timeout) as r:
            r.raise_for_status()
            for line in r.iter_lines():
                if cancel is not None and cancel.is_set():
                    break
                if not line:
                    continue
                chunk = json.loads(line)
                piece = chunk.get("message", {}).get("content", "")
                if piece:
                    yield piece
                if chunk.get("done"):
                    break
