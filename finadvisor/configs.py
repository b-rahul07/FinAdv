"""Loads the versioned YAML configs in configs/ and fingerprints them for reproducibility."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

CONFIG_DIR = Path(__file__).resolve().parent.parent / "configs"

_FILES = {
    "rules": "rules/{}.yaml",
    "shelf": "shelf/{}.yaml",
    "assumptions": "assumptions/{}.yaml",
    "willingness": "willingness/{}.yaml",
    "tax": "tax/{}.yaml",
}

# version id inside the file -> file stem, for the ids that differ from their stems
_STEMS = {
    "rules-v1": "v1",
    "rules-v2": "v2",
    "shelf-v1": "v1",
    "assumptions-v1": "v1",
    "gl13-in-v1": "gl13_in_v1",
    "tax-fy2026-27": "fy2026_27",
}


def _load_yaml(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def fingerprint(obj: Any) -> str:
    """Short stable hash of any JSON-serialisable object."""
    raw = json.dumps(obj, sort_keys=True, ensure_ascii=False, default=str).encode()
    return hashlib.sha256(raw).hexdigest()[:12]


@dataclass(frozen=True)
class Bundle:
    """Everything one pipeline run needs, loaded from config files."""

    pipeline: dict
    rules: dict
    shelf: dict
    assumptions: dict
    willingness: dict
    tax: dict
    models: dict

    @property
    def versions(self) -> dict[str, str]:
        return {
            "pipeline": self.pipeline["version"],
            "rules": self.rules["version"],
            "shelf": self.shelf["version"],
            "assumptions": self.assumptions["version"],
            "willingness": self.willingness["version"],
            "tax": self.tax["version"],
            "fingerprint": fingerprint(
                [self.pipeline, self.rules, self.shelf, self.assumptions, self.willingness, self.tax]
            ),
        }

    def with_pipeline(self, pipeline: dict) -> "Bundle":
        return Bundle(pipeline, self.rules, self.shelf, self.assumptions, self.willingness, self.tax, self.models)


def load_component(kind: str, version: str) -> dict:
    stem = _STEMS.get(version, version)
    data = _load_yaml(CONFIG_DIR / _FILES[kind].format(stem))
    if data.get("version") != version:
        raise ValueError(f"{kind} config {stem} declares version {data.get('version')!r}, expected {version!r}")
    return data


def load_bundle(pipeline_path: str | Path = "pipeline/default.yaml") -> Bundle:
    path = Path(pipeline_path)
    if not path.is_absolute():
        path = CONFIG_DIR / path
    pipeline = _load_yaml(path)
    return Bundle(
        pipeline=pipeline,
        rules=load_component("rules", pipeline["rules"]),
        shelf=load_component("shelf", pipeline["shelf"]),
        assumptions=load_component("assumptions", pipeline["assumptions"]),
        willingness=load_component("willingness", pipeline["willingness"]),
        tax=load_component("tax", pipeline["tax"]),
        models=_load_yaml(CONFIG_DIR / "models.yaml")["models"],
    )


@lru_cache(maxsize=1)
def default_bundle() -> Bundle:
    return load_bundle()
