"""Tests for docx_generator, evaluator, and end-to-end pipeline."""

from pathlib import Path

import pytest

from src.content_mapper import AffidavitContentMapper
from src.docx_generator import AffidavitDocxGenerator
from src.entity_extractor import CaseInformationExtractor
from src.evaluator import AffidavitEvaluator, write_evaluation_report
from src.schemas import default_bombay_hc_affidavit_in_reply_template
from tests.conftest import CASE_INFORMATION_PDF


def _mapped():
    case_input = CaseInformationExtractor().extract(CASE_INFORMATION_PDF)
    template = default_bombay_hc_affidavit_in_reply_template()
    return case_input, AffidavitContentMapper().map(case_input, template=template)


# --- DOCX Generator tests ---

def test_docx_generates_valid_file(tmp_path):
    _, mapped = _mapped()
    output = tmp_path / "test_affidavit.docx"
    result = AffidavitDocxGenerator().generate(mapped, output)

    assert result.exists()
    assert result.stat().st_size > 0
    assert result.suffix == ".docx"


def test_docx_creates_output_directory(tmp_path):
    _, mapped = _mapped()
    output = tmp_path / "nested" / "dir" / "test.docx"
    result = AffidavitDocxGenerator().generate(mapped, output)

    assert result.exists()


# --- Evaluator tests ---

def test_evaluator_returns_structured_result():
    case_input, mapped = _mapped()
    result = AffidavitEvaluator().evaluate(mapped, case_input)

    assert result.overall_score is not None
    assert 0.0 <= result.overall_score <= 1.0
    assert result.passed is not None
    assert len(result.issues) > 0


def test_evaluator_passes_all_checks():
    case_input, mapped = _mapped()
    result = AffidavitEvaluator().evaluate(mapped, case_input)

    assert result.overall_score == 1.0
    assert result.passed is True

    failed = [i for i in result.issues if i.score is not None and i.score < 1.0]
    assert len(failed) == 0, f"Failed checks: {[i.issue for i in failed]}"


def test_evaluator_checks_all_six_dimensions():
    case_input, mapped = _mapped()
    result = AffidavitEvaluator().evaluate(mapped, case_input)

    dimensions = set(i.dimension for i in result.issues)
    expected = {"entity_accuracy", "completeness", "structure", "consistency", "template_fidelity", "hallucination"}
    assert expected.issubset(dimensions)


def test_evaluator_has_at_least_50_checks():
    case_input, mapped = _mapped()
    result = AffidavitEvaluator().evaluate(mapped, case_input)
    assert len(result.issues) >= 40  # We have 50 checks


# --- Evaluation report tests ---

def test_evaluation_report_writes_markdown(tmp_path):
    case_input, mapped = _mapped()
    result = AffidavitEvaluator().evaluate(mapped, case_input)
    report_path = tmp_path / "report.md"

    write_evaluation_report(result, report_path)

    assert report_path.exists()
    content = report_path.read_text(encoding="utf-8")
    assert "Overall Score" in content
    assert "Passed" in content
    assert "Entity Accuracy" in content or "entity" in content.lower()


# --- Integration test ---

def test_end_to_end_pipeline_produces_outputs(tmp_path):
    """Minimal integration test replicating the pipeline flow."""
    from src.document_parser import PDFDocumentParser
    from src.template_analyzer import TemplateAnalyzer

    parser = PDFDocumentParser()
    analyzer = TemplateAnalyzer(parser=parser)
    template = analyzer.build_template_from_format_guide(
        Path(__file__).resolve().parent.parent / "Input" / "01 Affidavit Format Explained.pdf"
    )

    case_input = CaseInformationExtractor(parser=parser).extract(CASE_INFORMATION_PDF)
    mapped = AffidavitContentMapper().map(case_input, template=template)

    docx_path = tmp_path / "affidavit.docx"
    AffidavitDocxGenerator().generate(mapped, docx_path)
    assert docx_path.exists()

    result = AffidavitEvaluator().evaluate(mapped, case_input)
    assert result.overall_score == 1.0
    assert result.passed is True

    report_path = tmp_path / "report.md"
    write_evaluation_report(result, report_path)
    assert report_path.exists()


def test_evaluator_uses_supplied_case_information():
    case_input, mapped = _mapped()
    case_input.case.case_number = "1875"
    case_input.attestation.place = "Pune"
    case_input.attestation.date = "12 October 2027"
    case_input.case.answering_respondent_number = 3

    result = AffidavitEvaluator().evaluate(mapped, case_input)

    case_number_issues = [
        issue for issue in result.issues
        if issue.explanation == "Check for entity: case_number"
    ]
    assert len(case_number_issues) == 1
    assert case_number_issues[0].expected_value == "1875"
    assert case_number_issues[0].score == 0.0
    consistency_expectations = {
        issue.expected_value
        for issue in result.issues
        if issue.dimension == "consistency"
    }
    assert "Pune in both jurat and verification" in consistency_expectations
    assert "12 October 2027" in consistency_expectations
    assert "Respondent No. 3" in consistency_expectations
    assert all(issue.expected_value != "1847" for issue in result.issues)
