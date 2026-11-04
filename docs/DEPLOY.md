# Deploying MediQA v2

Target: a **Hugging Face Space (Docker)**. Cloud Run works with the same image (see the end). Nothing here has been
deployed yet: each step says what was verified locally and what was not.

## What runs where

| Piece | Where | Why |
|---|---|---|
| App (API + web UI) | Hugging Face Space, free CPU: 2 vCPU, 16 GB RAM | The container uses about 380 MB (measured in the container after answering a question). The Space sleeps after 48 h without visits and wakes on the next visit. Its disk is wiped on restart. |
| Search index | Qdrant Cloud, free cluster | The index is 175 MB on disk; the free tier is 1 GB. |
| Conversations + analytics | Neon, free Postgres | The Space's disk is wiped on restart, so SQLite would lose everything. |
| Answers | OpenAI (or Gemini) | About $0.0002 per question with `gpt-4o-mini`. |

## Steps

1. **Qdrant Cloud:** create a free cluster. Note its URL and API key.

2. **Copy the index** from your local Qdrant (no re-embedding). Verified against a second local Qdrant: 47,478 points in
   26 seconds, and the 105-case eval scored identically on the copy. `collection_names` matters: your local Qdrant also
   holds other projects' collections.

   ```bash
   uv run python - <<'PY'
   from qdrant_client import QdrantClient, models
   from qdrant_client.migrate import migrate

   src = QdrantClient(url="http://localhost:6333", timeout=60)
   dst = QdrantClient(url="https://YOUR-CLUSTER.cloud.qdrant.io", api_key="YOUR-KEY", timeout=60)
   migrate(src, dst, collection_names=["mediqa_v2"], recreate_on_collision=True, batch_size=500)
   dst.create_payload_index("mediqa_v2", "kind", models.PayloadSchemaType.KEYWORD)  # migrate() does not copy indexes
   print(src.count("mediqa_v2").count, dst.count("mediqa_v2").count)
   PY
   ```

   Not tested against the real cloud (TLS and the API key). To rebuild from the dataset instead:
   `V2_QDRANT_URL=... V2_QDRANT_API_KEY=... make ingest` (about 40 minutes on CPU; needs `dataset/medquad.csv`).

3. **Neon:** create a project and copy the connection string (it ends with `?sslmode=require`). The app creates its
   tables on first start.

4. **Create the Space:** huggingface.co/new-space, SDK **Docker**, hardware **CPU basic**. `README.md` already carries
   the Space header (`sdk: docker`, `app_port: 7860`).

5. **Settings → Variables and secrets** on the Space:

   | Name | Kind | Value |
   |---|---|---|
   | `OPENAI_API_KEY` | secret | your key (or `GEMINI_API_KEY` and variable `V2_LLM=gemini`) |
   | `DATABASE_URL` | secret | the Neon connection string |
   | `V2_QDRANT_API_KEY` | secret | the Qdrant Cloud key |
   | `ADMIN_API_KEY` | secret | any long random string (`openssl rand -hex 32`). Without it the admin endpoints answer 503. |
   | `V2_QDRANT_URL` | variable | `https://YOUR-CLUSTER.cloud.qdrant.io` |
   | `RATE_LIMIT_QA_TIMES` | variable | `30` for now: see the first risk below |

6. **Push the code** (the Space has its own git remote):

   ```bash
   git remote add space https://huggingface.co/spaces/YOUR-USER/YOUR-SPACE
   git push space v2:main
   ```

   The Space builds the Dockerfile. The first build downloads the packages and bakes in the embedding models; watch the
   Logs tab.

7. **Check it:** open the Space; `GET /api/v2/health` should report `healthy` and 47478 points; ask a question.

## Verified locally

The image (875 MB) builds; runs as uid 1000; has no torch or pandas; loads its models with the network disabled; is
healthy about 6 seconds after `docker run`; reaches a Qdrant through `host.docker.internal`; answers a real question in
one LLM call; serves the UI. See the measured numbers in
[V2_PLAN.md](V2_PLAN.md). CI (`.github/workflows/ci.yml`) extends the workflow that was already in the repo (same backend and frontend jobs and action versions); what was added (the `v2` branch trigger, the Python 3.11 pin, the Docker build job) has not run on GitHub yet.

## Risks to check after deploying

- **Rate limit by IP.** The app limits by client IP, read from `X-Forwarded-For` counting from the right
  (`TRUSTED_PROXY_COUNT`, default 1). If the proxy in front of a Space adds more hops than that, every visitor looks
  like one IP, and the default of 5 questions a minute would limit the whole site. That is why step 5 raises it. Check a
  few requests from different networks before trusting it.
- **Cold start after sleep.** Start-up loads the models: about 10 seconds on a laptop, probably longer on a shared CPU.
- **Memory resets on restart:** the answer cache, rate-limit counters and topic list are in memory.
- **Secrets** reach the app as environment variables; confirm in the Space settings that they are set as secrets, not
  public variables.
- **Not updated for v2:** `docker-compose.yml`, and the README body (it still describes v1).

## Cloud Run instead

The image reads `PORT` (Cloud Run sets it), so `gcloud run deploy --source .` works. Give it at least 1 GiB of memory
and the same environment variables and secrets. Not tried.

## Cutting over from v1

v1 keeps running on Cloud Run from `main`, untouched. Run v2 on the Space next to it, compare, then merge `v2` into
`main` and redeploy Cloud Run from the same Dockerfile. The merge removes v1's `/api/v1/ask`, `/search`, `/ingest` and
`/feedback` endpoints, so check nothing else calls them first.
