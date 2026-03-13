"""
Parser Engine for DocuMatch Architect.

Converts PDF documents to Markdown format using Docling,
with pdfplumber as a fallback option.
"""

import logging
import re
from pathlib import Path
from typing import Optional

import pdfplumber

from config import settings
from .models import ParseResult

# Configure logging
logger = logging.getLogger(__name__)


class ParserEngine:
    """
    PDF to Markdown parser using Docling with pdfplumber fallback.

    Usage:
        parser = ParserEngine()
        result = parser.parse_to_markdown("/path/to/document.pdf")
        if result.success:
            print(result.markdown)
    """

    def __init__(self, fallback_enabled: bool = True):
        """
        Initialize the parser engine.

        Args:
            fallback_enabled: Whether to use pdfplumber if Docling fails
        """
        self.fallback_enabled = fallback_enabled
        self._docling_available = self._check_docling()

    def _check_docling(self) -> bool:
        """Check if Docling is available."""
        try:
            from docling.document_converter import DocumentConverter
            return True
        except ImportError:
            logger.warning("Docling not available. Will use pdfplumber only.")
            return False

    def parse_to_markdown(self, file_path: str) -> ParseResult:
        """
        Parse a PDF file to Markdown format.

        Attempts Docling first, falls back to pdfplumber if enabled.

        Args:
            file_path: Path to the PDF file

        Returns:
            ParseResult with markdown content and metadata
        """
        path = Path(file_path)

        # Validate file exists
        if not path.exists():
            return ParseResult(
                markdown="",
                page_count=0,
                tables_found=0,
                parse_method="docling",
                success=False,
                error_message=f"File not found: {file_path}",
                file_path=str(path)
            )

        # Validate file is PDF
        if path.suffix.lower() != ".pdf":
            return ParseResult(
                markdown="",
                page_count=0,
                tables_found=0,
                parse_method="docling",
                success=False,
                error_message=f"Not a PDF file: {file_path}",
                file_path=str(path)
            )

        # Enforce max file size to prevent MemoryError
        file_size = path.stat().st_size
        if file_size > settings.max_file_size_bytes:
            size_mb = file_size / (1024 * 1024)
            return ParseResult(
                markdown="",
                page_count=0,
                tables_found=0,
                parse_method="docling",
                success=False,
                error_message=f"File too large: {size_mb:.1f}MB exceeds limit of {settings.max_file_size_mb}MB",
                file_path=str(path)
            )

        # Try Docling first
        if self._docling_available:
            result = self._parse_with_docling(path)
            if result.success:
                return result
            logger.warning(f"Docling failed: {result.error_message}")

        # Fallback to pdfplumber
        if self.fallback_enabled:
            logger.info("Falling back to pdfplumber")
            return self._parse_with_pdfplumber(path)

        return ParseResult(
            markdown="",
            page_count=0,
            tables_found=0,
            parse_method="docling",
            success=False,
            error_message="Docling failed and fallback is disabled",
            file_path=str(path)
        )

    def _parse_with_docling(self, file_path: Path) -> ParseResult:
        """
        Parse PDF using Docling library.

        Args:
            file_path: Path to PDF file

        Returns:
            ParseResult with extracted content
        """
        try:
            from docling.document_converter import DocumentConverter

            # Initialize converter
            converter = DocumentConverter()

            # Convert document
            result = converter.convert(str(file_path))

            # Export to markdown
            markdown = result.document.export_to_markdown()

            # Count tables in output
            tables_found = self._count_tables(markdown)

            # Estimate page count from document
            page_count = getattr(result.document, 'num_pages', 1)

            return ParseResult(
                markdown=markdown,
                page_count=page_count,
                tables_found=tables_found,
                parse_method="docling",
                success=True,
                error_message=None,
                file_path=str(file_path)
            )

        except Exception as e:
            logger.error(f"Docling parsing error: {e}")
            return ParseResult(
                markdown="",
                page_count=0,
                tables_found=0,
                parse_method="docling",
                success=False,
                error_message=str(e),
                file_path=str(file_path)
            )

    def _parse_with_pdfplumber(self, file_path: Path) -> ParseResult:
        """
        Parse PDF using pdfplumber as fallback.

        Args:
            file_path: Path to PDF file

        Returns:
            ParseResult with extracted content
        """
        try:
            markdown_parts = []
            tables_found = 0
            page_count = 0

            with pdfplumber.open(file_path) as pdf:
                page_count = len(pdf.pages)

                for i, page in enumerate(pdf.pages):
                    # Add page header
                    markdown_parts.append(f"\n## Page {i + 1}\n")

                    # Extract tables first
                    tables = page.extract_tables()
                    if tables:
                        tables_found += len(tables)
                        for table in tables:
                            markdown_parts.append(self._table_to_markdown(table))
                            markdown_parts.append("\n")

                    # Extract text
                    text = page.extract_text()
                    if text:
                        # Clean up the text
                        cleaned_text = self._clean_text(text)
                        markdown_parts.append(cleaned_text)
                        markdown_parts.append("\n")

            markdown = "\n".join(markdown_parts)

            return ParseResult(
                markdown=markdown,
                page_count=page_count,
                tables_found=tables_found,
                parse_method="pdfplumber",
                success=True,
                error_message=None,
                file_path=str(file_path)
            )

        except Exception as e:
            logger.error(f"pdfplumber parsing error: {e}")
            return ParseResult(
                markdown="",
                page_count=0,
                tables_found=0,
                parse_method="pdfplumber",
                success=False,
                error_message=str(e),
                file_path=str(file_path)
            )

    def _table_to_markdown(self, table: list) -> str:
        """
        Convert a table (list of lists) to Markdown format.

        Args:
            table: 2D list representing table rows and cells

        Returns:
            Markdown formatted table string
        """
        if not table or not table[0]:
            return ""

        lines = []

        # Process header row
        header = table[0]
        header_cells = [str(cell) if cell else "" for cell in header]
        lines.append("| " + " | ".join(header_cells) + " |")

        # Add separator
        lines.append("| " + " | ".join(["---"] * len(header_cells)) + " |")

        # Process data rows
        for row in table[1:]:
            if row:
                cells = [str(cell) if cell else "" for cell in row]
                # Pad or truncate to match header length
                while len(cells) < len(header_cells):
                    cells.append("")
                cells = cells[:len(header_cells)]
                lines.append("| " + " | ".join(cells) + " |")

        return "\n".join(lines)

    def _clean_text(self, text: str) -> str:
        """
        Clean extracted text for better markdown formatting.

        Args:
            text: Raw extracted text

        Returns:
            Cleaned text
        """
        # Remove excessive whitespace
        text = re.sub(r'\n{3,}', '\n\n', text)

        # Remove trailing whitespace on lines
        text = '\n'.join(line.rstrip() for line in text.split('\n'))

        return text.strip()

    def _count_tables(self, markdown: str) -> int:
        """
        Count the number of tables in markdown content.

        Args:
            markdown: Markdown text

        Returns:
            Number of tables found
        """
        # Count markdown table patterns (lines starting with |)
        table_separator_pattern = r'\|[\s\-:]+\|'
        matches = re.findall(table_separator_pattern, markdown)
        return len(matches)


# Convenience function for direct usage
def parse_pdf(file_path: str, fallback_enabled: bool = True) -> ParseResult:
    """
    Parse a PDF file to Markdown.

    Args:
        file_path: Path to PDF file
        fallback_enabled: Whether to use pdfplumber fallback

    Returns:
        ParseResult with markdown and metadata
    """
    parser = ParserEngine(fallback_enabled=fallback_enabled)
    return parser.parse_to_markdown(file_path)
