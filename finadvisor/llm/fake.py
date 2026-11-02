"""Scripted LLM for tests and offline demos. Deterministic by construction."""

from __future__ import annotations

import threading
from typing import Callable, Iterator

from finadvisor.llm.base import Generation, ModelIdentity

JsonFn = Callable[[str, str, dict, str], dict]
TextFn = Callable[[str, str, str], str]


def _default_json(system: str, prompt: str, schema: dict, purpose: str) -> dict:
    return {}


def _default_text(system: str, prompt: str, purpose: str) -> str:
    return "Here is what the numbers show."


class FakeLLM:
    def __init__(self, json_fn: JsonFn | None = None, text_fn: TextFn | None = None, self_hosted: bool = True):
        self.identity = ModelIdentity(provider="fake", model="scripted", self_hosted=self_hosted, seed=0)
        self.json_fn = json_fn or _default_json
        self.text_fn = text_fn or _default_text
        self.calls: list[tuple[str, str]] = []

    def json(self, system: str, prompt: str, schema: dict, *, purpose: str, template: str) -> tuple[dict, Generation]:
        self.calls.append((purpose, prompt))
        out = self.json_fn(system, prompt, schema, purpose)
        return out, Generation(purpose, template, 0.0, out)

    def stream(self, system: str, prompt: str, *, purpose: str, template: str,
               cancel: threading.Event | None = None) -> Iterator[str]:
        self.calls.append((purpose, prompt))
        for word in self.text_fn(system, prompt, purpose).split(" "):
            if cancel is not None and cancel.is_set():
                return
            yield word + " "
