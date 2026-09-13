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

1.The app loads the reference format and sample affidavit.
2.The user uploads the Case Information PDF.
3.The app checks whether the uploaded PDF is the correct type of document.
4.It extracts the case details and reply points from the PDF.
5.It studies the reference affidavit format.
6.It puts the extracted information into the correct affidavit sections.
7.It checks the affidavit content before generating it.
8.If everything is valid, it generates the Affidavit in Reply as a DOCX file.
9.The generated affidavit is checked using predefined evaluation rules.
10.Finally, the app creates an evaluation report showing the score, errors, and supporting evidence.

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


