from __future__ import annotations

import threading
import time
from dataclasses import asdict, dataclass, field
from typing import Callable, Iterator, Protocol


class PrivacyError(RuntimeError):
    """Raised when real-user data would reach a model we do not host."""


@dataclass
class ModelIdentity:
    provider: str
    model: str
    self_hosted: bool
    digest: str | None = None
    quantization: str | None = None
    temperature: float = 0.0
    seed: int | None = None
    options: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Generation:
    """One recorded LLM call."""

    purpose: str
    template: str            # prompt-template id@hash
    latency_s: float
    output: object
    prompt_tokens: int | None = None
    output_tokens: int | None = None
    cached: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


class LLM(Protocol):
    identity: ModelIdentity

    def json(self, system: str, prompt: str, schema: dict, *, purpose: str, template: str) -> tuple[dict, Generation]: ...

    def stream(self, system: str, prompt: str, *, purpose: str, template: str,
               cancel: threading.Event | None = None) -> Iterator[str]: ...


def require_self_hosted(llm: LLM) -> None:
    if not llm.identity.self_hosted:
        raise PrivacyError(f"{llm.identity.provider}/{llm.identity.model} is not self-hosted; "
                           "real-user data may only go to models we host.")


class JsonCache:
    """In-process memo for identical JSON calls (same prompt at temperature 0 gives the same output)."""

    def __init__(self, maxsize: int = 512):
        self._d: dict[tuple, dict] = {}
        self._max = maxsize
        self._lock = threading.Lock()

    def get(self, key: tuple) -> dict | None:
        with self._lock:
            return self._d.get(key)

    def put(self, key: tuple, value: dict) -> None:
        with self._lock:
            if len(self._d) >= self._max:
                self._d.pop(next(iter(self._d)))
            self._d[key] = value


def timed(fn: Callable[[], object]) -> tuple[object, float]:
    t = time.perf_counter()
    out = fn()
    return out, time.perf_counter() - t


def get_llm(name: str, models_cfg: dict, **kw) -> LLM:
    cfg = models_cfg[name]
    if cfg["provider"] == "ollama":
        from finadvisor.llm.ollama import OllamaLLM
        return OllamaLLM(cfg, **kw)
    if cfg["provider"] == "fake":
        from finadvisor.llm.fake import FakeLLM
        return FakeLLM(**kw)
    raise ValueError(f"unknown provider {cfg['provider']}")
