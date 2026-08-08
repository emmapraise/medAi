# 🩺 MediQA Bot — AI Medical Intelligence & Self-Corrective RAG (CRAG) PWA

[![FastAPI](https://img.shields.io/badge/FastAPI-00558C?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![React PWA](https://img.shields.io/badge/React_PWA-20232A?style=for-the-badge&logo=react&logoColor=61DAFB)](https://react.dev/)
[![LangGraph](https://img.shields.io/badge/LangGraph-FF6F61?style=for-the-badge&logo=python&logoColor=white)](https://www.langchain.com/langgraph)
[![Qdrant](https://img.shields.io/badge/Qdrant-DC2626?style=for-the-badge&logo=qdrant&logoColor=white)](https://qdrant.tech/)
[![PyTorch](https://img.shields.io/badge/PubMedBERT-EE4C2C?style=for-the-badge&logo=pytorch&logoColor=white)](https://huggingface.co/NeuML/pubmedbert-base-embeddings)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-336791?style=for-the-badge&logo=postgresql&logoColor=white)](https://www.postgresql.org/)

**MediQA Bot** is a production-ready, evidence-based Medical Question-Answering application powered by **Self-Corrective Retrieval-Augmented Generation (CRAG)** via **LangGraph**, **Qdrant Cloud Hybrid Search** (768-dim PubMedBERT Dense Vectors + FastEmbed BM25 Sparse Vectors with Reciprocal Rank Fusion), **PostgreSQL Analytics & Cost Tracking**, and a mobile-responsive **React Progressive Web App (PWA)**.

---

## 📚 Dataset Provenance & Attribution

The medical knowledge base backing MediQA Bot is built from the **MedQuAD** (Medical Question Answering Dataset):

* **Source**: Sourced from Kaggle — [MedQuAD: Medical Question Answer for AI Research](https://www.kaggle.com/datasets/pythonafroz/medquad-medical-question-answer-for-ai-research).
* **Origin**: Created by 12 National Institutes of Health (NIH) institutes (including NCI, NHLBI, NIDDK, NINDS, and MedlinePlus).
* **Coverage**: Contains 16,400+ curated medical question-answer pairs covering diseases, symptoms, causes, diagnosis, treatments, clinical trials, and procedures.
* **Vector Indexing**: The dataset is indexed into **Qdrant Cloud** using a hybrid dual-vector space:
  - **Dense Embeddings**: `NeuML/pubmedbert-base-embeddings` (768-dimensional clinical domain PubMedBERT transformer model).
  - **Sparse Embeddings**: `Qdrant/bm25` (FastEmbed BM25 sparse keyword vectors).
  - **Fusion Algorithm**: Reciprocal Rank Fusion (RRF) for combining dense semantic match scores with sparse exact keyword matches.

---

## ⚡ Architecture & Key Technical Features

```
                                  [START]
                                     │
                                     ▼
                           ┌───────────────────┐
                           │   Generate Query  │ (Context & Conversational History Resolution)
                           └─────────┬─────────┘
                                     │
                                     ▼
                           ┌───────────────────┐
                           │  Hybrid Retrieve  │ (Qdrant Cloud: PubMedBERT + BM25 + RRF)
                           └─────────┬─────────┘
                                     │
                                     ▼
                        ┌─────────────────────────┐
                        │ Grade Document Relevance│ (Evaluates retrieved passages)
                        └────────────┬────────────┘
                                     │
     ┌───────────────────────────────┴───────────────────────────────┐
     │ Relevant?                                                     │ Irrelevant?
     ▼                                                               ▼
┌──────────────────┐                                       ┌────────────────────┐
│  Generate Answer │                                       │ Query Rewrite Node │ (Rewrites query & retries)
└────────┬─────────┘                                       └─────────┬──────────┘
         │                                                           │
         ▼                                                           └─────────► (Loop back to Retrieve)
┌────────────────────────────────┐
│ Grade Answer (Self-Correction) │ (Validates Groundedness & Relevance against Hallucinations)
└────────┬───────────────────────┘
         │
  ┌──────┴──────┐
  │ Grounded &  │
  │ Useful?     ▼
  └──────────► [END] (Returns Validated Evidence-Based Answer with Interactive Follow-up Offer)
```

### 🎯 Key Capabilities:
1. **Self-Corrective RAG (CRAG)**: Evaluates retrieved medical passages before synthesis. If passages are irrelevant, it rewrites the search query and retries automatically.
2. **Hallucination & Groundedness Verification**: Evaluates generated answers in parallel to verify they are strictly supported by retrieved clinical literature.
3. **Interactive Yes/No Conversation Flow**: Prompts user with natural follow-up offers (e.g. *"Would you like to know more about treatments for HIV?"*). When the user answers with *"Yes"*, *"Sure"*, or *"Tell me more"*, the system automatically resolves the offer topic from conversation history and retrieves relevant documents.
4. **PostgreSQL Analytics & Cost Engine**: Logs every query execution trace, token consumption, latency (ms), document relevance scores, and estimated USD cost ($).
5. **Mobile-Responsive React PWA**: Features an offline-ready PWA with Service Worker (`sw.js`), web manifest, mobile slide-out drawer, past session drawer, copy answer button, and question editing capabilities.

---

## 📁 Repository Structure

```
MediQA Bot/
├── app/
├── app/agent/               # Modular LangGraph CRAG Package
│   ├── enums.py             # Strongly-typed NodeName Enum
│   ├── llm_client.py        # Gemini 2.5 Flash / OpenAI LLM Client
│   ├── nodes.py             # Graph nodes (query gen, retrieve, grade docs, generate answer, grade gen)
│   ├── service.py           # MedicalAgentService execution facade & MemorySaver state manager
│   ├── state.py             # GraphState & NodeName TypedDict
│   └── workflow.py          # StateGraph builder & conditional edge routers
├── app/routers/             # FastAPI Route Handlers
│   ├── analytics.py         # GET /analytics/summary, /logs, DELETE /sessions/{id}
│   ├── health.py            # GET /health
│   ├── ingest.py            # POST /ingest (Qdrant vector ingestion)
│   ├── qa.py                # POST /ask (LangGraph Agent Chat)
│   └── search.py            # POST /search (Direct Hybrid Vector Search)
├── app/services/            # Core Infrastructure Services
│   ├── analytics_service.py # PostgreSQL logger & cost calculator
│   └── search_service.py    # Qdrant client, PubMedBERT & BM25 hybrid search engine
├── dataset/                 # Medical QA dataset files (medquad.csv)
├── frontend/                # React Vite PWA Frontend
│   ├── src/                 # React components (DoctorChat, HybridSearch, AnalyticsDashboard, App.jsx)
│   ├── public/              # Service worker (sw.js), manifest.json, PWA icons
│   └── index.html           # Edge-to-edge mobile PWA index
├── Dockerfile               # Multi-stage Dockerfile with pre-cached PubMedBERT weights
├── pyproject.toml           # Locked UV Python dependencies
├── main.py                  # FastAPI application entrypoint with static PWA mounting
└── README.md
```

---

## 🛠️ Step-by-Step Setup Guide

Follow these instructions to clone, set up, and evaluate the project locally or in the cloud.

### Prerequisites
* **Python**: `3.11` or higher (Managed via [`uv`](https://github.com/astral-sh/uv) or standard `pip`).
* **Node.js**: `20.x` or higher & `npm`.
* **API Keys**:
  - **Gemini API Key**: Sourced from [Google AI Studio](https://aistudio.google.com/).
  - **Qdrant Vector Cloud API Key & URL**: Sourced from [Qdrant Cloud](https://cloud.qdrant.io/).

---

### Step 1: Clone the Repository

```bash
git clone https://github.com/emmapraise/medAi.git
cd "medAi"
```

---

### Step 2: Configure Environment Variables

Create a `.env` file in the root directory:

```bash
cp .env.example .env
```

Populate `.env` with your credentials:

```env
# LLM Credentials
GEMINI_API_KEY="your_gemini_api_key_here"
OPENAI_API_KEY="your_openai_api_key_optional"

# Qdrant Cloud Credentials
QDRANT_URL="https://67b23fca-0482-4a4e-9cdd-e579a9f6eced.europe-west3-0.gcp.cloud.qdrant.io"
QDRANT_API_KEY="your_qdrant_api_key_here"

# Database Connection (Defaults to SQLite fallback if PostgreSQL is unconfigured)
DATABASE_URL="postgresql://user:password@localhost:5432/medical_db"

# Server Port
PORT=8000
```

---

### Step 3: Install Backend Dependencies

Using `uv` (Recommended for fast locked installs):
```bash
uv sync
```

Or using standard `pip`:
```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

---

### Step 4: Build Frontend PWA Assets

Navigate to the `frontend/` directory, install Node packages, and build production dist assets:

```bash
cd frontend
npm install
npm run build
cd ..
```

---

### Step 5: Run the MediQA Bot Application

Launch the unified FastAPI server:

```bash
python main.py
```

The application will start at **`http://localhost:8000`**:
* 🌐 **React PWA Application**: [`http://localhost:8000`](http://localhost:8000)
* 📖 **Interactive OpenAPI Documentation**: [`http://localhost:8000/docs`](http://localhost:8000/docs)
* 🔍 **Health Check Endpoint**: [`http://localhost:8000/api/v1/health`](http://localhost:8000/api/v1/health)

---

### Step 6: Dataset Indexing into Qdrant Cloud (If Re-indexing)

To trigger Qdrant vector indexing for `dataset/medquad.csv`:

```bash
curl -X POST "http://localhost:8000/api/v1/ingest"
```
Or execute vector ingestion in Python:
```bash
python -c "from app.services.search_service import search_engine; search_engine.initialize(); search_engine.ingest_dataset('dataset/medquad.csv')"
```

---

## 🧪 Scoring & Evaluation Guide

Evaluators can verify every feature of the project using the following checks:

| Evaluation Test | Action / Endpoint | Expected Result |
| :--- | :--- | :--- |
| **1. Agent QA (CRAG)** | `POST /api/v1/ask`<br>`{"question": "What are the symptoms of Glaucoma?"}` | Returns evidence-based answer, PubMedBERT retrieval trace, relevance grade `YES`, and interactive follow-up question. |
| **2. Multi-Turn "Yes" Offer** | Send `POST /api/v1/ask`<br>`{"question": "Yes, tell me more", "session_id": "same_session"}` | Formulates query from previous history topic (e.g. `Glaucoma detection methods`) and answers seamlessly. |
| **3. Hybrid Search** | `POST /api/v1/search`<br>`{"query": "Infant hepatoblastoma"}` | Returns top 5 RRF-ranked medical passages combining PubMedBERT + BM25 score. |
| **4. PostgreSQL Logging** | `GET /api/v1/analytics/summary` | Returns total queries count, groundedness %, relevance %, and total cost ($ USD). |
| **5. Mobile PWA Responsiveness** | Open `http://localhost:8000` in mobile viewport (< 768px) | Slide-out mobile navigation drawer opens cleanly with dark backdrop blur. |

---

## 🐳 Docker Deployment & GCP Cloud Run

Build and run using Docker:

```bash
# Build Docker image (Pre-caches PubMedBERT model weights inside container image)
docker build -t mediqa-bot:latest .

# Run container locally
docker run -p 8000:8000 \
  -e GEMINI_API_KEY="your_key" \
  -e QDRANT_URL="your_qdrant_url" \
  -e QDRANT_API_KEY="your_qdrant_key" \
  mediqa-bot:latest
```

---

## 📄 License & Attribution

* **Codebase**: Open-source under MIT License.
* **Dataset Attribution**: Medical Question-Answering Dataset (MedQuAD) sourced from Kaggle ([pythonafroz/medquad-medical-question-answer-for-ai-research](https://www.kaggle.com/datasets/pythonafroz/medquad-medical-question-answer-for-ai-research)), created by NIH.
