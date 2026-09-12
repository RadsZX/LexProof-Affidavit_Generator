"""Deterministic extraction of AffidavitCaseInput from a case-information PDF."""

from __future__ import annotations

import re
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from src.document_parser import PDFDocumentParser
from src.schemas import (
    AdvocateDetails,
    AffidavitCaseInput,
    AttestationDetails,
    CaseDetails,
    DeponentCapacity,
    DeponentDetails,
    EvidenceReference,
    ExhibitReference,
    PartyDescription,
    ReplyMoveType,
    ReplyPoint,
    ReplyPoints,
    Respondent,
    VerificationVerb,
)

BULLET_RE = re.compile(r"[●•]\u200b?")
EXHIBIT_RE = re.compile(
    r"EXHIBIT\s*[-–—]?\s*['’‘]?([A-Za-z])['’‘]?",
    re.IGNORECASE,
)
DATED_RE = re.compile(r"dated\s+(\d{1,2}\s+\w+\s+\d{4})", re.IGNORECASE)
POINT_HEADING_RE = re.compile(
    r"Point\s+(\d+)\s+[—\-]\s*(.+)",
    re.IGNORECASE,
)
RESPONDENT_LABEL_RE = re.compile(r"^Respondent\s+No\.?\s*(\d+)\s*$", re.IGNORECASE)
FILED_ON_BEHALF_RE = re.compile(r"Respondent\s+No\.?\s*(\d+)", re.IGNORECASE)

FOOTER_RE = re.compile(r"^This file contains\b", re.IGNORECASE)
SECTION_HEADINGS = {
    "case": re.compile(r"^1\.\s*Court and Case Details\s*$", re.IGNORECASE),
    "deponent": re.compile(r"^2\.\s*Deponent Details\s*$", re.IGNORECASE),
    "reply_points": re.compile(r"^3\.\s*Reply Points to be Incorporated\s*$", re.IGNORECASE),
    "prayer": re.compile(r"^4\.\s*Prayer\s*$", re.IGNORECASE),
    "attestation": re.compile(r"^5\.\s*Attestation Details\s*$", re.IGNORECASE),
    "advocate": re.compile(r"^6\.\s*Advocate\s*$", re.IGNORECASE),
}

CASE_LABELS = [
    "Document Type",
    "Court",
    "Jurisdiction",
    "Proceeding Type",
    "Case Number",
    "Year",
    "Petitioner",
    "Filed on behalf of",
]
DEPONENT_LABELS = ["Name", "Designation", "Organisation", "Address", "Verification verb"]
ATTESTATION_LABELS = ["Place", "Date"]
ADVOCATE_LABELS = ["Advocate Firm", "Acting for"]

TITLE_MOVE_RULES: list[tuple[str, ReplyMoveType]] = [
    ("filing of affidavit", ReplyMoveType.IDENTITY_AND_PERUSAL),
    ("general denial", ReplyMoveType.BLANKET_DENIAL),
    ("preliminary position", ReplyMoveType.PRELIMINARY_POSITION),
    ("document relied upon", ReplyMoveType.DOCUMENT_RELIED_UPON),
    ("denial regarding", ReplyMoveType.SUBSTANTIVE_ANSWER),
    ("authority for", ReplyMoveType.SUBSTANTIVE_ANSWER),
]

VERB_ALIASES = {
    "solemnly affirm": VerificationVerb.SOLEMNLY_AFFIRM,
    "swear and affirm": VerificationVerb.SWEAR_AND_AFFIRM,
    "swear": VerificationVerb.SWEAR_AND_AFFIRM,
    "affirm": VerificationVerb.SOLEMNLY_AFFIRM,
}


class CaseExtractionError(Exception):
    """Raised when required case-information fields cannot be extracted."""


class ExtractionResult(BaseModel):
    """Validated case input plus a small evidence map."""

    model_config = ConfigDict(extra="forbid")

    case_input: AffidavitCaseInput
    evidence: dict[str, EvidenceReference] = Field(default_factory=dict)
    prayer_facts: list[str] = Field(
        default_factory=list,
        description="Prayer bullets from the source PDF; not a schema field yet.",
    )


def _find_page(pages: list, snippet: str) -> int | None:
    if not snippet:
        return None
    cleaned = re.sub(r"\s+", " ", snippet).strip().casefold()
    for page in pages:
        p_text = re.sub(r"\s+", " ", page.text).casefold()
        if cleaned in p_text:
            return page.page_number
    if len(cleaned) > 20:
        short = cleaned[:20]
        for page in pages:
            p_text = re.sub(r"\s+", " ", page.text).casefold()
            if short in p_text:
                return page.page_number
    return None


def _make_evidence(
    doc_name: str,
    pages: list,
    section: str,
    field_name: str,
    source_text: str,
) -> EvidenceReference:
    page = _find_page(pages, source_text)
    return EvidenceReference(
        source_document=doc_name,
        source_section=section,
        source_page=page,
        source_text=source_text.strip(),
        field_name=field_name,
    )


class CaseInformationExtractor:
    """Extract AffidavitCaseInput from a labelled case-information PDF."""

    def __init__(self, parser: PDFDocumentParser | None = None) -> None:
        self.parser = parser or PDFDocumentParser()

    def extract(self, file_path: str | Path) -> AffidavitCaseInput:
        return self.extract_with_evidence(file_path).case_input

    def extract_with_evidence(self, file_path: str | Path) -> ExtractionResult:
        document = self.parser.parse(file_path)
        text = _normalize_extracted_text(document.full_text)
        sections = _split_sections(text)
        evidence: dict[str, EvidenceReference] = {}
        pages = document.pages
        doc_name = document.filename

        case = self._extract_case_details(sections.get("case", ""), evidence, doc_name, pages)
        deponent = self._extract_deponent(sections.get("deponent", ""), case, evidence, doc_name, pages)
        reply_points = self._extract_reply_points(sections.get("reply_points", ""), evidence, doc_name, pages)
        attestation = self._extract_attestation(
            sections.get("attestation", ""),
            deponent.verification_verb,
            evidence,
            doc_name,
            pages,
        )
        advocate = self._extract_advocate(sections.get("advocate", ""), evidence, doc_name, pages)
        prayer_facts = _extract_bullets(sections.get("prayer", ""))

        case_input = AffidavitCaseInput(
            case=case,
            deponent=deponent,
            reply_points=reply_points,
            attestation=attestation,
            advocate=advocate,
            evidence=evidence,
        )
        return ExtractionResult(
            case_input=case_input,
            evidence=evidence,
            prayer_facts=prayer_facts,
        )

    def _extract_case_details(
        self,
        section: str,
        evidence: dict[str, EvidenceReference],
        doc_name: str,
        pages: list,
    ) -> CaseDetails:
        fields = _labeled_fields(section, CASE_LABELS)
        respondents = _extract_respondents(section)

        court = _require(fields, "Court", "court")
        jurisdiction = _require(fields, "Jurisdiction", "jurisdiction_type")
        proceeding = _require(fields, "Proceeding Type", "proceeding_type")
        case_number = _require(fields, "Case Number", "case_number")
        year_raw = _require(fields, "Year", "year")
        petitioner_name = _require(fields, "Petitioner", "petitioner")
        filed_for = _require(fields, "Filed on behalf of", "answering_respondent_number")

        match = FILED_ON_BEHALF_RE.search(filed_for)
        if not match:
            raise CaseExtractionError(
                f"Could not parse answering respondent number from '{filed_for}'."
            )
        answering = int(match.group(1))
        if not respondents:
            raise CaseExtractionError("No respondents found in case information.")

        sec_title = "1. Court and Case Details"
        evidence["court"] = _make_evidence(doc_name, pages, sec_title, "court", court)
        evidence["jurisdiction"] = _make_evidence(doc_name, pages, sec_title, "jurisdiction", jurisdiction)
        evidence["proceeding_type"] = _make_evidence(doc_name, pages, sec_title, "proceeding_type", proceeding)
        evidence["case_number"] = _make_evidence(doc_name, pages, sec_title, "case_number", case_number)
        evidence["year"] = _make_evidence(doc_name, pages, sec_title, "year", str(year_raw))
        evidence["petitioner"] = _make_evidence(doc_name, pages, sec_title, "petitioner", petitioner_name)
        evidence["answering_respondent"] = _make_evidence(doc_name, pages, sec_title, "answering_respondent", filed_for)

        resp_summary = "; ".join(f"Respondent No. {r.respondent_number}: {r.name}" for r in respondents)
        evidence["respondents"] = _make_evidence(doc_name, pages, sec_title, "respondents", resp_summary)
        for respondent in respondents:
            evidence[f"respondent_{respondent.respondent_number}"] = _make_evidence(
                doc_name, pages, sec_title, f"respondent_{respondent.respondent_number}", respondent.name
            )

        return CaseDetails(
            document_type=fields.get("Document Type", "Affidavit in Reply"),
            court=court,
            jurisdiction_type=jurisdiction,
            proceeding_type=proceeding,
            case_number=case_number,
            year=int(year_raw),
            petitioner=PartyDescription(name=petitioner_name),
            respondents=respondents,
            answering_respondent_number=answering,
        )

    def _extract_deponent(
        self,
        section: str,
        case: CaseDetails,
        evidence: dict[str, EvidenceReference],
        doc_name: str,
        pages: list,
    ) -> DeponentDetails:
        fields = _labeled_fields(section, DEPONENT_LABELS)
        name = _require(fields, "Name", "deponent.name")
        designation = fields.get("Designation")
        organisation = fields.get("Organisation")
        address = _require(fields, "Address", "deponent.address")
        verb = _parse_verification_verb(fields.get("Verification verb"))

        respondent_names = {item.name.casefold() for item in case.respondents}
        is_officer = bool(designation or organisation) and name.casefold() not in respondent_names
        capacity = (
            DeponentCapacity.ORGANISATION_OFFICER
            if is_officer
            else DeponentCapacity.RESPONDENT_PERSONAL
        )

        sec_title = "2. Deponent Details"
        evidence["deponent"] = _make_evidence(doc_name, pages, sec_title, "deponent", name)
        if designation:
            evidence["designation"] = _make_evidence(doc_name, pages, sec_title, "designation", designation)
        if organisation:
            evidence["organisation"] = _make_evidence(doc_name, pages, sec_title, "organisation", organisation)
        evidence["address"] = _make_evidence(doc_name, pages, sec_title, "address", address)
        evidence["verification_verb"] = _make_evidence(doc_name, pages, sec_title, "verification_verb", verb.value)
        evidence["deponent_capacity"] = _make_evidence(
            doc_name,
            pages,
            sec_title,
            "deponent_capacity",
            f"{capacity.value} ({designation or ''}, {organisation or ''})".strip(),
        )

        return DeponentDetails(
            name=name,
            capacity=capacity,
            designation=designation,
            organisation=organisation,
            address=address,
            verification_verb=verb,
        )

    def _extract_reply_points(
        self,
        section: str,
        evidence: dict[str, EvidenceReference],
        doc_name: str,
        pages: list,
    ) -> ReplyPoints:
        points = _parse_reply_points(section)
        if len(points) != 6:
            raise CaseExtractionError(
                f"Expected 6 reply points, found {len(points)}."
            )

        for point in points:
            sec_title = f"3. Reply Points to be Incorporated (Point {point.point_number})"
            facts_text = " | ".join(point.source_facts)
            evidence[f"reply_point_{point.point_number}"] = _make_evidence(
                doc_name,
                pages,
                sec_title,
                f"Reply Point {point.point_number}",
                facts_text,
            )
            if point.exhibit:
                exhibit_desc = f"{point.exhibit.label}: {point.exhibit.document_description}"
                if point.exhibit.document_date:
                    exhibit_desc += f" (dated {point.exhibit.document_date})"
                evidence["exhibits"] = _make_evidence(
                    doc_name,
                    pages,
                    sec_title,
                    "exhibits",
                    exhibit_desc,
                )

        return ReplyPoints(points=points)

    def _extract_attestation(
        self,
        section: str,
        verification_verb: VerificationVerb,
        evidence: dict[str, EvidenceReference],
        doc_name: str,
        pages: list,
    ) -> AttestationDetails:
        fields = _labeled_fields(section, ATTESTATION_LABELS)
        place = _require(fields, "Place", "attestation.place")
        date_value = _require(fields, "Date", "attestation.date")
        sec_title = "5. Attestation Details"
        evidence["attestation_place"] = _make_evidence(doc_name, pages, sec_title, "attestation_place", place)
        evidence["attestation_date"] = _make_evidence(doc_name, pages, sec_title, "attestation_date", date_value)
        evidence["attestation_details"] = _make_evidence(
            doc_name, pages, sec_title, "attestation_details", f"{place}, {date_value}"
        )
        return AttestationDetails(place=place, date=date_value, verification_verb=verification_verb)

    def _extract_advocate(
        self,
        section: str,
        evidence: dict[str, EvidenceReference],
        doc_name: str,
        pages: list,
    ) -> AdvocateDetails:
        fields = _labeled_fields(section, ADVOCATE_LABELS)
        firm = _require(fields, "Advocate Firm", "advocate.firm")
        acting_for = _require(fields, "Acting for", "advocate.acting_for")
        sec_title = "6. Advocate"
        evidence["advocate_firm"] = _make_evidence(doc_name, pages, sec_title, "advocate_firm", firm)
        evidence["advocate_acting_for"] = _make_evidence(doc_name, pages, sec_title, "advocate_acting_for", acting_for)
        evidence["advocate_details"] = _make_evidence(
            doc_name, pages, sec_title, "advocate_details", f"{firm} (Acting for {acting_for})"
        )
        return AdvocateDetails(firm=firm, acting_for=acting_for)


def extract_case_information(file_path: str | Path) -> AffidavitCaseInput:
    """Convenience wrapper around CaseInformationExtractor.extract."""
    return CaseInformationExtractor().extract(file_path)


def _normalize_extracted_text(text: str) -> str:
    normalized = (
        text.replace("\r\n", "\n")
        .replace("\u2018", "'")
        .replace("\u2019", "'")
        .replace("\u201c", '"')
        .replace("\u201d", '"')
        .replace("\ufeff", "")
        .replace("\u200b", "")
    )
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in normalized.splitlines()]
    return "\n".join(line for line in lines if line)


def _split_sections(text: str) -> dict[str, str]:
    lines = text.splitlines()
    headings: list[tuple[int, str]] = []
    for index, line in enumerate(lines):
        if FOOTER_RE.match(line):
            break
        for name, pattern in SECTION_HEADINGS.items():
            if pattern.match(line):
                headings.append((index, name))
                break

    sections: dict[str, str] = {}
    for position, (start, name) in enumerate(headings):
        end = headings[position + 1][0] if position + 1 < len(headings) else len(lines)
        sections[name] = "\n".join(lines[start + 1 : end]).strip()
    return sections


def _labeled_fields(section: str, labels: list[str]) -> dict[str, str]:
    """Parse a labelled block where each known label is followed by its value lines."""
    lines = [line.strip() for line in section.splitlines() if line.strip()]
    label_set = {label.casefold(): label for label in labels}
    fields: dict[str, list[str]] = {}
    current: str | None = None

    for line in lines:
        respondent_match = RESPONDENT_LABEL_RE.match(line)
        canonical = label_set.get(line.casefold())
        if canonical:
            current = canonical
            fields.setdefault(current, [])
            continue
        if respondent_match:
            if current is not None and not fields.get(current):
                fields[current].append(line)
                continue
            current = f"Respondent No. {respondent_match.group(1)}"
            fields.setdefault(current, [])
            continue
        if current is None:
            continue
        if FOOTER_RE.match(line) or _looks_like_next_heading(line):
            current = None
            continue
        fields[current].append(line)

    return {key: " ".join(values).strip() for key, values in fields.items() if values}


def _looks_like_next_heading(line: str) -> bool:
    return bool(re.match(r"^\d+\.\s+\S+", line)) or POINT_HEADING_RE.match(line) is not None


def _extract_respondents(section: str) -> list[Respondent]:
    fields = _labeled_fields(section, CASE_LABELS)
    respondents: list[Respondent] = []
    for key, value in fields.items():
        match = re.match(r"Respondent No\.?\s*(\d+)$", key, re.IGNORECASE)
        if match and value:
            respondents.append(
                Respondent(name=value, respondent_number=int(match.group(1)))
            )
    respondents.sort(key=lambda item: item.respondent_number)
    return respondents


def _parse_reply_points(section: str) -> list[ReplyPoint]:
    lines = [line.strip() for line in section.splitlines() if line.strip()]
    grouped: list[tuple[int, str, list[str]]] = []
    current: tuple[int, str, list[str]] | None = None

    for line in lines:
        heading = POINT_HEADING_RE.match(line)
        if heading:
            if current is not None:
                grouped.append(current)
            current = (int(heading.group(1)), heading.group(2).strip(), [])
            continue
        if current is None:
            continue
        current[2].append(line)

    if current is not None:
        grouped.append(current)

    points: list[ReplyPoint] = []
    for number, title, raw_lines in grouped:
        facts = _extract_bullets("\n".join(raw_lines))
        if not facts:
            raise CaseExtractionError(f"Reply point {number} has no source facts.")
        move = _move_for_title(title)
        exhibit = _exhibit_from_facts(facts)
        points.append(
            ReplyPoint(
                point_number=number,
                move=move,
                source_facts=facts,
                exhibit=exhibit,
            )
        )
    return points


def _extract_bullets(text: str) -> list[str]:
    if not text.strip():
        return []
    chunks = BULLET_RE.split(text)
    facts: list[str] = []
    for chunk in chunks:
        cleaned = re.sub(r"\s+", " ", chunk).strip(" \n\t-")
        if cleaned and not cleaned.lower().startswith("the following points"):
            facts.append(cleaned)
    return facts


def _move_for_title(title: str) -> ReplyMoveType:
    lowered = title.casefold()
    for needle, move in TITLE_MOVE_RULES:
        if needle in lowered:
            return move
    raise CaseExtractionError(f"No reply-move mapping for title '{title}'.")


def _exhibit_from_facts(facts: list[str]) -> ExhibitReference | None:
    for fact in facts:
        match = EXHIBIT_RE.search(fact)
        if not match:
            continue
        letter = match.group(1).upper()
        dated = DATED_RE.search(" ".join(facts))
        return ExhibitReference(
            label=f"EXHIBIT-'{letter}'",
            document_description=fact,
            document_date=dated.group(1) if dated else None,
        )
    return None


def _parse_verification_verb(raw: str | None) -> VerificationVerb:
    if not raw:
        return VerificationVerb.SOLEMNLY_AFFIRM
    key = re.sub(r"\s+", " ", raw).strip().casefold()
    if key in VERB_ALIASES:
        return VERB_ALIASES[key]
    raise CaseExtractionError(f"Unsupported verification verb '{raw}'.")


def _require(fields: dict[str, str], label: str, field_name: str) -> str:
    value = fields.get(label, "").strip()
    if not value:
        raise CaseExtractionError(f"Missing required field '{field_name}' (label '{label}').")
    return value
