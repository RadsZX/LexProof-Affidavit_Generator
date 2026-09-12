"""Pydantic schemas for Affidavit in Reply structured data.

These models represent case inputs, template rules, and evaluation outputs.
They are reusable across cases and do not embed assignment-specific values.
"""

from __future__ import annotations

from datetime import date as Date
from enum import Enum
from typing import Optional, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


# ---------------------------------------------------------------------------
# Shared enumerations
# ---------------------------------------------------------------------------


class VerificationVerb(str, Enum):
    """Deponent and jurat verb; Part 6 and Part 9 must agree."""

    SOLEMNLY_AFFIRM = "solemnly affirm"
    SWEAR_AND_AFFIRM = "swear and affirm"

    @property
    def jurat_past_tense(self) -> str:
        if self is VerificationVerb.SOLEMNLY_AFFIRM:
            return "Solemnly affirmed"
        return "Sworn"


class DeponentCapacity(str, Enum):
    """Whether the deponent is the respondent personally or an organisation officer."""

    RESPONDENT_PERSONAL = "respondent_personal"
    ORGANISATION_OFFICER = "organisation_officer"


class ReplyMoveType(str, Enum):
    """Rhetorical move for a numbered reply paragraph."""

    IDENTITY_AND_PERUSAL = "identity_and_perusal"
    BLANKET_DENIAL = "blanket_denial"
    PRELIMINARY_POSITION = "preliminary_position"
    SUBSTANTIVE_ANSWER = "substantive_answer"
    DOCUMENT_RELIED_UPON = "document_relied_upon"
    CLOSING = "closing"
    PRAYER_TO_DISMISS = "prayer_to_dismiss"


class AffidavitSection(str, Enum):
    """Required sections of an Affidavit in Reply, in canonical order."""

    FORUM_HEADING = "forum_heading"
    JURISDICTION = "jurisdiction"
    CASE_NUMBER = "case_number"
    CAUSE_TITLE = "cause_title"
    AFFIDAVIT_TITLE = "affidavit_title"
    DEPONENT_CLAUSE = "deponent_clause"
    NUMBERED_PARAGRAPHS = "numbered_paragraphs"
    PRAYER = "prayer"
    JURAT = "jurat"
    VERIFICATION = "verification"


class OptionalTemplateElement(str, Enum):
    """Elements shown in the reference sample but not prescribed by the format guide."""

    EXHIBIT_REFERENCE = "exhibit_reference"
    ADVOCATE_BLOCK = "advocate_block"


class EvaluationSeverity(str, Enum):
    """Severity of an evaluation finding."""

    CRITICAL = "critical"
    MAJOR = "major"
    MINOR = "minor"
    INFO = "info"


# ---------------------------------------------------------------------------
# 1. Case details
# ---------------------------------------------------------------------------


class PartyDescription(BaseModel):
    """Cause-title party block (name plus optional descriptive lines)."""

    model_config = ConfigDict(extra="forbid")

    name: str
    description_lines: list[str] = Field(
        default_factory=list,
        description="Additional lines such as age, occupation, or address.",
    )


class Respondent(PartyDescription):
    """A numbered respondent in the cause title."""

    respondent_number: int = Field(..., ge=1)


class CaseDetails(BaseModel):
    """Court and proceeding metadata for an Affidavit in Reply."""

    model_config = ConfigDict(extra="forbid")

    document_type: str = Field(
        default="Affidavit in Reply",
        description="Type of sworn document being filed.",
    )
    court: str = Field(
        ...,
        description="Forum heading, e.g. 'IN THE HIGH COURT OF JUDICATURE AT BOMBAY'.",
    )
    jurisdiction_type: str = Field(
        ...,
        description="Jurisdiction line ending with 'JURISDICTION', e.g. 'ORDINARY ORIGINAL CIVIL JURISDICTION'.",
    )
    proceeding_type: str = Field(
        ...,
        description="Proceeding label used in the case number and body, e.g. 'WRIT PETITION'.",
    )
    case_number: str
    year: int = Field(..., ge=1)
    petitioner: PartyDescription
    respondents: list[Respondent] = Field(..., min_length=1)
    answering_respondent_number: int = Field(
        ...,
        ge=1,
        description="Respondent number on whose behalf the affidavit is filed.",
    )

    @field_validator("respondents")
    @classmethod
    def respondents_must_be_numbered_in_order(cls, respondents: list[Respondent]) -> list[Respondent]:
        expected = list(range(1, len(respondents) + 1))
        actual = [r.respondent_number for r in respondents]
        if actual != expected:
            msg = "Respondents must be numbered contiguously starting at 1."
            raise ValueError(msg)
        return respondents


# ---------------------------------------------------------------------------
# 2. Deponent details
# ---------------------------------------------------------------------------


class DeponentDetails(BaseModel):
    """Person swearing or affirming the affidavit."""

    model_config = ConfigDict(extra="forbid")

    name: str
    capacity: DeponentCapacity
    designation: Optional[str] = Field(
        default=None,
        description="Required when capacity is organisation_officer.",
    )
    organisation: Optional[str] = Field(
        default=None,
        description="Organisation represented when capacity is organisation_officer.",
    )
    address: str
    age: Optional[int] = Field(default=None, ge=1)
    occupation: Optional[str] = None
    verification_verb: VerificationVerb = VerificationVerb.SOLEMNLY_AFFIRM

    @model_validator(mode="after")
    def designation_required_for_officer(self) -> Self:
        if self.capacity is DeponentCapacity.ORGANISATION_OFFICER and not self.designation:
            raise ValueError("designation is required when deponent is an organisation officer.")
        return self


# ---------------------------------------------------------------------------
# 3. Reply points
# ---------------------------------------------------------------------------


class ExhibitReference(BaseModel):
    """Optional exhibit details for a document-relied-upon paragraph."""

    model_config = ConfigDict(extra="forbid")

    label: str = Field(..., description="Exhibit mark, e.g. \"EXHIBIT-'A'\".")
    document_description: str
    document_date: Optional[str] = None


class ReplyPoint(BaseModel):
    """One numbered reply paragraph, preserving supplied order and content."""

    model_config = ConfigDict(extra="forbid")

    point_number: int = Field(..., ge=1)
    move: ReplyMoveType
    source_facts: list[str] = Field(
        ...,
        min_length=1,
        description="Ordered bullet facts or content to incorporate into the paragraph.",
    )
    exhibit: Optional[ExhibitReference] = None


class ReplyPoints(BaseModel):
    """Ordered collection of reply points for the affidavit body."""

    model_config = ConfigDict(extra="forbid")

    points: list[ReplyPoint] = Field(..., min_length=1)

    @field_validator("points")
    @classmethod
    def points_must_be_numbered_in_order(cls, points: list[ReplyPoint]) -> list[ReplyPoint]:
        expected = list(range(1, len(points) + 1))
        actual = [point.point_number for point in points]
        if actual != expected:
            msg = "Reply points must be numbered contiguously starting at 1."
            raise ValueError(msg)
        return points


# ---------------------------------------------------------------------------
# 4. Attestation
# ---------------------------------------------------------------------------


class AttestationDetails(BaseModel):
    """Place, date, and verification verb for jurat and verification blocks."""

    model_config = ConfigDict(extra="forbid")

    place: str
    date: Date | str = Field(
        ...,
        description="Attestation date as ISO date or prose, e.g. '5 September 2026'.",
    )
    verification_verb: VerificationVerb = VerificationVerb.SOLEMNLY_AFFIRM


# ---------------------------------------------------------------------------
# 5. Advocate details
# ---------------------------------------------------------------------------


class AdvocateDetails(BaseModel):
    """Optional advocate drafting block shown in the reference sample."""

    model_config = ConfigDict(extra="forbid")

    firm: str
    acting_for: str = Field(
        ...,
        description="Party represented, e.g. 'Respondent No. 2'.",
    )


# ---------------------------------------------------------------------------
# 6. Template schema
# ---------------------------------------------------------------------------


class SectionSpec(BaseModel):
    """One required affidavit section and its formatting convention."""

    model_config = ConfigDict(extra="forbid")

    section: AffidavitSection
    title: str
    order: int = Field(..., ge=1)
    required: bool = True
    formatting_notes: str = ""


class ParagraphNumberingRule(BaseModel):
    """Rules for the continuous numbered body paragraphs (Part 7)."""

    model_config = ConfigDict(extra="forbid")

    use_decimal_numbers: bool = True
    number_bold: bool = True
    suffix: str = "."
    continuous_sequence: bool = True
    prayer_excluded_from_sequence: bool = True
    closing_is_final_numbered_paragraph: bool = True


class PrayerLetteringRule(BaseModel):
    """Rules for the lettered prayer block (Part 8)."""

    model_config = ConfigDict(extra="forbid")

    heading: str = "PRAYER"
    heading_bold_caps_centred: bool = True
    letters: list[str] = Field(default_factory=lambda: ["a", "b", "c"])
    letters_bold: bool = True
    letter_suffix: str = ")"
    standard_clauses: list[str] = Field(
        default_factory=list,
        description="Canonical prayer sub-clauses in letter order.",
    )


class VerificationRangeRule(BaseModel):
    """Rules for the verification paragraph-range statement (Part 10)."""

    model_config = ConfigDict(extra="forbid")

    includes_prayer: bool = True
    range_must_match_body_paragraph_count: bool = True
    verification_verb_must_match_deponent_clause: bool = True
    place_and_date_repeat_jurat: bool = True


class FixedPhraseRule(BaseModel):
    """Fixed phrase or wording that must be preserved in generation."""

    model_config = ConfigDict(extra="forbid")

    context: str = Field(
        ...,
        description="Section or move where the phrase applies, e.g. 'blanket_denial'.",
    )
    phrase: str
    required: bool = True


class FormattingConvention(BaseModel):
    """Document-wide formatting rules from the format guide."""

    model_config = ConfigDict(extra="forbid")

    bold_caps_centred_sections: list[AffidavitSection] = Field(default_factory=list)
    cause_title_petitioner_left: bool = True
    cause_title_status_tags_right: bool = True
    versus_centred_on_own_line: bool = True
    paragraph_text_justified: bool = True
    deponent_caps_right_aligned: bool = True
    before_me_left_aligned: bool = True
    date_format_note: str = "ordinal day + month + year, e.g. 5th day of September 2026"


class EvidenceReference(BaseModel):
    """Provenance citation linking generated or extracted information to its source document."""

    model_config = ConfigDict(extra="forbid")

    source_document: str = Field(..., description="Source filename or document identifier.")
    source_section: Optional[str] = Field(default=None, description="Section heading in source document.")
    source_page: Optional[int] = Field(default=None, description="1-based page index in source document.")
    source_text: str = Field(..., description="Concise excerpt/snippet of source text.")
    field_name: Optional[str] = Field(default=None, description="Generated or extracted field name.")


class AffidavitTemplateSchema(BaseModel):
    """Reference-template rules for Affidavit in Reply structure and phrasing."""

    model_config = ConfigDict(extra="forbid")

    document_family: str = "affidavit_in_reply"
    document_type: str = "Affidavit in Reply"
    sections: list[SectionSpec] = Field(..., min_length=1)
    paragraph_numbering: ParagraphNumberingRule = Field(default_factory=ParagraphNumberingRule)
    prayer_lettering: PrayerLetteringRule = Field(default_factory=PrayerLetteringRule)
    verification_range: VerificationRangeRule = Field(default_factory=VerificationRangeRule)
    fixed_phrases: list[FixedPhraseRule] = Field(default_factory=list)
    formatting: FormattingConvention = Field(default_factory=FormattingConvention)
    optional_elements: list[OptionalTemplateElement] = Field(default_factory=list)
    reply_move_sequence: list[ReplyMoveType] = Field(
        default_factory=list,
        description="Typical rhetorical order for body paragraphs.",
    )

    @field_validator("sections")
    @classmethod
    def sections_must_be_ordered(cls, sections: list[SectionSpec]) -> list[SectionSpec]:
        orders = [section.order for section in sections]
        if orders != sorted(orders):
            raise ValueError("Section specs must be listed in ascending order.")
        return sections


# ---------------------------------------------------------------------------
# 7. Evaluation result
# ---------------------------------------------------------------------------


class EvaluationIssue(BaseModel):
    """One scored finding from document evaluation."""

    model_config = ConfigDict(extra="forbid")

    dimension: str = Field(
        ...,
        description="Evaluation axis, e.g. 'structure', 'fixed_phrases', 'verification_range'.",
    )
    score: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    issue: Optional[str] = None
    severity: EvaluationSeverity = EvaluationSeverity.INFO
    expected_value: Optional[str] = None
    actual_value: Optional[str] = None
    source: Optional[str] = Field(
        default=None,
        description="Evidence or citation supporting the finding.",
    )
    explanation: Optional[str] = None


class EvaluationResult(BaseModel):
    """Aggregate evaluation output for a generated or reviewed affidavit."""

    model_config = ConfigDict(extra="forbid")

    issues: list[EvaluationIssue] = Field(default_factory=list)
    overall_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    passed: Optional[bool] = None
    evidence: dict[str, EvidenceReference] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Composite input bundle
# ---------------------------------------------------------------------------


class AffidavitCaseInput(BaseModel):
    """Structured case input for affidavit generation (no hard-coded assignment data)."""

    model_config = ConfigDict(extra="forbid")

    case: CaseDetails
    deponent: DeponentDetails
    reply_points: ReplyPoints
    attestation: AttestationDetails
    advocate: Optional[AdvocateDetails] = None
    template: Optional[AffidavitTemplateSchema] = None
    evidence: dict[str, EvidenceReference] = Field(default_factory=dict)


def default_bombay_hc_affidavit_in_reply_template() -> AffidavitTemplateSchema:
    """Return template rules derived from the format guide (not case-specific)."""

    sections = [
        SectionSpec(
            section=AffidavitSection.FORUM_HEADING,
            title="Forum heading",
            order=1,
            formatting_notes="Bold, ALL CAPS, centred.",
        ),
        SectionSpec(
            section=AffidavitSection.JURISDICTION,
            title="Jurisdiction",
            order=2,
            formatting_notes="Bold, ALL CAPS, centred; ends with JURISDICTION.",
        ),
        SectionSpec(
            section=AffidavitSection.CASE_NUMBER,
            title="Case number",
            order=3,
            formatting_notes="Bold, ALL CAPS, centred; uses NO. and OF.",
        ),
        SectionSpec(
            section=AffidavitSection.CAUSE_TITLE,
            title="Cause title",
            order=4,
            formatting_notes="Party names left; status tags right; VERSUS centred.",
        ),
        SectionSpec(
            section=AffidavitSection.AFFIDAVIT_TITLE,
            title="Affidavit title",
            order=5,
            formatting_notes="Bold, ALL CAPS, centred; includes respondent number.",
        ),
        SectionSpec(
            section=AffidavitSection.DEPONENT_CLAUSE,
            title="Deponent clause",
            order=6,
            formatting_notes="Single unnumbered sentence; verb must match jurat.",
        ),
        SectionSpec(
            section=AffidavitSection.NUMBERED_PARAGRAPHS,
            title="Numbered paragraphs",
            order=7,
            formatting_notes="Bold decimal numbers; one continuous sequence.",
        ),
        SectionSpec(
            section=AffidavitSection.PRAYER,
            title="Prayer",
            order=8,
            formatting_notes="Bold caps heading; bold lettered sub-clauses.",
        ),
        SectionSpec(
            section=AffidavitSection.JURAT,
            title="Jurat",
            order=9,
            formatting_notes="DEPONENT right, caps; Before Me left.",
        ),
        SectionSpec(
            section=AffidavitSection.VERIFICATION,
            title="Verification",
            order=10,
            formatting_notes="Range must match body paragraph count; includes Prayer.",
        ),
    ]

    fixed_phrases = [
        FixedPhraseRule(
            context="deponent_clause",
            phrase="the Respondent No.[N] above named",
        ),
        FixedPhraseRule(
            context="deponent_clause_officer",
            phrase="the [DESIGNATION] of the Respondent No.[N] above named",
        ),
        FixedPhraseRule(
            context="deponent_clause",
            phrase="do hereby solemnly affirm and state as under:",
        ),
        FixedPhraseRule(
            context="identity_and_perusal",
            phrase="am well acquainted with the facts and circumstances of the case",
        ),
        FixedPhraseRule(
            context="identity_and_perusal",
            phrase="I have perused the Petition and the documents annexed thereto",
        ),
        FixedPhraseRule(
            context="identity_and_perusal",
            phrase="am competent to affirm this Affidavit in Reply",
        ),
        FixedPhraseRule(
            context="blanket_denial",
            phrase="At the outset, I deny each and every allegation, contention and submission",
        ),
        FixedPhraseRule(
            context="blanket_denial",
            phrase="save and except those specifically admitted herein",
        ),
        FixedPhraseRule(
            context="blanket_denial",
            phrase="misconceived, devoid of merits and is liable to be dismissed in limine",
        ),
        FixedPhraseRule(
            context="preliminary_position",
            phrase="has suppressed material facts",
        ),
        FixedPhraseRule(
            context="preliminary_position",
            phrase="strictly in accordance with law and after following due procedure",
        ),
        FixedPhraseRule(
            context="preliminary_position",
            phrase="No legal, constitutional or fundamental right",
        ),
        FixedPhraseRule(
            context="substantive_answer",
            phrase="With reference to the averments made in the Petition",
        ),
        FixedPhraseRule(
            context="substantive_answer",
            phrase="the same are false, incorrect and denied",
        ),
        FixedPhraseRule(
            context="substantive_answer",
            phrase="has failed to make out any case warranting interference",
        ),
        FixedPhraseRule(
            context="substantive_answer",
            phrase="the extraordinary writ jurisdiction of this Hon'ble Court",
        ),
        FixedPhraseRule(
            context="closing",
            phrase="In the premises aforesaid",
        ),
        FixedPhraseRule(
            context="closing",
            phrase="deserves to be dismissed with costs",
        ),
        FixedPhraseRule(
            context="prayer",
            phrase="I therefore respectfully pray that this Hon'ble Court may be pleased to:",
        ),
        FixedPhraseRule(
            context="prayer",
            phrase="grant such other and further reliefs as this Hon'ble Court may deem fit and proper",
        ),
        FixedPhraseRule(
            context="verification",
            phrase="true and correct to my knowledge and belief",
        ),
        FixedPhraseRule(
            context="verification",
            phrase="nothing material has been concealed therefrom",
        ),
    ]

    prayer = PrayerLetteringRule(
        standard_clauses=[
            "dismiss the present [PROCEEDING TYPE] with costs",
            "refuse any interim or ad-interim relief sought by the Petitioner",
            "grant such other and further reliefs as this Hon'ble Court may deem fit and proper in the facts and circumstances of the case",
        ],
    )

    formatting = FormattingConvention(
        bold_caps_centred_sections=[
            AffidavitSection.FORUM_HEADING,
            AffidavitSection.JURISDICTION,
            AffidavitSection.CASE_NUMBER,
            AffidavitSection.AFFIDAVIT_TITLE,
            AffidavitSection.PRAYER,
            AffidavitSection.VERIFICATION,
        ],
    )

    return AffidavitTemplateSchema(
        sections=sections,
        prayer_lettering=prayer,
        fixed_phrases=fixed_phrases,
        formatting=formatting,
        optional_elements=[
            OptionalTemplateElement.EXHIBIT_REFERENCE,
            OptionalTemplateElement.ADVOCATE_BLOCK,
        ],
        reply_move_sequence=[
            ReplyMoveType.IDENTITY_AND_PERUSAL,
            ReplyMoveType.BLANKET_DENIAL,
            ReplyMoveType.PRELIMINARY_POSITION,
            ReplyMoveType.SUBSTANTIVE_ANSWER,
            ReplyMoveType.DOCUMENT_RELIED_UPON,
            ReplyMoveType.CLOSING,
            ReplyMoveType.PRAYER_TO_DISMISS,
        ],
    )
