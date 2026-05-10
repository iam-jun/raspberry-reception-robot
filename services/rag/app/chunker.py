from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any


FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n?", re.DOTALL)
HEADING_RE = re.compile(r"^(#{1,3})\s+(.+)$", re.MULTILINE)


@dataclass
class Chunk:
    chunk_id: str
    text: str
    metadata: dict[str, Any]


def parse_frontmatter(markdown: str) -> tuple[dict[str, str], str]:
    match = FRONTMATTER_RE.match(markdown)
    if not match:
        return {}, markdown.strip()
    metadata: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        metadata[key.strip()] = value.strip().strip('"').strip("'")
    return metadata, markdown[match.end() :].strip()


def chunk_markdown(markdown: str, target_size: int = 2000, overlap: int = 250) -> list[Chunk]:
    metadata, body = parse_frontmatter(markdown)
    sections = _split_by_headings(body)
    chunks: list[Chunk] = []

    for section in sections:
        for part in _split_long_text(section, target_size=target_size, overlap=overlap):
            index = len(chunks)
            source_id = metadata.get("source_id", "unknown_source")
            digest = hashlib.sha1(part.encode("utf-8")).hexdigest()[:10]
            chunk_id = f"{source_id}-{index:04d}-{digest}"
            chunk_meta = {
                "source_id": source_id,
                "source_url": metadata.get("source_url", ""),
                "title": metadata.get("title", ""),
                "domain": metadata.get("domain", ""),
                "language": metadata.get("language", ""),
                "chunk_index": index,
            }
            chunks.append(Chunk(chunk_id=chunk_id, text=part, metadata=chunk_meta))
    return chunks


def _split_by_headings(text: str) -> list[str]:
    text = text.strip()
    if not text:
        return []
    matches = list(HEADING_RE.finditer(text))
    if not matches:
        return [text]

    sections: list[str] = []
    if matches[0].start() > 0:
        intro = text[: matches[0].start()].strip()
        if intro:
            sections.append(intro)
    for i, match in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        section = text[match.start() : end].strip()
        if section:
            sections.append(section)
    return sections


def _split_long_text(text: str, target_size: int, overlap: int) -> list[str]:
    text = text.strip()
    if len(text) <= target_size:
        return [text] if text else []

    parts: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + target_size, len(text))
        if end < len(text):
            end = _nearest_boundary(text, start, end)
        part = text[start:end].strip()
        if part:
            parts.append(part)
        if end >= len(text):
            break
        start = max(0, end - overlap)
        while start < len(text) and start > 0 and not text[start - 1].isspace():
            start += 1
    return parts


def _nearest_boundary(text: str, start: int, proposed_end: int) -> int:
    window = text[start:proposed_end]
    for pattern in ("\n\n", "\n- ", ". ", "? ", "! ", "; "):
        idx = window.rfind(pattern)
        if idx > max(400, len(window) // 2):
            return start + idx + len(pattern)
    while proposed_end > start and not text[proposed_end - 1].isspace():
        proposed_end -= 1
    return max(proposed_end, start + len(window))

