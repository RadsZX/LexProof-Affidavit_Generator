import pytest

from src.document_parser import DocumentParseError, parse_pdf
from tests.conftest import CASE_INFORMATION_PDF, FORMAT_GUIDE_PDF, REFERENCE_AFFIDAVIT_PDF


@pytest.mark.parametrize(
    "pdf_path",
    [FORMAT_GUIDE_PDF, REFERENCE_AFFIDAVIT_PDF, CASE_INFORMATION_PDF],
    ids=["format_guide", "reference_affidavit", "case_information"],
)
def test_pdf_text_extraction_succeeds(pdf_path):
    document = parse_pdf(pdf_path)

    assert document.filename == pdf_path.name
    assert document.page_count >= 1
    assert len(document.pages) == document.page_count
    assert document.full_text.strip()
    assert all(page.text is not None for page in document.pages)


def test_parser_raises_clear_error_for_missing_file(tmp_path):
    missing = tmp_path / "does_not_exist.pdf"

    with pytest.raises(DocumentParseError, match="File not found"):
        parse_pdf(missing)


def test_parser_raises_clear_error_for_unsupported_extension(tmp_path):
    text_file = tmp_path / "notes.txt"
    text_file.write_text("not a pdf", encoding="utf-8")

    with pytest.raises(DocumentParseError, match="Unsupported file type"):
        parse_pdf(text_file)
