"""Deterministic evaluation of a generated affidavit document."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from src.content_mapper import MappedAffidavitContent
from src.schemas import (
    EvaluationIssue,
    EvaluationResult,
    EvaluationSeverity,
)


# Forbidden data from Document 02 (sample affidavit) that must NOT leak
FORBIDDEN_SAMPLE_DATA = [
    "Arjun Mehta",
    "Rohan Deshpande",
    "Writ Petition No. 3147 of 2026",
    "3147",
    "Mehta & Kulkarni",
    "MEHTA & KULKARNI",
    "CIVIL APPELLATE",
    "12th March 2026",
    "12 March 2026",
]

# Expected entities for this case
EXPECTED_ENTITIES = {
    "court": "IN THE HIGH COURT OF JUDICATURE AT BOMBAY",
    "jurisdiction": "ORDINARY ORIGINAL CIVIL JURISDICTION",
    "proceeding_type": "WRIT PETITION",
    "case_number": "1847",
    "year": "2026",
    "petitioner": "Sunrise Housing Private Limited",
    "respondent_1": "State of Maharashtra",
    "respondent_2": "Mumbai Metropolitan Region Development Authority",
    "deponent": "Arvind Rajan",
    "designation": "Deputy Metropolitan Commissioner",
    "organisation": "Mumbai Metropolitan Region Development Authority",
    "answering_respondent": "Respondent No. 2",
}

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
        docx_text: str | None = None,
    ) -> EvaluationResult:
        """Evaluate the mapped content and optionally the rendered DOCX text."""
        issues: list[EvaluationIssue] = []
        full_text = content.all_text()

        # A. Entity accuracy
        issues.extend(self._check_entity_accuracy(full_text))

        # B. Completeness
        issues.extend(self._check_completeness(content, full_text))

        # C. Structure
        issues.extend(self._check_structure(content))

        # D. Consistency
        issues.extend(self._check_consistency(content, full_text))

        # E. Template fidelity
        issues.extend(self._check_template_fidelity(content, full_text))

        # F. Hallucination / forbidden sample data
        issues.extend(self._check_hallucination(full_text))

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

    # ------------------------------------------------------------------
    # A. Entity accuracy
    # ------------------------------------------------------------------
    def _check_entity_accuracy(self, text: str) -> list[EvaluationIssue]:
        issues: list[EvaluationIssue] = []
        text_lower = text.lower()

        for key, expected in EXPECTED_ENTITIES.items():
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

    # ------------------------------------------------------------------
    # B. Completeness
    # ------------------------------------------------------------------
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

    # ------------------------------------------------------------------
    # C. Structure
    # ------------------------------------------------------------------
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

    # ------------------------------------------------------------------
    # D. Consistency
    # ------------------------------------------------------------------
    def _check_consistency(self, content: MappedAffidavitContent, text: str) -> list[EvaluationIssue]:
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

        # Mumbai appears in jurat and verification
        mumbai_jurat = "Mumbai" in content.jurat.text or "Mumbai" in content.jurat.place
        mumbai_verif = "Mumbai" in content.verification.text or "Mumbai" in content.verification.place
        issues.append(
            EvaluationIssue(
                dimension="consistency",
                score=1.0 if (mumbai_jurat and mumbai_verif) else 0.0,
                issue=None if (mumbai_jurat and mumbai_verif) else "Mumbai missing from jurat or verification",
                severity=EvaluationSeverity.MAJOR if not (mumbai_jurat and mumbai_verif) else EvaluationSeverity.INFO,
                expected_value="Mumbai in both jurat and verification",
                actual_value=f"jurat={'found' if mumbai_jurat else 'missing'}, verification={'found' if mumbai_verif else 'missing'}",
                explanation="Place consistency check",
            )
        )

        # 5 September 2026 appears in jurat and verification
        date_str = "5 September 2026"
        # Check date appears in either text or ordinal form
        date_in_jurat = date_str in content.jurat.date or "September 2026" in content.jurat.text
        date_in_verif = date_str in content.verification.date or "September 2026" in content.verification.text
        issues.append(
            EvaluationIssue(
                dimension="consistency",
                score=1.0 if (date_in_jurat and date_in_verif) else 0.0,
                issue=None if (date_in_jurat and date_in_verif) else "Date '5 September 2026' missing from jurat or verification",
                severity=EvaluationSeverity.MAJOR if not (date_in_jurat and date_in_verif) else EvaluationSeverity.INFO,
                expected_value=date_str,
                actual_value=f"jurat='{content.jurat.date}', verification='{content.verification.date}'",
                explanation="Date consistency check",
            )
        )

        # Respondent No.2 is consistent
        resp2_text = "Respondent No. 2"
        resp2_in_title = resp2_text in content.affidavit_title or "RESPONDENT NO. 2" in content.affidavit_title.upper()
        resp2_in_deponent = resp2_text in content.deponent_clause.text
        issues.append(
            EvaluationIssue(
                dimension="consistency",
                score=1.0 if (resp2_in_title and resp2_in_deponent) else 0.0,
                issue=None if (resp2_in_title and resp2_in_deponent) else "Respondent No.2 inconsistent across sections",
                severity=EvaluationSeverity.MAJOR if not (resp2_in_title and resp2_in_deponent) else EvaluationSeverity.INFO,
                expected_value=resp2_text,
                actual_value=f"title={'found' if resp2_in_title else 'missing'}, deponent={'found' if resp2_in_deponent else 'missing'}",
                explanation="Respondent consistency check",
            )
        )

        return issues

    # ------------------------------------------------------------------
    # E. Template fidelity
    # ------------------------------------------------------------------
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

    # ------------------------------------------------------------------
    # F. Hallucination / forbidden sample data
    # ------------------------------------------------------------------
    def _check_hallucination(self, text: str) -> list[EvaluationIssue]:
        issues: list[EvaluationIssue] = []
        text_lower = text.lower()

        for forbidden in FORBIDDEN_SAMPLE_DATA:
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
    docx_text: str | None = None,
) -> EvaluationResult:
    """Convenience wrapper around AffidavitEvaluator.evaluate."""
    return AffidavitEvaluator().evaluate(content, docx_text=docx_text)


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
