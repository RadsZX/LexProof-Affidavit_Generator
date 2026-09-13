# LexProof - Affidavit Generator

LexProof is a Streamlit-based application that generates an Affidavit from structured case information while preserving the structure of a predefined affidavit format.

The system validates the input, extracts case entities and reply points, maps the information to the reference structure, generates the affidavit, and evaluates the generated document using deterministic checks.

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

1. The application loads the predefined reference format and sample affidavit.
2. The user uploads the Case Information PDF.
3. The document role is validated.
4. Case information and reply points are extracted into a structured representation.
5. The reference format is analyzed.
6. Extracted information is mapped to the affidavit structure.
7. Pre-generation validation checks the mapped content.
8. If validation passes, the Affidavit in Reply is generated as a DOCX file.
9. The generated affidavit is evaluated using deterministic checks.
10. An evaluation report with scores, issues, and evidence mapping is produced.

## Evaluation

The generated affidavit is evaluated across six dimensions:

* Entity Accuracy
* Completeness
* Structure
* Consistency
* Template Fidelity
* Hallucination / Forbidden Sample Data

The evaluation is deterministic and does not depend on an LLM at evaluation time.

The final evaluation report also includes evidence mapping showing the source document, page, section, and source text associated with major generated fields.

## Testing

Run the test suite using:

```bash
pytest
```


