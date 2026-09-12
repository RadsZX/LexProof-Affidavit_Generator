from src.content_mapper import AffidavitContentMapper
from src.entity_extractor import CaseInformationExtractor
from src.schemas import DeponentCapacity, ReplyMoveType, default_bombay_hc_affidavit_in_reply_template
from tests.conftest import CASE_INFORMATION_PDF

SAMPLE_DOC_02_LEAKS = [
    "Arjun Mehta",
    "Rohan Deshpande",
    "3147",
    "MEHTA & KULKARNI",
    "CIVIL APPELLATE",
    "12th March 2026",
    "12 March 2026",
]

EXPECTED_MOVES = [
    ReplyMoveType.IDENTITY_AND_PERUSAL,
    ReplyMoveType.BLANKET_DENIAL,
    ReplyMoveType.PRELIMINARY_POSITION,
    ReplyMoveType.SUBSTANTIVE_ANSWER,
    ReplyMoveType.SUBSTANTIVE_ANSWER,
    ReplyMoveType.DOCUMENT_RELIED_UPON,
    ReplyMoveType.CLOSING,
]


def _mapped_content():
    case_input = CaseInformationExtractor().extract(CASE_INFORMATION_PDF)
    template = default_bombay_hc_affidavit_in_reply_template()
    return AffidavitContentMapper().map(case_input, template=template)


def test_body_has_exactly_seven_numbered_paragraphs():
    mapped = _mapped_content()
    numbers = [paragraph.number for paragraph in mapped.body_paragraphs]
    moves = [paragraph.move for paragraph in mapped.body_paragraphs]

    assert mapped.body_paragraph_count == 7
    assert numbers == list(range(1, 8))
    assert moves == EXPECTED_MOVES
    assert all(clause.label.startswith("(") for clause in mapped.prayer.clauses)
    assert "PRAYER" not in " ".join(paragraph.text for paragraph in mapped.body_paragraphs)


def test_paragraph_six_has_exhibit_a_only():
    mapped = _mapped_content()
    paragraph_six = mapped.body_paragraphs[5]
    others = mapped.body_paragraphs[:5] + mapped.body_paragraphs[6:]

    assert paragraph_six.move is ReplyMoveType.DOCUMENT_RELIED_UPON
    assert paragraph_six.exhibit is not None
    assert paragraph_six.exhibit.label == "EXHIBIT-'A'"
    assert "15 July 2026" in paragraph_six.text
    assert all(paragraph.exhibit is None for paragraph in others)


def test_organisation_officer_deponent_and_respondent_represented():
    mapped = _mapped_content()
    clause = mapped.deponent_clause

    assert clause.capacity is DeponentCapacity.ORGANISATION_OFFICER
    assert clause.name == "Arvind Rajan"
    assert clause.designation == "Deputy Metropolitan Commissioner"
    assert clause.organisation == "Mumbai Metropolitan Region Development Authority"
    assert clause.answering_respondent_number == 2
    assert "Respondent No. 2" in clause.capacity_phrase
    assert "the Deputy Metropolitan Commissioner of the Respondent No. 2" in clause.text
    assert "I am the Respondent No. 2" not in clause.text
    assert "I, Arvind Rajan" in clause.text and "the Respondent No. 2 above named" in clause.text
    assert mapped.affidavit_title == "AFFIDAVIT IN REPLY ON BEHALF OF RESPONDENT NO. 2"
    assert mapped.advocate is not None
    assert "Respondent No. 2" in mapped.advocate.acting_for
    assert "I am the Respondent No. 2" not in mapped.body_paragraphs[0].text


def test_verification_range_jurat_and_attestation():
    mapped = _mapped_content()

    assert mapped.verification.paragraph_start == 1
    assert mapped.verification.paragraph_end == 7
    assert mapped.verification.includes_prayer is True
    assert "paragraphs 1 to 7" in mapped.verification.text
    assert "Prayer" in mapped.verification.text
    assert "true and correct to my knowledge and belief" in mapped.verification.text

    assert mapped.jurat.verb_past == "Solemnly affirmed"
    assert mapped.jurat.text.startswith("Solemnly affirmed")
    assert mapped.jurat.place == "Mumbai"
    assert mapped.verification.place == "Mumbai"
    assert mapped.jurat.date == "5 September 2026"
    assert mapped.verification.date == "5 September 2026"
    assert "5th day of September 2026" in mapped.jurat.text
    assert "5th day of September 2026" in mapped.verification.text


def test_source_evidence_and_no_sample_party_data():
    mapped = _mapped_content()
    body = mapped.body_paragraphs

    assert body[0].source_point_number == 1
    assert body[1].source_point_number == 2
    assert body[2].source_point_number == 3
    assert body[3].source_point_number == 4
    assert body[4].source_point_number == 5
    assert body[5].source_point_number == 6
    assert body[6].source_point_number is None
    assert "perused" in body[0].text.lower()
    assert "writ petition" in body[0].text.lower()
    assert "misconceived" in body[2].text.lower()
    assert "redevelopment procedure" in body[2].text.lower()
    assert "without authority" in body[3].text.lower()
    assert "relevant records" in body[4].text.lower()
    assert "dismissed with costs" in body[6].text.lower()

    rendered = mapped.all_text()
    for leak in SAMPLE_DOC_02_LEAKS:
        assert leak.lower() not in rendered.lower()
