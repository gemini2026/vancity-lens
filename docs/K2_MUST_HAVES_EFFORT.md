# K2 Must-Haves and Effort Estimate (Bill47 Migration Lens)

This is a high-level engineering assessment of what it would take to make the **K2 (Knowledge2 / k2_mvp)** platform a "definite yes" replacement for Bill47's current RAG stack, focused on the gaps that matter for due diligence workflows (metadata-heavy search, stable citations, exports, governance, and predictable ops).

All current-state notes are based on the local repo at `/Users/antonmishel/k2/devops/k2_mvp`.

## Current-State Snapshot (What K2 Already Has)

- Self-hosting/devops foundations (kind/k8s, rollouts, E2E harness): `/Users/antonmishel/k2/devops/k2_mvp/docs/k8s_runbook.md`
- Python SDK (public API client): `/Users/antonmishel/k2/devops/k2_mvp/sdk/README.md`
- Hybrid retrieval (dense + BM25) with fusion and optional rewrite/rerank:
  - Retrieval pipeline and filters: `/Users/antonmishel/k2/devops/k2_mvp/retriever/services/retrieval.py`
  - FAISS flat index wrapper: `/Users/antonmishel/k2/devops/k2_mvp/ml/ml/indexing/faiss_index.py`
- FAISS in this environment supports filter selectors for `IndexFlatIP` searches via `SearchParameters.sel` + `IDSelectorBatch` (important for making dense retrieval filter-aware without changing index type).
- Provenance fields exist (chunk metadata + page/offset) and can be returned via API:
  - Ingestion metadata composition: `/Users/antonmishel/k2/devops/k2_mvp/k2_core/ingestion.py`
  - Search API response: `/Users/antonmishel/k2/devops/k2_mvp/api/app/api/retrieval.py`
- Console UI direction (PRD; implementation may be partial depending on branch): `/Users/antonmishel/k2/devops/k2_mvp/docs/k2_console_prd.md`

## Must-Haves (What Would Make K2 a "Definite Move")

1. **Real metadata search**
2. **Filter-aware retrieval (not "post-filter and hope")**
3. **Document upsert + versioning (stable IDs)**
4. **Citation-grade provenance (canonical source links + page/section)**
5. **Data portability (export/import)**
6. **Governance + access control suitable for customer use**
7. **Cost controls and predictable limits**
8. **UI to manage corpora and debug retrieval**

## Effort Estimate (Using Codex as an Implementation Accelerator)

Estimates below assume 1 engineer with Codex assistance and include tests + docs. Add ~25% for production hardening and rollout coordination in a real environment.

| Must-have | Current K2 status | What you’d build/change | Est. effort | Risk |
|---|---|---|---:|---|
| Real metadata search | Filters exist but are equality / list-only and applied late. | Add a filter DSL (AND/OR groups, ranges, exists, string ops), typed metadata conventions, facets (counts), and server-side validation. | 2-4 weeks | Medium |
| Filter-aware retrieval | Dense/sparse search happens first; filters applied post-fusion in DB. | Make retrieval filter-aware: prefilter candidate chunk IDs; use FAISS `SearchParameters.sel` with `IDSelectorBatch` when filter selectivity is reasonable; fallback to oversample+filter. | 2-5 weeks | High |
| Upsert + versioning | New `document_id` per ingest; chunk IDs are stable only within a `document_id`. | Introduce `(corpus_id, source_uri)` uniqueness and an "upsert ingest" path that reuses `document_id`; add document version rows or `replaced_by_document_id`; ensure reindex/deletion semantics are consistent. | 2-4 weeks | Medium |
| Citation-grade provenance | Chunk-level provenance exists, but citation UX is not standardized. | Standardize doc metadata fields (`title`, `publisher`, `published_at`, `canonical_url`, `retrieved_at`), add first-class citation objects in API responses, and ensure PDFs/URLs map to resolvable links. | 1-2 weeks | Low |
| Data portability | Internal chunk export exists behind job-context auth. | Public "export corpus" API (docs, chunks, metadata, feedback, evals) plus "import corpus" tooling; streaming exports; redaction options. | 1-3 weeks | Medium |
| Governance + access control | Good foundations (org/project/corpus, keys, audit) but customer-grade RBAC/ACL depth depends on requirements. | RBAC matrix in API + UI, scoped API keys per corpus/project, optional per-document ACLs, retention policies, deletion verification, admin audit views. | 2-6 weeks | Medium |
| Cost controls | Limits exist, usage endpoints exist, but budgets/quotas enforcement is usually incomplete in MVPs. | Quotas per API key/project, budget alerts, request metering by route (search, generate, ingest), backpressure/throttling rules. | 1-3 weeks | Medium |
| UI to manage/debug | Console PRD exists; partial implementation is likely. | Corpus + document browser, ingestion progress, search playground with filter builder, provenance preview, export flows, usage dashboards. | 3-8 weeks | Medium |

### Bottom line timeline

- **Minimum "move-worthy" for Bill47 (metadata + citations + export + basic console)**: ~6-10 weeks (1 engineer with Codex) if you accept approximation for filter-aware retrieval.
- **Strong "definite move" (filter-aware retrieval + upsert/versioning + governance + cost controls + polished UI)**: ~10-18 weeks for 1 engineer, or ~6-10 weeks for 2 engineers.

## Suggested Build Order (To De-Risk Fast)

1. Citation-grade provenance first (unblocks PDF + UI citations without touching retrieval core).
2. Upsert/versioning next (prevents long-term data integrity headaches).
3. Metadata DSL + validation (gives you stable semantics to build UI + tests against).
4. Filter-aware dense retrieval using FAISS selectors (hardest, highest leverage).
5. Public export/import (migration + customer trust).
6. Governance + cost controls.
7. Console polish.

## “When You’d Benefit From Moving”

- You want a self-hostable RAG platform with a real management console, auditability, and a path to model tuning.
- Your app is metadata-first (parcel/address/municipality/date/source type) and you need filters that behave predictably.
- You expect to run multiple corpora and need operational tooling (jobs, metrics, usage) out of the box.

## “You Likely Won’t Benefit Yet”

- You only need simple RAG on a small document set and your current system is already stable.
- You need highly selective metadata constraints at large scale but cannot invest in filter-aware retrieval work (or accept approximations).
- You need built-in connectors for proprietary data sources (Land Titles, assessment, comps) rather than building ingestion pipelines separately.

## Open Questions (Needed for a Precise Estimate)

1. Expected corpus size (chunks per corpus) and filter selectivity (common queries).
2. Which metadata operators are non-negotiable (ranges, geo, text contains, OR groups).
3. Whether per-document ACLs are required, or per-corpus is sufficient.
4. Export scope: "just docs/chunks" vs full lineage (jobs, evals, feedback, models).
