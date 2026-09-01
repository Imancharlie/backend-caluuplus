# Mr Caluu Chatbot Reimplementation — Assessment & Specification

Status: Draft for review (no code changed yet)
Scope decisions (confirmed with product owner):
- Deliverable now: this written spec. Implementation begins after review.
- Infrastructure: keep SQLite for now, add Redis cache only.
- Model strategy: keep the cheap/fast model (Gemini flash) and rely on semantic RAG + response caching for accuracy, speed, and cost.
- Admin review of learned knowledge: a dedicated staff-only dashboard in the webapp.

---

## Part 1 — Assessment of the current system (baseline)

### 1.1 Request flow and where time is spent

The web app hits `POST /api/chatbot/conversations/{uuid}/send_message/`
(`webapp: src/pages/Chatbot.tsx:367`). The handler is `ChatbotViewSet.send_message`
(`backend: chatbot/views.py:95`).

Step by step (all synchronous inside the HTTP request thread):

1. `conversation = self.get_object()` — DB query (views.py:98)
2. sanitize input — fast (views.py:101-117)
3. **`with transaction.atomic():` wraps the ENTIRE flow, including the LLM call** (views.py:130)
4. `Message.objects.create(role="user", ...)` — DB write (views.py:132)
5. Create `EnhancedClaudeService()` + `VectorSearchService()` **on every request** (views.py:139-140)
6. `conversation.messages.count()` — DB query (views.py:143)
7. If a "quick" keyword matches → return DB-based text, no LLM (views.py:146-159)
8. Else AI branch:
   - RAG search `vector_service.search(...)` (views.py:183) — keyword full-DB scan on cache miss (see 1.3)
   - `enhanced_service.get_enhanced_response(...)` (views.py:219) — see 1.2
   - analytics update (views.py:230)
   - `Message.objects.create(role="assistant", content=ai_response.text, ...)` (views.py:238-244)
9. `conversation.save()` (views.py:249)
10. `time.sleep(0.005)` + `update_memory(...)` (views.py:280-281)
11. token consumption via `tokens.services.consume` (views.py:292)
12. return `ConversationSerializer(conversation)` (views.py:302)

### 1.2 Latency sources (the "loads for a long time" issue)

- **Synchronous LLM HTTP call** with 20s timeout and up to 3 retries with
  `time.sleep()` backoff — the dominant cost (~2-4s typical). Runs in the request thread
  inside `transaction.atomic()` (`enhanced_service.get_enhanced_response`).
- **Per-user blocking throttle**: `_throttle_request` sleeps `ANTHROPIC_MIN_REQUEST_INTERVAL`
  seconds (default 3s) before an AI call. A hard blocking sleep in the request thread.
- **`build_student_context(...)` runs many DB queries on EVERY AI turn** (program, courses,
  credit sums, timetable, notifications) with no caching (inside `enhanced_service`).
- **RAG is a keyword-only full-DB scan** because `sentence-transformers` and `faiss` are not
  installed — every cache miss re-fetches and re-scores up to 5*top_k `KnowledgeDocument` rows
  with pure-Python string matching, then writes `usage_count` per doc.
- **SQLite + `transaction.atomic()` around the LLM call** holds the SQLite write lock during the
  whole request; on concurrency the view retries with `time.sleep()` on "database is locked"
  (views.py:257-267), adding serialized waits.
- **Cache is Django's default LocMemCache** (per-process, tiny, not shared, not persistent).
  Response cache, RAG cache, and the throttle all use it — so under more than one worker they
  are effectively broken.
- Services (`EnhancedClaudeService`, `VectorSearchService`) reconstructed per request; no
  class-level reuse.

### 1.3 RAG / knowledge base state

- `KnowledgeDocument` model is solid (views in models.py:88-120): UUID pk, title, content,
  category, university scoping, tags, priority, usage_count, is_active, indexes.
- Retrieval in `vector_service.VectorSearchService.search()` is **semantic-embeddings-disabled**
  (model = None due to missing packages) so it degrades to keyword matching.
- `build_index()` is a stub (counts docs only) — no embeddings/precomputed index exists.
- Knowledge is populated only manually (Django admin bulk import / `add_knowledge` command).

### 1.4 Learning / admin-review pipeline — MISSING

- No "pending question / proposed knowledge" model.
- No collection→review→approve→KB loop.
- `Feedback` model only captures explicit user ratings (not new knowledge).
- `ConversationAnalytics.knowledge_gaps` is **defined but never written** anywhere.
- The only way to grow the KB is manual admin entry. Nothing learns from conversations.

### 1.5 The "raw JSON reply" bug (`{"reply": ...}`)

- The model is instructed to return strict JSON:
  `{"reply": ..., "current_topic": ..., "topic_summary": ..., "topic_changed": ...,
   "personality_notes": ..., "instructions": ..., "summary": ...}`.
- `send_message` saves `ai_response.text` into `Message.content` (views.py:241). If JSON parsing
  fails and the cleanup regexes don't match (single quotes / escaped content / line breaks /
  non-ASCII), the raw JSON string becomes the "reply" and is rendered verbatim.
- The webapp renders `conversation.messages[].content` directly (Chatbot.tsx:368), so the raw
  JSON is shown to the user. The `quick/` endpoint returns a flat `{"reply": ...}` wrapper too,
  but the webapp does not use it.

### 1.6 Security

- Anthropic and Gemini API keys are **hardcoded** in `academic_backend/settings.py` and
  `academic_backend/production.py`. There is no `.env` file. This must move to environment
  variables only.

---

## Part 2 — Target architecture ("learn, confirm, then teach")

Principles:
1. Academic answers are sensitive: the bot may ONLY surface information that is grounded in the
   knowledge base or the student's own profile. Never invent policies. When unsure, say so and
   escalate ("ask your registrar").
2. Nothing a user asks auto-enters the KB. Questions/answers are COLLECTED as suggestions,
   reviewed and APPROVED by an admin, and only then promoted to `KnowledgeDocument`. This is the
   "learn as it chats when it notices something" loop, gated by human confirmation.
3. Speed first: respond fast for common/known queries (quick + cached + RAG) and only call the
   LLM when needed; stream replies so the UI feels instant.
4. Accuracy via real semantic retrieval (embeddings) on top of the existing keyword layer.

### 2.1 Pipeline overview

```
user turn
   |
   v
[1 sanitize + safety]
   |
   v
[2 quick-response match?] ----- yes --> DB text (0 tokens, <100ms)
   |
   no
   v
[3 semantic + keyword RAG] --> knowledge context
   |
   v
[4 LLM (Gemini flash), grounded, JSON-schema guaranteed]
   |
   v
[5 save reply; clean JSON extraction (never leak raw JSON)]
   |
   v
[6 low-confidence / negative-rating / unanswered detection]
   |
   v
[7 create KnowledgeSuggestion (pending)]  -->  admin reviews + approves
                                                 |
                                                 v
                                          promote -> KnowledgeDocument (KB)
```

---

## Part 3 — Phase A: foundational fixes (fast, low-risk, no new infra beyond Redis)

These fix the visible slowness, the JSON leak, and locking. They are the priority.

### A1. Remove the blocking throttle sleep, add a real limiter
- In `enhanced_service._throttle_request`, replace the synchronous `time.sleep(interval)` with a
  per-user token/rate check using Redis (`SETNX`/`INCR` TTL). No request thread sleeps.
- Keep the check fast and non-blocking; if at the limit, return a short "please wait a moment"
  only when the user is genuinely spamming, never sleep the worker.

### A2. Guarantee clean replies — kill the raw-JSON leak
- Harden the JSON extraction in `enhanced_service` with two guaranteed fallbacks:
  1. Robust regex extraction of `"reply"` from any JSON block (handles single quotes, escaped
     chars, newlines, Unicode) — improve the existing regexes.
  2. If no valid reply is found, NEVER store raw JSON. Return a friendly generic message and log
     the raw model output for diagnostics.
- Add a contract test: for N curated prompts the stored `Message.content` is always plain text.

### A3. Reduce the DB work per AI turn
- Cache `build_student_context(...)` results in Redis keyed by `user.id` with a short TTL
  (e.g., 60-120s) and invalidate on relevant profile writes. Eliminates ~6-9 DB queries per turn.
- Add `select_related('university')` where missing and index the hot lookup columns.
- Reuse a single cacheable service instance (module-level factory) instead of constructing
  `EnhancedClaudeService`/`VectorSearchService` on every request (views.py:139-140).

### A4. Stop holding the SQLite write lock across the LLM call
- Move the slow/blocking work (RAG + LLM call) OUTSIDE `transaction.atomic()`:
  - Save the user message first (commit).
  - Compute the reply (no DB writes held).
  - Save the assistant message in a short transaction.
- Keep the lock-retry fallback for the smaller critical section only.

### A5. Configure Redis as the cache backend
- Add `CACHES` using a Redis backend (`django-redis` or the built-in Redis cache client).
- This makes response cache, RAG cache, context cache, and the rate limiter shared + persistent.
- Set `ANTHROPIC_MIN_REQUEST_INTERVAL` via env, not source.

### A6. Streaming for perceived speed (recommended within Phase A)
- Add a `/send_message/` streaming mode returning `text/event-stream` (SSE) that pushes the
  assistant text as it is generated, then a final event with the saved message/conv state.
- Webapp `Chatbot.tsx` subscribes to the stream instead of blocking on one long HTTP call,
  removing the "loads for a very long time" feel. Keep the existing non-streaming endpoint as a
  fallback (feature-flagged).

### A7. Security
- Remove hardcoded keys from source; read `ANTHROPIC_API_KEY` / `GEMINI_API_KEY` from env only.
- Add `.env.example` documenting every setting.

Deliverable of Phase A: fast, non-locking, no-JSON-leak, cache-backed chatbot with streaming.
No new packages beyond a Redis client. DB stays SQLite.

---

## Part 4 — Phase B: real semantic RAG (accuracy) — optional but high-value

- Add `sentence-transformers` and `faiss` (+ a small model weighed for size/speed, e.g.
  `all-MiniLM-L6-v2` or `bge-small`).
- Add embedding storage: `embedding` BLOB/vector field (or a small `DocumentEmbedding` table /
  faiss index file) on `KnowledgeDocument`, scoped by `university`.
- Implement `build_index()` for real: batch-embed all active documents into FAISS (or a
  precomputed table) via a management command `rebuild_embeddings`.
- `search()` becomes: embed query → ANN nearest-neighbor lookups in milliseconds → rank a small
  candidate set → return top_k. Keyword scoring remains as a hybrid fallback for when embeddings
  are unavailable.
- Cache results in Redis. This is the single biggest accuracy + latency win on knowledge queries
  and directly supports "intelligent, quick to respond".

---

## Part 5 — Phase C: the learning / admin-review pipeline

### C1. New model: `KnowledgeSuggestion` (from a conversation, pending approval)

Fields:
- `id` UUID pk
- `user` FK -> User (who asked)
- `conversation` FK nullable, `source_message` FK nullable (the user turn)
- `query` Text (the user's question)
- `proposed_answer` Text (the model's grounded draft, or "unresolved")
- `category` (same choices as KnowledgeDocument), `university` FK nullable
- `confidence` float (0-1) — how sure we are this is a learnable gap
- `reason` CharField — why it was captured (no_kb_result / low_confidence / negative_rating /
  duplicate_flagged)
- `status` CharField: `pending` / `approved` / `rejected` / `duplicate`
- `reviewed_by` FK nullable, `reviewed_at` datetime, `admin_note` Text
- `created_at`, `updated_at`
- `duplicate_of` FK -> KnowledgeDocument (nullable, set on approval if merging)

### C2. Automatic capture triggers (in `send_message` + `feedback`)
Capture a suggestion (status=pending) when ANY of:
- RAG returned no relevant results AND the user message was a question (heuristic: `?` or
  interrogative) → `reason=no_kb_result` with `proposed_answer="unresolved"`.
- LLM confidence/grounding was low or the model hedged (response contained "not sure /
  not certain / I don't have"). → `low_confidence`.
- User rated the reply negatively (Feedback rating <= 2). → `negative_rating`.
- Same/normalized question appears frequently (Redis counter) with no great KB hit →
  `duplicate_flagged`.

Deduplicate: skip if an identical pending suggestion already exists (handle by normalized-query
hash) or if an identical accepted KnowledgeDocument already covers it.

### C3. Town-review: the webapp admin dashboard
New staff-only route in the webapp (`/staff/chatbot-suggestions`, gated exactly like other staff
pages and the same `/staff/me/roles/` check used for staff/ambassador access):
- List pending suggestions: query, proposed answer, reason, confidence, user, category,
  timestamp. Filters: status / reason / category.
- Actions per row:
  - **Approve** → POST `/api/chatbot/suggestions/{id}/approve/` → backend promotes it to a
    `KnowledgeDocument` (title=query, content=proposed_answer, category, university,
    is_active=True), marks it approved, records admin + time, then triggers an index/embedding
    rebuild so it becomes searchable immediately.
  - **Reject** → POST `.../{id}/reject/` (optional admin_note).
  - **Merge** → attach to an existing KnowledgeDocument.
- Show top "knowledge gaps" (from suggestions and the formerly-unused
  `ConversationAnalytics.knowledge_gaps`, now actually populated) so admins know what to add.

### C4. Backend endpoints for the dashboard (new, staff-only)
- `GET /api/chatbot/suggestions/` (filter by status/category/reason, paginated)
- `GET /api/chatbot/suggestions/{id}/`
- `POST /api/chatbot/suggestions/{id}/approve/`
- `POST /api/chatbot/suggestions/{id}/reject/`
- `GET /api/chatbot/gaps/` (aggregated knowledge-gap stats)
- Permission: require staff/ambassador (same check used across the webapp staff area).
- For convenience and safety also register `KnowledgeSuggestion` in Django admin.

### C5. Model behavior to support learning
- The system prompt already tracks topics/summaries/memory. Add a lightweight instruction: when
  the model genuinely cannot answer from context, it must clearly hedge (this becomes the signal
  for `no_kb_result`/`low_confidence`) instead of fabricating.

---

## Part 6 — Reliability & correctness guardrails

- **Grounding policy**: instruct the model to prefer KB + student profile; never extrapolate
  official policy; when unsure, say so and direct to the registrar/office.
- **A single in-flight LLM call guarantee per user** to prevent abuse and cost spikes; enforce
  via the Redis limiter (not sleeps).
- **Provider fallback**: Gemini -> Anthropic on timeout/429 (already partially present; formalize it).
- **Idempotent capture**: suggestion creation is guarded by a normalized-query hash to avoid
  duplicate pending rows and duplicate KB entries.
- **Contract tests** for: clean reply extraction (Phase A2), grounded "I'm not sure" behavior,
  and the approve→promote→index pipeline (Phase C).

---

## Part 7 — Suggested implementation order & effort

| Order | Work | Risk | Effort |
|-------|------|------|--------|
| 1 | Phase A1 + A2 (limiter + JSON leak) | Low | Small |
| 2 | Phase A3 + A4 (context cache, out-of-lock LLM, service reuse) | Low-Med | Medium |
| 3 | Phase A5 + A7 (Redis cache + secrets to env) | Low | Small |
| 4 | Phase A6 (SSE streaming) + webapp stream client | Med | Medium |
| 5 | Phase C (suggestion model, capture, endpoints) | Low | Medium |
| 6 | Phase C3/C4 (webapp staff dashboard + approve/reject) | Med | Medium |
| 7 | Phase B (semantic embeddings/FAISS + rebuild command) | Med | Medium |
| 8 | Backfill knowledge base + load-test + monitor | — | Ongoing |

Recommended: do 1-4 first (fixes the current pain: slowness + JSON), then 5-6 (the learning loop
you asked for), then 7 (accuracy polish). Each phase torches verifiable without the next.

---

## Part 8 — Success metrics

- Median first-token latency < 1s (with streaming); full reply < 3s.
- Zero raw-JSON leaks in stored messages (contract-tested).
- Response cache hit rate > 25%; semantic RAG hit rate high on KB questions.
- Suggestions captured on unanswered/low-confidence/negative-rated turns; approved suggestions
  become searchable quickly (pending queue does not grow unbounded).
- No blocking sleeps in the request path.
- API keys no longer present in source control.

---

## Open questions for the reviewer (before implementation)

1. Streaming (Phase A6): OK to add SSE to `send_message`, keeping the old JSON endpoint as a
   fallback? Or keep it simple (non-streaming) for now?
2. Embedding model for Phase B: prefer a small/fast/local model (cheap, offline) vs a hosted
   embedding API (higher quality, costs money/network). Recommend local small model.
3. Capture triggers in C2 — is "capture on every unanswered continuous question" acceptable, or
   should capture ALSO require it to not look like a greeting/small-talk (to avoid noise)?
