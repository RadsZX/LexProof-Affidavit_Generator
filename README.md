# LexProof - Affidavit Generator
LexProof is an AI-powered Streamlit application that generates an Affidavit in Reply from supplied case information while following the structure of a predefined reference affidavit. The system extracts case entities and reply points, analyzes the reference document structure, maps the supplied information to the appropriate sections, and generates the final document. It then evaluates the generated affidavit using deterministic validation checks for entity accuracy, completeness, structure, consistency, template fidelity, and hallucination. The project is designed as a proof of concept for reliable legal document generation rather than a full legal drafting platform.

## Workflow

```text
Reference Format + Case Information PDF
                  │
                  ▼
        Document Role Validation
                  │
                  ▼
          PDF Parsing / Extraction
                  │
                  ▼
        Structured Case Information
                  │
                  ▼
            Template Analysis
                  │
                  ▼
             Content Mapping
                  │
                  ▼
       Pre-generation Validation
                  │
            ┌─────┴─────┐
            │           │
          Failed      Passed
            │           │
            ▼           ▼
        Stop       DOCX Generation
                        │
                        ▼
                    Evaluation
                        │
                        ▼
              Evaluation Report
```
Processing Pipeline
1. Document Role Validation

The uploaded PDF is first validated to ensure that it is the expected Case Information document.

2. Entity and Content Extraction

The system extracts the required case entities and substantive information into a structured representation.

3. Template Analysis

The predefined reference affidavit is analyzed to identify:

Major sections
Headings
Paragraph organization
Numbering conventions
Fixed phrases
Prayer structure
Verification / jurat blocks
Advocate / drafting blocks
4. Content Mapping

The extracted case information is mapped to the appropriate locations in the reference structure.

5. Document Generation

The system generates a new Affidavit in Reply using the supplied case information while preserving the reference document's structure and organization.

6. Validation and Evaluation

The generated document is extracted and evaluated against the expected ground truth using deterministic checks.

7. Evaluation Report

The system produces an evaluation report containing the overall score, individual dimension scores, passed and failed checks, and detected issues.

## Steps to Run Locally

### 1. Clone the repository


### 2. Create and activate a virtual environment

```bash
python -m venv .venv
```

**Windows PowerShell:**

```powershell
.venv\Scripts\Activate.ps1
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Start the Streamlit application

```bash
python -m streamlit run app.py
```

## Project Workflow

1. **Load Reference Documents** – The app loads the predefined affidavit format and sample affidavit.
2. **Upload Case Information** – The user uploads the Case Information PDF.
3. **Validate Document** – The app checks whether the uploaded PDF is the correct document type.
4. **Extract Information** – Case details and reply points are extracted from the PDF.
5. **Analyze Template** – The reference affidavit format is analyzed to identify its structure.
6. **Map Content** – The extracted case information is placed into the appropriate affidavit sections.
7. **Validate Content** – The mapped content is checked for missing or invalid information.
8. **Generate Affidavit** – If validation passes, the Affidavit in Reply is generated as a DOCX file.
9. **Evaluate Document** – The generated affidavit is evaluated using deterministic validation checks.
10. **Generate Evaluation Report** – A report containing scores, issues, and evidence mapping is generated.

Evaluation

The generated affidavit is evaluated using deterministic checks across six dimensions:

1. Entity Accuracy

Checks whether important case entities such as the court, jurisdiction, case number, parties, and other relevant information are correctly represented.

2. Completeness

Checks whether the required information and expected sections are present in the generated affidavit.

3. Structure

Checks whether the generated affidavit follows the expected document structure.

4. Consistency

Checks whether extracted case information is represented consistently throughout the generated document.

5. Template Fidelity

Checks whether the generated affidavit preserves the structure and expected formatting of the predefined reference format.

6. Hallucination Check

Checks whether the generated affidavit contains unsupported information that was not present in the supplied case information.

The application displays an overall evaluation score along with the number of passed and failed checks.

Validation Approach

LexProof uses deterministic validation checks to systematically assess the generated document.

The evaluation checks whether the document:

Contains the required case entities.
Includes the required information.
Follows the expected structure.
Maintains consistency with the source information.
Preserves the predefined reference format.
Avoids introducing unsupported information.

Deterministic Validation

The evaluation layer includes deterministic checks that do not depend on an LLM.

Examples include:

Respondent number consistency throughout the document
Required section presence
Expected section ordering
Verification paragraph range consistency
Required entity presence
Exhibit reference consistency
Detection of unsupported entities or information

This provides a reproducible validation layer instead of relying solely on an LLM to judge its own output, because apparently even artificial intelligence benefits from having a supervisor.

Known Limitations
Supports only one document type: Affidavit in Reply.
The system depends on the quality and structure of the supplied Case Information PDF.
Complex PDF layouts or unusual extraction patterns may affect entity extraction.
Template fidelity focuses on the required structure and conventions rather than pixel-perfect reproduction of professional court formatting.
Deterministic validation covers defined checks and cannot guarantee that every possible document error is detected.
The application does not perform independent legal research.


Failure Cases

Potential failure cases include:

Incorrect or unsupported input document
Missing case entities
Ambiguous entity values
Unexpected PDF formatting
Missing required sections
Inconsistent respondent or party information
Incorrect exhibit references
Unsupported information appearing in the generated document
Structural deviations from the reference affidavit

AI assistance was used during development of this project for overall structure , debugging, refinement.

## Testing

Run the test suite using:

```bash
pytest
```


