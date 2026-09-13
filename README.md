# LexProof - Affidavit Generator

LexProof is an AI-powered Streamlit application that generates an **Affidavit in Reply** from supplied case information while following the structure of a predefined reference affidavit. The system extracts case entities and reply points, analyzes the reference document structure, maps the supplied information to the appropriate sections, and generates the final document. It then evaluates the generated affidavit using deterministic validation checks for entity accuracy, completeness, structure, consistency, template fidelity, and hallucination. The project is designed as a proof of concept for reliable legal document generation rather than a full legal drafting platform.

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
          Stop      DOCX Generation
                        │
                        ▼
                    Evaluation
                        │
                        ▼
              Evaluation Report
```

## Processing Pipeline

### 1. Document Role Validation

The uploaded PDF is first validated to ensure that it is the expected **Case Information** document.

### 2. Entity and Content Extraction

The system extracts the required case entities and substantive information into a structured representation.

The extracted information includes:

* Court
* Jurisdiction
* Case number
* Year
* Petitioner
* Respondent
* Respondent number
* Deponent
* Capacity / designation
* Address
* Dates
* Exhibits
* Advocate details
* Reply points

### 3. Template Analysis

The predefined reference affidavit is analyzed to identify:

* Major sections
* Headings
* Paragraph organization
* Numbering conventions
* Fixed phrases
* Prayer structure
* Verification and jurat blocks
* Advocate / drafting blocks

### 4. Content Mapping

The extracted case information is mapped to the appropriate locations in the reference structure.

### 5. Pre-generation Validation

Before document generation, the mapped information is validated for missing or inconsistent required information.

If validation fails, document generation is stopped and the detected issues are reported.

If validation passes, the system proceeds to document generation.

### 6. Document Generation

The system generates a new **Affidavit in Reply** using the supplied case information while preserving the reference document's structure and organization.

### 7. Validation and Evaluation

The generated document is extracted and evaluated against the expected ground truth using deterministic checks.

### 8. Evaluation Report

The system produces an evaluation report containing:

* Overall score
* Individual dimension scores
* Passed checks
* Failed checks
* Detected issues
* Evidence / source information where applicable

## Steps to Run Locally

### 1. Clone the Repository

### 2. Create and Activate a Virtual Environment

```bash
python -m venv .venv
```

**Windows PowerShell:**

```powershell
.venv\Scripts\Activate.ps1
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Start the Streamlit Application

```bash
python -m streamlit run app.py
```

## Usage

1. **Load Reference Documents** - The application loads the predefined affidavit format and sample affidavit.
2. **Upload Case Information** - Upload the Case Information PDF.
3. **Validate Document** - The application checks whether the uploaded PDF is the expected document type.
4. **Extract Information** - Case details and reply points are extracted from the PDF.
5. **Analyze Template** - The reference affidavit is analyzed to identify its structure.
6. **Map Content** - The extracted case information is mapped to the appropriate affidavit sections.
7. **Validate Content** - The mapped content is checked for missing or invalid information.
8. **Generate Affidavit** - If validation passes, the Affidavit in Reply is generated as a DOCX file.
9. **Evaluate Document** - The generated affidavit is evaluated using deterministic validation checks.
10. **Generate Evaluation Report** - A report containing scores, issues, and evidence mapping is generated.

## Evaluation

The generated affidavit is evaluated using deterministic checks across six dimensions.

### 1. Entity Accuracy
### 2. Completeness
### 3. Structure
### 4. Consistency
### 5. Template Fidelity
### 6. Hallucination Check

## Validation Approach

LexProof uses deterministic validation checks to systematically assess the generated document.

The evaluation checks whether the document:
* Contains the required case entities
* Includes the required information
* Follows the expected structure
* Maintains consistency with the source information
* Preserves the predefined reference format
* Avoids introducing unsupported information

### Deterministic Validation

The evaluation layer includes validation checks that do not depend on an LLM.

Examples include:
* Respondent number consistency throughout the document
* Required section presence
* Expected section ordering
* Verification paragraph range consistency
* Required entity presence
* Exhibit reference consistency
* Detection of unsupported entities or information

## Design Decisions

### Structured Intermediate Representation

Extracted case information is converted into a structured representation before document generation.

**Reason:** Separating extraction, mapping, and generation makes the workflow easier to validate and debug.

### Deterministic Evaluation

Deterministic checks are used for critical validation requirements.

**Reason:** Checks such as entity consistency, section presence, and paragraph numbering should produce reproducible results.


## Known Limitations

* Supports only one document type: Affidavit in Reply.
* The system depends on the quality and structure of the supplied Case Information PDF.
* Complex PDF layouts or unusual extraction patterns may affect entity extraction.
* Template fidelity focuses on required structure and conventions rather than pixel-perfect reproduction of professional court formatting.
* Deterministic validation covers defined checks and cannot guarantee that every possible document error is detected.
* The application does not perform independent legal research.
* Para-wise replies are outside the current scope.

## Failure Cases

Potential failure cases include:

* Incorrect or unsupported input document
* Missing case entities
* Ambiguous entity values
* Unexpected PDF formatting
* Missing required sections
* Inconsistent respondent or party information
* Incorrect exhibit references
* Unsupported information appearing in the generated document
* Structural deviations from the reference affidavit

## Generated Artefacts

The repository contains an `/outputs` folder with the generated artefacts for the case:

```text
outputs/
├── generated_affidavit.docx
└── evaluation_report.txt
```
This is for reference purpose only.The affidavit annd evaluation report are generated when user inputs the case information.

## Testing

Run the test suite using:

```bash
pytest
```

## Working Demo

**Live Application:** https://lexproof-affidavitgenerator-ocg6yidwsas5trjauosxxe.streamlit.app/

**Video Demonstration:** https://drive.google.com/file/d/1WorzFqjJjBBrIUN7aU_bBMrDGxKoLnWT/view?usp=drive_link


## AI Coding Assistance

AI coding assistance was used during development of this project for overall project structure, debugging and refinement.

