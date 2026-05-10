from __future__ import annotations

import re
from typing import Any

from bs4 import BeautifulSoup, NavigableString, Tag


DROP_TAGS = {"script", "style", "nav", "footer", "header", "noscript", "svg", "form"}
SKIP_TEXT_PATTERNS = (
    "toggle navigation",
    "skip to main content",
    "đăng nhập",
    "login",
)


def normalize_whitespace(text: str) -> str:
    text = text.replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def clean_html_to_markdown(html: str, metadata: dict[str, Any] | None = None) -> str:
    """Convert a public admission page into stable Markdown-like text."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all(DROP_TAGS):
        tag.decompose()
    for tag in soup.find_all(attrs={"aria-hidden": "true"}):
        tag.decompose()

    root = _best_content_root(soup)
    lines: list[str] = []
    _walk(root, lines)
    markdown = normalize_whitespace("\n".join(lines))
    markdown = _remove_low_value_lines(markdown)
    markdown = _enhance_faq_structure(markdown)

    if metadata and metadata.get("source_url") and metadata["source_url"] not in markdown:
        markdown = f"{markdown}\n\nNguồn: {metadata['source_url']}".strip()
    return markdown


def _best_content_root(soup: BeautifulSoup) -> Tag:
    candidates = []
    selectors = [
        "main",
        "article",
        "[role=main]",
        ".content",
        ".main-content",
        ".region-content",
        "#content",
        ".node",
    ]
    for selector in selectors:
        candidates.extend(soup.select(selector))
    if not candidates:
        body = soup.body
        return body if body is not None else soup
    return max(candidates, key=lambda tag: len(tag.get_text(" ", strip=True)))


def _walk(node: Tag | NavigableString, lines: list[str], list_depth: int = 0) -> None:
    if isinstance(node, NavigableString):
        return
    if not isinstance(node, Tag):
        return

    name = node.name.lower() if node.name else ""
    if name in DROP_TAGS:
        return

    if name in {"h1", "h2", "h3"}:
        text = _clean_text(node.get_text(" ", strip=True))
        if text:
            level = {"h1": "#", "h2": "##", "h3": "###"}[name]
            _append(lines, f"\n{level} {text}\n")
        return

    if name in {"p", "div", "section", "article"}:
        if _has_block_children(node):
            for child in node.children:
                _walk(child, lines, list_depth)
        else:
            text = _clean_text(node.get_text(" ", strip=True))
            if text:
                _append(lines, text)
        if name in {"section", "article"}:
            _append(lines, "")
        return

    if name in {"ul", "ol"}:
        for child in node.find_all("li", recursive=False):
            _walk(child, lines, list_depth + 1)
        _append(lines, "")
        return

    if name == "li":
        text = _clean_text(node.get_text(" ", strip=True))
        if text:
            indent = "  " * max(list_depth - 1, 0)
            _append(lines, f"{indent}- {text}")
        return

    if name == "table":
        table_md = _table_to_markdown(node)
        if table_md:
            _append(lines, table_md)
            _append(lines, "")
        return

    if name == "br":
        _append(lines, "")
        return

    for child in node.children:
        _walk(child, lines, list_depth)


def _has_block_children(node: Tag) -> bool:
    return any(
        isinstance(child, Tag)
        and child.name
        and child.name.lower() in {"h1", "h2", "h3", "p", "ul", "ol", "li", "table", "section", "article"}
        for child in node.children
    )


def _clean_text(text: str) -> str:
    text = normalize_whitespace(text)
    text = re.sub(r"\s+([,.!?;:%])", r"\1", text)
    return text


def _append(lines: list[str], text: str) -> None:
    text = text.strip()
    if not text:
        if lines and lines[-1] != "":
            lines.append("")
        return
    if any(pattern in text.lower() for pattern in SKIP_TEXT_PATTERNS):
        return
    if lines and lines[-1] == text:
        return
    lines.append(text)


def _table_to_markdown(table: Tag) -> str:
    rows: list[list[str]] = []
    for tr in table.find_all("tr"):
        cells = [_clean_text(cell.get_text(" ", strip=True)) for cell in tr.find_all(["th", "td"])]
        if any(cells):
            rows.append(cells)
    if not rows:
        return ""
    width = max(len(row) for row in rows)
    rows = [row + [""] * (width - len(row)) for row in rows]
    header = rows[0]
    separator = ["---"] * width
    body = rows[1:]
    parts = ["| " + " | ".join(header) + " |", "| " + " | ".join(separator) + " |"]
    parts.extend("| " + " | ".join(row) + " |" for row in body)
    return "\n".join(parts)


def _remove_low_value_lines(markdown: str) -> str:
    lines = []
    seen_empty = False
    for raw_line in markdown.splitlines():
        line = raw_line.strip()
        if not line:
            if not seen_empty:
                lines.append("")
            seen_empty = True
            continue
        seen_empty = False
        if len(line) <= 2 and not line.startswith("#"):
            continue
        lines.append(line)
    return normalize_whitespace("\n".join(lines))


def _enhance_faq_structure(markdown: str) -> str:
    """Turn common UIT FAQ inline numbering into scan-friendly Markdown."""
    text = markdown
    for number in range(1, 30):
        text = re.sub(rf"\s+({number}\.\s+)", rf"\n\n## \1", text)
    text = re.sub(r"\s+(Trả lời:)", r"\n\n\1", text)
    text = re.sub(r"\s+([a-z]\)\s+[A-ZĐÂĂÊÔƠƯ])", r"\n\n### \1", text)
    text = re.sub(r"\s+(Mã trường:)", r"\n\n- \1", text)
    text = re.sub(r"\s+(Các tuyến xe bus|Các tuyến bus lận cận|Tuyến 6,)", r"\n\n- \1", text)
    return normalize_whitespace(text)
