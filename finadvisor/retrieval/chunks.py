"""Splitting library guides into searchable pieces, shared by Chroma and keyword search.

A guide is plain text: the title on the first line, a "Last checked: YYYY-MM-DD" line, then sections, each a short
heading line followed by paragraphs or "- " bullets, and a closing "Sources" section. Each piece is one section (split
further if long) and starts with "<title> — <heading>", so a passage from the middle of a guide still says what it is
about; fixed character windows used to cut sections apart and drop the topic. The Sources section isn't indexed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from finadvisor.retrieval import DOCS_DIR

MAX_CHARS = 900
CHECKED = re.compile(r"^Last checked:\s*(\d{4}-\d{2}-\d{2})\s*$", re.M)


@dataclass
class Chunk:
    chunk_id: str          # "{file}_chunk{n}", stable for citations
    document_name: str
    content: str
    relevance_score: float = 0.0


def _is_heading(line: str) -> bool:
    line = line.strip()
    return 0 < len(line) <= 70 and not line.endswith((".", ":", "?", "!", ";", ",")) and not line.startswith("- ")


def parse(text: str) -> tuple[str, str | None, list[tuple[str, list[str]]]]:
    """(title, last checked date, [(heading, [paragraphs])]); stops at the Sources section."""
    blocks = [b.strip() for b in re.split(r"\n\s*\n", text.replace("\r", "")) if b.strip()]
    if not blocks:
        return "", None, []
    head = blocks[0].splitlines()
    title = head[0].strip()
    m = CHECKED.search(text)
    checked = m.group(1) if m else None
    rest = ["\n".join(head[1:])] if len(head) > 1 else []
    sections: list[tuple[str, list[str]]] = []
    heading = ""
    for b in rest + blocks[1:]:
        b = CHECKED.sub("", b).strip()
        if not b:
            continue
        lines = b.splitlines()
        if _is_heading(lines[0]) and (len(lines) > 1 or len(blocks) > 1):
            heading = lines[0].strip()
            if heading.lower() == "sources":
                break
            body = "\n".join(lines[1:]).strip()
            sections.append((heading, [body] if body else []))
        elif sections:
            sections[-1][1].append(b)
        else:
            sections.append((heading, [b]))
    return title, checked, [(h, ps) for h, ps in sections if ps]


def _split(paragraphs: list[str]) -> list[str]:
    """Groups paragraphs up to MAX_CHARS; a longer paragraph is split by lines, then by sentences."""
    pieces: list[str] = []
    for p in paragraphs:
        parts = [p] if len(p) <= MAX_CHARS else (p.splitlines() if "\n" in p else re.split(r"(?<=[.!?])\s+", p))
        for part in parts:
            if pieces and len(pieces[-1]) + len(part) + 1 <= MAX_CHARS:
                pieces[-1] += "\n" + part
            else:
                pieces.append(part)
    return pieces


def chunk_text(name: str, text: str) -> list[Chunk]:
    title, _, sections = parse(text)
    out = []
    for heading, paragraphs in sections:
        label = f"{title} — {heading}" if heading else title
        for piece in _split(paragraphs):
            out.append(Chunk(f"{name}_chunk{len(out)}", name, f"{label}\n{piece}"))
    return out


def chunk_file(path: Path) -> list[Chunk]:
    return chunk_text(path.name, path.read_text(encoding="utf-8", errors="ignore"))


@lru_cache(maxsize=256)
def _meta(name: str, mtime: float) -> tuple[str, str | None]:
    title, checked, _ = parse((DOCS_DIR / name).read_text(encoding="utf-8", errors="ignore"))
    return title, checked


def doc_title(name: str) -> str:
    """The guide's own first line, or a title made from the file name if it has none."""
    f = DOCS_DIR / name
    title = _meta(name, f.stat().st_mtime)[0] if f.exists() else ""
    if title and len(title) <= 120:
        return title
    parts = Path(name).stem.split("_")
    return " ".join(p.capitalize() for p in (parts[1:] if parts and parts[0].isdigit() else parts))


def last_checked(name: str) -> str | None:
    f = DOCS_DIR / name
    return _meta(name, f.stat().st_mtime)[1] if f.exists() else None
