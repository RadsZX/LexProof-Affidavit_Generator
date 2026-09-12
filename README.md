LexProof-Affidavit Generator
It is a Streamlit-based application that generates an Affidavit from structured case information while preserving the structure of a predefined affidavit format. The system validates the input, extracts case entities and reply points, maps the information to the reference structure, generates the affidavit, and evaluates the generated document using deterministic checks.

Workflow:
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
          ┌───────┴───────┐
          │               │
        Failed           Passed
          │               │
          ▼               ▼
       Stop         DOCX Generation
                          │
                          ▼
                    Evaluation
                          │
                          ▼
              Evaluation Report
              
Steps to run locally:-

1.Clone the repository

2.Create virtual environment
   python -m venv .venv 
   .\.venv\Scripts\Activate.ps1  

3.Install dependencies
   pip install -r requirements.txt

4.Start Streamlit Application
   python -m streamlit run app.py
