# VanCity Lens — RAG Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              FRONTEND (Next.js 15)                          │
│                                                                             │
│   ChatRequest { query, session_id?, neighborhood_filter?, date_from/to? }   │
│                              │                                              │
│                    POST /api/v1/intel/chat                                   │
└──────────────────────────────┬──────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        API GATEWAY  (routes.py)                             │
│                                                                             │
│   ┌───────────────────────────────────────────────────┐                     │
│   │  TIER DETERMINATION (request-time)                │                     │
│   │                                                   │                     │
│   │   ANTHROPIC_API_KEY?  COHERE_API_KEY?  → Mode     │                     │
│   │        ✓                  ✓           → FULL      │                     │
│   │        ✓                  ✗           → PARTIAL   │                     │
│   │        ✗                  ✗           → DEMO      │                     │
│   └───────────────────────────────────────────────────┘                     │
│                              │                                              │
│              rate_limit_llm  │  get_db_pool()                               │
└──────────────────────────────┬──────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                       handle_chat()  (chat.py)                              │
│                                                                             │
│  ┌─────────────┐    ┌──────────────────────────────────────────────────┐    │
│  │   SESSION    │    │              RETRIEVAL PIPELINE                  │    │
│  │  MANAGEMENT  │    │                                                 │    │
│  │             │    │  ┌─────────────────────────────────────────┐    │    │
│  │ create or   │    │  │  QUERY ANALYSIS (query_planner.py)      │    │    │
│  │ resume      │    │  │                                         │    │    │
│  │ session     │    │  │  is_multi_hop(query)?                   │    │    │
│  │             │    │  │    "Compare X to Y" → decompose_query() │    │    │
│  │ build       │    │  │    → ["X context", "Y context"]         │    │    │
│  │ context     │    │  │    → parallel sub-searches              │    │    │
│  │ window      │    │  │    → merge + deduplicate                │    │    │
│  │ (history)   │    │  └──────────────┬──────────────────────────┘    │    │
│  └─────────────┘    │                 │                               │    │
│                     │                 ▼                               │    │
│                     │  ┌──────────────────────────────────────┐       │    │
│                     │  │         SEARCH DISPATCH              │       │    │
│                     │  │                                      │       │    │
│                     │  │  FULL ────→ hybrid_search()          │       │    │
│                     │  │  PARTIAL ─→ sparse_search()          │       │    │
│                     │  │  DEMO ────→ sparse_search()          │       │    │
│                     │  └──────────────────────────────────────┘       │    │
│                     └────────────────────────────────────────────────┘    │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                  ANSWER GENERATION                                  │    │
│  │                                                                     │    │
│  │  FULL / PARTIAL ──→ Claude API (claude-sonnet-4-5-20250514)         │    │
│  │                      system_prompt + context + history + query       │    │
│  │                                                                     │    │
│  │  DEMO ────────────→ _build_demo_answer()                            │    │
│  │                      formatted markdown (no LLM call)               │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                              │                                              │
│              ChatResponse { answer, citations[], signals[], session_id,      │
│                              mode: "full"|"partial"|"demo" }                │
└──────────────────────────────┬──────────────────────────────────────────────┘
                               │
                               ▼
                         ┌───────────┐
                         │  Frontend  │
                         └───────────┘


═══════════════════════════════════════════════════════════════════════════════
                    HYBRID SEARCH PIPELINE  (embeddings.py)
═══════════════════════════════════════════════════════════════════════════════

  hybrid_search(query, cohere_key)          sparse_search(query)
  ┌──────────────────────────────┐          ┌────────────────────────┐
  │                              │          │                        │
  │  STAGE 1: PARALLEL RETRIEVAL │          │  BM25-ONLY SEARCH      │
  │                              │          │  (no API keys)         │
  │  ┌────────────┐ ┌──────────┐ │          │                        │
  │  │   DENSE    │ │  SPARSE  │ │          │  tsvector @@ tsquery   │
  │  │            │ │          │ │          │  ts_rank_cd() scoring  │
  │  │  Cohere    │ │  BM25    │ │          │  ORDER BY text_score   │
  │  │  embed +   │ │ tsvector │ │          │                        │
  │  │  pgvector  │ │ tsquery  │ │          │  Returns:              │
  │  │  cosine    │ │ GIN idx  │ │          │  final_score =         │
  │  │            │ │          │ │          │    text_score           │
  │  │  Top 30    │ │  Top 30  │ │          └────────────────────────┘
  │  └─────┬──────┘ └────┬─────┘ │
  │        │              │       │
  │        ▼              ▼       │
  │  ┌──────────────────────────┐ │
  │  │  STAGE 2: RRF FUSION     │ │
  │  │                          │ │
  │  │  score = Σ w / (k + rank)│ │
  │  │  k = 60                  │ │
  │  │  vector_weight = 0.5     │ │
  │  │  text_weight = 0.5       │ │
  │  │  FULL OUTER JOIN         │ │
  │  └────────────┬─────────────┘ │
  │               │               │
  │               ▼               │
  │  ┌──────────────────────────┐ │
  │  │  STAGE 3: COHERE RERANK  │ │
  │  │                          │ │
  │  │  rerank-english-v3.0     │ │
  │  │  Re-scores top 3×limit   │ │
  │  │  → final_score           │ │
  │  └──────────────────────────┘ │
  └──────────────────────────────┘


═══════════════════════════════════════════════════════════════════════════════
                    CONTEXT ASSEMBLY  (chat.py)
═══════════════════════════════════════════════════════════════════════════════

  ┌──────────────────────────┐  ┌──────────────────────────┐
  │  DOCUMENT CHUNKS (top 10) │  │ INTELLIGENCE SIGNALS (5)  │
  │                          │  │                          │
  │  Score, Source Title,    │  │  headline, signal_type,  │
  │  URL, Section Header,   │  │  severity, decision,     │
  │  Chunk Text              │  │  vote counts, addresses, │
  │                          │  │  neighborhood, summary   │
  └────────────┬─────────────┘  └────────────┬─────────────┘
               │                              │
               └──────────┬───────────────────┘
                          │
                          ▼
  ┌──────────────────────────────────────────┐
  │         CONTEXT STRING                   │
  │                                          │
  │  ## RETRIEVED DOCUMENT CHUNKS            │
  │  ### Chunk 1 (Score: 0.952)              │
  │  Source: Council Meeting Jan 2026        │
  │  ...chunk text...                        │
  │                                          │
  │  ## INTELLIGENCE SIGNALS                 │
  │  ### Signal 1: 1234 Main rezoned         │
  │  Decision: approved (8-3)                │
  │  ...                                     │
  └────────────────┬─────────────────────────┘
                   │
                   ▼
  ┌──────────────────────────────────────────┐
  │  + Conversation History (up to 10 msgs)  │
  │  + System Prompt (VanCity Lens persona)   │
  │  + User Query                            │
  └──────────────────────────────────────────┘


═══════════════════════════════════════════════════════════════════════════════
               OFFLINE PIPELINES  (scripts/)
═══════════════════════════════════════════════════════════════════════════════

  PIPELINE 1: SEED CHUNKS (no API keys)
  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  ┌───────────┐    ┌─────────────┐    ┌───────────────────────┐
  │ documents │───→│ chunk_      │───→│ document_chunks       │
  │ table     │    │ document()  │    │                       │
  │           │    │             │    │  embedding = NULL     │
  │ raw_text  │    │ semchunk +  │    │  chunk_tsvector = ✓   │
  │           │    │ tiktoken    │    │  (BM25-ready)         │
  └───────────┘    │ 800 tokens  │    └───────────────────────┘
                   └─────────────┘
                   python scripts/seed_chunks.py [--force]


  PIPELINE 2: EMBED CHUNKS (requires Cohere key)
  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  ┌───────────────────┐    ┌─────────────┐    ┌───────────────────────┐
  │ document_chunks   │───→│ batch_embed │───→│ document_chunks       │
  │ WHERE embedding   │    │ ()          │    │                       │
  │ IS NULL           │    │             │    │  embedding = ✓        │
  │                   │    │ Cohere API  │    │  (1024-dim vector)    │
  └───────────────────┘    │ batch=96    │    │  (hybrid-ready)       │
                           └─────────────┘    └───────────────────────┘
                   python scripts/embed_chunks.py --cohere-key KEY


═══════════════════════════════════════════════════════════════════════════════
               DATABASE SCHEMA  (PostgreSQL 16 + PostGIS + pgvector)
═══════════════════════════════════════════════════════════════════════════════

  ┌─────────────────────┐       ┌──────────────────────────────┐
  │     documents        │       │     document_chunks           │
  ├─────────────────────┤       ├──────────────────────────────┤
  │ id (PK)             │──┐    │ id (PK)                      │
  │ source_type         │  │    │ document_id (FK) ────────────│──┐
  │ source_url (UNIQUE) │  │    │ chunk_index                  │  │
  │ title               │  │    │ chunk_text                   │  │
  │ published_date      │  │    │ section_header               │  │
  │ raw_text            │  │    │ token_count                  │  │
  │ text_length         │  │    │ embedding vector(1024)       │  │
  │ metadata (JSONB)    │  │    │ chunk_tsvector (tsvector)    │  │
  │ url_status          │  │    ├──────────────────────────────┤  │
  │ archive_url         │  │    │ IDX: IVFFlat(cosine) on emb  │  │
  │ processed_at        │  │    │ IDX: GIN on chunk_tsvector   │  │
  │ scraped_at          │  │    └──────────────────────────────┘  │
  └─────────────────────┘  │                                      │
           │               │    ┌──────────────────────────────┐  │
           │               └───→│  intelligence_signals         │  │
           │                    ├──────────────────────────────┤  │
           │                    │ id (PK)                      │  │
           │                    │ document_id (FK) ◄───────────│──┘
           │                    │ chunk_id (FK, nullable)      │
           │                    │ signal_type                  │
           │                    │ summary, headline            │
           │                    │ addresses[]                  │
           │                    │ neighborhood                 │
           │                    │ decision, vote_for/against   │
           │                    │ sentiment, severity          │
           │                    │ confidence (0-1)             │
           │                    │ geom (PostGIS)               │
           │                    │ event_date                   │
           │                    └──────────────────────────────┘
           │
           │                    ┌──────────────────────────────┐
           │                    │     chat_sessions             │
           │                    ├──────────────────────────────┤
           │                    │ id (PK)                      │
           │                    │ session_id (UUID)            │──┐
           │                    │ user_label                   │  │
           │                    │ created_at                   │  │
           │                    └──────────────────────────────┘  │
           │                                                      │
           │                    ┌──────────────────────────────┐  │
           │                    │     chat_messages             │  │
           │                    ├──────────────────────────────┤  │
           │                    │ id (PK)                      │  │
           │                    │ session_id (FK) ◄────────────│──┘
           │                    │ role (user/assistant)        │
           │                    │ content                      │
           │                    │ source_chunks[]              │
           │                    │ source_signals[]             │
           │                    │ created_at                   │
           │                    └──────────────────────────────┘


═══════════════════════════════════════════════════════════════════════════════
               EXTERNAL SERVICES & CONCURRENCY  (external_clients.py)
═══════════════════════════════════════════════════════════════════════════════

  ┌───────────────────────────────────────────────────────────────────┐
  │                                                                   │
  │  ┌──────────────────────┐        ┌──────────────────────┐        │
  │  │  COHERE API          │        │  ANTHROPIC API       │        │
  │  │                      │        │                      │        │
  │  │  embed-english-v3.0  │        │  claude-sonnet-4-5   │        │
  │  │  1024-dim embeddings │        │  -20250514           │        │
  │  │                      │        │                      │        │
  │  │  rerank-english-v3.0 │        │  Chat generation     │        │
  │  │  Final re-scoring    │        │  Signal extraction   │        │
  │  │                      │        │                      │        │
  │  │  Timeout: 10s        │        │  Chat timeout: 30s   │        │
  │  │  Max concurrent: 3   │        │  Extract timeout: 45s│        │
  │  │  Batch size: 96      │        │  Max concurrent: 3   │        │
  │  │  Retries: 3 (exp BO) │        │                      │        │
  │  └──────────────────────┘        └──────────────────────┘        │
  │                                                                   │
  │  ┌──────────────────────────────────────────────────────────┐    │
  │  │  PostgreSQL 16 + PostGIS + pgvector                      │    │
  │  │                                                          │    │
  │  │  IVFFlat index (cosine) — dense vector search            │    │
  │  │  GIN index (tsvector) — BM25 full-text search            │    │
  │  │  GiST index (geom) — spatial queries                     │    │
  │  └──────────────────────────────────────────────────────────┘    │
  └───────────────────────────────────────────────────────────────────┘
```
