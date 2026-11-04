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
