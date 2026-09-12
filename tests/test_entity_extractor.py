import re

from src.schemas import DeponentCapacity, ReplyMoveType, VerificationVerb
from src.entity_extractor import CaseInformationExtractor
from tests.conftest import CASE_INFORMATION_PDF

EXPECTED_MOVES = [
    ReplyMoveType.IDENTITY_AND_PERUSAL,
    ReplyMoveType.BLANKET_DENIAL,
    ReplyMoveType.PRELIMINARY_POSITION,
    ReplyMoveType.SUBSTANTIVE_ANSWER,
    ReplyMoveType.SUBSTANTIVE_ANSWER,
    ReplyMoveType.DOCUMENT_RELIED_UPON,
]


def _compact(value: str) -> str:
    return re.sub(r"\s+", "", value)


def test_extracts_validated_case_information():
    result = CaseInformationExtractor().extract_with_evidence(CASE_INFORMATION_PDF)
    case_input = result.case_input
    case = case_input.case
    deponent = case_input.deponent
    attestation = case_input.attestation
    advocate = case_input.advocate

    assert case.court == "IN THE HIGH COURT OF JUDICATURE AT BOMBAY"
    assert case.jurisdiction_type == "ORDINARY ORIGINAL CIVIL JURISDICTION"
    assert case.proceeding_type == "WRIT PETITION"
    assert case.case_number == "1847"
    assert case.year == 2026
    assert case.petitioner.name == "Sunrise Housing Private Limited"
    assert case.respondents[0].name == "State of Maharashtra"
    assert case.respondents[0].respondent_number == 1
    assert case.respondents[1].name == "Mumbai Metropolitan Region Development Authority"
    assert case.respondents[1].respondent_number == 2
    assert case.answering_respondent_number == 2

    assert deponent.name == "Arvind Rajan"
    assert deponent.designation == "Deputy Metropolitan Commissioner"
    assert deponent.organisation == "Mumbai Metropolitan Region Development Authority"
    assert deponent.verification_verb is VerificationVerb.SOLEMNLY_AFFIRM

    points = case_input.reply_points.points
    assert len(points) == 6
    assert [point.move for point in points] == EXPECTED_MOVES
    assert all(point.source_facts for point in points)

    exhibit_points = [point for point in points if point.exhibit is not None]
    assert len(exhibit_points) == 1
    assert exhibit_points[0].point_number == 6
    assert exhibit_points[0].exhibit.label == "EXHIBIT-'A'"
    assert any("EXHIBIT-'A'" in fact for fact in exhibit_points[0].source_facts)

    assert attestation.place == "Mumbai"
    assert attestation.date == "5 September 2026"
    assert attestation.verification_verb is VerificationVerb.SOLEMNLY_AFFIRM

    assert advocate.firm == "Rajan & Associates"
    assert _compact(advocate.acting_for) == _compact("Respondent No.2")


def test_deponent_is_organisation_officer():
    case_input = CaseInformationExtractor().extract(CASE_INFORMATION_PDF)
    deponent = case_input.deponent

    assert deponent.capacity is DeponentCapacity.ORGANISATION_OFFICER
    assert deponent.capacity is not DeponentCapacity.RESPONDENT_PERSONAL
    assert deponent.name != case_input.case.respondents[1].name
    assert deponent.designation
    assert deponent.organisation


def test_extracted_model_validates_as_affidavit_case_input():
    case_input = CaseInformationExtractor().extract(CASE_INFORMATION_PDF)
    dumped = case_input.model_dump()
    from src.schemas import AffidavitCaseInput

    AffidavitCaseInput.model_validate(dumped)
