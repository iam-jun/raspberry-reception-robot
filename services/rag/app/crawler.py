from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
import yaml
from bs4 import BeautifulSoup

from .cleaner import clean_html_to_markdown
from .config import MARKDOWN_DIR, RAW_HTML_DIR, SOURCES_PATH, ensure_directories


@dataclass
class Source:
    id: str
    name: str
    url: str
    source_type: str
    domain: str
    language: str
    enabled: bool = True


def load_sources(path: Path = SOURCES_PATH, enabled_only: bool = True) -> list[Source]:
    if not path.exists():
        raise FileNotFoundError(f"Source configuration not found: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    sources = []
    for item in data.get("sources", []):
        source = Source(
            id=str(item["id"]),
            name=str(item["name"]),
            url=str(item["url"]),
            source_type=str(item.get("source_type", "public_website")),
            domain=str(item.get("domain", "")),
            language=str(item.get("language", "vi")),
            enabled=bool(item.get("enabled", True)),
        )
        if source.enabled or not enabled_only:
            sources.append(source)
    return sources


def crawl_enabled_sources(path: Path = SOURCES_PATH) -> list[dict[str, Any]]:
    ensure_directories()
    results = []
    for source in load_sources(path, enabled_only=True):
        results.append(crawl_source(source))
    return results


def crawl_source(source: Source) -> dict[str, Any]:
    response = requests.get(
        source.url,
        timeout=30,
        headers={"User-Agent": "SmartReceptionRobotRAG/0.1 (+student MVP)"},
    )
    try:
        response.raise_for_status()
    except requests.HTTPError as error:
        raise RuntimeError(f"Could not crawl {source.id} from {source.url}: {error}") from error

    html = response.text
    raw_path = RAW_HTML_DIR / f"{source.id}.html"
    markdown_path = MARKDOWN_DIR / f"{source.id}.md"
    raw_path.write_text(html, encoding="utf-8")

    title = source.name or _page_title(html)
    metadata = {
        "source_id": source.id,
        "title": title,
        "source_url": source.url,
        "source_type": source.source_type,
        "domain": source.domain,
        "language": source.language,
        "crawled_at": datetime.now(timezone.utc).isoformat(),
    }
    body = clean_html_to_markdown(html, metadata=metadata)
    markdown_path.write_text(_frontmatter(metadata) + "\n\n" + body + "\n", encoding="utf-8")

    return {
        "source_id": source.id,
        "url": source.url,
        "raw_html_path": str(raw_path),
        "markdown_path": str(markdown_path),
        "bytes": len(html.encode("utf-8")),
        "title": title,
    }


def _page_title(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    h1 = soup.find("h1")
    if h1:
        text = h1.get_text(" ", strip=True)
        if text:
            return text
    if soup.title and soup.title.string:
        return soup.title.string.strip()
    return ""


def _frontmatter(metadata: dict[str, str]) -> str:
    lines = ["---"]
    for key, value in metadata.items():
        escaped = str(value).replace('"', '\\"')
        lines.append(f'{key}: "{escaped}"')
    lines.append("---")
    return "\n".join(lines)
