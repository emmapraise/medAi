import os
import json
import pandas as pd
from dotenv import load_dotenv
from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer
from openai import OpenAI

load_dotenv()

def main():
    print("=========================================")
    print("      Medical QA Bot (MediQA Bot)       ")
    print("=========================================")

    QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
    QDRANT_PORT = int(os.getenv("QDRANT_PORT", 6333))
    QDRANT_URL = os.getenv("QDRANT_URL", f"http://{QDRANT_HOST}:{QDRANT_PORT}")

    try:
        client = QdrantClient(url=QDRANT_URL, check_compatibility=False, timeout=5)
        cols = [c.name for c in client.get_collections().collections]
        print(f"Connected to Qdrant at {QDRANT_URL}. Collections: {cols}")
    except Exception as e:
        print(f"Could not connect to Qdrant server at {QDRANT_URL}: {e}")
        print("Please ensure Docker Qdrant is running.")
        return

    print("\nReady! For the full hybrid search and interactive AI agent loop, open 'Hybrid Search.ipynb'.")

if __name__ == "__main__":
    main()
