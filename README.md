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


