# Medical QA Bot (MediQA Bot API)

A Production-Ready Medical Question-Answering API using **Qdrant Hybrid Search** (Dense PubMedBERT + FastEmbed BM25) and **LangGraph Self-Corrective RAG (CRAG)** with **Gemini 2.5 Flash** / OpenAI.

---

## ⚡ Self-Corrective RAG (CRAG) Workflow & Action Tracing

```
                  [START]
                     │
                     ▼
           ┌───────────────────┐
           │   Generate Query  │ (Context-Aware Query Formulation)
           └─────────┬─────────┘
                     │
                     ▼
           ┌───────────────────┐
           │  Hybrid Retrieve  │ (Qdrant Dense PubMedBERT + FastEmbed BM25 + RRF)
           └─────────┬─────────┘
                     │
                     ▼
        ┌─────────────────────────┐
        │ Grade Document Relevance│ (Evaluates retrieved passages)
        └────────────┬────────────┘
                     │
     ┌───────────────┴───────────────┐
     │ Relevant?                     │ Irrelevant?
     ▼                               ▼
┌──────────────────┐       ┌────────────────────┐
│  Generate Answer │       │ Query Rewrite Node │ (Rewrites query & retries search)
└────────┬─────────┘       └─────────┬──────────┘
         │                           │
         ▼                           └─────────► (Loop back to Retrieve)
┌────────────────────────────────┐
│ Grade Answer (Self-Correction) │ (Validates Groundedness & Relevance)
└────────┬───────────────────────┘
         │
  ┌──────┴──────┐
  │ Grounded &  │
  │ Useful?     ▼
  └──────────► [END] (Returns Validated Evidence-Based Answer)
```

### 🗣️ Multi-Turn Follow-Up Questions (`session_id`)
LangGraph maintains conversation state per session using `MemorySaver()`. To ask a follow-up question (e.g. *"What are the treatments for it?"*), pass the same `session_id` in your request. LangGraph resolves pronouns and context automatically!

---

## 📁 Project Architecture

```
MediQA Bot/
├── app/
│   ├── config.py             # Centralized settings & environment loading
│   ├── schemas.py            # Pydantic request & response models (includes execution_trace & session_id)
│   ├── services/
│   │   ├── search_service.py # Qdrant vector DB, PubMedBERT + FastEmbed BM25, RRF search
│   │   └── agent_service.py  # LangGraph CRAG state machine + MemorySaver + 429 LLM Fallback
│   └── routers/
│       ├── health.py         # GET /api/v1/health
│       ├── search.py         # POST /api/v1/search
│       ├── qa.py             # POST /api/v1/ask (LangGraph CRAG with Session Memory)
│       └── ingest.py         # POST /api/v1/ingest
├── main.py                   # Clean FastAPI application entrypoint
├── dataset/                  # Medical QA dataset (medquad.csv)
└── README.md
```

---

## 🚀 API Endpoints

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| **`GET`** | `/` | API Root & Documentation URL |
| **`GET`** | `/api/v1/health` | Health Check (Qdrant connection & dataset count) |
| **`POST`** | `/api/v1/search` | Execute Hybrid Vector Search (Dense + BM25 + RRF) |
| **`POST`** | `/api/v1/ask` | Ask AI Agent (LangGraph CRAG + Session Memory + Action Tracing) |
| **`POST`** | `/api/v1/ingest` | Trigger dataset indexing into Qdrant |

---

## 🛠️ Quick Start

1. **Install Dependencies**
   ```bash
   uv sync
   ```

2. **Start FastAPI Application**
   ```bash
   python main.py
   # Or with Uvicorn:
   uvicorn main:app --reload --port 8000
   ```

3. **Interactive Swagger Documentation**
   Navigate to [http://localhost:8000/docs](http://localhost:8000/docs) in your browser.
