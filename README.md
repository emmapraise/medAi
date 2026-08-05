# Medical QA Bot (MediQA Bot)

A Medical Question-Answering assistant using **Qdrant Hybrid Search** (Dense PubMedBERT + Sparse BM25) and **Groq LLMs** (`llama-3.1-8b-instant`).

## Features
- **Dense Vector Search**: Powered by `NeuML/pubmedbert-base-embeddings` to capture conceptual medical meaning.
- **Sparse Vector Search**: Powered by `BM25Encoder` to capture exact medical terminology and rare conditions.
- **Reciprocal Rank Fusion (RRF)**: Merges dense & sparse results in Qdrant for optimal relevance.
- **Disk Persistence**: Saves Qdrant collections persistently in `./qdrant_storage`.
- **Tool-Augmented Medical Agent**: Uses Groq LLMs with native function calling to retrieve context and answer complex health questions.

## Setup & Prerequisites

1. **Environment Variables**  
   Ensure your `.env` file contains your Groq API key and Qdrant settings:
   ```env
   GROQ_API_KEY=your_groq_api_key
   QDRANT_HOST=localhost
   QDRANT_PORT=6333
   ```

2. **Start Qdrant Vector Database (Docker)**  
   ```bash
   docker run -d \
     --name qdrant \
     -p 6333:6333 \
     -p 6334:6334 \
     -v "$(pwd)/qdrant_storage:/qdrant/storage" \
     qdrant/qdrant:latest
   ```

3. **Install Dependencies**  
   ```bash
   uv sync
   ```

## Usage

- **Interactive Jupyter Notebook**: Open `Hybrid Search.ipynb` to run data ingestion, vector indexing, hybrid search comparisons, and the AI Medical Agent loop.
- **CLI Application**: Run `python main.py` to start an interactive terminal QA session.
