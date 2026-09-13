"""Deterministic evaluation of a generated affidavit document."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from src.content_mapper import MappedAffidavitContent
from src.schemas import (
    AffidavitCaseInput,
    EvaluationIssue,
    EvaluationResult,
    EvaluationSeverity,
)


REQUIRED_SECTIONS = [
    "forum",
    "jurisdiction",
    "case_number",
    "cause_title",
    "affidavit_title",
    "deponent_clause",
    "body_paragraphs",
    "prayer",
    "jurat",
    "verification",
]


class AffidavitEvaluator:
    """Run deterministic checks against a generated affidavit."""

    def evaluate(
        self,
        content: MappedAffidavitContent,
        case_input: AffidavitCaseInput,
        docx_text: str | None = None,
        reference_text: str | None = None,
    ) -> EvaluationResult:
        """Evaluate generated content against the extracted case information."""
        issues: list[EvaluationIssue] = []
        full_text = content.all_text()

        # A. Entity accuracy
        issues.extend(self._check_entity_accuracy(full_text, case_input))

        # B. Completeness
        issues.extend(self._check_completeness(content, full_text))

        # C. Structure
        issues.extend(self._check_structure(content))

        # D. Consistency
        issues.extend(self._check_consistency(content, case_input, full_text))

        # E. Template fidelity
        issues.extend(self._check_template_fidelity(content, full_text))

        # F. Hallucination / forbidden sample data
        issues.extend(self._check_hallucination(full_text, case_input, reference_text))

        # Calculate overall score
        total = len(issues)
        if total == 0:
            overall_score = 1.0
        else:
            passed_count = sum(1 for i in issues if i.score is not None and i.score >= 1.0)
            failed_count = total - passed_count
            overall_score = round(passed_count / total, 4) if total > 0 else 1.0

        passed = all(
            i.score is not None and i.score >= 1.0
            for i in issues
            if i.severity in (EvaluationSeverity.CRITICAL, EvaluationSeverity.MAJOR)
        )

        return EvaluationResult(
            issues=issues,
            overall_score=overall_score,
            passed=passed,
            evidence=content.evidence,
        )

    # A. Entity accuracy

    def _check_entity_accuracy(
        self, text: str, case_input: AffidavitCaseInput
    ) -> list[EvaluationIssue]:
        issues: list[EvaluationIssue] = []
        text_lower = text.lower()

        expected_entities = {
            "court": case_input.case.court,
            "jurisdiction": case_input.case.jurisdiction_type,
            "proceeding_type": case_input.case.proceeding_type,
            "case_number": case_input.case.case_number,
            "year": str(case_input.case.year),
            "petitioner": case_input.case.petitioner.name,
            **{
                f"respondent_{respondent.respondent_number}": respondent.name
                for respondent in case_input.case.respondents
            },
            "deponent": case_input.deponent.name,
            "designation": case_input.deponent.designation,
            "organisation": case_input.deponent.organisation,
            "answering_respondent": _respondent_label(
                case_input.case.answering_respondent_number
            ),
        }

        for key, expected in expected_entities.items():
            if not expected:
                continue
            found = expected.lower() in text_lower
            issues.append(
                EvaluationIssue(
                    dimension="entity_accuracy",
                    score=1.0 if found else 0.0,
                    issue=None if found else f"Expected entity '{key}' not found: '{expected}'",
                    severity=EvaluationSeverity.CRITICAL if not found else EvaluationSeverity.INFO,
                    expected_value=expected,
                    actual_value="found" if found else "missing",
                    explanation=f"Check for entity: {key}",
                )
            )
        return issues

    # B. Completeness
    
    def _check_completeness(self, content: MappedAffidavitContent, text: str) -> list[EvaluationIssue]:
        issues: list[EvaluationIssue] = []

        checks = {
            "forum": bool(content.forum_heading),
            "jurisdiction": bool(content.jurisdiction),
            "case_number": bool(content.case_number_line),
            "cause_title": bool(content.cause_title and content.cause_title.petitioner),
            "affidavit_title": bool(content.affidavit_title),
            "deponent_clause": bool(content.deponent_clause and content.deponent_clause.text),
            "body_paragraphs": len(content.body_paragraphs) > 0,
            "prayer": bool(content.prayer and content.prayer.clauses),
            "jurat": bool(content.jurat and content.jurat.text),
            "verification": bool(content.verification and content.verification.text),
        }

        for section, present in checks.items():
            issues.append(
                EvaluationIssue(
                    dimension="completeness",
                    score=1.0 if present else 0.0,
                    issue=None if present else f"Missing required section: {section}",
                    severity=EvaluationSeverity.CRITICAL if not present else EvaluationSeverity.INFO,
                    expected_value=section,
                    actual_value="present" if present else "missing",
                    explanation=f"Section completeness check: {section}",
                )
            )
        return issues

    # C. Structure

    def _check_structure(self, content: MappedAffidavitContent) -> list[EvaluationIssue]:
        issues: list[EvaluationIssue] = []

        # Exactly 7 numbered body paragraphs
        para_count = len(content.body_paragraphs)
        issues.append(
            EvaluationIssue(
                dimension="structure",
                score=1.0 if para_count == 7 else 0.0,
                issue=None if para_count == 7 else f"Expected 7 body paragraphs, found {para_count}",
                severity=EvaluationSeverity.CRITICAL if para_count != 7 else EvaluationSeverity.INFO,
                expected_value="7",
                actual_value=str(para_count),
                explanation="Body paragraph count check",
            )
        )

        # Numbering 1 through 7
        numbers = [p.number for p in content.body_paragraphs]
        expected_nums = list(range(1, 8))
        correct_numbering = numbers == expected_nums
        issues.append(
            EvaluationIssue(
                dimension="structure",
                score=1.0 if correct_numbering else 0.0,
                issue=None if correct_numbering else f"Expected numbering {expected_nums}, found {numbers}",
                severity=EvaluationSeverity.CRITICAL if not correct_numbering else EvaluationSeverity.INFO,
                expected_value=str(expected_nums),
                actual_value=str(numbers),
                explanation="Paragraph numbering sequence check",
            )
        )

        # Prayer uses (a), (b), etc.
        prayer_letters = [c.letter for c in content.prayer.clauses]
        has_lettered = all(c.isalpha() and len(c) == 1 for c in prayer_letters)
        issues.append(
            EvaluationIssue(
                dimension="structure",
                score=1.0 if has_lettered else 0.0,
                issue=None if has_lettered else "Prayer clauses not properly lettered",
                severity=EvaluationSeverity.MAJOR if not has_lettered else EvaluationSeverity.INFO,
                expected_value="(a), (b), (c), ...",
                actual_value=str(prayer_letters),
                explanation="Prayer lettering check",
            )
        )

        # Prayer not counted as body paragraph
        body_moves = [p.move.value for p in content.body_paragraphs]
        prayer_in_body = "prayer_to_dismiss" in body_moves
        issues.append(
            EvaluationIssue(
                dimension="structure",
                score=1.0 if not prayer_in_body else 0.0,
                issue=None if not prayer_in_body else "Prayer incorrectly included as body paragraph",
                severity=EvaluationSeverity.MAJOR if prayer_in_body else EvaluationSeverity.INFO,
                expected_value="Prayer separate from body",
                actual_value="prayer in body" if prayer_in_body else "prayer separate",
                explanation="Prayer separation check",
            )
        )

        return issues

    # D. Consistency

    def _check_consistency(
        self,
        content: MappedAffidavitContent,
        case_input: AffidavitCaseInput,
        text: str,
    ) -> list[EvaluationIssue]:
        issues: list[EvaluationIssue] = []

        # Jurat says "Solemnly affirmed"
        jurat_affirmed = "Solemnly affirmed" in content.jurat.text
        issues.append(
            EvaluationIssue(
                dimension="consistency",
                score=1.0 if jurat_affirmed else 0.0,
                issue=None if jurat_affirmed else "Jurat does not say 'Solemnly affirmed'",
                severity=EvaluationSeverity.CRITICAL if not jurat_affirmed else EvaluationSeverity.INFO,
                expected_value="Solemnly affirmed",
                actual_value=content.jurat.verb_past,
                explanation="Jurat verb check",
            )
        )

        # Verification refers to paragraphs 1 to 7
        verif_range = "paragraphs 1 to 7" in content.verification.text
        issues.append(
            EvaluationIssue(
                dimension="consistency",
                score=1.0 if verif_range else 0.0,
                issue=None if verif_range else "Verification does not refer to 'paragraphs 1 to 7'",
                severity=EvaluationSeverity.CRITICAL if not verif_range else EvaluationSeverity.INFO,
                expected_value="paragraphs 1 to 7",
                actual_value=content.verification.text[:100],
                explanation="Verification range check",
            )
        )

        # Verification includes Prayer
        verif_prayer = "Prayer" in content.verification.text
        issues.append(
            EvaluationIssue(
                dimension="consistency",
                score=1.0 if verif_prayer else 0.0,
                issue=None if verif_prayer else "Verification does not mention Prayer",
                severity=EvaluationSeverity.MAJOR if not verif_prayer else EvaluationSeverity.INFO,
                expected_value="Prayer mentioned",
                actual_value="found" if verif_prayer else "missing",
                explanation="Verification Prayer reference check",
            )
        )

        # The extracted attestation place appears in both repeated blocks.
        place = case_input.attestation.place
        place_jurat = place.casefold() in content.jurat.text.casefold() or place.casefold() in content.jurat.place.casefold()
        place_verif = place.casefold() in content.verification.text.casefold() or place.casefold() in content.verification.place.casefold()
        issues.append(
            EvaluationIssue(
                dimension="consistency",
                score=1.0 if (place_jurat and place_verif) else 0.0,
                issue=None if (place_jurat and place_verif) else f"Attestation place '{place}' missing from jurat or verification",
                severity=EvaluationSeverity.MAJOR if not (place_jurat and place_verif) else EvaluationSeverity.INFO,
                expected_value=f"{place} in both jurat and verification",
                actual_value=f"jurat={'found' if place_jurat else 'missing'}, verification={'found' if place_verif else 'missing'}",
                explanation="Place consistency check",
            )
        )

        # The extracted attestation date appears in both repeated blocks.
        date_str = _date_prose(case_input.attestation.date)
        date_in_jurat = date_str.casefold() in content.jurat.date.casefold()
        date_in_verif = date_str.casefold() in content.verification.date.casefold()
        issues.append(
            EvaluationIssue(
                dimension="consistency",
                score=1.0 if (date_in_jurat and date_in_verif) else 0.0,
                issue=None if (date_in_jurat and date_in_verif) else f"Date '{date_str}' missing from jurat or verification",
                severity=EvaluationSeverity.MAJOR if not (date_in_jurat and date_in_verif) else EvaluationSeverity.INFO,
                expected_value=date_str,
                actual_value=f"jurat='{content.jurat.date}', verification='{content.verification.date}'",
                explanation="Date consistency check",
            )
        )

        # The extracted answering respondent is consistent across sections.
        respondent_text = _respondent_label(case_input.case.answering_respondent_number)
        respondent_in_title = respondent_text.casefold() in content.affidavit_title.casefold()
        respondent_in_deponent = respondent_text.casefold() in content.deponent_clause.text.casefold()
        issues.append(
            EvaluationIssue(
                dimension="consistency",
                score=1.0 if (respondent_in_title and respondent_in_deponent) else 0.0,
                issue=None if (respondent_in_title and respondent_in_deponent) else f"{respondent_text} inconsistent across sections",
                severity=EvaluationSeverity.MAJOR if not (respondent_in_title and respondent_in_deponent) else EvaluationSeverity.INFO,
                expected_value=respondent_text,
                actual_value=f"title={'found' if respondent_in_title else 'missing'}, deponent={'found' if respondent_in_deponent else 'missing'}",
                explanation="Respondent consistency check",
            )
        )

        return issues

    # E. Template fidelity

    def _check_template_fidelity(self, content: MappedAffidavitContent, text: str) -> list[EvaluationIssue]:
        issues: list[EvaluationIssue] = []

        # Check required headings exist and in order
        required_headings = [
            ("IN THE HIGH COURT", "forum_heading"),
            ("JURISDICTION", "jurisdiction"),
            ("WRIT PETITION NO.", "case_number"),
            ("AFFIDAVIT IN REPLY", "affidavit_title"),
            ("PRAYER", "prayer_heading"),
            ("VERIFICATION", "verification_heading"),
        ]

        text_upper = text.upper()
        last_pos = -1
        for heading, label in required_headings:
            pos = text_upper.find(heading)
            found = pos >= 0
            in_order = pos > last_pos if found else False

            issues.append(
                EvaluationIssue(
                    dimension="template_fidelity",
                    score=1.0 if (found and in_order) else 0.0,
                    issue=None if (found and in_order) else f"Heading '{heading}' {'missing' if not found else 'out of order'}",
                    severity=EvaluationSeverity.MAJOR if not (found and in_order) else EvaluationSeverity.INFO,
                    expected_value=heading,
                    actual_value="found and ordered" if (found and in_order) else ("missing" if not found else "out of order"),
                    explanation=f"Template heading check: {label}",
                )
            )
            if found:
                last_pos = pos

        # Check VERSUS appears
        versus_found = "VERSUS" in text_upper
        issues.append(
            EvaluationIssue(
                dimension="template_fidelity",
                score=1.0 if versus_found else 0.0,
                issue=None if versus_found else "VERSUS not found in cause title",
                severity=EvaluationSeverity.MAJOR if not versus_found else EvaluationSeverity.INFO,
                expected_value="VERSUS",
                actual_value="found" if versus_found else "missing",
                explanation="VERSUS marker check",
            )
        )

        # Check deponent clause verb
        verb_found = "do hereby solemnly affirm and state as under" in text.lower()
        issues.append(
            EvaluationIssue(
                dimension="template_fidelity",
                score=1.0 if verb_found else 0.0,
                issue=None if verb_found else "Deponent clause missing standard verb phrase",
                severity=EvaluationSeverity.MAJOR if not verb_found else EvaluationSeverity.INFO,
                expected_value="do hereby solemnly affirm and state as under",
                actual_value="found" if verb_found else "missing",
                explanation="Deponent clause verb check",
            )
        )

        # Check exhibit reference
        exhibit_found = "EXHIBIT-'A'" in text or "EXHIBIT-'A'" in text
        issues.append(
            EvaluationIssue(
                dimension="template_fidelity",
                score=1.0 if exhibit_found else 0.0,
                issue=None if exhibit_found else "EXHIBIT-'A' reference not found",
                severity=EvaluationSeverity.MINOR if not exhibit_found else EvaluationSeverity.INFO,
                expected_value="EXHIBIT-'A'",
                actual_value="found" if exhibit_found else "missing",
                explanation="Exhibit reference check",
            )
        )

        return issues

    # F. Hallucination / forbidden sample data

    def _check_hallucination(
        self,
        text: str,
        case_input: AffidavitCaseInput,
        reference_text: str | None,
    ) -> list[EvaluationIssue]:
        issues: list[EvaluationIssue] = []
        text_lower = text.lower()

        forbidden_values = _reference_case_values(reference_text, case_input)
        if not forbidden_values:
            return [
                EvaluationIssue(
                    dimension="hallucination",
                    score=1.0,
                    severity=EvaluationSeverity.INFO,
                    expected_value="reference-specific values unavailable",
                    actual_value="not checked",
                    explanation="Reference sample leakage check",
                )
            ]

        for forbidden in forbidden_values:
            leaked = forbidden.lower() in text_lower
            issues.append(
                EvaluationIssue(
                    dimension="hallucination",
                    score=1.0 if not leaked else 0.0,
                    issue=None if not leaked else f"Forbidden sample data leaked: '{forbidden}'",
                    severity=EvaluationSeverity.CRITICAL if leaked else EvaluationSeverity.INFO,
                    expected_value="absent",
                    actual_value="leaked" if leaked else "absent",
                    explanation=f"Hallucination check for: {forbidden}",
                )
            )
        return issues


def evaluate_affidavit(
    content: MappedAffidavitContent,
    case_input: AffidavitCaseInput,
    docx_text: str | None = None,
    reference_text: str | None = None,
) -> EvaluationResult:
    """Convenience wrapper around AffidavitEvaluator.evaluate."""
    return AffidavitEvaluator().evaluate(
        content,
        case_input,
        docx_text=docx_text,
        reference_text=reference_text,
    )


def _respondent_label(number: int) -> str:
    return f"Respondent No. {number}"


def _date_prose(value: object) -> str:
    if hasattr(value, "day") and hasattr(value, "month") and hasattr(value, "year"):
        import calendar

        return f"{value.day} {calendar.month_name[value.month]} {value.year}"
    return str(value).strip()


def _reference_case_values(
    reference_text: str | None,
    case_input: AffidavitCaseInput,
) -> list[str]:
    """Extract case-like values from the reference document, excluding this case."""
    if not reference_text:
        return []

    candidates: list[str] = []
    patterns = [
        r"(?im)^\s*([A-Z][A-Za-z .&'-]+),\s*(?:Age|residing)",
        r"(?i)\bI,\s*([^,\n]+),",
        r"(?i)\b(?:WRIT PETITION|CIVIL APPEAL)\s+NO\.\s*([^\s]+)\s+OF\s+(\d{4})",
        r"(?i)\bdated\s+([0-9]{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]+\s+\d{4})",
        r"(?im)^\s*([A-Z][A-Z &]+)\s*$\n\s*Advocates for",
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, reference_text):
            candidates.append(" ".join(group for group in match.groups() if group))

    current_values = {
        case_input.case.court,
        case_input.case.jurisdiction_type,
        case_input.case.case_number,
        str(case_input.case.year),
        case_input.case.petitioner.name,
        *(respondent.name for respondent in case_input.case.respondents),
        case_input.deponent.name,
        case_input.deponent.designation or "",
        case_input.deponent.organisation or "",
        case_input.attestation.place,
        _date_prose(case_input.attestation.date),
        case_input.advocate.firm if case_input.advocate else "",
    }
    current_lower = {value.casefold() for value in current_values if value}
    unique: list[str] = []
    for candidate in candidates:
        candidate = candidate.strip()
        if len(candidate) < 3 or candidate.casefold() in current_lower:
            continue
        if candidate.casefold() not in {item.casefold() for item in unique}:
            unique.append(candidate)
    return unique


def write_evaluation_report(
    result: EvaluationResult,
    output_path: str | Path,
) -> Path:
    """Write a Markdown evaluation report to disk."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    lines: list[str] = []
    lines.append("# Affidavit Evaluation Report\n")
    lines.append(f"Overall Score:{result.overall_score:.2%}\n")
    lines.append(f"Passed: {'YES' if result.passed else 'NO'}\n")
    lines.append("---\n")

    # Group issues by dimension
    dimensions: dict[str, list[EvaluationIssue]] = {}
    for issue in result.issues:
        dimensions.setdefault(issue.dimension, []).append(issue)

    for dim, dim_issues in dimensions.items():
        dim_passed = sum(1 for i in dim_issues if i.score is not None and i.score >= 1.0)
        dim_total = len(dim_issues)
        dim_score = dim_passed / dim_total if dim_total > 0 else 1.0

        lines.append(f"## {dim.replace('_', ' ').title()}")
        lines.append(f"Score:{dim_score:.2%} ({dim_passed}/{dim_total} checks passed)\n")

        for i in dim_issues:
            status = "✓" if (i.score is not None and i.score >= 1.0) else "✗"
            lines.append(f"- {status} {i.explanation or i.dimension}")
            if i.issue:
                lines.append(f"  - Issue: {i.issue}")
            if i.expected_value and i.actual_value and i.score is not None and i.score < 1.0:
                lines.append(f"  - Expected: {i.expected_value}")
                lines.append(f"  - Actual: {i.actual_value}")

        lines.append("")

    lines.append("---\n")

    # Evidence Mapping section
    if result.evidence:
        lines.append("## Evidence Mapping\n")
        lines.append(
            "Every major generated field is traced back to its source document, "
            "page number, and section:\n"
        )
        lines.append("| Generated Field | Source Document | Page | Source Section | Evidence |")
        lines.append("| :--- | :--- | :---: | :--- | :--- |")

        ordered_keys = [
            ("court", "Court"),
            ("jurisdiction", "Jurisdiction"),
            ("proceeding_type", "Proceeding Type"),
            ("case_number", "Case Number"),
            ("year", "Year"),
            ("petitioner", "Petitioner"),
            ("respondents", "Respondents"),
            ("answering_respondent", "Answering Respondent"),
            ("deponent", "Deponent"),
            ("designation", "Designation"),
            ("organisation", "Organisation"),
            ("deponent_capacity", "Deponent Capacity"),
            ("verification_verb", "Verification Verb"),
            ("reply_point_1", "Reply Paragraph 1"),
            ("reply_point_2", "Reply Paragraph 2"),
            ("reply_point_3", "Reply Paragraph 3"),
            ("reply_point_4", "Reply Paragraph 4"),
            ("reply_point_5", "Reply Paragraph 5"),
            ("reply_point_6", "Reply Paragraph 6"),
            ("reply_paragraph_7", "Reply Paragraph 7 (Closing)"),
            ("exhibits", "Exhibits"),
            ("attestation_place", "Attestation Place"),
            ("attestation_date", "Attestation Date"),
            ("advocate_firm", "Advocate Firm"),
            ("advocate_acting_for", "Advocate Acting For"),
        ]

        seen_keys = set()
        for key, display_label in ordered_keys:
            ev = result.evidence.get(key)
            if ev:
                seen_keys.add(key)
                page_str = str(ev.source_page) if ev.source_page is not None else "-"
                sec_str = (ev.source_section or "-").replace("|", "/")
                snippet = ev.source_text.replace("\n", " ").replace("|", "/")
                if len(snippet) > 85:
                    snippet = snippet[:82] + "..."
                lines.append(f"| {display_label} | {ev.source_document} | {page_str} | {sec_str} | {snippet} |")

        for key, ev in result.evidence.items():
            if key not in seen_keys and not key.startswith("reply_paragraph_"):
                page_str = str(ev.source_page) if ev.source_page is not None else "-"
                sec_str = (ev.source_section or "-").replace("|", "/")
                snippet = ev.source_text.replace("\n", " ").replace("|", "/")
                if len(snippet) > 85:
                    snippet = snippet[:82] + "..."
                label = ev.field_name or key.replace("_", " ").title()
                lines.append(f"| {label} | {ev.source_document} | {page_str} | {sec_str} | {snippet} |")

        lines.append("")
        lines.append("---\n")

    lines.append(f"Total checks: {len(result.issues)}\n")

    output_path.write_text("\n".join(lines), encoding="utf-8")
    return output_path
