# Deploying on Vercel (free Hobby plan)

Branch `vercel` runs the same app as Cloud Run with three differences.

- **Frontend:** `vercel.json` builds `frontend/`, and `main.py` serves `frontend/dist` from inside the function, as on Cloud Run. (A `public/` folder produced by the build command was not served.)
- **Models:** `vercel_models/` holds the two fastembed models (64MB, copied out of the Docker image with symlinks resolved), because the function filesystem is read-only. `main.py` points `FASTEMBED_CACHE_PATH` at it when `VERCEL` is set.
- **Limits:** Vercel cannot cap instances, so the answer cache and the per-IP rate limit are per instance. Keep the LLM on Gemini's free tier (or set a hard OpenAI budget) so a flood of requests cannot cost money.

Environment variables (Project Settings): `DATABASE_URL`, `V2_QDRANT_URL`, `V2_QDRANT_API_KEY`, `V2_LLM`, `GEMINI_API_KEY`, `V2_MIN_DENSE`, `TRUSTED_PROXY_COUNT=1`.
Do not set `DB`: it overrides `DATABASE_URL`.
