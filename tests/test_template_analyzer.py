from src.schemas import AffidavitSection, OptionalTemplateElement, ReplyMoveType
from src.template_analyzer import MAJOR_REPLY_MOVE_SEQUENCE
from tests.conftest import FORMAT_GUIDE_PDF, REFERENCE_AFFIDAVIT_PDF


def test_template_contains_exactly_ten_required_sections(analyzer):
    template = analyzer.build_template_from_format_guide(FORMAT_GUIDE_PDF)

    assert len(template.sections) == 10
    assert [section.order for section in template.sections] == list(range(1, 11))
    assert [section.section for section in template.sections] == list(AffidavitSection)


def test_reference_affidavit_contains_major_structural_elements(analyzer):
    result = analyzer.analyze_reference_affidavit(REFERENCE_AFFIDAVIT_PDF)

    assert result.all_required_sections_present
    assert result.major_reply_moves_present
    assert result.body_paragraph_count == 5
    assert OptionalTemplateElement.EXHIBIT_REFERENCE in result.optional_elements_found
    assert OptionalTemplateElement.ADVOCATE_BLOCK in result.optional_elements_found


def test_reference_affidavit_reply_move_order(analyzer):
    result = analyzer.analyze_reference_affidavit(REFERENCE_AFFIDAVIT_PDF)
    detected = result.reply_moves_detected

    indices = [detected.index(move) for move in MAJOR_REPLY_MOVE_SEQUENCE]
    assert indices == sorted(indices)
