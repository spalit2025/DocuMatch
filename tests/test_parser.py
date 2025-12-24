"""
Tests for the Parser Engine.

Run with: pytest tests/test_parser.py -v
"""

import tempfile
from pathlib import Path

import pytest

from core.parser_engine import ParserEngine, parse_pdf
from core.models import ParseResult


class TestParserEngine:
    """Test cases for ParserEngine class."""

    def test_init_default(self):
        """Test default initialization."""
        parser = ParserEngine()
        assert parser.fallback_enabled is True

    def test_init_no_fallback(self):
        """Test initialization with fallback disabled."""
        parser = ParserEngine(fallback_enabled=False)
        assert parser.fallback_enabled is False

    def test_parse_nonexistent_file(self):
        """Test parsing a file that doesn't exist."""
        parser = ParserEngine()
        result = parser.parse_to_markdown("/nonexistent/path/file.pdf")

        assert result.success is False
        assert "not found" in result.error_message.lower()
        assert result.markdown == ""

    def test_parse_non_pdf_file(self):
        """Test parsing a non-PDF file."""
        parser = ParserEngine()

        # Create a temporary non-PDF file
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"This is not a PDF")
            temp_path = f.name

        try:
            result = parser.parse_to_markdown(temp_path)
            assert result.success is False
            assert "not a pdf" in result.error_message.lower()
        finally:
            Path(temp_path).unlink()

    def test_parse_result_model(self):
        """Test ParseResult model creation."""
        result = ParseResult(
            markdown="# Test\n\nContent here",
            page_count=5,
            tables_found=2,
            parse_method="docling",
            success=True,
            error_message=None,
            file_path="/test/path.pdf"
        )

        assert result.markdown == "# Test\n\nContent here"
        assert result.page_count == 5
        assert result.tables_found == 2
        assert result.parse_method == "docling"
        assert result.success is True

    def test_table_to_markdown(self):
        """Test table conversion to markdown."""
        parser = ParserEngine()

        table = [
            ["Header 1", "Header 2", "Header 3"],
            ["Row 1 Col 1", "Row 1 Col 2", "Row 1 Col 3"],
            ["Row 2 Col 1", "Row 2 Col 2", "Row 2 Col 3"],
        ]

        markdown_table = parser._table_to_markdown(table)

        assert "| Header 1 | Header 2 | Header 3 |" in markdown_table
        assert "| --- | --- | --- |" in markdown_table
        assert "| Row 1 Col 1 | Row 1 Col 2 | Row 1 Col 3 |" in markdown_table

    def test_table_to_markdown_empty(self):
        """Test table conversion with empty table."""
        parser = ParserEngine()

        assert parser._table_to_markdown([]) == ""
        assert parser._table_to_markdown([[]]) == ""

    def test_table_to_markdown_none_cells(self):
        """Test table conversion with None cells."""
        parser = ParserEngine()

        table = [
            ["Header 1", None, "Header 3"],
            [None, "Value", None],
        ]

        markdown_table = parser._table_to_markdown(table)
        assert "| Header 1 |  | Header 3 |" in markdown_table

    def test_clean_text(self):
        """Test text cleaning."""
        parser = ParserEngine()

        dirty_text = "Line 1\n\n\n\n\nLine 2   \nLine 3  "
        cleaned = parser._clean_text(dirty_text)

        assert "\n\n\n" not in cleaned  # No triple newlines
        assert "Line 2   " not in cleaned  # Trailing spaces removed
        assert "Line 1" in cleaned
        assert "Line 2" in cleaned

    def test_count_tables(self):
        """Test table counting in markdown."""
        parser = ParserEngine()

        markdown_with_tables = """
# Document

| Col1 | Col2 |
| --- | --- |
| A | B |

Some text here.

| Header |
| --- |
| Data |
"""
        count = parser._count_tables(markdown_with_tables)
        assert count == 2

    def test_count_tables_no_tables(self):
        """Test table counting with no tables."""
        parser = ParserEngine()

        markdown_no_tables = "# Just a heading\n\nSome paragraph text."
        count = parser._count_tables(markdown_no_tables)
        assert count == 0

    def test_convenience_function(self):
        """Test the parse_pdf convenience function."""
        result = parse_pdf("/nonexistent/file.pdf")
        assert isinstance(result, ParseResult)
        assert result.success is False


class TestParserIntegration:
    """Integration tests requiring actual PDF files."""

    @pytest.fixture
    def sample_pdf_path(self):
        """
        Fixture to provide a sample PDF path.

        Override this in your test environment with an actual PDF.
        """
        # Check for sample PDFs in data directory
        sample_paths = [
            Path("data/contracts/sample.pdf"),
            Path("data/invoices/sample.pdf"),
            Path("tests/fixtures/sample.pdf"),
        ]

        for path in sample_paths:
            if path.exists():
                return str(path)

        pytest.skip("No sample PDF found for integration testing")

    def test_parse_real_pdf(self, sample_pdf_path):
        """Test parsing a real PDF file."""
        parser = ParserEngine()
        result = parser.parse_to_markdown(sample_pdf_path)

        assert result.success is True
        assert len(result.markdown) > 0
        assert result.page_count > 0
        assert result.parse_method in ["docling", "pdfplumber"]

    def test_parse_real_pdf_with_fallback(self, sample_pdf_path):
        """Test parsing with fallback forced."""
        parser = ParserEngine(fallback_enabled=True)
        # Force pdfplumber by setting docling as unavailable
        parser._docling_available = False

        result = parser.parse_to_markdown(sample_pdf_path)

        assert result.success is True
        assert result.parse_method == "pdfplumber"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
