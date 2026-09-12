"""Tests for PreGenerationValidator and single-upload document validation."""

from pathlib import Path
import pytest
import copy

from src.document_validator import (
    DocumentRoleValidator,
    PreGenerationValidator,
    resolve_reference_paths,
)
from src.entity_extractor import CaseInformationExtractor
from src.template_analyzer import TemplateAnalyzer
from src.content_mapper import AffidavitContentMapper
from tests.conftest import FORMAT_GUIDE_PDF, REFERENCE_AFFIDAVIT_PDF, CASE_INFORMATION_PDF


@pytest.fixture
def valid_case_and_mapped(parser):
    analyzer = TemplateAnalyzer(parser=parser)
    template = analyzer.build_template_from_format_guide(FORMAT_GUIDE_PDF)
    case_input = CaseInformationExtractor(parser=parser).extract(CASE_INFORMATION_PDF)
    mapped = AffidavitContentMapper().map(case_input, template=template)
    return case_input, mapped


def test_resolve_reference_paths():
    guide_path, sample_path = resolve_reference_paths()
    assert guide_path.exists(), f"Guide path not found: {guide_path}"
    assert sample_path.exists(), f"Sample path not found: {sample_path}"


def test_document_role_validator_with_case_info_only(parser):
    validator = DocumentRoleValidator(parser=parser)
    suite = validator.validate_all(case_info_path=CASE_INFORMATION_PDF)

    assert suite.all_valid is True
    assert suite.format_guide.valid is True
    assert suite.sample_affidavit.valid is True
    assert suite.case_information.valid is True


def test_document_role_validator_handles_missing_files(parser, tmp_path):
    missing_file = tmp_path / "non_existent.pdf"
    validator = DocumentRoleValidator(
        parser=parser,
        format_guide_path=missing_file,
    )
    suite = validator.validate_all(case_info_path=CASE_INFORMATION_PDF)

    assert suite.all_valid is False
    assert suite.format_guide.valid is False
    assert "missing" in suite.format_guide.message.lower()


def test_pre_generation_validator_passes_valid_data(valid_case_and_mapped):
    case_input, mapped = valid_case_and_mapped
    validator = PreGenerationValidator()
    result = validator.validate(case_input, mapped)

    assert result.valid is True
    assert len(result.errors) == 0
    assert len(result.checks) == 5
    for check in result.checks:
        assert check.passed is True, f"Check {check.name} failed: {check.details}"


def test_pre_generation_validator_fails_missing_required_entity(valid_case_and_mapped):
    case_input, mapped = valid_case_and_mapped
    case_input_bad = copy.deepcopy(case_input)
    case_input_bad.deponent.name = ""

    validator = PreGenerationValidator()
    result = validator.validate(case_input_bad, mapped)

    assert result.valid is False
    chk = next(c for c in result.checks if c.check_id == "required_entities")
    assert chk.passed is False
    assert any("deponent name" in d.lower() for d in chk.details)


def test_pre_generation_validator_fails_respondent_mismatch(valid_case_and_mapped):
    case_input, mapped = valid_case_and_mapped
    case_input_bad = copy.deepcopy(case_input)
    # Change answering respondent number to 99
    case_input_bad.case.answering_respondent_number = 99

    validator = PreGenerationValidator()
    result = validator.validate(case_input_bad, mapped)

    assert result.valid is False
    chk = next(c for c in result.checks if c.check_id == "respondent_consistency")
    assert chk.passed is False


def test_pre_generation_validator_fails_missing_section(valid_case_and_mapped):
    case_input, mapped = valid_case_and_mapped
    mapped_bad = copy.deepcopy(mapped)
    mapped_bad.forum_heading = ""

    validator = PreGenerationValidator()
    result = validator.validate(case_input, mapped_bad)

    assert result.valid is False
    chk = next(c for c in result.checks if c.check_id == "required_sections")
    assert chk.passed is False
    assert any("forum heading" in d.lower() for d in chk.details)


def test_pre_generation_validator_fails_inconsistent_exhibit(valid_case_and_mapped):
    case_input, mapped = valid_case_and_mapped
    mapped_bad = copy.deepcopy(mapped)
    # Paragraph 5 has an exhibit in the valid mapped content; clear its document description
    for p in mapped_bad.body_paragraphs:
        if p.exhibit:
            p.exhibit.document_description = ""

    validator = PreGenerationValidator()
    result = validator.validate(case_input, mapped_bad)

    assert result.valid is False
    chk = next(c for c in result.checks if c.check_id == "exhibit_consistency")
    assert chk.passed is False


def test_pre_generation_validator_fails_verification_range_mismatch(valid_case_and_mapped):
    case_input, mapped = valid_case_and_mapped
    mapped_bad = copy.deepcopy(mapped)
    # Set verification end paragraph to something other than body count
    mapped_bad.verification.paragraph_end = 99

    validator = PreGenerationValidator()
    result = validator.validate(case_input, mapped_bad)

    assert result.valid is False
    chk = next(c for c in result.checks if c.check_id == "verification_range")
    assert chk.passed is False
    assert any("mismatch" in d.lower() or "expected" in d.lower() for d in chk.details)
