````markdown
# 🏥 MediGaurd RAG

### Secure, Role-Aware Hospital Intelligence Assistant with Hybrid RAG

MediGaurd RAG is a secure hospital intelligence assistant built for the **Code Carnival Hackathon**. It combines a cleaned synthetic hospital database derived from **Synthea** with live PDF uploads into one unified, role-aware, citation-grounded RAG system.

> 🔐 **Core Principle: Unauthorized information must never be retrieved and sent to the LLM.**

**Team:** Nikhil Mugali (Lead) · Prince Naliyapara · Titli Rajdev · Nanditi Joshi  
**Repository:** https://github.com/NikhilMMugali/MediGaurd-RAG.git

---

## 🚨 Problem Statement

> **Secure Multi-Modal RAG System with Access Control**

Hospitals contain sensitive information across structured databases, clinical records, financial systems, and documents. A useful AI assistant must not only answer questions accurately, but also ensure that a user can **never access information outside their authorization scope**.

### Traditional RAG

```text
User Query
    ↓
Retrieve Everything
    ↓
Send Everything to LLM
    ↓
Ask LLM to Hide Restricted Data
    ↓
Answer
````

This is unsafe because restricted information may already have entered the LLM context.

### MediGaurd

```text
User Query
    ↓
Authenticate
    ↓
Authorize
    ↓
Classify Query
    ↓
Apply Retrieval Filter
    ↓
Retrieve ONLY Authorized Data
    ↓
Send Authorized Context to LLM
    ↓
Generate Grounded Answer
    ↓
Citations + Audit Log
```

> **MediGaurd enforces security before retrieval, not after generation.**

---

## 💡 What MediGaurd Solves

MediGaurd provides a single hospital intelligence assistant while enforcing different access boundaries for different users.

| Role          | Access                                                                                                                  |
| ------------- | ----------------------------------------------------------------------------------------------------------------------- |
| **DOCTOR**    | Assigned patient clinical information, conditions, medications, allergies, observations, procedures, relevant documents |
| **NURSE**     | Assigned patients, assigned wards, limited clinical information                                                         |
| **FINANCE**   | Claims, expenses, payers, financial transactions                                                                        |
| **RECEPTION** | Patient information, encounters, operational/visit information                                                          |
| **ADMIN**     | Authorized hospital-wide access                                                                                         |

The backend verifies the stored account role. A frontend-selected role is never trusted by itself.

---

# 🧠 Main Innovation — Hybrid RAG

MediGaurd does **not** use vector search for every question.

Instead, a query classifier determines the most appropriate retrieval strategy.

### Structured Queries → SQL

Examples:

```text
"What is the age of patient P001?"
"What medications does P001 take?"
"When was P001's last encounter?"
"What is the outstanding amount for P001?"
```

These use deterministic database retrieval.

### Semantic Queries → Qdrant + LLM

Examples:

```text
"What clinical patterns are visible in P001's recent history?"
"What relevant risks appear in this patient's recent clinical history?"
```

These use semantic retrieval and LLM reasoning.

### Complex Queries → Hybrid

Questions requiring both exact facts and contextual understanding can combine SQL + Qdrant.

### Hybrid RAG Flow

```text
                     USER QUERY
                          ↓
                  QUERY CLASSIFIER
                          ↓
          ┌───────────────┼───────────────┐
          ↓               ↓               ↓
      Structured        Summary         Semantic
          ↓               ↓               ↓
         SQL             SQL            Qdrant
          └───────────────┼───────────────┘
                          ↓
                AUTHORIZED CONTEXT
                          ↓
                         LLM
                          ↓
                  GROUNDED ANSWER
                          ↓
                      CITATIONS
```

### Why Hybrid RAG?

| Traditional Vector RAG                  | MediGaurd Hybrid RAG                           |
| --------------------------------------- | ---------------------------------------------- |
| Vector search for almost everything     | Retrieval selected by query intent             |
| Exact facts may be approximate          | Exact facts come directly from SQL             |
| Unnecessary semantic search             | Semantic retrieval only when useful            |
| More unnecessary LLM usage              | LLM used where reasoning adds value            |
| Less transparent                        | Clear retrieval path + citations               |
| Authorization is harder to reason about | Authorization enforced on every retrieval path |

> **MediGaurd treats retrieval as a decision problem, not just a similarity-search problem.**

---

# 🔍 Query Flow

Every question follows the same security-first pipeline:

```text
User Query
    ↓
Authentication
    ↓
Build Authorization Context
    ↓
Query Classification
    ↓
Determine Allowed Record Types
    ↓
Apply Role / Patient / Ward / Department Access
    ↓
┌─────────────────────────────────────┐
│ Structured SQL OR Qdrant OR Hybrid │
└─────────────────────────────────────┘
    ↓
Authorized Context ONLY
    ↓
LLM
    ↓
Grounded Answer
    ↓
Citation Validation
    ↓
Audit Log
```

### Example

A doctor is assigned to **P001** but not **P050**.

If the doctor asks:

```text
"What medications does P050 take?"
```

MediGaurd does:

```text
Question
   ↓
Authorization Context
   ↓
P050 outside assigned scope
   ↓
DENY
   ↓
No SQL retrieval
No Qdrant retrieval
No LLM context
```

The system does **not** retrieve the restricted record and ask the LLM to hide it.

---

# 📄 PDF → Unified Knowledge Pipeline

MediGaurd supports live PDF ingestion.

Uploaded PDFs do not remain isolated documents. They are transformed into the same canonical knowledge system used by the hospital database.

```text
PDF Upload
    ↓
File Validation
    ↓
Text Extraction
    ↓
Schema Mapping
    ↓
Validation
    ↓
Canonical Database Records
    ↓
Knowledge Records
    ↓
Chunking
    ↓
Embeddings
    ↓
Qdrant
    ↓
Immediately Queryable
```

### Unified Data Flow

```text
Synthea / Hospital Database
            +
       Uploaded PDFs
            ↓
    Unified Knowledge Layer
            ↓
     Unified Authorization
            ↓
      Unified Retrieval
            ↓
            LLM
            ↓
    Grounded Answer + Sources
```

---

# 🧬 Data Architecture

The active demo dataset is a deterministic **100-patient cleaned subset** derived from Synthea.

* Raw sample: approximately 108 patients
* Active dataset: **100 patients**
* Source tables: **18 CSV files**
* Display IDs: `P001` → `P100`
* Sensitive identifiers removed from active RAG representations
* Relationships between records preserved
* Clinical, operational, and financial data retained

### Canonical Model

```text
Patients
   ├── Encounters
   ├── Conditions
   ├── Medications
   ├── Allergies
   ├── Observations
   ├── Procedures
   ├── Immunizations
   ├── Imaging
   ├── Claims
   └── Other Hospital Records
```

---

# 🔐 Authorization Architecture

Authorization is based on:

```text
User
 ├── Role
 ├── Department
 ├── Ward
 ├── Assigned Patients
 ├── Allowed Record Types
 └── Document Access
          ↓
Authorization Context
          ↓
Retrieval Filter
      ┌───────┴────────┐
      ↓                ↓
     SQL             Qdrant
   WHERE              FILTER
      └───────┬────────┘
              ↓
      Authorized Data ONLY
```

### Structured Retrieval

Authorization conditions are applied before SQL records are returned.

### Semantic Retrieval

Authorization filters are passed directly into the Qdrant search before retrieval.

> **Unauthorized information never enters the LLM context.**

---

# 📚 Citation-Grounded Answers

Every factual claim in a response is grounded in an actual source.

Possible sources include:

* Database records
* Uploaded documents
* PDF pages
* PDF sections
* Stored provenance metadata

MediGaurd also validates citations so the model cannot freely invent arbitrary source identifiers.

---

# 📝 Audit Logging

Every query can be traced through an audit trail containing:

```text
User
Role
Query
Authorization Outcome
Retrieved Sources
Retrieval / Answer Path
```

This provides visibility into both the security decision and the information used to generate the answer.

---

# 🏗️ System Architecture

```text
                    ┌──────────────────────┐
                    │    React Frontend    │
                    │   React 19 + Vite    │
                    │     TypeScript       │
                    └──────────┬───────────┘
                               ↓
                    ┌──────────────────────┐
                    │    FastAPI Backend   │
                    ├──────────────────────┤
                    │ Authentication       │
                    │ Authorization         │
                    │ Query Classification │
                    │ Hybrid RAG            │
                    │ PDF Ingestion        │
                    │ Audit Logging        │
                    └───────┬───────┬──────┘
                            │       │
                            ↓       ↓
                  ┌────────────┐  ┌──────────────┐
                  │ PostgreSQL │  │    Qdrant    │
                  │ / SQLite   │  │ Vector +     │
                  │            │  │ Metadata     │
                  └────────────┘  └──────┬───────┘
                                         ↓
                               ┌──────────────────┐
                               │ Sentence         │
                               │ Transformers     │
                               │ all-MiniLM-L6-v2 │
                               └────────┬─────────┘
                                        ↓
                               ┌──────────────────┐
                               │     Groq LLM     │
                               │   gpt-oss-120b   │
                               └──────────────────┘
```

---

# ⚙️ Technical Stack

| Layer               | Technology                               |
| ------------------- | ---------------------------------------- |
| Frontend            | React 19, TypeScript, Vite               |
| UI                  | Tailwind CSS, Radix UI, lucide-react     |
| Routing / Rendering | React Router, react-markdown, remark-gfm |
| Backend             | FastAPI, Python 3.12                     |
| ORM                 | SQLAlchemy 2.0                           |
| Authentication      | JWT + bcrypt                             |
| Database            | PostgreSQL                               |
| Local Development   | SQLite                                   |
| Vector Database     | Qdrant                                   |
| Embeddings          | Sentence Transformers                    |
| Embedding Model     | `all-MiniLM-L6-v2`                       |
| LLM                 | Groq `gpt-oss-120b`                      |
| PDF Processing      | PyMuPDF + pdfplumber                     |
| Testing             | Pytest                                   |
| Infrastructure      | Docker Compose                           |

> PostgreSQL is the intended database architecture; SQLite may be used for local development/testing when PostgreSQL or Docker is unavailable.

---

# 🎯 Problem Statement Mapping

| Requirement                     | MediGaurd Implementation                                    |
| ------------------------------- | ----------------------------------------------------------- |
| Mixed data ingestion            | Structured hospital records + PDF ingestion                 |
| Unified vector + metadata index | Knowledge records + Qdrant                                  |
| Row/document-level access       | Role + patient + ward + department + document authorization |
| Retrieval-layer authorization   | SQL filters + pre-search Qdrant filters                     |
| Natural-language queries        | Query classification + Hybrid RAG                           |
| LLM/embedding pipeline          | Sentence Transformers + Qdrant + Groq                       |
| Citation grounding              | Record/page/section citations                               |
| Hallucination reduction         | Deterministic SQL + grounded semantic RAG                   |
| Auditability                    | Query audit logs                                            |

> OCR and full image-based multimodal processing are planned future enhancements.

---

# 🧪 Security & Testing

MediGaurd validates both access and denial scenarios:

```text
DOCTOR
 ├── Authorized patient → ALLOW
 └── Unauthorized patient → DENY

NURSE
 ├── Authorized ward/patient → ALLOW
 └── Unauthorized scope → DENY

FINANCE
 ├── Financial query → ALLOW
 └── Clinical query → DENY

RECEPTION
 ├── Operational query → ALLOW
 └── Restricted clinical query → DENY

ADMIN
 └── Authorized hospital-wide access
```

Testing also covers:

* Role verification
* Retrieval-level authorization
* Unauthorized retrieval prevention
* PDF ingestion
* New-document queryability
* Citation grounding
* Qdrant retrieval
* Audit logging

---

# 🚀 Demo Flow

```text
Login as DOCTOR
      ↓
Select P001
      ↓
Ask exact clinical question
      ↓
Show SQL retrieval + citation
      ↓
Ask contextual clinical question
      ↓
Show semantic retrieval + citation
      ↓
Ask unauthorized financial question
      ↓
Show DENIED access
      ↓
Upload new patient PDF
      ↓
PDF enters unified knowledge system
      ↓
Ask question about uploaded document
      ↓
Show PDF page / section citation
```

---

# 💬 Sample Questions

```text
What conditions does patient P001 have?
```

```text
What medications is P001 currently taking?
```

```text
When was P001's last encounter?
```

```text
What is the outstanding amount for P001?
```

```text
Summarize P001's recent clinical history.
```

---

# 👤 Demo Accounts

| Username      | Role      | Password       |
| ------------- | --------- | -------------- |
| `doctor01`    | DOCTOR    | `medigaurd123` |
| `nurse01`     | NURSE     | `medigaurd123` |
| `finance01`   | FINANCE   | `medigaurd123` |
| `reception01` | RECEPTION | `medigaurd123` |
| `admin01`     | ADMIN     | `medigaurd123` |

> ⚠️ These are hackathon/demo credentials only. Never use them in production.

---

# 🛠️ Setup

## Backend

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
cp .env.example .env
```

## Database

```bash
docker compose up -d postgres qdrant
alembic -c backend/alembic.ini upgrade head
```

## Prepare Dataset

```bash
cd backend
python ../scripts/build_clean_dataset.py
python ../scripts/validate_clean_dataset.py
python ../scripts/seed_users.py
python ../scripts/import_synthea.py
python ../scripts/seed_authorization_data.py
python ../scripts/generate_knowledge_records.py
python ../scripts/index_knowledge.py
```

## Run Backend

```bash
uvicorn app.main:app --reload
```

Health check:

```bash
curl http://127.0.0.1:8000/health
```

## Run Frontend

```bash
cd frontend
npm install
cp .env.example .env
npm run dev
```

Open:

```text
http://localhost:5173
```

Environment variables are documented in `.env.example`.

---

# 🔮 Future Scope

```text
Scanned PDFs
    ↓
OCR
    ↓
Medical Image Understanding
    ↓
Multimodal Embeddings
    ↓
Hybrid Lexical + Dense Retrieval
    ↓
Reranking
    ↓
Multi-Hospital / Multi-Tenant Isolation
```

Future versions can extend MediGaurd from structured data + text documents toward a complete multimodal hospital intelligence platform.

---

# 📚 Documentation

* [PRD](docs/PRD.md)
* [Requirements](docs/REQUIREMENTS.md)
* [Project Requirements](docs/PROJECT_REQUIREMENTS.md)
* [Architecture](docs/ARCHITECTURE.md)
* [System Architecture](docs/SYSTEM_ARCHITECTURE.md)
* [Data Model](docs/DATA_MODEL.md)
* [Database Schema](docs/DATABASE_SCHEMA.md)
* [Data Flow](docs/DATA_FLOW.md)
* [RAG Design](docs/RAG_DESIGN.md)
* [Security](docs/SECURITY.md)
* [Security Model](docs/SECURITY_MODEL.md)
* [API Specification](docs/API_SPECIFICATION.md)
* [Tech Stack](docs/TECH_STACK.md)
* [Progress](progress/PROGRESS.md)
* [TODO](progress/TODO.md)
* [Engineering Decisions](progress/DECISIONS.md)

---

# ⭐ What Makes MediGaurd Different?

### 1. Authorization Before Retrieval

Security is enforced at the retrieval layer, ensuring unauthorized information does not enter the LLM context.

### 2. Hybrid RAG

Exact questions use structured SQL, contextual questions use semantic Qdrant retrieval, and complex questions can combine both.

### 3. Unified Knowledge

Synthea records and uploaded PDFs are brought into the same canonical knowledge and authorization system.

### 4. Citation-Grounded AI

Answers are connected to actual database records or document sources.

### 5. Auditable Intelligence

Every query has an authorization decision and retrieval trail.

---

# 🏆 Final Summary

> **MediGaurd RAG is a secure hospital AI assistant that combines structured database retrieval with semantic RAG while enforcing authorization before retrieval, ensuring sensitive information never reaches the LLM unless the user is authorized to access it.**

```
```
