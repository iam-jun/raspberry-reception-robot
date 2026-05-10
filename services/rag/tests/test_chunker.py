from __future__ import annotations

from app.chunker import chunk_markdown


def test_chunker_creates_non_empty_chunks_with_metadata() -> None:
    markdown = """---
source_id: "uit_admission_faq"
title: "Câu hỏi thường gặp - Tuyển sinh UIT"
source_url: "https://tuyensinh.uit.edu.vn/cau-hoi-thuong-gap"
domain: "UIT tuyển sinh"
language: "vi"
---

# Câu hỏi thường gặp

## UIT là trường gì?

UIT là trường đại học công lập.
"""

    chunks = chunk_markdown(markdown)

    assert chunks
    assert chunks[0].text
    assert chunks[0].metadata["source_id"] == "uit_admission_faq"
    assert chunks[0].metadata["chunk_index"] == 0

