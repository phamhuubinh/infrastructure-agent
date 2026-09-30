# RAG service

## Current implementation

Document ingestion and retrieval run inside the Orion application process. There is no
separate RAG service. SQLite persists document metadata and normalized segments, while
the local blob directory persists original bytes. On a normal restart Orion reconciles
non-terminal `uploaded`, `parsing`, or `indexing` records without resurrecting tombstones.

RAG v2 stores embedding profiles, vectors, and per-document semantic progress in SQLite.
Production `knowledge.search` defaults to the Phase 3A lexical plus token-hash ranking. Set
`ORION_KNOWLEDGE_SEMANTIC_SEARCH=hybrid` before starting Orion to opt into hybrid ranking;
absent or `off` keeps the exact baseline ranking and scores. Other values also leave it off.
The enabled path obtains up to 50 dense candidates from the existing semantic service and fuses
their segment ranks with the top 50 baseline ranks using RRF (`k=60`), the Phase 3A exact-filename
bonus, and segment-ID tie-breaking. It returns no more than the requested limit. No tool-routing
behavior changes.

Document `ready`, model `installed`/`missing`/`corrupt`, semantic index
`ready`/`missing`/`failed`, and production mode `off`/`hybrid` are independent states. A ready
document remains lexically searchable and readable with missing, failed, or partial vectors.
Hybrid uses only valid current-profile vectors already present; enabling it does not imply full
semantic coverage. Missing/corrupt/unavailable model files, recoverable query inference failure,
or no visible dense hits fall back to the exact lexical result. Unexpected SQLite, scope, and
programming failures propagate. Startup does not load E5, download weights, or backfill vectors.
The first enabled search with visible segments loads the local E5 model lazily and reuses it after
success; this incurs the measured roughly 1.1 GiB peak process memory cost at that time.

## Local semantic model

`orion model status embeddings` reports `missing`, `installed`, or `corrupt`. Provision explicitly
with `orion model install embeddings`. The command downloads the five files needed by
FastEmbed/ONNX from the pinned `intfloat/multilingual-e5-small` revision
`614241f622f53c4eeff9890bdc4f31cfecc418b3`, verifies their SHA-256 digests, and publishes
the verified directory only after all files are complete. Repeating install is idempotent.
The cache is under `ORION_DATA_DIR/models/embeddings/<profile_id>/`, or by default
`~/.local/share/orion/models/embeddings/<profile_id>/`. It is operator-managed local data; remove
it only when ready to reinstall. An interrupted install leaves only a removable staging directory.
Runtime loading passes the verified path to FastEmbed with `local_files_only=True` and the CPU
execution provider. It never resolves a floating model revision or uses an embedding endpoint.

`orion knowledge semantic-index --max-documents 100` is the explicit bounded backfill command.
`--max-documents N` means **at most N live ready documents are inspected in that invocation**,
whether or not they need embedding. The default is 100. SQLite selects one page in deterministic
`(created_at, document_id)` order after a per-profile persisted cursor. The cursor advances after each completed document inspection, including a recoverable per-document indexing failure. Unexpected persistence, programming, or invariant failures abort the invocation without advancing past the unfinished document. An interrupted process resumes after its last persisted cursor; repeating an already committed document is safe. Output distinguishes inspected, reindexed, and failed counts, whether the cursor wrapped, and its last document ID. It does not claim that the whole library is complete.

For each selected document, stored segment text digests, vector validity, window ordinals, and
persisted expected window counts are checked before tokenization. Healthy documents do not run
the tokenizer. Missing, failed, stale-text, or incomplete-window candidates are repaired from
persisted segment text without reparsing source files. Deleted documents/projects are excluded;
SQLite rechecks liveness and source digest before committing vectors. A missing/corrupt model
makes this command fail clearly, while Orion, Chat, lexical `knowledge.search`, and
`knowledge.read` continue to work. Existing multi-window rows from before the window-count
migration are rebuilt when their turn arrives.

The profile ID is SHA-256 of the canonical profile definition: FastEmbed 0.8.1,
ONNX Runtime 1.30.0 CPU, NumPy 2.5.3, tokenizers 0.23.2,
repository and pinned revision, model and tokenizer/config artifact digests, float32, 384
dimensions, attention-mask mean pooling, L2 normalization, `query: ` and `passage: ` prefixes,
and token window policy. A change to any field gives a different profile ID; run semantic-index
again to build new vectors. Old profile rows remain isolated until explicitly cleaned up.

Passage windows use the pinned tokenizer without truncation. They reserve special and `passage: `
prefix tokens within E5's 512-token model limit, overlap 32 source tokens, and have stable
zero-based ordinals. Empty text gets one empty window. Windows rank independently, but the
semantic search aggregates by maximum cosine score per original segment and returns that
segment's canonical citation identity. There is no cross-segment windowing.

## Frozen Phase 3A measurement

The reproducible command is `cd backend && PYTHONPATH=src ../.venv/bin/python
scripts/semantic_retrieval_benchmark.py`; its complete output is checked in at
`backend/benchmarks/retrieval_v2_semantic_phase3a.json`. It uses the unchanged Phase 1 corpus
and baseline. Metrics on this machine:

| Ranker | Recall@1 | Recall@5 | Recall@10 | MRR@10 | nDCG@10 | Exact filename top-one | Leakage |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Production baseline | .444 | .556 | .556 | .472 | .492 | 100% | 0 |
| E5 dense only | .556 | .889 | 1.000 | .705 | .776 | 0% | 0 |
| Experimental RRF fusion | .556 | .889 | 1.000 | .741 | .805 | 100% | 0 |

All three report 100% canonical provenance checks. First relevant rank by hard case (blank means
no relevant document in the top ten; isolation cases intentionally have no relevant target):

| Case | Baseline | Dense | Fusion |
| --- | ---: | ---: | ---: |
| English paraphrase | 4 | 2 | 2 |
| Vietnamese paraphrase | — | 1 | 1 |
| English→Vietnamese | — | 5 | 6 |
| Vietnamese→English | — | 2 | 2 |
| Acronym expansion | — | 1 | 2 |
| Lexical distractors | 1 | 1 | 1 |
| Exact filename | 1 | 7 | 1 |
| Project scope/provenance | 1 | 1 | 1 |

The model cache is 487,352,567 bytes. Cold load was 3.92 s; warm query embedding p50/p95 was
6.39/6.55 ms over 30 calls. Passage throughput was 429/s over 64 passages in batches of 16.
Peak process RSS was 1,179,940 KiB. Backfill of 10 live benchmark documents and 10 windows took
0.168 s; SQLite grew 20,480 bytes (vectors have 1,536-byte float32 payloads). The small corpus
does not establish large-library scan cost. Dense-only filename regression and roughly 1.1 GiB
peak RSS are why Phase 3B production activation is explicit and defaults off.
Peak RSS is reported when the platform provides the Unix resource counter; it is omitted on Windows.
These retained timing/storage samples predate the bounded-cursor change; the frozen ranking
metrics and every first-relevant rank were rerun after it and remained unchanged.

## Phase 3C evidence-selection experiment

Phase 3C measures a pure document-balanced selector on a separate real-ingestion corpus with
multi-chunk documents. It consumes at most 50 already ranked candidates, takes the first segment
from each document in upstream order, then fills remaining slots in upstream order. It preserves
segment scores and provenance and adds no model or runtime resource dependency. It is **not wired
into production**; Phase 3B ranking and fallback remain unchanged. There is no learned reranker.

Run the deterministic offline measurement with `cd backend && PYTHONPATH=src ../.venv/bin/python
scripts/document_balance_benchmark.py`. Its corpus and baseline artifact are
`backend/benchmarks/retrieval_v2_document_balance_phase3c_corpus.json` and
`backend/benchmarks/retrieval_v2_document_balance_phase3c.json`. On a machine where E5 is already
installed, add `--with-hybrid` to measure the same selector after Phase 3B hybrid ranking; the
optional result is recorded in `backend/benchmarks/retrieval_v2_document_balance_phase3c_hybrid.json`.
The command never downloads a model. The frozen Phase 3A corpus and artifacts are unchanged.

At a three-segment evidence window, relevant-document coverage on the two multi-document cases
rose from 75% to 100% for both baseline and hybrid candidates. Baseline Recall@3 rose from 90%
to 100%, MRR@3 from .867 to .900, and nDCG@3 from .823 to .910. Hybrid Recall@3 rose from 90%
to 100%, MRR@3 stayed .900, and nDCG@3 rose from .849 to .910. Exact-filename top-one remained
correct; provenance accuracy was 100%, and scope/deletion leakage was zero. The single-document
filtered case returned three segments before and after selection. These results describe this
small corpus only; production activation is deferred.

The target architecture remains: RAG is a model-callable knowledge source, not an
always-on pre-model stage, and project scope is runtime-bound.
