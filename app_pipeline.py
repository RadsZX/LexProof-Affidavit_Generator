from __future__ import annotations

import sys
from pathlib import Path

# Ensure project root is on the path
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.document_parser import PDFDocumentParser
from src.template_analyzer import TemplateAnalyzer
from src.entity_extractor import CaseInformationExtractor
from src.content_mapper import AffidavitContentMapper
from src.docx_generator import AffidavitDocxGenerator
from src.evaluator import AffidavitEvaluator, write_evaluation_report
from src.document_validator import (
    DocumentRoleValidator,
    PreGenerationValidator,
    resolve_reference_paths,
)

# Reference files (resolved from reference/ or Input/)
FORMAT_GUIDE_PDF, REFERENCE_AFFIDAVIT_PDF = resolve_reference_paths(PROJECT_ROOT)
INPUT_DIR = PROJECT_ROOT / "Input"
CASE_INFORMATION_PDF = INPUT_DIR / "03_Case_Information.pdf"

# Output files
OUTPUT_DIR = PROJECT_ROOT / "outputs"
GENERATED_DOCX = OUTPUT_DIR / "generated_affidavit.docx"
EVALUATION_REPORT = OUTPUT_DIR / "evaluation_report.md"


def run_pipeline(case_info_pdf: Path | str = CASE_INFORMATION_PDF) -> dict:
    """Run the full pipeline and return a summary dict."""
    case_path = Path(case_info_pdf)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("  Legal Document Generation & Evaluation Pipeline")
    print("=" * 60)

    # Step 1: Validate document roles & input
    print("\n[1/7] Validating documents & roles...")
    parser = PDFDocumentParser()
    validator = DocumentRoleValidator(
        parser=parser,
        format_guide_path=FORMAT_GUIDE_PDF,
        sample_path=REFERENCE_AFFIDAVIT_PDF,
    )
    suite = validator.validate_all(case_info_path=case_path)
    if not suite.all_valid:
        print("  [ERROR] Document validation failed:")
        for r in [suite.format_guide, suite.sample_affidavit, suite.case_information]:
            if not r.valid:
                print(f"    - {r.document_role}: {r.message}")
                for d in r.details:
                    print(f"      * {d}")
        raise ValueError("Document validation failed.")
    print("  [OK] Bundled references and case information validated successfully.")

    # Step 2: Parse input PDFs
    print("\n[2/7] Parsing input PDFs...")
    format_doc = parser.parse(FORMAT_GUIDE_PDF)
    reference_doc = parser.parse(REFERENCE_AFFIDAVIT_PDF)
    case_doc = parser.parse(case_path)
    print(f"  [OK] Format guide: {format_doc.page_count} pages")
    print(f"  [OK] Reference sample: {reference_doc.page_count} pages")
    print(f"  [OK] Case information: {case_doc.page_count} pages")

    # Step 3: Analyze template
    print("\n[3/7] Analyzing template...")
    analyzer = TemplateAnalyzer(parser=parser)
    template = analyzer.build_template_from_format_guide(FORMAT_GUIDE_PDF)
    ref_analysis = analyzer.analyze_reference_affidavit(REFERENCE_AFFIDAVIT_PDF, template=template)
    print(f"  [OK] Template: {len(template.sections)} sections defined")
    print(f"  [OK] Reference: all sections present = {ref_analysis.all_required_sections_present}")

    # Step 4: Extract case entities
    print("\n[4/7] Extracting case entities...")
    extractor = CaseInformationExtractor(parser=parser)
    extraction = extractor.extract_with_evidence(case_path)
    case_input = extraction.case_input
    print(f"  [OK] Case: {case_input.case.proceeding_type} No. {case_input.case.case_number} of {case_input.case.year}")
    print(f"  [OK] Deponent: {case_input.deponent.name} ({case_input.deponent.designation})")
    print(f"  [OK] Reply points: {len(case_input.reply_points.points)}")

    # Step 5: Map content
    print("\n[5/7] Mapping content...")
    mapper = AffidavitContentMapper()
    mapped = mapper.map(case_input, template=template)
    print(f"  [OK] Body paragraphs: {mapped.body_paragraph_count}")
    print(f"  [OK] Prayer clauses: {len(mapped.prayer.clauses)}")
    print(f"  [OK] Jurat: {mapped.jurat.verb_past} at {mapped.jurat.place}")

    # Step 6: Pre-generation deterministic validation
    print("\n[6/7] Running pre-generation deterministic validation...")
    pre_gen_validator = PreGenerationValidator()
    pre_gen_result = pre_gen_validator.validate(case_input, mapped)
    if not pre_gen_result.valid:
        print("  [ERROR] Pre-generation validation failed! Generation aborted.")
        for err in pre_gen_result.errors:
            print(f"    - {err}")
        raise ValueError(f"Pre-generation validation failed: {pre_gen_result.errors}")
    print("  [OK] All 5 pre-generation deterministic integrity checks passed.")

    # Step 7: Generate DOCX & Evaluate
    print("\n[7/7] Generating DOCX and post-generation evaluation...")
    generator = AffidavitDocxGenerator()
    docx_path = generator.generate(mapped, GENERATED_DOCX)
    print(f"  [OK] Generated: {docx_path}")

    evaluator = AffidavitEvaluator()
    result = evaluator.evaluate(
        mapped,
        case_input,
        reference_text=reference_doc.full_text,
    )
    report_path = write_evaluation_report(result, EVALUATION_REPORT)
    print(f"  [OK] Overall score: {result.overall_score:.2%}")
    print(f"  [OK] Passed: {'YES' if result.passed else 'NO'}")
    print(f"  [OK] Total checks: {len(result.issues)}")

    passed_count = sum(1 for i in result.issues if i.score is not None and i.score >= 1.0)
    failed_count = len(result.issues) - passed_count
    print(f"  [OK] Passed checks: {passed_count}")
    print(f"  [OK] Failed checks: {failed_count}")

    if failed_count > 0:
        print("\n  Failed checks:")
        for i in result.issues:
            if i.score is not None and i.score < 1.0:
                print(f"    [FAIL] [{i.dimension}] {i.issue}")

    print(f"\n  Report: {report_path}")

    print("\n" + "=" * 60)
    print("  Pipeline complete!")
    print("=" * 60)
    print(f"\n  Output files:")
    print(f"    - {GENERATED_DOCX}")
    print(f"    - {EVALUATION_REPORT}")

    return {
        "docx_path": str(docx_path),
        "report_path": str(report_path),
        "overall_score": result.overall_score,
        "passed": result.passed,
        "total_checks": len(result.issues),
        "passed_checks": passed_count,
        "failed_checks": failed_count,
        "mapped_content": mapped,
        "evaluation_result": result,
    }


if __name__ == "__main__":
    run_pipeline()
