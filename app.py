
import base64
import sys
import re
from pathlib import Path

import streamlit as st

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
    DocumentValidationResult,
    PreGenerationValidator,
    ValidationSuite,
    resolve_reference_paths,
)

INPUT_DIR = PROJECT_ROOT / "Input"
OUTPUT_DIR = PROJECT_ROOT / "outputs"
GENERATED_DOCX = OUTPUT_DIR / "generated_affidavit.docx"
EVALUATION_REPORT = OUTPUT_DIR / "evaluation_report.md"
LEXPROOF_ICON = PROJECT_ROOT / "icon.png"

# Resolve bundled fixed reference resources
FORMAT_GUIDE_PATH, SAMPLE_PATH = resolve_reference_paths(PROJECT_ROOT)
format_guide_exists = FORMAT_GUIDE_PATH.exists()
sample_exists = SAMPLE_PATH.exists()
references_ready = format_guide_exists and sample_exists


def _format_report_as_text(markdown_report: str) -> str:
    """Convert Markdown tables into readable non-overlapping text sections."""
    lines = markdown_report.splitlines()
    formatted: list[str] = []
    index = 0

    table_separator = re.compile(
        r"^\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?\s*$"
    )

    while index < len(lines):
        if (
            index + 1 < len(lines)
            and "|" in lines[index]
            and table_separator.match(lines[index + 1])
        ):
            table_rows: list[list[str]] = []
            while index < len(lines) and "|" in lines[index]:
                if not table_separator.match(lines[index]):
                    table_rows.append(
                        [cell.strip() for cell in lines[index].strip().strip("|").split("|")]
                    )
                index += 1

            headers = table_rows[0]
            for row in table_rows[1:]:
                formatted.append(f"[{row[0] if row else 'Evidence'}]")
                for column, header in enumerate(headers):
                    if column == 0:
                        continue
                    value = row[column] if column < len(row) else "-"
                    formatted.append(f"{header}: {value}")
                formatted.append("")
            formatted.append("")
            continue

        formatted.append(re.sub(r"^#{1,6}\s*", "", lines[index]))
        index += 1

    return "\n".join(formatted).strip() + "\n"

# 1. Page Configuration
st.set_page_config(
    page_title="LexProof | Affidavit Generator & Evaluator",
    layout="wide",
)

# Custom styling — interactive, polished, no How-it-works footer
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Source+Sans+3:wght@400;500;600;700&family=Source+Serif+4:wght@600;700&display=swap');

    /* Page layout */
    .block-container {
        padding-top: 0.8rem !important;
        padding-bottom: 1.25rem !important;
        max-width: 1280px !important;
        font-family: 'Source Sans 3', -apple-system, BlinkMacSystemFont, sans-serif !important;
    }
    [data-testid="stAppViewContainer"] {
        background: linear-gradient(135deg, #f8f2ff 0%, #eee2ff 52%, #e4d4fb 100%);
        background-attachment: fixed;
    }
    [data-testid="stHeader"] {
        background: transparent;
    }
    div[data-testid="stVerticalBlockBorderWrapper"] {
        background: linear-gradient(145deg, #fffaff 0%, #f5ecff 100%);
        border: 2px solid #a855f7 !important;
        border-radius: 12px;
        padding: 0.85rem 1rem;
        box-shadow:
            0 0 0 1px rgba(124, 58, 237, 0.28),
            0 0 14px rgba(192, 132, 252, 0.32),
            0 6px 20px rgba(109, 40, 217, 0.16);
        overflow: visible;
        margin-bottom: 0.75rem;
    }
    h1, h2, h3, h4 {
        font-family: 'Source Serif 4', Georgia, serif;
    }

    /* File uploader — hover lift */
    div[data-testid="stFileUploader"] {
        padding-bottom: 0.25rem !important;
        transition: transform 0.18s ease, box-shadow 0.18s ease;
        border-radius: 8px;
    }
    div[data-testid="stFileUploader"]:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 14px rgba(15,23,42,0.08);
    }
    div[data-testid="stFileUploader"] section {
        padding: 0.4rem 0.75rem !important;
        transition: border-color 0.2s ease;
    }
    div[data-testid="stFileUploader"] label {
        font-size: 0.85rem !important;
        font-weight: 600 !important;
        color: #1e293b !important;
        margin-bottom: 0.15rem !important;
    }

    /* Primary button — pulse animation when enabled */
    div[data-testid="stButton"] > button[kind="primary"]:not(:disabled) {
        background: linear-gradient(135deg, #4c1d95 0%, #6d28d9 100%) !important;
        border: none !important;
        box-shadow: 0 4px 14px rgba(109,40,217,0.30) !important;
        transition: all 0.2s ease !important;
        font-weight: 600 !important;
        letter-spacing: 0.01em !important;
    }
    div[data-testid="stButton"] > button[kind="primary"]:not(:disabled):hover {
        transform: translateY(-2px) !important;
        box-shadow: 0 8px 20px rgba(109,40,217,0.40) !important;
        background: linear-gradient(135deg, #3730a3 0%, #5b21b6 100%) !important;
    }
    div[data-testid="stButton"] > button[kind="primary"]:not(:disabled):active {
        transform: translateY(0px) !important;
    }

    /* Metric cards — hover glow */
    div[data-testid="stMetric"] {
        background: linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%);
        border: 1px solid #e2e8f0;
        border-radius: 10px;
        padding: 0.75rem 1rem !important;
        transition: transform 0.18s ease, box-shadow 0.18s ease;
    }
    div[data-testid="stMetric"]:hover {
        transform: translateY(-2px);
        box-shadow: 0 6px 18px rgba(15,23,42,0.10);
        border-color: #cbd5e1;
    }
    div[data-testid="stMetricValue"] {
        font-size: 1.5rem !important;
        font-weight: 700 !important;
        color: #0f172a !important;
    }
    div[data-testid="stMetricLabel"] {
        font-size: 0.78rem !important;
        font-weight: 600 !important;
        color: #64748b !important;
        text-transform: uppercase;
        letter-spacing: 0.04em;
    }

    /* Download buttons — lift on hover */
    div[data-testid="stDownloadButton"] {
        animation: downloadReveal 0.45s ease both;
    }
    div[data-testid="stDownloadButton"] > button {
        border-radius: 8px !important;
        transition: transform 0.18s ease, box-shadow 0.18s ease !important;
    }
    div[data-testid="stDownloadButton"] > button[kind="primary"] {
        background: linear-gradient(135deg, #4c1d95 0%, #6d28d9 100%) !important;
        border: none !important;
        color: #ffffff !important;
        box-shadow: 0 4px 12px rgba(109,40,217,0.25) !important;
    }
    div[data-testid="stDownloadButton"] > button[kind="secondary"] {
        background: #f3edff !important;
        border: 1px solid #c4b5fd !important;
        color: #4c1d95 !important;
    }
    div[data-testid="stDownloadButton"] > button:hover {
        transform: translateY(-2px) !important;
        box-shadow: 0 7px 16px rgba(76,29,149,0.22) !important;
    }

    /* Fade-in animation for result panels */
    @keyframes fadeSlideIn {
        from { opacity: 0; transform: translateY(8px); }
        to   { opacity: 1; transform: translateY(0); }
    }
    .anim-fadein {
        animation: fadeSlideIn 0.4s ease forwards;
    }

    /* Spinning loader icon */
    @keyframes spin {
        to { transform: rotate(360deg); }
    }
    @keyframes downloadReveal {
        from { opacity: 0; transform: translateY(5px); }
        to { opacity: 1; transform: translateY(0); }
    }
    @keyframes lawMarkFloat {
        0%, 100% { transform: translateY(0) rotate(-2deg); }
        50% { transform: translateY(-3px) rotate(2deg); }
    }
    .law-mark {
        position: relative;
        display: inline-block;
        animation: lawMarkFloat 3.2s ease-in-out infinite;
        transform-origin: 50% 80%;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# 2. Top Hero / Header (Centered)
icon_data = base64.b64encode(LEXPROOF_ICON.read_bytes()).decode("ascii")
st.markdown(
    f"""
    <div style="text-align: center; margin-bottom: 0.85rem;">
        <div style="display:flex; align-items:center; justify-content:center; gap:0.7rem;">
            <img src="data:image/png;base64,{icon_data}" alt="LexProof logo" style="width:52px; height:52px; object-fit:contain;">
            <h1 style="font-size: 1.75rem; font-weight: 700; margin: 0; letter-spacing: -0.02em; background:linear-gradient(135deg,#4c1d95 0%,#a855f7 55%,#6d28d9 100%); -webkit-background-clip:text; background-clip:text; color:transparent;">
               LexProof Affidavit
            </h1>
        </div>
        <p style="font-size: 0.95rem; color: #64748b; margin: 0;">
            Draft with confidence. Review with clarity.
        </p>
    </div>
    """,
    unsafe_allow_html=True,
)


# Helper: compact per-document validation status panel

def _render_validation_status(result: "DocumentValidationResult | ValidationSuite") -> None:
    """Render a compact validation status section for the uploaded Case Information PDF."""
    if isinstance(result, ValidationSuite):
        r = result.case_information
    else:
        r = result

    if r.valid:
        header_bg, header_border, header_color = "#eef2ff", "#c7d2fe", "#3730a3"
        header_icon, header_text = "✓", "Uploaded Case Information is valid."
        icon_color, icon = "#3730a3", "✓"
        body = '<div style="margin-top:2px; font-size:0.80rem; color:#4338ca;">Case Information PDF validated successfully.</div>'
    else:
        header_bg, header_border, header_color = "#fef2f2", "#fecaca", "#991b1b"
        header_icon, header_text = "✗", ""
        icon_color, icon = "#991b1b", "✗"
        display_details = [
            detail
            for detail in r.details
            if "missing required information: court" not in detail.lower()
        ]
        detail_lines = "".join(
            f'<li style="margin:2px 0; color:#64748b; font-size:0.80rem;">{d}</li>'
            for d in display_details
        )
        body = (
            f'<div style="margin-top:3px; padding-left:1.4rem;">'
            f'<div style="font-size:0.82rem; color:#7f1d1d; font-weight:500;">{r.message}</div>'
            + (f'<ul style="margin:4px 0 0 0; padding-left:1rem;">{detail_lines}</ul>' if display_details else "")
            + "</div>"
        )

    row_html = (
        f'<div style="padding:4px 0;">'
        f'  <span style="font-weight:600; color:{icon_color}; font-size:0.88rem;">{icon} Case Information</span>'
        f'  {body}'
        f'</div>'
    )

    st.markdown(
        f"""
        <div style="margin-bottom:0.9rem; border:1px solid {header_border}; border-radius:7px; overflow:hidden;">
            <div style="background:{header_bg}; padding:7px 12px; display:flex; align-items:center; gap:6px;">
                <span style="font-weight:700; color:{header_color}; font-size:0.85rem;">{header_icon}</span>
                <span style="font-weight:600; font-size:0.85rem; color:{header_color};">Document Validation</span>
                <span style="margin-left:auto; font-size:0.80rem; color:{header_color};">{header_text}</span>
            </div>
            <div style="padding:6px 12px 6px 12px; background:#ffffff;">
                {row_html}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# 3. Main Application Area (Two-Column Layout: 42% / 58%)
col_left, col_right = st.columns([42, 58], gap="large")


# ----------------- LEFT COLUMN: Upload Document -----------------
with col_left.container(border=True):
    st.markdown(
        """
        <div style="margin-bottom: 0.75rem;">
            <h3 style="font-size: 1.15rem; font-weight: 600; color: #0f172a; margin: 0 0 0.2rem 0;">Case Information</h3>
           
        </div>
        """,
        unsafe_allow_html=True,
    )

    # if references_ready:
    #     st.markdown(
    #         '<div style="margin-bottom:0.65rem; padding:5px 10px; background:#eef2ff; border:1px solid #c7d2fe; border-radius:6px; font-size:0.78rem; color:#3730a3;">✓ Reference format ready</div>',
    #         unsafe_allow_html=True,
    #     )

    # # Preconfigured Reference Resources Status Card
    # if references_ready:
    #     st.markdown(
    #         f"""
    #         <div style="margin-bottom:0.75rem; padding:8px 12px; background:#f0fdf4; border:1px solid #bbf7d0; border-radius:8px; font-size:0.80rem; color:#166534;">
    #             <div style="font-weight:600; margin-bottom:2px; display:flex; align-items:center; gap:5px;">

    #                 <span>✓</span> <span>Preconfigured Reference Resources Loaded</span>
    #             </div>
    #             <div style="color:#15803d; font-size:0.74rem; line-height:1.45; margin-top:3px;">
    #                 <div>• Format Guide: <code>{FORMAT_GUIDE_PATH.name}</code></div>
    #                 <div>• Reference Sample: <code>{SAMPLE_PATH.name}</code></div>
    #             </div>
    #         </div>
    #         """,
    #         unsafe_allow_html=True,
    #     )
    # else:
    #     missing_res = []
    #     if not format_guide_exists:
    #         missing_res.append(f"Format Guide ({FORMAT_GUIDE_PATH.name})")
    #     if not sample_exists:
    #         missing_res.append(f"Reference Sample ({SAMPLE_PATH.name})")
    #     st.error(
    #         f"❌ Missing required project reference file(s): {', '.join(missing_res)}.\n"
    #         "Please verify reference files exist in the project repository."
    #     )

    uploader_key = st.session_state.get("case_file_uploader_key", 0)
    case_file = st.file_uploader(
        "Upload Case Information PDF",
        type=["pdf"],
        help="Upload the case-specific information and reply points PDF.",
        key=f"case_file_{uploader_key}",
    )
    if case_file and st.button("Remove selected PDF", use_container_width=True):
        st.session_state["case_file_uploader_key"] = uploader_key + 1
        st.rerun()

    can_generate = (case_file is not None) and references_ready

    # # Animated 5-step progress bar: Case Information -> Extract -> Validate -> Generate -> Evaluate
    # pipeline_done = st.session_state.get("pipeline_done", False)
    # step_labels = ["Case Information", "Extract", "Validate", "Generate", "Evaluate"]
    # steps_html = ""
    # for i, label in enumerate(step_labels):
    #     if i == 0:
    #         active = case_file is not None
    #     else:
    #         active = pipeline_done

    #     if active:
    #         bg, tc, dot = "#dbeafe", "#1d4ed8", "#2563eb"
    #         symbol = "✓"
    #     else:
    #         bg, tc, dot = "#f1f5f9", "#94a3b8", "#cbd5e1"
    #         symbol = str(i + 1)

    #     steps_html += (
    #         f'<div style="display:flex;align-items:center;gap:4px;padding:3px 7px;background:{bg};'
    #         f'border-radius:6px;font-size:0.72rem;font-weight:600;color:{tc};transition:background 0.3s ease;">'
    #         f'<span style="width:15px;height:15px;border-radius:50%;background:{dot};color:#fff;'
    #         f'display:flex;align-items:center;justify-content:center;font-size:0.60rem;flex-shrink:0;">{symbol}</span>'
    #         f'{label}</div>'
    #     )
    #     if i < len(step_labels) - 1:
    #         conn_color = "#2563eb" if active else "#e2e8f0"
    #         steps_html += f'<div style="width:10px;height:2px;background:{conn_color};border-radius:1px;transition:background 0.3s ease;"></div>'

    # st.markdown(
    #     f'<div class="anim-fadein" style="display:flex;align-items:center;justify-content:space-between;gap:2px;'
    #     f'padding:8px 8px;background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;margin:0.55rem 0;">'
    #     f'{steps_html}</div>',
    #     unsafe_allow_html=True,
    # )

    btn_label = "⚡ Generate Draft Affidavit" if can_generate else "Generate Draft Affidavit"
    generate_btn = st.button(
        btn_label,
        type="primary",
        use_container_width=True,
        disabled=not can_generate,
    )
    if not case_file:
        st.caption("Select a Case Information PDF to continue.")


# ----------------- RIGHT COLUMN: Generation & Results -----------------
with col_right.container(border=True):
    st.markdown(
        """
        <div style="margin-bottom: 0.75rem;">
            <h5 style="font-size: 1.15rem; font-weight: 600; color: #0f172a; margin: 0 0 0.2rem 0;">Results</h5>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Pipeline execution on button click
    if generate_btn and can_generate:
        # Reset previous run state so invalid input never shows old downloads or dashboard
        st.session_state["pipeline_done"] = False
        for key in ["score", "passed", "total", "passed_count", "result", "pre_result"]:
            st.session_state.pop(key, None)

        INPUT_DIR.mkdir(parents=True, exist_ok=True)
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

        case_info_path = OUTPUT_DIR / "_uploaded_case_information.pdf"
        with open(case_info_path, "wb") as f:
            f.write(case_file.getbuffer())

        # ── Step 1: Validate ONLY the uploaded Case Information PDF ──────────
        parser = PDFDocumentParser()
        try:
            validator = DocumentRoleValidator(parser=parser)
            case_result = validator.validate_case_information(case_info_path)
        except Exception as exc:  # noqa: BLE001
            import logging
            logging.getLogger(__name__).exception("Unexpected validation error: %s", exc)
            case_result = DocumentValidationResult(
                valid=False,
                document_role="Case Information",
                message="The uploaded document is incorrect. Please upload the correct Case Information PDF.",
                details=[str(exc)],
            )

        # Render compact validation status panel (user input only) 
        _render_validation_status(case_result)

        # Step 2: If valid, run the generation pipeline 
        if case_result.valid:
            try:
                with st.status("Preparing draft affidavit...", expanded=True) as status:
                    st.write("✓ Validate and parse source documents")
                    parser.parse(FORMAT_GUIDE_PATH)
                    parser.parse(SAMPLE_PATH)
                    parser.parse(case_info_path)

                    st.write("✓ Analyze template")
                    analyzer = TemplateAnalyzer(parser=parser)
                    template = analyzer.build_template_from_format_guide(FORMAT_GUIDE_PATH)

                    st.write("✓ Extract case information")
                    extractor = CaseInformationExtractor(parser=parser)
                    case_input = extractor.extract(case_info_path)

                    st.write("✓ Map content")
                    mapper = AffidavitContentMapper()
                    mapped = mapper.map(case_input, template=template)

                    st.write("✓ Pre-generation deterministic validation")
                    pre_validator = PreGenerationValidator()
                    pre_result = pre_validator.validate(case_input, mapped)

                    if not pre_result.valid:
                        status.update(
                            label="Pre-generation validation failed! Generation aborted.",
                            state="error",
                            expanded=True,
                        )
                        st.session_state["pipeline_done"] = False
                        st.error("❌ Pre-generation validation failed! Stopped before document generation to prevent invalid output:")
                        for err in pre_result.errors:
                            st.markdown(f"- {err}")
                    else:
                        st.write("✓ Generate draft affidavit")
                        generator = AffidavitDocxGenerator()
                        generator.generate(mapped, GENERATED_DOCX)

                        st.write("✓ Evaluate document")
                        evaluator = AffidavitEvaluator()
                        result = evaluator.evaluate(
                            mapped,
                            case_input,
                            reference_text=parser.parse(SAMPLE_PATH).full_text,
                        )
                        write_evaluation_report(result, EVALUATION_REPORT)

                        status.update(
                            label="Pipeline complete! Evaluation ready.",
                            state="complete",
                            expanded=False,
                        )

                        st.session_state["pipeline_done"] = True
                        st.session_state["score"] = result.overall_score
                        st.session_state["passed"] = result.passed
                        st.session_state["total"] = len(result.issues)
                        st.session_state["passed_count"] = sum(
                            1 for i in result.issues if i.score is not None and i.score >= 1.0
                        )
                        st.session_state["result"] = result

            except Exception as exc:  # noqa: BLE001
                import logging
                logging.getLogger(__name__).exception("Pipeline error: %s", exc)
                st.session_state["pipeline_done"] = False
                st.error(
                    "❌ An unexpected error occurred while generating the document.\n"
                    "Please check the uploaded PDF and try again."
                )

    # Display Results Dashboard or Empty State
    if st.session_state.get("pipeline_done"):
        # 4. Results Dashboard
        m_col1, m_col2, m_col3 = st.columns(3)
        score_val = st.session_state.get("score", 1.0)
        is_passed = st.session_state.get("passed", True)
        passed_count = st.session_state.get("passed_count", 0)
        total_checks = st.session_state.get("total", 0)

        m_col1.metric("Overall Score", f"{score_val:.0%}")
        m_col2.metric("Status", "PASSED" if is_passed else "FAILED")
        m_col3.metric("Evaluation Checks", f"{passed_count} / {total_checks}")

        st.markdown(
            '<div style="margin:0.55rem 0 0.8rem; font-size:0.74rem; line-height:1.45; color:#64748b;">'
            'Full breakdown across 6 evaluation dimensions (entity accuracy, completeness, structure, consistency, template fidelity, hallucination check) is in the downloadable evaluation report.'
            '</div>',
            unsafe_allow_html=True,
        )

        result_obj = st.session_state.get("result")
        if result_obj:
            failed_issues = [
                i for i in result_obj.issues if i.score is not None and i.score < 1.0
            ]
            if failed_issues:
                st.error(f"FAILED — {len(failed_issues)} evaluation check(s) did not pass:")
                with st.expander(f"View checks ({passed_count} passed)", expanded=True):
                    for issue in result_obj.issues:
                        check_name = issue.explanation or issue.dimension
                        if issue.score is not None and issue.score < 1.0:
                            st.markdown(
                                f'<div style="color:#b91c1c; margin:0.25rem 0;">✗ <strong>{check_name}</strong>'
                                f'{f": {issue.issue}" if issue.issue else ""}</div>',
                                unsafe_allow_html=True,
                            )
                        else:
                            st.markdown(f"✓ {check_name}")
            else:
                st.markdown(
                    """
                    <div style="background-color: #eef2ff; border: 1px solid #c7d2fe; border-radius: 6px; padding: 10px 14px; margin-top: 0.75rem; color: #3730a3; font-size: 0.88rem; font-weight: 500;">
                        ✓ All evaluation checks passed.
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                with st.expander(f"View checks ({passed_count} passed)", expanded=False):
                    for issue in result_obj.issues[:5]:
                        st.markdown(f"✓ {issue.explanation or issue.dimension}")

        # 5. Download Section
        st.markdown(
            """
            <div style="margin-top: 1rem; margin-bottom: 0.4rem;">
                <h4 style="font-size: 0.95rem; font-weight: 600; color: #0f172a; margin: 0;">Downloads</h4>
            </div>
            """,
            unsafe_allow_html=True,
        )

        col_d1, col_d2 = st.columns([1, 1], gap="small")

        if GENERATED_DOCX.exists():
            with open(GENERATED_DOCX, "rb") as f:
                col_d1.download_button(
                    label="Download Draft Affidavit (.docx)",
                    data=f.read(),
                    file_name="generated_affidavit.docx",
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    type="primary",
                    use_container_width=True,
                )

        if EVALUATION_REPORT.exists():
            with open(EVALUATION_REPORT, "r", encoding="utf-8") as f:
                evaluation_report_text = _format_report_as_text(f.read())
                col_d2.download_button(
                    label="Download Evaluation Report (.txt)",
                    data=evaluation_report_text,
                    file_name="evaluation_report.txt",
                    mime="text/plain",
                    type="secondary",
                    use_container_width=True,
                )

    elif not generate_btn:
        # Engaging animated empty-state panel
        st.markdown(
            """
              <div class="anim-fadein" style="border: 1px dashed #c4b5fd; border-radius: 12px; padding: 1.75rem 1.5rem;
                  text-align: center; background: linear-gradient(135deg,#f7f2ff 0%,#ede3ff 100%); margin: 0.75rem 0 1.25rem 0; clear: both;">
                <div style="font-size: 1.05rem; font-weight: 700; color: #1e293b; margin-bottom: 0.55rem;">
                    Ready to generate
                </div>
                <div style="font-size: 0.875rem; color: #64748b; line-height: 1.5; max-width: 380px; margin: 0 auto 1rem auto;">
                    Upload the Case Information PDF, then click
                    <strong style="background:linear-gradient(135deg,#4c1d95 0%,#a855f7 55%,#6d28d9 100%); -webkit-background-clip:text; background-clip:text; color:transparent;">⚡ Generate Draft Affidavit</strong>
                    to run the pipeline.
                </div>
                <div style="display:flex; justify-content:center; gap:0.5rem; flex-wrap:wrap;">
                    <span style="background:#e0e7ff;padding:4px 12px;border-radius:20px;font-size:0.78rem;font-weight:600;"><span style="background:linear-gradient(135deg,#4c1d95 0%,#a855f7 55%,#6d28d9 100%);-webkit-background-clip:text;background-clip:text;color:transparent;">✦ Extract</span></span>
                    <span style="background:#e0e7ff;padding:4px 12px;border-radius:20px;font-size:0.78rem;font-weight:600;"><span style="background:linear-gradient(135deg,#4c1d95 0%,#a855f7 55%,#6d28d9 100%);-webkit-background-clip:text;background-clip:text;color:transparent;">✦ Validate</span></span>
                    <span style="background:#e0e7ff;padding:4px 12px;border-radius:20px;font-size:0.78rem;font-weight:600;"><span style="background:linear-gradient(135deg,#4c1d95 0%,#a855f7 55%,#6d28d9 100%);-webkit-background-clip:text;background-clip:text;color:transparent;">✦ Generate</span></span>
                    <span style="background:#e0e7ff;padding:4px 12px;border-radius:20px;font-size:0.78rem;font-weight:600;"><span style="background:linear-gradient(135deg,#4c1d95 0%,#a855f7 55%,#6d28d9 100%);-webkit-background-clip:text;background-clip:text;color:transparent;">✦ Evaluate</span></span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
