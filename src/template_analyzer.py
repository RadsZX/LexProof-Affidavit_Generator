"""Analyze affidavit format guide and reference documents against template schema."""

from __future__ import annotations

import re
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from src.document_parser import PDFDocumentParser, ParsedDocument
from src.schemas import (
    AffidavitSection,
    AffidavitTemplateSchema,
    OptionalTemplateElement,
    ReplyMoveType,
    default_bombay_hc_affidavit_in_reply_template,
)

# Generic structural markers derived from the format guide (not case-specific).
SECTION_MARKERS: dict[AffidavitSection, list[str]] = {
    AffidavitSection.FORUM_HEADING: ["IN THE HIGH COURT OF JUDICATURE AT"],
    AffidavitSection.JURISDICTION: [" JURISDICTION"],
    AffidavitSection.CASE_NUMBER: [" NO. ", " OF "],
    AffidavitSection.CAUSE_TITLE: ["VERSUS", "...Petitioner", "...Respondent"],
    AffidavitSection.AFFIDAVIT_TITLE: ["AFFIDAVIT IN REPLY ON BEHALF OF RESPONDENT NO."],
    AffidavitSection.DEPONENT_CLAUSE: ["do hereby solemnly affirm and state as under:"],
    AffidavitSection.NUMBERED_PARAGRAPHS: ["\n1.", "1. I say that I am"],
    AffidavitSection.PRAYER: ["PRAYER", "(a)"],
    AffidavitSection.JURAT: ["Solemnly affirmed at", "Before Me", "DEPONENT"],
    AffidavitSection.VERIFICATION: ["VERIFICATION", "paragraphs 1 to", "Verified at"],
}

OPTIONAL_ELEMENT_MARKERS: dict[OptionalTemplateElement, list[str]] = {
    OptionalTemplateElement.EXHIBIT_REFERENCE: ["EXHIBIT-", "Hereto annexed and marked as"],
    OptionalTemplateElement.ADVOCATE_BLOCK: ["Advocates for"],
}

REPLY_MOVE_MARKERS: dict[ReplyMoveType, list[str]] = {
    ReplyMoveType.IDENTITY_AND_PERUSAL: [
        "am well acquainted with the facts and circumstances of the case",
        "I have perused the Petition and the documents annexed thereto",
        "am competent to affirm this Affidavit in Reply",
    ],
    ReplyMoveType.BLANKET_DENIAL: [
        "At the outset, I deny each and every allegation, contention and submission",
        "save and except those specifically admitted herein",
    ],
    ReplyMoveType.PRELIMINARY_POSITION: [
        "has suppressed material facts",
        "strictly in accordance with law and after following due procedure",
        "No legal, constitutional or fundamental right",
    ],
    ReplyMoveType.SUBSTANTIVE_ANSWER: [
        "With reference to the averments made in the Petition",
        "the same are false, incorrect and denied",
    ],
    ReplyMoveType.CLOSING: [
        "In the premises aforesaid",
        "deserves to be dismissed with costs",
    ],
    ReplyMoveType.PRAYER_TO_DISMISS: [
        "I therefore respectfully pray that this Hon'ble Court may be pleased to:",
        "dismiss the present",
    ],
}

FORMAT_GUIDE_SECTION_HINTS = [
    "Forum heading",
    "Jurisdiction",
    "Case number",
    "Cause title",
    "Affidavit title",
    "Deponent clause",
    "Numbered paragraphs",
    "Prayer",
    "Jurat",
    "Verification",
]

MAJOR_REPLY_MOVE_SEQUENCE = [
    ReplyMoveType.IDENTITY_AND_PERUSAL,
    ReplyMoveType.BLANKET_DENIAL,
    ReplyMoveType.PRELIMINARY_POSITION,
    ReplyMoveType.SUBSTANTIVE_ANSWER,
    ReplyMoveType.CLOSING,
    ReplyMoveType.PRAYER_TO_DISMISS,
]


class SectionDetection(BaseModel):
    """Whether a required affidavit section was found in document text."""

    model_config = ConfigDict(extra="forbid")

    section: AffidavitSection
    order: int
    detected: bool
    evidence: str | None = None


class ReferenceAnalysisResult(BaseModel):
    """Outcome of validating a reference affidavit against the template schema."""

    model_config = ConfigDict(extra="forbid")

    template: AffidavitTemplateSchema
    sections: list[SectionDetection]
    optional_elements_found: list[OptionalTemplateElement] = Field(default_factory=list)
    reply_moves_detected: list[ReplyMoveType] = Field(default_factory=list)
    body_paragraph_count: int | None = None
    validation_issues: list[str] = Field(default_factory=list)

    @property
    def all_required_sections_present(self) -> bool:
        return all(section.detected for section in self.sections)

    @property
    def major_reply_moves_present(self) -> bool:
        return all(move in self.reply_moves_detected for move in MAJOR_REPLY_MOVE_SEQUENCE)


class TemplateAnalyzer:
    """Build and validate affidavit templates from format and reference PDFs."""

    def __init__(self, parser: PDFDocumentParser | None = None) -> None:
        self.parser = parser or PDFDocumentParser()

    def build_template_from_format_guide(
        self,
        format_guide_path: str | Path,
    ) -> AffidavitTemplateSchema:
        """Load the format guide and return the canonical template schema."""
        document = self.parser.parse(format_guide_path)
        template = default_bombay_hc_affidavit_in_reply_template()
        self._validate_format_guide(document, template)
        return template

    def analyze_reference_affidavit(
        self,
        reference_path: str | Path,
        template: AffidavitTemplateSchema | None = None,
    ) -> ReferenceAnalysisResult:
        """Detect structural elements in a reference affidavit sample."""
        document = self.parser.parse(reference_path)
        template = template or default_bombay_hc_affidavit_in_reply_template()
        text = _normalize_text(document.full_text)
        searchable = _flatten_text(text)

        sections = self._detect_sections(searchable, template)
        optional_elements = self._detect_optional_elements(searchable)
        reply_moves = self._detect_reply_moves(searchable)
        body_paragraph_count = _count_numbered_body_paragraphs(text)
        issues = self._collect_validation_issues(
            text=searchable,
            template=template,
            sections=sections,
            reply_moves=reply_moves,
            body_paragraph_count=body_paragraph_count,
        )

        return ReferenceAnalysisResult(
            template=template,
            sections=sections,
            optional_elements_found=optional_elements,
            reply_moves_detected=reply_moves,
            body_paragraph_count=body_paragraph_count,
            validation_issues=issues,
        )

    def _validate_format_guide(
        self,
        document: ParsedDocument,
        template: AffidavitTemplateSchema,
    ) -> None:
        text = _flatten_text(_normalize_text(document.full_text))
        missing_hints = [hint for hint in FORMAT_GUIDE_SECTION_HINTS if hint.lower() not in text.lower()]
        if missing_hints:
            msg = f"Format guide missing expected section descriptions: {missing_hints}"
            raise ValueError(msg)

        if len(template.sections) != 10:
            msg = f"Template must define exactly 10 sections; found {len(template.sections)}."
            raise ValueError(msg)

    def _detect_sections(
        self,
        text: str,
        template: AffidavitTemplateSchema,
    ) -> list[SectionDetection]:
        detections: list[SectionDetection] = []
        for spec in template.sections:
            markers = SECTION_MARKERS.get(spec.section, [])
            matched_marker = next((marker for marker in markers if marker in text), None)
            detections.append(
                SectionDetection(
                    section=spec.section,
                    order=spec.order,
                    detected=matched_marker is not None,
                    evidence=matched_marker,
                )
            )
        return detections

    def _detect_optional_elements(self, text: str) -> list[OptionalTemplateElement]:
        found: list[OptionalTemplateElement] = []
        for element, markers in OPTIONAL_ELEMENT_MARKERS.items():
            if any(marker in text for marker in markers):
                found.append(element)
        return found

    def _detect_reply_moves(self, text: str) -> list[ReplyMoveType]:
        detected: list[ReplyMoveType] = []
        for move in MAJOR_REPLY_MOVE_SEQUENCE:
            markers = REPLY_MOVE_MARKERS[move]
            if any(marker in text for marker in markers):
                detected.append(move)

        exhibit_markers = OPTIONAL_ELEMENT_MARKERS[OptionalTemplateElement.EXHIBIT_REFERENCE]
        if any(marker in text for marker in exhibit_markers) and ReplyMoveType.DOCUMENT_RELIED_UPON not in detected:
            if ReplyMoveType.CLOSING in detected:
                detected.insert(detected.index(ReplyMoveType.CLOSING), ReplyMoveType.DOCUMENT_RELIED_UPON)
            else:
                detected.append(ReplyMoveType.DOCUMENT_RELIED_UPON)
        return detected

    def _collect_validation_issues(
        self,
        text: str,
        template: AffidavitTemplateSchema,
        sections: list[SectionDetection],
        reply_moves: list[ReplyMoveType],
        body_paragraph_count: int | None,
    ) -> list[str]:
        issues: list[str] = []

        for detection in sections:
            if not detection.detected:
                issues.append(f"Missing required section: {detection.section.value}")

        for move in MAJOR_REPLY_MOVE_SEQUENCE:
            if move not in reply_moves:
                issues.append(f"Missing reply move: {move.value}")

        if body_paragraph_count is not None and template.verification_range.range_must_match_body_paragraph_count:
            range_match = re.search(r"paragraphs\s+1\s+to\s+(\d+)", text, re.IGNORECASE)
            if range_match:
                declared = int(range_match.group(1))
                if declared != body_paragraph_count:
                    issues.append(
                        f"Verification range paragraphs 1 to {declared} "
                        f"does not match body paragraph count {body_paragraph_count}."
                    )

        if template.verification_range.verification_verb_must_match_deponent_clause:
            if "do hereby solemnly affirm" in text.lower() and "Solemnly affirmed at" not in text:
                issues.append("Deponent clause uses affirm but jurat does not use 'Solemnly affirmed at'.")

        return issues


def _normalize_text(text: str) -> str:
    """Normalize line endings, quotes, and intra-line spacing while keeping line breaks."""
    normalized = (
        text.replace("\r\n", "\n")
        .replace("\u2018", "'")
        .replace("\u2019", "'")
        .replace("\u201c", '"')
        .replace("\u201d", '"')
        .strip()
    )
    return re.sub(r"[ \t]+", " ", normalized)


def _flatten_text(text: str) -> str:
    """Collapse whitespace so wrapped PDF phrases can be matched as continuous text."""
    return re.sub(r"\s+", " ", text).strip()


def _count_numbered_body_paragraphs(text: str) -> int | None:
    """Count numbered body paragraphs before the PRAYER section."""
    prayer_index = text.find("PRAYER")
    body = text if prayer_index == -1 else text[:prayer_index]
    numbers = [int(match) for match in re.findall(r"(?:^|\n)\s*(\d+)\.\s", body)]
    if not numbers:
        return None
    return max(numbers)
