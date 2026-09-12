"""Pre-generation document-role validation.

Validates that each uploaded PDF corresponds to its intended role (format guide,
affidavit sample, or case information) by inspecting document content — NOT filenames.

Reuses existing TemplateAnalyzer and CaseInformationExtractor logic.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from src.content_mapper import MappedAffidavitContent
from src.schemas import AffidavitCaseInput

from src.document_parser import PDFDocumentParser, ParsedDocument
from src.entity_extractor import CaseExtractionError, CaseInformationExtractor
from src.template_analyzer import (
    FORMAT_GUIDE_SECTION_HINTS,
    SECTION_MARKERS,
    _flatten_text,
    _normalize_text,
)
from src.schemas import AffidavitSection

log = logging.getLogger(__name__)


# Result model



class DocumentValidationResult(BaseModel):
    """Outcome of a single-document role check."""

    model_config = ConfigDict(extra="forbid")

    valid: bool
    document_role: str = Field(
        ...,
        description="Human-readable label for the expected document role.",
    )
    message: str = Field(
        ...,
        description="Primary user-facing message (shown on failure; brief on success).",
    )
    details: list[str] = Field(
        default_factory=list,
        description="Optional list of more specific failure reasons.",
    )


class ValidationSuite(BaseModel):
    """Aggregated validation results for all three required documents."""

    model_config = ConfigDict(extra="forbid")

    format_guide: DocumentValidationResult
    sample_affidavit: DocumentValidationResult
    case_information: DocumentValidationResult

    @property
    def all_valid(self) -> bool:
        return (
            self.format_guide.valid
            and self.sample_affidavit.valid
            and self.case_information.valid
        )



# Minimum signal thresholds (tuned for robustness, not perfection)

_FORMAT_GUIDE_MIN_HINTS = 7

# Section markers used to recognise a finished affidavit sample document.
_SAMPLE_REQUIRED_SECTIONS: list[AffidavitSection] = [
    AffidavitSection.FORUM_HEADING,
    AffidavitSection.CAUSE_TITLE,
    AffidavitSection.AFFIDAVIT_TITLE,
    AffidavitSection.DEPONENT_CLAUSE,
    AffidavitSection.PRAYER,
    AffidavitSection.JURAT,
    AffidavitSection.VERIFICATION,
]
_SAMPLE_MIN_SECTIONS = 5  

# Labels from the Case Information PDF that indicate the document is correct.
_CASE_INFO_REQUIRED_LABELS = [
    "Court",
    "Case Number",
    "Petitioner",
    "Filed on behalf of",
    "Name",
    "Address",
]
_CASE_INFO_MIN_LABELS = 4


# Reference Path Resolution


def resolve_reference_paths(project_root: str | Path | None = None) -> tuple[Path, Path]:
    """Resolve the paths to the fixed reference files (format guide and sample affidavit).

    Searches 'reference/' first, then falls back to 'Input/'.
    Returns (format_guide_path, sample_path).
    """
    root = Path(project_root) if project_root else Path(__file__).resolve().parent.parent
    candidate_dirs = [root / "reference", root / "Input"]

    format_guide_path: Path | None = None
    sample_path: Path | None = None

    format_guide_names = [
        "01 Affidavit Format Explained.pdf",
        "01_Affidavit_format_explained.pdf",
        "01 Affidavit format explained.pdf",
        "01_Affidavit_Format_Explained.pdf",
    ]
    sample_names = [
        "02 Affidavit in Reply Sample.docx.pdf",
        "02 Affidavit in Reply Sample.pdf",
        "02_Affidavit_in_reply_sample.pdf",
        "02 Affidavit in reply sample.pdf",
        "02_Affidavit_In_Reply_Sample.pdf",
    ]

    for d in candidate_dirs:
        if not d.is_dir():
            continue
        if format_guide_path is None:
            for name in format_guide_names:
                p = d / name
                if p.exists():
                    format_guide_path = p
                    break
        if sample_path is None:
            for name in sample_names:
                p = d / name
                if p.exists():
                    sample_path = p
                    break

    default_dir = (root / "reference") if (root / "reference").exists() else (root / "Input")
    if format_guide_path is None:
        format_guide_path = default_dir / "01 Affidavit Format Explained.pdf"
    if sample_path is None:
        sample_path = default_dir / "02 Affidavit in Reply Sample.docx.pdf"

    return format_guide_path, sample_path


# Public validator


class DocumentRoleValidator:
    """Validate that each PDF plays the expected role."""

    def __init__(
        self,
        parser: PDFDocumentParser | None = None,
        format_guide_path: str | Path | None = None,
        sample_path: str | Path | None = None,
    ) -> None:
        self._parser = parser or PDFDocumentParser()
        resolved_guide, resolved_sample = resolve_reference_paths()
        self._format_guide_path = Path(format_guide_path) if format_guide_path else resolved_guide
        self._sample_path = Path(sample_path) if sample_path else resolved_sample

    # Top-level entry point

    def validate_all(
        self,
        format_guide_path: str | Path | None = None,
        sample_path: str | Path | None = None,
        case_info_path: str | Path | None = None,
    ) -> ValidationSuite:
        """Run all three role checks and return a ValidationSuite.

        Supports both:
        - validate_all(format_guide_path, sample_path, case_info_path)
        - validate_all(case_info_path) (using bundled reference files)
        """
        # If single argument provided, treat as case_info_path
        if sample_path is None and case_info_path is None and format_guide_path is not None:
            case_info_path = format_guide_path
            format_guide_path = self._format_guide_path
            sample_path = self._sample_path
        else:
            format_guide_path = Path(format_guide_path) if format_guide_path else self._format_guide_path
            sample_path = Path(sample_path) if sample_path else self._sample_path
            case_info_path = Path(case_info_path) if case_info_path else None

        # Validate format guide
        if not format_guide_path.exists():
            res_guide = DocumentValidationResult(
                valid=False,
                document_role="Affidavit Format Guide",
                message="Reference format guide file is missing from project resources.",
                details=[f"Expected file at: {format_guide_path}"],
            )
        else:
            try:
                guide_doc = self._parser.parse(format_guide_path)
                res_guide = self._validate_format_guide(guide_doc)
            except Exception as exc:  # noqa: BLE001
                res_guide = DocumentValidationResult(
                    valid=False,
                    document_role="Affidavit Format Guide",
                    message="Failed to parse Affidavit Format Guide.",
                    details=[str(exc)],
                )

        # Validate sample affidavit
        if not sample_path.exists():
            res_sample = DocumentValidationResult(
                valid=False,
                document_role="Affidavit in Reply Sample",
                message="Reference sample affidavit file is missing from project resources.",
                details=[f"Expected file at: {sample_path}"],
            )
        else:
            try:
                sample_doc = self._parser.parse(sample_path)
                res_sample = self._validate_sample_affidavit(sample_doc)
            except Exception as exc:  # noqa: BLE001
                res_sample = DocumentValidationResult(
                    valid=False,
                    document_role="Affidavit in Reply Sample",
                    message="Failed to parse Affidavit in Reply Sample.",
                    details=[str(exc)],
                )

        # Validate case information
        res_case = self.validate_case_information(case_info_path)

        return ValidationSuite(
            format_guide=res_guide,
            sample_affidavit=res_sample,
            case_information=res_case,
        )

    def validate_case_information(
        self, case_info_path: str | Path | None
    ) -> DocumentValidationResult:
        """Validate only the uploaded case information PDF without re-validating reference files."""
        if case_info_path is None or not Path(case_info_path).exists():
            return DocumentValidationResult(
                valid=False,
                document_role="Case Information",
                message="The input file is missing. Please upload the Case Information PDF.",
                details=[f"Expected file at: {case_info_path}" if case_info_path else "No path provided."],
            )
        try:
            case_doc = self._parser.parse(case_info_path)
            return self._validate_case_information(case_doc, case_info_path)
        except Exception as exc:  # noqa: BLE001
            log.warning("Failed to parse Case Information PDF: %s", exc)
            return DocumentValidationResult(
                valid=False,
                document_role="Case Information",
                message="The uploaded document is incorrect. Please upload the correct Case Information PDF.",
                details=[str(exc)],
            )

    # 1. Format guide validator

    def _validate_format_guide(self, doc: ParsedDocument) -> DocumentValidationResult:
        """Check that the document describes affidavit format sections."""
        role = "Affidavit Format Guide"
        text = _flatten_text(_normalize_text(doc.full_text)).lower()

        found = [hint for hint in FORMAT_GUIDE_SECTION_HINTS if hint.lower() in text]
        missing = [hint for hint in FORMAT_GUIDE_SECTION_HINTS if hint.lower() not in text]

        if len(found) >= _FORMAT_GUIDE_MIN_HINTS:
            return DocumentValidationResult(
                valid=True,
                document_role=role,
                message="Valid Affidavit Format Guide.",
            )

        log.warning("Format guide validation failed: missing hints %s", missing)
        return DocumentValidationResult(
            valid=False,
            document_role=role,
            message=(
                "The uploaded document does not appear to be the required "
                "Affidavit Format Guide. Please upload the correct format guide PDF."
            ),
            details=[f"Missing section description: '{h}'" for h in missing],
        )

    # 2. Sample affidavit validator

    def _validate_sample_affidavit(self, doc: ParsedDocument) -> DocumentValidationResult:
        """Check that the document is a finished Affidavit in Reply."""
        role = "Affidavit in Reply Sample"
        text = _flatten_text(_normalize_text(doc.full_text))

        detected = [
            section
            for section in _SAMPLE_REQUIRED_SECTIONS
            if any(marker in text for marker in SECTION_MARKERS.get(section, []))
        ]
        missing = [s for s in _SAMPLE_REQUIRED_SECTIONS if s not in detected]

        if len(detected) >= _SAMPLE_MIN_SECTIONS:
            return DocumentValidationResult(
                valid=True,
                document_role=role,
                message="Valid Affidavit in Reply Sample.",
            )

        log.warning("Sample affidavit validation failed: missing sections %s", missing)
        return DocumentValidationResult(
            valid=False,
            document_role=role,
            message=(
                "The uploaded document does not appear to be the required "
                "Affidavit in Reply Sample. "
                "Please upload the reference Affidavit in Reply PDF."
            ),
            details=[
                f"Missing structural element: '{s.value}'" for s in missing
            ],
        )

    # 3. Case information validator

    def _validate_case_information(
        self, doc: ParsedDocument, path: str | Path
    ) -> DocumentValidationResult:
        """Check that the document contains the required case-information fields.

        Attempts a full extraction (cheapest reuse of existing logic). On
        CaseExtractionError the specific missing-field message is surfaced. On any
        other unexpected exception a generic message is returned so tracebacks are
        never shown to the user.
        """
        role = "Case Information"

        # --- Lightweight structural pre-check (label presence) ---
        text_lower = doc.full_text.lower()
        found_labels = [lbl for lbl in _CASE_INFO_REQUIRED_LABELS if lbl.lower() in text_lower]
        if len(found_labels) < _CASE_INFO_MIN_LABELS:
            missing = [lbl for lbl in _CASE_INFO_REQUIRED_LABELS if lbl.lower() not in text_lower]
            log.warning("Case information pre-check failed: missing labels %s", missing)
            return DocumentValidationResult(
                valid=False,
                document_role=role,
                message="The uploaded document is incorrect. Please upload the correct Case Information PDF.",
                details=[f"Missing expected label: '{lbl}'" for lbl in missing],
            )

        try:
            extractor = CaseInformationExtractor(parser=self._parser)
            extractor.extract(path)
            return DocumentValidationResult(
                valid=True,
                document_role=role,
                message="Valid Case Information document.",
            )
        except CaseExtractionError as exc:
            human = _humanize_extraction_error(str(exc))
            log.warning("Case information extraction failed: %s", exc)
            return DocumentValidationResult(
                valid=False,
                document_role=role,
                message="The uploaded document is incorrect. Please upload the correct Case Information PDF.",
                details=[human],
            )
        except Exception as exc:  # noqa: BLE001
            log.exception("Unexpected error validating case information: %s", exc)
            return DocumentValidationResult(
                valid=False,
                document_role=role,
                message="The uploaded document is incorrect. Please upload the correct Case Information PDF.",
                details=[str(exc)],
            )


# Pre-generation Deterministic Validation

class PreGenCheck(BaseModel):
    """Result of a single deterministic pre-generation check."""

    model_config = ConfigDict(extra="forbid")

    check_id: str
    name: str
    passed: bool
    message: str
    details: list[str] = Field(default_factory=list)


class PreGenValidationResult(BaseModel):
    """Outcome of the pre-generation deterministic validation layer."""

    model_config = ConfigDict(extra="forbid")

    valid: bool
    checks: list[PreGenCheck] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class PreGenerationValidator:
    """Deterministic validation layer that catches errors before document generation.

    Enforces 5 critical integrity checks:
    1. Required case entities are present.
    2. Respondent number is consistent with the mapped case information.
    3. Required structural sections are available.
    4. Exhibit references are internally consistent.
    5. Verification paragraph range matches the generated body paragraph count.
    """

    def validate(
        self,
        case_input: "AffidavitCaseInput",
        mapped: "MappedAffidavitContent",
    ) -> PreGenValidationResult:
        checks: list[PreGenCheck] = [
            self._check_required_entities(case_input, mapped),
            self._check_respondent_consistency(case_input, mapped),
            self._check_required_sections(mapped),
            self._check_exhibit_consistency(case_input, mapped),
            self._check_verification_range(mapped),
        ]

        errors: list[str] = []
        for c in checks:
            if not c.passed:
                errors.append(f"{c.name}: {c.message}")
                for d in c.details:
                    errors.append(f"  - {d}")

        valid = all(c.passed for c in checks)
        return PreGenValidationResult(valid=valid, checks=checks, errors=errors)

    def _check_required_entities(
        self,
        case_input: "AffidavitCaseInput",
        mapped: "MappedAffidavitContent",
    ) -> PreGenCheck:
        """Check 1: Required case entities are present and non-empty."""
        missing = []
        c = case_input.case
        if not (c.court and c.court.strip()):
            missing.append("Court forum")
        if not (c.jurisdiction_type and c.jurisdiction_type.strip()):
            missing.append("Jurisdiction type")
        if not (c.proceeding_type and c.proceeding_type.strip()):
            missing.append("Proceeding type")
        if not (c.case_number and str(c.case_number).strip()):
            missing.append("Case number")
        if not c.year or c.year < 1900:
            missing.append("Valid year")
        if not (c.petitioner and c.petitioner.name and c.petitioner.name.strip()):
            missing.append("Petitioner name")
        if not c.respondents:
            missing.append("Respondents list")
        else:
            for idx, r in enumerate(c.respondents, start=1):
                if not (r.name and r.name.strip()):
                    missing.append(f"Respondent {idx} name")

        d = case_input.deponent
        if not (d.name and d.name.strip()):
            missing.append("Deponent name")
        if not (d.address and d.address.strip()):
            missing.append("Deponent address")
        from src.schemas import DeponentCapacity
        if d.capacity == DeponentCapacity.ORGANISATION_OFFICER:
            if not (d.designation and d.designation.strip()):
                missing.append("Deponent designation (for organisation officer)")
            if not (d.organisation and d.organisation.strip()):
                missing.append("Deponent organisation (for organisation officer)")

        att = case_input.attestation
        if not (att.place and att.place.strip()):
            missing.append("Attestation place")
        if not att.date:
            missing.append("Attestation date")

        rp = case_input.reply_points
        if not rp.points:
            missing.append("Reply points")
        else:
            for p in rp.points:
                if not p.source_facts:
                    missing.append(f"Reply point {p.point_number} source facts")

        passed = len(missing) == 0
        return PreGenCheck(
            check_id="required_entities",
            name="Required Case Entities",
            passed=passed,
            message="All required case entities are present." if passed else "Missing required case entities.",
            details=missing,
        )

    def _check_respondent_consistency(
        self,
        case_input: "AffidavitCaseInput",
        mapped: "MappedAffidavitContent",
    ) -> PreGenCheck:
        """Check 2: Respondent number is consistent across all mapped sections."""
        issues = []
        ans_num = case_input.case.answering_respondent_number
        valid_nums = [r.respondent_number for r in case_input.case.respondents]

        if ans_num not in valid_nums:
            issues.append(
                f"Answering respondent number {ans_num} does not exist in respondents list {valid_nums}."
            )

        # Deponent clause
        if mapped.deponent_clause.answering_respondent_number != ans_num:
            issues.append(
                f"Deponent clause respondent number ({mapped.deponent_clause.answering_respondent_number}) "
                f"does not match case answering respondent ({ans_num})."
            )

        resp_tag = f"Respondent No. {ans_num}"
        resp_tag_compact = f"Respondent No.{ans_num}"
        if resp_tag.lower() not in mapped.affidavit_title.lower() and resp_tag_compact.lower() not in mapped.affidavit_title.lower():
            issues.append(
                f"Affidavit title '{mapped.affidavit_title}' does not reference {resp_tag}."
            )

        if resp_tag.lower() not in mapped.deponent_clause.text.lower() and resp_tag_compact.lower() not in mapped.deponent_clause.text.lower():
            issues.append(
                f"Deponent clause text does not reference {resp_tag}."
            )

        if mapped.advocate:
            if resp_tag.lower() not in mapped.advocate.acting_for.lower() and resp_tag_compact.lower() not in mapped.advocate.acting_for.lower():
                issues.append(
                    f"Advocate block 'acting_for' ({mapped.advocate.acting_for}) does not reference {resp_tag}."
                )

        passed = len(issues) == 0
        return PreGenCheck(
            check_id="respondent_consistency",
            name="Respondent Number Consistency",
            passed=passed,
            message="Respondent number is consistent across all mapped sections." if passed else "Respondent number inconsistency detected.",
            details=issues,
        )

    def _check_required_sections(
        self,
        mapped: "MappedAffidavitContent",
    ) -> PreGenCheck:
        """Check 3: Required structural sections are available."""
        missing = []
        if not (mapped.forum_heading and mapped.forum_heading.strip()):
            missing.append("Forum Heading")
        if not (mapped.jurisdiction and mapped.jurisdiction.strip()):
            missing.append("Jurisdiction")
        if not (mapped.case_number_line and mapped.case_number_line.strip()):
            missing.append("Case Number Line")
        if not mapped.cause_title.petitioner or not mapped.cause_title.petitioner.name:
            missing.append("Cause Title Petitioner")
        if not mapped.cause_title.respondents:
            missing.append("Cause Title Respondents")
        if not (mapped.affidavit_title and mapped.affidavit_title.strip()):
            missing.append("Affidavit Title")
        if not (mapped.deponent_clause and mapped.deponent_clause.text.strip()):
            missing.append("Deponent Clause")
        if not mapped.body_paragraphs:
            missing.append("Body Paragraphs")
        if not mapped.prayer or not mapped.prayer.clauses:
            missing.append("Prayer Clauses")
        if not (mapped.jurat and mapped.jurat.text.strip()):
            missing.append("Jurat")
        if not (mapped.verification and mapped.verification.text.strip()):
            missing.append("Verification")

        passed = len(missing) == 0
        return PreGenCheck(
            check_id="required_sections",
            name="Structural Sections Availability",
            passed=passed,
            message="All required structural sections are available." if passed else "Missing structural sections.",
            details=missing,
        )

    def _check_exhibit_consistency(
        self,
        case_input: "AffidavitCaseInput",
        mapped: "MappedAffidavitContent",
    ) -> PreGenCheck:
        """Check 4: Exhibit references are internally consistent."""
        issues = []
        seen_labels: dict[str, str] = {}

        # Scan input points
        for pt in case_input.reply_points.points:
            if pt.exhibit:
                lbl = pt.exhibit.label.strip()
                desc = pt.exhibit.document_description.strip()
                if not lbl:
                    issues.append(f"Reply point {pt.point_number} has an exhibit with an empty label.")
                if not desc:
                    issues.append(f"Reply point {pt.point_number} exhibit '{lbl}' has an empty document description.")
                if lbl in seen_labels and seen_labels[lbl] != desc:
                    issues.append(
                        f"Exhibit label '{lbl}' is bound to conflicting descriptions: '{seen_labels[lbl]}' vs '{desc}'."
                    )
                seen_labels[lbl] = desc

        # Scan mapped paragraphs
        for para in mapped.body_paragraphs:
            if para.exhibit:
                lbl = para.exhibit.label.strip()
                desc = para.exhibit.document_description.strip()
                if not lbl:
                    issues.append(f"Paragraph {para.number} exhibit label is empty.")
                if not desc:
                    issues.append(f"Paragraph {para.number} exhibit '{lbl}' document description is empty.")
                # Verify that the paragraph text references the exhibit label
                if lbl.upper() not in para.text.upper() and lbl.replace("'", "").upper() not in para.text.upper():
                    issues.append(
                        f"Paragraph {para.number} references exhibit '{lbl}' in metadata but not in paragraph text."
                    )

        passed = len(issues) == 0
        return PreGenCheck(
            check_id="exhibit_consistency",
            name="Exhibit Reference Consistency",
            passed=passed,
            message="Exhibit references are internally consistent." if passed else "Exhibit reference inconsistencies detected.",
            details=issues,
        )

    def _check_verification_range(
        self,
        mapped: "MappedAffidavitContent",
    ) -> PreGenCheck:
        """Check 5: Verification paragraph range matches generated body paragraph count."""
        issues = []
        body_count = len(mapped.body_paragraphs)
        v = mapped.verification

        if v.paragraph_start != 1:
            issues.append(f"Verification start paragraph is {v.paragraph_start}, expected 1.")
        if v.paragraph_end != body_count:
            issues.append(
                f"Verification end paragraph is {v.paragraph_end}, expected {body_count} (matching body paragraph count)."
            )

        # Check text contains matching range e.g. "paragraphs 1 to 6"
        expected_range_str = f"{v.paragraph_start} to {v.paragraph_end}"
        if expected_range_str not in v.text:
            issues.append(
                f"Verification text does not explicitly state the paragraph range '{expected_range_str}'."
            )

        passed = len(issues) == 0
        return PreGenCheck(
            check_id="verification_range",
            name="Verification Paragraph Range Consistency",
            passed=passed,
            message=f"Verification range (1 to {body_count}) matches body paragraph count." if passed else "Verification paragraph range mismatch.",
            details=issues,
        )

# Helpers

def _humanize_extraction_error(raw: str) -> str:
    """Convert a CaseExtractionError message into a concise user-facing string."""
    raw_lower = raw.lower()
    if "missing required field" in raw_lower:
        match = re.search(r"label '([^']+)'", raw)
        label = match.group(1) if match else "a required field"
        return f"Missing required information: {label}."
    if "no respondents found" in raw_lower:
        return "Missing required information: respondents."
    if "could not parse answering respondent" in raw_lower:
        return "Missing required information: answering respondent."
    if "expected 6 reply points" in raw_lower:
        match = re.search(r"found (\d+)", raw)
        found = match.group(1) if match else "unknown number of"
        return f"Expected 6 reply points but found {found}."
    if "reply point" in raw_lower and "no source facts" in raw_lower:
        return "One or more reply points are missing their supporting facts."
    if "no reply-move mapping" in raw_lower:
        return "A reply point heading could not be classified."
    return raw.split("\n")[0][:120]
