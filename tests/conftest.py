from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
INPUT_DIR = PROJECT_ROOT / "Input"

FORMAT_GUIDE_PDF = INPUT_DIR / "01 Affidavit Format Explained.pdf"
REFERENCE_AFFIDAVIT_PDF = INPUT_DIR / "02 Affidavit in Reply Sample.docx.pdf"
CASE_INFORMATION_PDF = INPUT_DIR / "03_Case_Information.pdf"


@pytest.fixture
def parser():
    from src.document_parser import PDFDocumentParser

    return PDFDocumentParser()


@pytest.fixture
def analyzer(parser):
    from src.template_analyzer import TemplateAnalyzer

    return TemplateAnalyzer(parser=parser)


@pytest.fixture
def extractor(parser):
    from src.entity_extractor import CaseInformationExtractor

    return CaseInformationExtractor(parser=parser)
