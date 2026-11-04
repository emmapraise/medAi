# MediQA Bot v2 — Plan

## Why v2 (what the v1 code tells us)

| Finding in v1 | Consequence |
|---|---|
| `/ask` is a blocking call running ~5–7 sequential LLM calls (generate_query → grade_docs → generate → grade_grounded + grade_useful, plus rewrite loops) | Slow (many seconds of blank screen), expensive, rate-limit-prone on free Gemini tier |
| Dense text is `question + " " + answer`, but MedQuAD answers are long and BERT-class models cap at 512 tokens | Most of each answer is silently truncated before embedding. Retrieval quality bug |
| `sentence-transformers` imports torch just to run ONNX | ~300–400MB of wasted RAM; ~900MB total |
| 110M-param model, 768-dim | Heavy RAM, 2x Qdrant storage |
| No eval set; tests only cover API plumbing, caching, rate limiting | Can't prove v2 is better than v1, or catch regressions |
| Sessions live in browser localStorage; no accounts | No sync across devices |
| LangChain + LangGraph + OpenAI + Gemini SDKs for a mostly linear flow with one loop | Big dependency/import footprint, hard to stream |
| No medical safety layer (emergency red flags, "no evidence found" abstain) | Real risk for a medical product |

## v2 goals (measurable)

- Peak RAM **< 300MB** (v1: ~900MB) so it fits free tiers
- LLM calls per question **≤ 2** (v1: 5–7); cost per question down ~70%
- **Time to first token < 2s**, answer streamed
- Retrieval hit@5 and answer groundedness **≥ v1** on the same eval set
- Every answer cites its NIH source with a link

## Phase 0 — Foundations (do first, nothing else starts without it)

1. Branch `v2`; new Qdrant collection `medquad_v2` so v1 stays live and both can be compared.
2. **Eval harness** (`eval/`): ~100 golden questions (mix: direct, follow-up, typo'd, out-of-scope, emergency). Metrics: retrieval hit@1/5/MRR, groundedness (LLM judge, run offline only), abstain correctness, latency, tokens. Run it against v1 to record the baseline numbers.
3. Repo layout decision (see Decisions below).

## Phase 1 — Retrieval core

- Dense model via `fastembed` (ONNX, no torch): start with `BAAI/bge-small-en-v1.5` (384-dim); candidates compared on the eval set: arctic-embed-xs, MiniLM-L6, current PubMedBERT.
- **Chunk answers** by section/sentence window (~200 tokens) and embed each chunk with its question/focus_area as a prefix; keep parent answer id in payload. This fixes the truncation problem.
- Keep BM25 sparse + RRF fusion. Add payload index on `focus_area`/`source` for filtered search.
- Optional small cross-encoder reranker (fastembed rerank, ~80MB) only if the eval shows a gain; replaces LLM document grading.
- Ingestion script becomes a standalone CLI (`python -m mediqa.ingest`), not auto-run on app startup.

## Phase 2 — Agent v2 (fewer calls, streaming)

Replace the 5–7-call CRAG chain with:

1. **Query resolve** (1 cheap call, *only* when there is chat history; skip for first turn).
2. **Retrieve + rerank**; relevance decided by score threshold, not an LLM.
3. **Generate** with structured output (JSON: answer, citations[], confidence, follow_up_suggestions[]) and **stream** tokens.
4. **Low confidence / no good chunks** → abstain with "I couldn't find this in NIH sources" instead of guessing; one optional query rewrite + retry.
5. Groundedness check becomes an *offline eval metric*, not a per-request call.

Use the Gemini SDK directly with Pydantic schemas; drop LangChain/LangGraph unless we decide to keep it (see Decisions).

## Phase 3 — Medical safety layer

- Emergency red-flag detector (chest pain, stroke signs, suicidal ideation, overdose…) answered with a fixed, non-LLM message and local emergency guidance.
- Persistent "informational, not medical advice" notice; out-of-scope refusal (dosing for individuals, diagnosis).
- Source attribution on every claim; show the NIH source name and link.
- Prompt-injection hardening on user text and retrieved text.

## Phase 4 — API v2

- `/api/v2/ask` streaming via **SSE** (events: `status`, `token`, `citations`, `done`); async endpoints.
- Server-side sessions in Postgres (optional anonymous login later) so history survives device change.
- Keep: rate limiter, admin key, caching, health checks. Cache by normalized question so repeat questions cost nothing.
- Langfuse tracing stays optional (env-gated).
- Tests: unit (retrieval, safety rules), API tests, and the eval harness as a CI gate.

## Phase 5 — UI v2

Redesign, mobile-first, same PWA shell.

- Streaming answer with inline citation chips; tap to open a **source drawer** with the NIH passage.
- Follow-up suggestion chips under each answer.
- Starter questions and a **topic explorer** (browse by `focus_area`) on the empty state.
- Clear confidence / "not found in sources" states instead of the current trace dump; trace moves behind a "How I answered" toggle.
- Light/dark theme, keyboard + screen-reader accessibility (WCAG AA), reduced motion.
- Bookmarks, copy/share/export answer, thumbs feedback with reason.
- Offline: cached past conversations and starter content via the service worker.

## Phase 6 — Extra feature candidates (pick after Phase 5)

Voice input and read-aloud · multilingual Q&A (translate in/out) · "explain simply" reading-level toggle · printable/PDF summary for a doctor visit · admin dashboard for analytics and feedback review.

## Phase 7 — Deploy & CI

- GitHub Actions: ruff, pytest, frontend build, eval gate (fail if hit@5 or groundedness drops).
- Slim Dockerfile (no torch, int8/small model baked in); target Hugging Face Spaces (free, 16GB) or Cloud Run; Qdrant Cloud free + Neon free Postgres.
- Cut over: run v1 and v2 side by side, compare on eval + real feedback, then repoint.

## Decisions needed (my recommendation first)

1. **Agent framework:** plain async Python + Gemini SDK (recommended; flow is linear, easier to stream, far fewer deps) vs keep LangGraph.
2. **Frontend stack:** keep React + Vite and add TypeScript + Tailwind (recommended) vs plain JS/CSS vs a different framework.
3. **Repo layout:** rewrite in place on the `v2` branch (recommended) vs new repo.
4. **First features after Phase 5:** which of Phase 6 do you want?

## Suggested order

Phase 0 → 1 → 2 (these three give the RAM/latency/cost wins and can be verified on the eval set) → 3 → 4 → 5 → 7 → 6.

## Phase 0 result — v1 baseline (local Qdrant, `mediqa_v1_baseline`, 105 retrieval cases)

| Kind | n | hit@1 | hit@5 | MRR@10 |
|---|---|---|---|---|
| paraphrase | 80 | 0.537 | 0.900 | 0.671 |
| typo | 15 | 0.667 | 0.933 | 0.798 |
| keyword | 10 | 0.800 | 1.000 | 0.900 |
| **ALL** | 105 | **0.581** | **0.914** | **0.711** |

Latency p50 30ms / p95 66ms (warm, 6 threads). Peak RSS ~1.1GB. Full v1 ingest: ~1h10m of CPU.

Reading the 9 misses: 8 retrieve the *right disease but the wrong question type* (e.g. "why do people get X" returns "What is X?"). v2 should target hit@1, not hit@5: chunking with a question-type signal, plus the reranker, are the likely fixes.

## Phase 1 result — v2 retriever (bge-small + BM25 + chunking, local `mediqa_v2`, 31,066 chunks)

| Kind | n | v1 hit@1 | v2 hit@1 | v1 hit@5 | v2 hit@5 | v1 MRR | v2 MRR |
|---|---|---|---|---|---|---|---|
| paraphrase | 80 | 0.537 | 0.662 | 0.900 | 0.963 | 0.671 | 0.795 |
| typo | 15 | 0.667 | 0.600 | 0.933 | **0.733** | 0.798 | 0.680 |
| keyword | 10 | 0.800 | 0.900 | 1.000 | 1.000 | 0.900 | 0.950 |
| **ALL** | 105 | 0.581 | **0.676** | 0.914 | **0.933** | 0.711 | **0.793** |

Latency p50 30ms -> 10ms. Peak RSS 1103MB -> 431MB (eval process, includes Python + both models).
Ingest: v1 ~70 min -> v2 ~60 min wall clock but with throttling stalls; clean pace is ~24 chunks/s (v1: ~4 rows/s).

Regression: typos (hit@5 0.933 -> 0.733). bge's tokenizer and BM25 both break on misspelled medical terms. Next: snap query words to the corpus vocabulary (difflib against focus_area words) before searching.

### Phase 1b — typo snapping (`fix_typos`, corpus vocabulary in `app/services/vocab.txt`)

| | v1 | v2 | v2 + typo fix |
|---|---|---|---|
| hit@1 (ALL) | 0.581 | 0.676 | 0.667 |
| hit@5 (ALL) | 0.914 | 0.933 | **0.971** |
| MRR@10 | 0.711 | 0.793 | **0.805** |
| typo hit@5 | 0.933 | 0.733 | **1.000** |

hit@1 on paraphrase/keyword moved by 1-2 cases between runs although `fix_typos` leaves those queries unchanged. Likely cause: Qdrant's HNSW index finished building between the two runs (first run was exact search). Not verified. Remaining 3 misses are all "right disease, wrong question type".
Known limit: non-medical words absent from the corpus get snapped too ("Lagos" -> "logos"); harmless for queries that should be refused anyway.
Regenerate the vocab with `python -c "from app.services.search_v2 import write_vocab; write_vocab()"` (ingest does it automatically).

### Phase 1c — question-only vectors (16,412 extra dense points, `kind: question`, own RRF list)

| | v1 | v2 + typo fix | + question vectors |
|---|---|---|---|
| hit@1 | 0.581 | 0.667 | 0.657 |
| hit@5 | 0.914 | 0.971 | **1.000** |
| MRR@10 | 0.711 | 0.805 | **0.814** |
| p50 latency | 30ms | 11ms | 14ms |

Tried first mixing question points into the single dense list: hit@5 1.0 but hit@1 fell to 0.543 (same-disease questions crowd the list). Giving them their own prefetch list fixed that.
Caveat: eval gold is the exact MedQuAD question text, which is also what these vectors embed, so this eval favours them. Real-user gain is probably smaller. Re-check once we have real queries/feedback.
Cost: +80s to build, +16k points, +3ms per search. Zero misses left in the retrieval eval.

## Phase 2 status — agent v2 (`app/agent/v2.py`)

Built: retrieve -> abstain or ONE streamed Gemini call (google-genai direct, no LangGraph/LangChain). Greetings are canned (0 calls). Follow-ups add one small query-resolve call (2 total). Answers cite `[n]`; only cited sources are returned; 3 follow-up questions come from the same call (split off the stream by a marker). 503 "high demand" is retried (3 tries, before any text is sent).
Abstain: best raw dense cosine < 0.65 (`V2_MIN_DENSE`). Eval separation: in-corpus queries >= 0.80 (one typo case 0.658), off-topic <= 0.646. Margin is thin; recalibrate when real queries exist.
Live check (2 questions that got through): 1 LLM call each, first token 0.6-1.1s, total 1.1-2.4s, ~700 prompt + 110-230 completion tokens. v1: up to 6 calls.
Tests: 5 new (stream splitter, abstain without LLM, one-call answer + cited sources, greeting).
NOT yet verified live: the follow-up (2-call) path and a typo query end to end. Gemini started returning 403 "billing account has an outstanding balance" for the key in .env.

### Phase 2 update — OpenAI provider (default when `OPENAI_API_KEY` is set; `V2_LLM=gemini` switches back)

Live results on gpt-4o-mini (typo, follow-up, "yes", off-topic all verified):
- 1 LLM call for a fresh question, 2 for a follow-up that needs the history (e.g. "what causes it?" -> "What causes glaucoma?"; "yes" -> "What are the treatments for lissencephaly?").
- First token ~3.0-4.8s, total 3.9-7.6s. Slower than Gemini (0.6-1.1s first token) and above the <2s goal. Gemini key was returning 403 (unpaid balance).
- Vague question with no history ("what causes it?") used to produce an answer mixing unrelated diseases; the system prompt now makes it ask which condition is meant (verified).
- OpenAI client timeout 30s (one request timed out once during testing; SDK retries 429/5xx twice).

## Phase 3 status — safety gate (`app/agent/safety.py`)

Rule-based, runs before search and the LLM (0 calls, instant, fixed replies). Kinds: `self_harm` (988 / findahelpline.com + emergency number), `emergency` (call local emergency number), `personal_advice` (no diagnosis / prescribing / personal dosing / stop-or-mix medicines), `injection` (ignore-instructions, system-prompt probes). Every `done` event carries `disclaimer` and `safety`.
Tests (28 in tests/test_safety.py, all from the real eval cases plus rephrasings): 8/8 eval emergencies caught, all personal-advice and injection cases caught, 0 of the 105 retrieval + 6 off-topic eval queries flagged, 8 informational questions ("what are the symptoms of a stroke?", "what is acetaminophen overdose") pass through. Prompt now says sources/questions are data, never reveal instructions.
Limits: English only; regexes were written knowing the eval cases (rephrasings added to check this, but a real red-team pass is still needed); crisis numbers are generic because user location is unknown; "suicide prevention"-style informational questions get the crisis reply (deliberate bias to safety); injection hidden inside retrieved text is mitigated by the prompt only, not tested (corpus is NIH).

## Phase 4 status — API v2 (`POST /api/v2/ask`, SSE)

`app/routers/ask_v2.py`. Events: `status`, `token`, `citations`, `done`, `error`. `done` carries the saved log `id`, `followups`, `citations`, `safety`, `disclaimer`, tokens, latency, `cached`.
- Sessions: history (last 3 turns) is read from `rag_query_logs`; each answer is saved there with a new JSON column `extra` (citations, follow-ups, safety kind, disclaimer). Session list / history / delete / feedback reuse `/api/v1/analytics/*` (history now returns `extra`). Session ids stay private capabilities, no accounts.
- Cache: first-turn questions only (a follow-up depends on the conversation); replays the stored answer as SSE with `cached: true`, 0 LLM calls. Errors, abstains and safety replies are not cached.
- Rate limit: shares the existing `/ask` limiter. Startup now warms the v2 models and creates/migrates tables (`create_all` + `ALTER ... extra`); v1 PubMedBERT is no longer preloaded (v1 endpoints load it on first use).
- Live check (real server, OpenAI, SQLite): streamed answer in small chunks, follow-up resolved via history, repeat question served from cache (0 calls), emergency handled with 0 calls, history returned with citations.
- Tests: 5 new in tests/test_ask_v2.py (event order and saved id, history persistence, cache hit, follow-ups never cached, bad session id); full suite 61 passing.
Not done: Langfuse tracing in v2, accounts/login, Postgres run (tested on SQLite only), delete of the old v1 `/ask` (Phase 7 cutover).

## Phase 5 status — UI v2 (React PWA, Apple HIG)

Built: `frontend/src` rewritten. Streaming chat (SSE) with a Stop button; answers render bold/lists and tappable `[n]` citation chips; a Sources row (44pt chips) opens a **source sheet** (modal `<dialog>`: bottom sheet with grabber, medium/large detents, swipe-down and Close on phones; side panel on wide screens; Esc closes, focus starts on Close); follow-up chips under the latest answer; topic explorer (search + common topics, `GET /api/v2/topics`, "General" bucket excluded); safety/not-found replies shown as notice cards (icon + title, not colour alone); AI-disclosure and "not medical advice" notice always reachable. Navigation: tab bar (Ask / Topics / History) on narrow screens, sidebar on wide, same destinations. System font stack for UI and body, `ui-serif` (New York on Apple devices) for headlines only; **no web fonts, so no third-party font request**. No app-level theme switch: follows light/dark, `prefers-contrast`, reduced motion and reduced transparency.
Removed vs v1: the "How it was checked" ledger (relevance/grounded/useful grades and step list). v2 no longer produces those per request; sources replace it.

HIG review of the result (measured):
- Contrast (WCAG AA, computed from the token hex values): all text pairs >= 4.5:1 in light and dark (lowest: secondary label on fill 4.73:1 light); control edges >= 3:1 (light 3.15:1, dark 3.46:1); on-accent text 5.9:1 / 8.0:1.
- Targets: of 17 interactive elements on a phone-width conversation, 15 are >= 44px. The two inline `[n]` markers are 24px with an enlarged tap area (>= 28pt) and duplicate the full-size Sources chips (trade-off, deliberate).
- 375px width: no horizontal overflow. 200% text: no overflow; on short or large-text screens the composer stacks (full-width input, send below) and the long notice moves from the pinned composer into the feed so the answer keeps the room.
- Verified live in the browser (real backend + OpenAI): streamed answer, citations, sheet (bottom and side), Esc, Close, grabber toggle, topics list and search, emergency notice, cached replay, wide layout in light mode, dark mode on phone.
Not done / not verified: bookmarks, share/export (copy only), offline cache of past conversations, feedback "reason", onboarding; swipe-down dismissal (code written, only the state logic was exercised), increased-contrast mode, VoiceOver and a real iPhone, a persisted partial answer when Stop is pressed (only completed answers are saved server-side), Postgres (SQLite only). Source passages are raw MedQuAD text (some contain page boilerplate like "Watch the animated video...").

## Phase 6 status — extras

Built (the three that are cheap and clearly useful):
- **Plain language**: a real `role="switch"` above the chat (remembered in localStorage). `AskRequest.reading_level` ("standard" | "simple") adds a 6th-grade-reading-level rule to the system prompt; the first-turn cache is keyed by level so the two never mix. Live: same question, simpler list-style answer.
- **Voice input**: a mic button using the browser's SpeechRecognition, shown only where the browser has it; fills the text box (nothing is sent until you press send); shows "Listening… your browser's speech service may process your voice" while active, and a plain message if the mic is blocked. The browser asks for microphone permission itself.
- **Save as PDF**: uses the browser's print dialog. A print stylesheet turns the conversation into a document: dated header with the notice, each question and answer, citations as superscripts, sources listed as text; nav, buttons and composer are hidden. Verified with print-media emulation.
Tests: 2 new (reading level reaches the agent, separate cache entry, invalid level rejected; the prompt rule is added only when asked). Suite: 65 passing.
Not verified: dictation with a real microphone (only that the button appears, toggles and the API exists); the real print dialog and its page margins.
Not built: **multilingual answers** (retrieval is English-only, so it needs a translate-the-query step and its own eval, not just a prompt line), **admin dashboard** (`GET /api/v1/analytics/summary` already returns the numbers as JSON).

## Auth — paused

Email + password and Google sign-in were started and are **not** in the branch: stashed as `stash@{0}` ("WIP auth (paused)"). Contents: users and login-session tables (token stored hashed), argon2id passwords, Google OIDC with PKCE, ownership checks on ask/list/history/delete, claim-anonymous-chats, account deletion, `tests/test_auth.py`. The full suite had passed (63) before the last test edit; the auth tests themselves had not been run to completion. Resume with `git stash pop`. Needs from you: `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REDIRECT_URI` (OAuth client from Google Cloud console) and a decision on password reset (needs an email provider).

## v1 unloaded from the app (memory)

Cause found by measuring: `import main` pulled in torch (via sentence-transformers) because `main.py` mounted the v1 routers, `app/agent/__init__.py` built the v1 agent eagerly, and `ask_v2` borrowed its rate limiter from the v1 `qa` router. Peak RSS (import + warm-up + one search): **847 MB -> 523 MB**. A running server process after start-up, a health check, the topic index and one chat request: **440 MB**. The "under 300 MB" goal is still not met; plan on a 512 MB host at the very least (1 GB for headroom).
Removed (still in git history): `app/agent/{service,nodes,workflow,llm_client,state}.py`, `app/services/agent_service.py`, routers `qa`, `search`, `ingest`. Kept: `app/services/search_service.py` (only for the v1 baseline in `eval/run_retrieval.py v1`). Rewritten: `GET /api/v2/health` (reads the v2 index). Gone from the API: `/api/v1/ask`, `/api/v1/search`, `/api/v1/ingest`, `/api/v1/feedback` (Langfuse), `/api/v1/health`; `/api/v1/analytics/*` stays (the UI uses it). `make ingest` now builds the v2 index.
Bug fixed on the way: when the agent failed, `v2.run` put the raw exception text into the SSE `error` event (could include connection details). It is now logged on the server and the browser gets a fixed message (test added; it replaces the v1 "errors do not leak internals" test).
Not done: the dependencies (torch, transformers, sentence-transformers, pandas, langchain*, langgraph, langfuse, ...) are still in `pyproject.toml`, so the Docker image would still install ~1 GB it never loads. Remove them in Phase 7 together with the Dockerfile rewrite (the Dockerfile still bakes the old PubMedBERT model).

## Phase 7 status — deploy and CI

Done and checked locally:
- **Dependencies:** the runtime set is 63 packages (lockfile, `--no-dev`): no torch, transformers, pandas, LangChain, Langfuse. Index building (`ingest` group: pandas) and the v1 baseline (`baseline` group: sentence-transformers, optimum, onnx, langfuse) are optional groups; `dev` includes `ingest`. pandas is imported only when indexing.
- **Dockerfile:** runs as uid 1000, listens on `PORT` (default 7860, what a Hugging Face Space expects), bakes `bge-small` + BM25 into the image. **875 MB**, down from 1.46 GB after removing a `chown -R` layer that duplicated the environment (416 MB). Verified: no torch/pandas inside, models load with the network disabled, container healthy ~6 s after start, 378 MB of memory after one question, real answer in 1 LLM call, `/api/v2/health` reads 47,478 points through `host.docker.internal`.
- **Qdrant copy** (`qdrant_client.migrate`, restricted to `mediqa_v2`): 47,478 points in 26 s into a second local Qdrant; the 105-case eval scored identically on the copy. The index is 175 MB on disk (Qdrant Cloud free tier: 1 GB). `V2_QDRANT_API_KEY` is now read for remote clusters.
- **CI:** the existing `.github/workflows/ci.yml` (backend ruff + pytest, frontend lint + build, same action versions) extended with the `v2` branch trigger, a Python 3.11 pin matching the image, and a Docker build job (no push). Valid YAML; the additions have not run on GitHub. `ruff check` passes (6 older findings fixed).
- **Docs:** `docs/DEPLOY.md` (Hugging Face Space, Qdrant Cloud, Neon, secrets, risks, Cloud Run, cutover). README got the Space header.
Not done: a real deploy (needs your Hugging Face, Qdrant Cloud and Neon accounts and keys); the eval gate in CI (needs an index); `docker-compose.yml` and the README body still describe v1; Qdrant Cloud copy not tried over TLS with an API key.

## Deployed

v2 runs on Cloud Run as `medai` (https://medai-19247955175.europe-west1.run.app, project `oneevent-485310`, europe-west1), public, with the index on Qdrant Cloud (`mediqa_v2`, 47,478 points) and the existing Neon database (v1's 18 conversations and 40 questions untouched; one optional column added). Hugging Face was ruled out: Docker Spaces on the free tier need PRO (HTTP 402). There was no v1 service left to replace (its README URL was dead), so this is a new service at the same URL. Details, redeploy, take-offline and rollback commands: `docs/DEPLOY.md`.
Open: the paused auth work (stash), README body and `docker-compose.yml` still describe v1, no CI eval gate, the public health endpoint shows the Qdrant hostname, no billing alert, and the Hugging Face token that sits in an old local commit (branch `test`) of a public repo should be rotated.

CI/CD: `.github/workflows/ci.yml` now also deploys (push to `main`, or a manual run): build and push the image, deploy a no-traffic revision, smoke-test its own URL, then shift traffic. Keyless Google login (Workload Identity Federation) via `scripts/setup-github-deploy.sh`, which the owner runs once. The first deploy of `medai` was done by hand from a laptop, before this existed. Not yet exercised on GitHub; `v2` is not pushed there.
