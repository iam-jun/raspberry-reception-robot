from __future__ import annotations

from app.cleaner import clean_html_to_markdown


def test_cleaner_removes_scripts_and_styles() -> None:
    html = """
    <html>
      <head><style>.x{color:red}</style><script>alert("x")</script></head>
      <body>
        <header>Menu</header>
        <main>
          <h1>Câu hỏi thường gặp</h1>
          <p>UIT là trường công lập.</p>
        </main>
      </body>
    </html>
    """

    markdown = clean_html_to_markdown(html, metadata={"source_url": "https://example.test"})

    assert "alert" not in markdown
    assert "color:red" not in markdown
    assert "# Câu hỏi thường gặp" in markdown
    assert "UIT là trường công lập." in markdown

