"""PDF text extraction utilities."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

SUPPORTED_EXTENSIONS = {".pdf"}


class DocumentParseError(Exception):
    """Raised when a document cannot be parsed."""


class ParsedPage(BaseModel):
    """Text extracted from a single PDF page."""

    model_config = ConfigDict(extra="forbid")

    page_number: int = Field(..., ge=1, description="1-based page index.")
    text: str


class ParsedDocument(BaseModel):
    """Structured output from PDF text extraction."""

    model_config = ConfigDict(extra="forbid")

    filename: str
    filepath: str
    page_count: int = Field(..., ge=1)
    pages: list[ParsedPage] = Field(..., min_length=1)

    @property
    def full_text(self) -> str:
        return "\n\n".join(page.text for page in self.pages)


class PDFDocumentParser:
    """Extract text from PDF files while preserving page boundaries."""

    def parse(self, file_path: str | Path) -> ParsedDocument:
        path = Path(file_path)

        if not path.exists():
            raise DocumentParseError(f"File not found: {path}")

        if not path.is_file():
            raise DocumentParseError(f"Path is not a file: {path}")

        if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            raise DocumentParseError(
                f"Unsupported file type '{path.suffix}'. Supported extensions: {sorted(SUPPORTED_EXTENSIONS)}"
            )

        pages = self._extract_pages(path)
        if not pages:
            raise DocumentParseError(f"No text could be extracted from PDF: {path.name}")

        return ParsedDocument(
            filename=path.name,
            filepath=str(path.resolve()),
            page_count=len(pages),
            pages=pages,
        )

    def _extract_pages(self, path: Path) -> list[ParsedPage]:
        extractors = (self._extract_with_pymupdf, self._extract_with_pypdf)
        import_failures = 0
        last_error: Exception | None = None

        for extractor in extractors:
            try:
                return extractor(path)
            except ImportError:
                import_failures += 1
            except Exception as exc:
                last_error = exc

        if import_failures == len(extractors):
            raise DocumentParseError(
                "No PDF library available. Install pymupdf or pypdf."
            )

        raise DocumentParseError(
            f"Failed to extract text from PDF: {path.name}"
        ) from last_error

    def _extract_with_pymupdf(self, path: Path) -> list[ParsedPage]:
        import pymupdf

        pages: list[ParsedPage] = []
        with pymupdf.open(path) as document:
            for index in range(document.page_count):
                page = document.load_page(index)
                pages.append(
                    ParsedPage(
                        page_number=index + 1,
                        text=page.get_text("text").strip(),
                    )
                )
        return pages

    def _extract_with_pypdf(self, path: Path) -> list[ParsedPage]:
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        pages: list[ParsedPage] = []
        for index, page in enumerate(reader.pages, start=1):
            text = (page.extract_text() or "").strip()
            pages.append(ParsedPage(page_number=index, text=text))
        return pages


def parse_pdf(file_path: str | Path) -> ParsedDocument:
    """Convenience wrapper around PDFDocumentParser.parse."""
    return PDFDocumentParser().parse(file_path)
