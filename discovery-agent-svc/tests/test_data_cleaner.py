"""Tests for DataCleaner — HTML to Markdown conversion."""

from app.scrapers.data_cleaner import DataCleaner


class TestHtmlToMarkdown:
    """HTML-to-Markdown conversion tests."""

    def test_simple_html_converts(self) -> None:
        cleaner = DataCleaner()
        result = cleaner.clean("<h1>Title</h1><p>Content here.</p>")
        assert "Title" in result
        assert "Content here." in result

    def test_strips_script_tags(self) -> None:
        cleaner = DataCleaner()
        result = cleaner.clean(
            "<p>Good content</p><script>alert('evil')</script>"
        )
        assert "alert" not in result
        assert "Good content" in result

    def test_strips_style_tags(self) -> None:
        cleaner = DataCleaner()
        result = cleaner.clean(
            "<style>body{color:red}</style><p>Visible text</p>"
        )
        assert "color:red" not in result
        assert "Visible text" in result

    def test_strips_nav_elements(self) -> None:
        cleaner = DataCleaner()
        result = cleaner.clean(
            "<nav><a href='/'>Home</a></nav><p>Main content</p>"
        )
        assert "Main content" in result
        # nav should be stripped
        assert "<nav>" not in result

    def test_strips_header_and_footer(self) -> None:
        cleaner = DataCleaner()
        result = cleaner.clean(
            "<header>Site Header</header>"
            "<p>Main content</p>"
            "<footer>Site Footer</footer>"
        )
        assert "Main content" in result
        assert "Site Header" not in result
        assert "Site Footer" not in result

    def test_empty_html_returns_empty(self) -> None:
        cleaner = DataCleaner()
        assert cleaner.clean("") == ""
        assert cleaner.clean("   ") == ""

    def test_only_scripts_returns_empty(self) -> None:
        cleaner = DataCleaner()
        result = cleaner.clean(
            "<script>var x = 1;</script><style>.a{}</style>"
        )
        assert result == ""

    def test_truncates_long_content(self) -> None:
        cleaner = DataCleaner(max_length=100)
        long_html = "<p>" + "x" * 500 + "</p>"
        result = cleaner.clean(long_html)
        assert len(result) <= 100

    def test_strips_noscript_and_iframe(self) -> None:
        cleaner = DataCleaner()
        result = cleaner.clean(
            "<noscript>Enable JS</noscript>"
            "<iframe src='https://ad.com'></iframe>"
            "<p>Real content</p>"
        )
        assert "Enable JS" not in result
        assert "Real content" in result


class TestIsDownloadable:
    """Downloadable file detection tests."""

    def test_pdf_is_downloadable(self) -> None:
        assert DataCleaner.is_downloadable("file.pdf", "application/pdf")

    def test_xlsx_is_downloadable(self) -> None:
        assert DataCleaner.is_downloadable(
            "report.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    def test_csv_is_downloadable(self) -> None:
        assert DataCleaner.is_downloadable("data.csv", "text/csv")

    def test_html_is_not_downloadable(self) -> None:
        assert not DataCleaner.is_downloadable("page.html", "text/html")

    def test_image_is_not_downloadable(self) -> None:
        assert not DataCleaner.is_downloadable("photo.png", "image/png")

    def test_url_extension_fallback(self) -> None:
        # Even with empty content-type, PDF extension detected
        assert DataCleaner.is_downloadable("https://example.com/report.pdf", "")

    def test_docx_is_downloadable(self) -> None:
        assert DataCleaner.is_downloadable(
            "doc.docx",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
