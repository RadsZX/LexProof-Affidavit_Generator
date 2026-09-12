"""Map validated case input onto affidavit template structure (no LLM, no DOCX)."""

from __future__ import annotations

import calendar
import re
from datetime import date as Date
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.schemas import (
    AdvocateDetails,
    AffidavitCaseInput,
    AffidavitTemplateSchema,
    AttestationDetails,
    CaseDetails,
    DeponentCapacity,
    DeponentDetails,
    EvidenceReference,
    ExhibitReference,
    ReplyMoveType,
    ReplyPoint,
    VerificationVerb,
    default_bombay_hc_affidavit_in_reply_template,
)


class ContentMappingError(Exception):
    """Raised when case input cannot be mapped onto the affidavit template."""


class MappedParty(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    description_lines: list[str] = Field(default_factory=list)
    status_tag: str
    respondent_number: Optional[int] = None


class MappedCauseTitle(BaseModel):
    model_config = ConfigDict(extra="forbid")

    petitioner: MappedParty
    respondents: list[MappedParty]
    versus: str = "VERSUS"


class MappedDeponentClause(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    designation: Optional[str] = None
    organisation: Optional[str] = None
    address: str
    capacity: DeponentCapacity
    answering_respondent_number: int
    capacity_phrase: str
    verification_verb: VerificationVerb
    text: str


class MappedBodyParagraph(BaseModel):
    model_config = ConfigDict(extra="forbid")

    number: int = Field(..., ge=1)
    move: ReplyMoveType
    text: str
    source_facts: list[str] = Field(default_factory=list)
    source_point_number: Optional[int] = None
    exhibit: Optional[ExhibitReference] = None
    evidence: Optional[EvidenceReference] = None


class MappedPrayerClause(BaseModel):
    model_config = ConfigDict(extra="forbid")

    letter: str
    text: str

    @property
    def label(self) -> str:
        return f"({self.letter})"


class MappedPrayer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    heading: str = "PRAYER"
    introductory_phrase: str
    clauses: list[MappedPrayerClause]


class MappedJurat(BaseModel):
    model_config = ConfigDict(extra="forbid")

    place: str
    date: str
    date_ordinal: str
    verb_past: str
    text: str


class MappedVerification(BaseModel):
    model_config = ConfigDict(extra="forbid")

    deponent_name: str
    paragraph_start: int
    paragraph_end: int
    includes_prayer: bool = True
    place: str
    date: str
    date_ordinal: str
    text: str


class MappedAdvocateBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")

    firm: str
    acting_for: str
    text: str


class MappedAffidavitContent(BaseModel):
    """Structured affidavit content ready for a later DOCX renderer."""

    model_config = ConfigDict(extra="forbid")

    forum_heading: str
    jurisdiction: str
    case_number_line: str
    cause_title: MappedCauseTitle
    affidavit_title: str
    deponent_clause: MappedDeponentClause
    body_paragraphs: list[MappedBodyParagraph]
    prayer: MappedPrayer
    jurat: MappedJurat
    verification: MappedVerification
    advocate: Optional[MappedAdvocateBlock] = None
    evidence: dict[str, EvidenceReference] = Field(default_factory=dict)
    template: Optional[AffidavitTemplateSchema] = None

    @field_validator("body_paragraphs")
    @classmethod
    def paragraphs_must_be_contiguous(cls, paragraphs: list[MappedBodyParagraph]) -> list[MappedBodyParagraph]:
        numbers = [paragraph.number for paragraph in paragraphs]
        expected = list(range(1, len(paragraphs) + 1))
        if numbers != expected:
            raise ValueError("Body paragraphs must be numbered contiguously from 1.")
        return paragraphs

    @property
    def body_paragraph_count(self) -> int:
        return len(self.body_paragraphs)

    def all_text(self) -> str:
        parts = [
            self.forum_heading,
            self.jurisdiction,
            self.case_number_line,
            self.cause_title.petitioner.name,
            self.cause_title.versus,
            *(party.name for party in self.cause_title.respondents),
            self.affidavit_title,
            self.deponent_clause.text,
            *(paragraph.text for paragraph in self.body_paragraphs),
            self.prayer.heading,
            self.prayer.introductory_phrase,
            *(clause.text for clause in self.prayer.clauses),
            self.jurat.text,
            "VERIFICATION",
            self.verification.text,
        ]
        if self.advocate:
            parts.append(self.advocate.text)
        return "\n".join(parts)


class AffidavitContentMapper:
    """Deterministically map case input onto the 10-part affidavit skeleton."""

    def map(
        self,
        case_input: AffidavitCaseInput,
        template: AffidavitTemplateSchema | None = None,
    ) -> MappedAffidavitContent:
        template = template or case_input.template or default_bombay_hc_affidavit_in_reply_template()
        case = case_input.case
        deponent = case_input.deponent
        answering = case.answering_respondent_number
        proceeding = _proceeding_display(case.proceeding_type)
        respondent_label = _respondent_label(answering)

        deponent_clause = self._map_deponent_clause(deponent, answering, template)
        body_paragraphs = self._map_body_paragraphs(
            case_input=case_input,
            template=template,
            deponent_clause=deponent_clause,
            proceeding=proceeding,
            respondent_label=respondent_label,
        )
        prayer = self._map_prayer(case, template)
        jurat = self._map_jurat(case_input.attestation)
        verification = self._map_verification(
            deponent=deponent,
            attestation=case_input.attestation,
            paragraph_count=len(body_paragraphs),
            template=template,
        )
        advocate = self._map_advocate(case_input.advocate, respondent_label)

        evidence_map = dict(case_input.evidence) if case_input.evidence else {}
        for p in body_paragraphs:
            if p.evidence:
                evidence_map[f"reply_paragraph_{p.number}"] = p.evidence

        return MappedAffidavitContent(
            forum_heading=case.court.strip(),
            jurisdiction=case.jurisdiction_type.strip(),
            case_number_line=_case_number_line(case),
            cause_title=self._map_cause_title(case),
            affidavit_title=(
                f"AFFIDAVIT IN REPLY ON BEHALF OF RESPONDENT NO. {answering}"
            ),
            deponent_clause=deponent_clause,
            body_paragraphs=body_paragraphs,
            prayer=prayer,
            jurat=jurat,
            verification=verification,
            advocate=advocate,
            evidence=evidence_map,
            template=template,
        )

    def _map_cause_title(self, case: CaseDetails) -> MappedCauseTitle:
        petitioner = MappedParty(
            name=case.petitioner.name,
            description_lines=list(case.petitioner.description_lines),
            status_tag="...Petitioner",
        )
        respondents = [
            MappedParty(
                name=respondent.name,
                description_lines=list(respondent.description_lines),
                status_tag=f"...Respondent No.{respondent.respondent_number}",
                respondent_number=respondent.respondent_number,
            )
            for respondent in case.respondents
        ]
        return MappedCauseTitle(petitioner=petitioner, respondents=respondents)

    def _map_deponent_clause(
        self,
        deponent: DeponentDetails,
        answering: int,
        template: AffidavitTemplateSchema,
    ) -> MappedDeponentClause:
        respondent_label = _respondent_label(answering)
        if deponent.capacity is DeponentCapacity.ORGANISATION_OFFICER:
            if not deponent.designation:
                raise ContentMappingError("Organisation officer deponent requires a designation.")
            capacity_phrase = (
                f"the {deponent.designation} of the {respondent_label} above named"
            )
            office_line = f"having office at {deponent.address}"
            org_bit = f", {deponent.organisation}" if deponent.organisation else ""
            text = (
                f"I, {deponent.name}, {deponent.designation}{org_bit}, {office_line}, "
                f"{capacity_phrase}, "
                f"{_deponent_verb_clause(deponent.verification_verb, template)}"
            )
        else:
            capacity_phrase = f"the {respondent_label} above named"
            text = (
                f"I, {deponent.name}, residing at {deponent.address}, {capacity_phrase}, "
                f"{_deponent_verb_clause(deponent.verification_verb, template)}"
            )

        return MappedDeponentClause(
            name=deponent.name,
            designation=deponent.designation,
            organisation=deponent.organisation,
            address=deponent.address,
            capacity=deponent.capacity,
            answering_respondent_number=answering,
            capacity_phrase=capacity_phrase,
            verification_verb=deponent.verification_verb,
            text=text,
        )

    def _map_body_paragraphs(
        self,
        case_input: AffidavitCaseInput,
        template: AffidavitTemplateSchema,
        deponent_clause: MappedDeponentClause,
        proceeding: str,
        respondent_label: str,
    ) -> list[MappedBodyParagraph]:
        source_points = [
            point
            for point in case_input.reply_points.points
            if point.move not in {ReplyMoveType.CLOSING, ReplyMoveType.PRAYER_TO_DISMISS}
        ]
        evidence_dict = case_input.evidence or {}
        paragraphs: list[MappedBodyParagraph] = []
        for index, point in enumerate(source_points, start=1):
            point_ev = evidence_dict.get(f"reply_point_{point.point_number}")
            paragraphs.append(
                self._map_source_paragraph(
                    number=index,
                    point=point,
                    template=template,
                    deponent_clause=deponent_clause,
                    proceeding=proceeding,
                    respondent_label=respondent_label,
                    evidence=point_ev,
                )
            )

        if not any(paragraph.move is ReplyMoveType.CLOSING for paragraph in paragraphs):
            closing_ev = EvidenceReference(
                source_document="01 Affidavit Format Explained.pdf",
                source_section="Part 7 - Continuous Numbered Paragraphs",
                source_page=2,
                source_text="Standard dismissal closing: In the premises aforesaid, the petition deserves to be dismissed with costs.",
                field_name="reply_paragraph_7",
            )
            paragraphs.append(
                MappedBodyParagraph(
                    number=len(paragraphs) + 1,
                    move=ReplyMoveType.CLOSING,
                    text=_closing_text(proceeding, template),
                    source_facts=[],
                    source_point_number=None,
                    evidence=closing_ev,
                )
            )

        if len(paragraphs) != 7:
            raise ContentMappingError(
                f"Expected 7 numbered body paragraphs for this case, found {len(paragraphs)}."
            )
        return paragraphs

    def _map_source_paragraph(
        self,
        number: int,
        point: ReplyPoint,
        template: AffidavitTemplateSchema,
        deponent_clause: MappedDeponentClause,
        proceeding: str,
        respondent_label: str,
        evidence: Optional[EvidenceReference] = None,
    ) -> MappedBodyParagraph:
        facts = list(point.source_facts)
        if point.move is ReplyMoveType.IDENTITY_AND_PERUSAL:
            text = _identity_text(deponent_clause, proceeding, facts, template)
        elif point.move is ReplyMoveType.BLANKET_DENIAL:
            text = _join_sentences(
                [
                    (
                        f"{_phrase(template, 'blanket_denial', 'At the outset, I deny each and every allegation, contention and submission')} "
                        f"made in the {proceeding}, "
                        f"{_phrase(template, 'blanket_denial', 'save and except those specifically admitted herein')}."
                    ),
                    *facts,
                ]
            )
        elif point.move is ReplyMoveType.PRELIMINARY_POSITION:
            text = _join_sentences([f"I say that {_as_continuation(facts[0])}", *facts[1:]])
        elif point.move is ReplyMoveType.DOCUMENT_RELIED_UPON:
            exhibit = point.exhibit
            if exhibit:
                date_str = f" dated {exhibit.document_date}" if exhibit.document_date else ""
                text = f"{respondent_label} relies upon the communication{date_str}. A copy thereof is annexed hereto and marked as {exhibit.label}."
            else:
                text = _join_sentences(facts)
        else:
            opener = _phrase(
                template,
                "substantive_answer",
                "With reference to the averments made in the Petition",
            )
            text = _join_sentences(
                [f"{opener}, I say that {_as_continuation(facts[0])}", *facts[1:]]
            )

        return MappedBodyParagraph(
            number=number,
            move=point.move,
            text=text,
            source_facts=facts,
            source_point_number=point.point_number,
            exhibit=point.exhibit if point.move is ReplyMoveType.DOCUMENT_RELIED_UPON else None,
            evidence=evidence,
        )

    def _map_prayer(self, case: CaseDetails, template: AffidavitTemplateSchema) -> MappedPrayer:
        proceeding = _proceeding_display(case.proceeding_type)
        intro = _phrase(
            template,
            "prayer",
            "I therefore respectfully pray that this Hon'ble Court may be pleased to:",
        )
        letters = template.prayer_lettering.letters or ["a", "b", "c"]
        clauses: list[MappedPrayerClause] = []
        for index, raw in enumerate(template.prayer_lettering.standard_clauses):
            letter = letters[index] if index < len(letters) else chr(ord("a") + index)
            clause_text = raw.replace("[PROCEEDING TYPE]", proceeding)
            clauses.append(MappedPrayerClause(letter=letter, text=clause_text))
        if not clauses:
            clauses.append(
                MappedPrayerClause(
                    letter="a",
                    text=f"dismiss the present {proceeding} with costs",
                )
            )
        return MappedPrayer(
            heading=template.prayer_lettering.heading,
            introductory_phrase=intro,
            clauses=clauses,
        )

    def _map_jurat(self, attestation: AttestationDetails) -> MappedJurat:
        verb_past = attestation.verification_verb.jurat_past_tense
        date_prose = _date_prose(attestation.date)
        date_ordinal = _date_ordinal(attestation.date)
        text = f"{verb_past} at {attestation.place}\nOn this {date_ordinal}"
        return MappedJurat(
            place=attestation.place,
            date=date_prose,
            date_ordinal=date_ordinal,
            verb_past=verb_past,
            text=text,
        )

    def _map_verification(
        self,
        deponent: DeponentDetails,
        attestation: AttestationDetails,
        paragraph_count: int,
        template: AffidavitTemplateSchema,
    ) -> MappedVerification:
        date_prose = _date_prose(attestation.date)
        date_ordinal = _date_ordinal(attestation.date)
        true_correct = _phrase(
            template,
            "verification",
            "true and correct to my knowledge and belief",
        )
        concealed = _phrase(
            template,
            "verification",
            "nothing material has been concealed therefrom",
        )
        text = (
            f"I, {deponent.name}, the Deponent above named, do hereby verify that the "
            f"contents of paragraphs 1 to {paragraph_count} and the Prayer above are "
            f"{true_correct} and that {concealed}. "
            f"Verified at {attestation.place} on this {date_ordinal}."
        )
        return MappedVerification(
            deponent_name=deponent.name,
            paragraph_start=1,
            paragraph_end=paragraph_count,
            includes_prayer=True,
            place=attestation.place,
            date=date_prose,
            date_ordinal=date_ordinal,
            text=text,
        )

    def _map_advocate(
        self,
        advocate: AdvocateDetails | None,
        respondent_label: str,
    ) -> MappedAdvocateBlock | None:
        if advocate is None:
            return None
        acting_for = advocate.acting_for.strip()
        text = f"{advocate.firm}\nAdvocates for the {acting_for.rstrip('.')}."
        return MappedAdvocateBlock(firm=advocate.firm, acting_for=acting_for, text=text)


def map_affidavit_content(
    case_input: AffidavitCaseInput,
    template: AffidavitTemplateSchema | None = None,
) -> MappedAffidavitContent:
    return AffidavitContentMapper().map(case_input, template=template)


def _case_number_line(case: CaseDetails) -> str:
    proceeding = case.proceeding_type.strip().upper()
    return f"{proceeding} NO. {case.case_number} OF {case.year}"


def _proceeding_display(proceeding_type: str) -> str:
    stripped = proceeding_type.strip()
    return stripped.title() if stripped.isupper() else stripped


def _respondent_label(number: int) -> str:
    return f"Respondent No. {number}"


def _deponent_verb_clause(verb: VerificationVerb, template: AffidavitTemplateSchema) -> str:
    if verb is VerificationVerb.SOLEMNLY_AFFIRM:
        return _phrase(template, "deponent_clause", "do hereby solemnly affirm and state as under:")
    return "do hereby swear and affirm and state as under:"


def _phrase(template: AffidavitTemplateSchema, context: str, fallback: str) -> str:
    candidates = [rule.phrase for rule in template.fixed_phrases if rule.context == context]
    for phrase in candidates:
        if phrase == fallback:
            return phrase
    for phrase in candidates:
        if fallback.rstrip(":") in phrase or phrase.rstrip(":") in fallback:
            if fallback.endswith(":") and not phrase.endswith(":"):
                return phrase.rstrip(":") + ":"
            return phrase
    return fallback


def _identity_text(
    deponent_clause: MappedDeponentClause,
    proceeding: str,
    facts: list[str],
    template: AffidavitTemplateSchema,
) -> str:
    if deponent_clause.capacity is DeponentCapacity.ORGANISATION_OFFICER:
        role = (
            f"the {deponent_clause.designation} of the "
            f"{_respondent_label(deponent_clause.answering_respondent_number)}"
        )
        if deponent_clause.organisation:
            role += f", {deponent_clause.organisation},"
    else:
        role = f"the {_respondent_label(deponent_clause.answering_respondent_number)}"

    acquainted = _phrase(
        template,
        "identity_and_perusal",
        "am well acquainted with the facts and circumstances of the case",
    )
    competent = _phrase(
        template,
        "identity_and_perusal",
        "am competent to affirm this Affidavit in Reply",
    )
    opening = (
        f"I say that I am {role} in the above {proceeding} and {acquainted}."
    )
    return _join_sentences([opening, *facts, f"I {competent}."])


def _closing_text(proceeding: str, template: AffidavitTemplateSchema) -> str:
    premises = _phrase(template, "closing", "In the premises aforesaid")
    dismissed = _phrase(template, "closing", "deserves to be dismissed with costs")
    return f"{premises}, I say that the {proceeding} {dismissed}."


def _as_continuation(sentence: str) -> str:
    """Lowercase a leading 'The' so the fact can follow 'I say that'."""
    stripped = sentence.strip().rstrip(".")
    if stripped.startswith("The "):
        return "the " + stripped[4:]
    return stripped


def _join_sentences(parts: list[str]) -> str:
    sentences: list[str] = []
    for part in parts:
        cleaned = re.sub(r"\s+", " ", part).strip()
        if not cleaned:
            continue
        if not cleaned.endswith((".", ":", ";")):
            cleaned += "."
        sentences.append(cleaned)
    return " ".join(sentences)


def _date_prose(value: Date | str) -> str:
    if isinstance(value, Date):
        return f"{value.day} {calendar.month_name[value.month]} {value.year}"
    return str(value).strip()


def _date_ordinal(value: Date | str) -> str:
    prose = _date_prose(value)
    match = re.match(r"(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+)\s+(\d{4})$", prose)
    if not match:
        return prose
    day = int(match.group(1))
    month = match.group(2)
    year = match.group(3)
    return f"{day}{_ordinal_suffix(day)} day of {month} {year}"


def _ordinal_suffix(day: int) -> str:
    if 10 <= day % 100 <= 20:
        return "th"
    return {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
