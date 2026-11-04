# Deploying MediQA v2

## Where it actually runs: Cloud Run

**https://medai-19247955175.europe-west1.run.app** (service `medai`, project `oneevent-485310`, europe-west1; public).
1 GiB memory, 1 CPU, 0 to 3 instances, 300 s timeout. The OpenAI key, Qdrant key and Neon URL are Secret Manager secrets
(`mediqa-openai-key`, `mediqa-qdrant-key`, `mediqa-database-url`); the Qdrant cluster URL is a plain variable. The index
is the `mediqa_v2` collection on the Qdrant Cloud cluster (47,478 points, copied from the local one in about 16 minutes;
v1's `medical_knowledge_base_hybrid` collection sits next to it, untouched). The database is the Neon `medical_db` that
v1 used: v2 only adds one optional column, `rag_query_logs.extra`, and v1's rows are untouched.

- **Redeploy by hand, if the pipeline is not set up or is down** (keeps the settings, secrets and variables already on the service):
  `gcloud run deploy medai --project oneevent-485310 --region europe-west1 --source .`
- **Take it offline:** `gcloud run services remove-iam-policy-binding medai --project oneevent-485310 --region europe-west1 --member=allUsers --role=roles/run.invoker`
- **Roll back:** after a second revision exists, `gcloud run services update-traffic medai --project oneevent-485310 --region europe-west1 --to-revisions=REVISION=100` (`gcloud run revisions list --service medai ...` shows the names).
- Cloud Run reserves the `/healthz` path (it answers 404 from outside); it checks the port instead, and `/api/v2/health` is the real health check.
- Verified before it was made public: private by default (403), health with Qdrant Cloud connected and all points, a real answer with
  sources saved to Neon, the rate limit (429 after 5 questions a minute, and a forged `X-Forwarded-For` does not get around
  it), no errors in the logs.
- Known gaps: `/api/v2/health` shows the Qdrant cluster hostname to anyone; no billing alert is set; no uptime check.

## Deploying from GitHub (CI/CD)

`.github/workflows/ci.yml` tests and then deploys. On every push to `main`, or a manual run (Actions > CI > Run workflow,
pick the branch), once lint and the tests pass the `deploy` job: builds the image and pushes it to Artifact Registry,
deploys it as a **new revision with no traffic** and its own test URL, checks `/api/v2/health` and the UI title on that URL,
and only then sends it the traffic. A build that fails its check never serves a visitor. The service's memory, scaling,
secrets and variables are left as they are (they are not in GitHub).

**No Google key is stored in GitHub.** The job logs in with a short-lived token (Workload Identity Federation), and only
this repository can get one.

**One-time setup, which you run yourself** (it changes IAM; the pipeline cannot do it for itself):

```bash
DRY_RUN=1 bash scripts/setup-github-deploy.sh   # prints the 11 commands it would run; changes nothing
bash scripts/setup-github-deploy.sh             # does it, and sets the two GitHub variables with gh
```

It creates a `github-deployer` service account that may deploy only the `medai` service (not `oneevent-backend`), push
only to the one image repository, and run revisions as the service's own identity; and a trust that accepts tokens from
`emmapraise/medAi` only. The two GitHub *variables* it sets (`GCP_WORKLOAD_IDENTITY_PROVIDER`, `GCP_SERVICE_ACCOUNT`) are
IDs, not secrets. Until they exist the deploy job stops at its first step with a message saying so.

**Getting v2 deployed this way:** `main` on GitHub is still v1 and `v2` has not been pushed. Either push `v2` and run
the workflow on it by hand, or merge `v2` into `main` (that removes v1's `/api/v1/ask`, `/search`, `/ingest` and `/feedback`
endpoints) and let the push deploy.

**Checked here:** the workflow passes `actionlint`; the setup script passes a dry run and `bash -n`; and the test that
finds the candidate URL and smoke-tests it was run against the live service (it found the URL, both checks passed, and
the tag was removed). **Not checked:** the pipeline itself has never run on GitHub, and the setup script has not been run
for real.

Old images pile up in Artifact Registry (about 875 MB each, with 0.5 GB free); add a cleanup policy that keeps the last
few when it starts to matter.

## Hugging Face Spaces: needs PRO

The sections below were written for a Hugging Face Space. Creating a Docker Space on the free CPU tier is refused
(HTTP 402: "hosting Gradio and Docker Spaces on free cpu-basic requires a PRO subscription"), so it was not used.
Keep them only if you subscribe to PRO. The Qdrant, Neon and image details apply to any host.

Each step below says what was verified locally and what was not.

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

## Cutting over from v1

v1 keeps running on Cloud Run from `main`, untouched. Run v2 on the Space next to it, compare, then merge `v2` into
`main` and redeploy Cloud Run from the same Dockerfile. The merge removes v1's `/api/v1/ask`, `/search`, `/ingest` and
`/feedback` endpoints, so check nothing else calls them first.
