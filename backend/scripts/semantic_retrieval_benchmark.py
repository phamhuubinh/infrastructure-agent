"""Explicit, local-only experiment over the frozen Phase 1 retrieval corpus."""

from __future__ import annotations

import importlib
import json
import statistics
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from retrieval_quality_benchmark import CORPUS, _metrics, _scope, run_baseline

from orion.knowledge.blob_store import LocalBlobStore
from orion.knowledge.local_embeddings import LocalE5Embeddings, model_directory
from orion.knowledge.ranking import HYBRID_CANDIDATE_DEPTH, fuse_hybrid_ranks
from orion.knowledge.semantic import SemanticIndexService
from orion.knowledge.service import KnowledgeService
from orion.persistence.sqlite import SQLiteStore


def _peak_rss_kb() -> int | None:
    """Resource usage is optional; its RSS unit differs on Linux and macOS."""
    if not (sys.platform.startswith("linux") or sys.platform == "darwin"):
        return None
    try:
        resource = importlib.import_module("resource")
        peak = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    except (ImportError, AttributeError, OSError):
        return None
    return peak // 1024 if sys.platform == "darwin" else peak


def _ranked_documents(
    segment_ids: list[str], segment_to_document: dict[str, str], document_to_key: dict[str, str]
) -> list[str]:
    seen: set[str] = set()
    keys: list[str] = []
    for segment_id in segment_ids:
        key = document_to_key[segment_to_document[segment_id]]
        if key not in seen:
            keys.append(key)
            seen.add(key)
    return keys[:10]


def _summarize(
    cases: list[dict[str, Any]], allowed: set[str], ranker: str, canonical: set[str]
) -> dict[str, Any]:
    evaluated = [case for case in cases if case["relevant"]]
    ranks = [
        [
            case["retrieved"].index(key) + 1 if key in case["retrieved"] else 11
            for key in case["relevant"]
        ]
        for case in evaluated
    ]
    filenames = [case for case in cases if case["category"] == "filename"]
    returned_segments = [segment for case in cases for segment in case["segment_ids"]]
    return {
        "ranker": ranker,
        "metrics": _metrics(ranks),
        "filename_top1_rate": sum(
            bool(case["retrieved"]) and case["retrieved"][0] in case["relevant"]
            for case in filenames
        )
        / len(filenames),
        "provenance_accuracy": (
            sum(segment in canonical for segment in returned_segments) / len(returned_segments)
            if returned_segments
            else 1.0
        ),
        "leakage_count": sum(key not in allowed for case in cases for key in case["retrieved"]),
        "cases": [
            {key: value for key, value in case.items() if key != "segment_ids"} for case in cases
        ],
    }


def run_experiment(corpus_path: Path = CORPUS) -> dict[str, Any]:
    baseline = run_baseline(corpus_path)
    corpus = json.loads(corpus_path.read_text(encoding="utf-8"))
    started = time.perf_counter()
    embeddings = LocalE5Embeddings()
    cold_load_seconds = time.perf_counter() - started
    with TemporaryDirectory(prefix="orion-semantic-benchmark-") as temporary:
        root = Path(temporary)
        database = root / "benchmark.db"
        store = SQLiteStore(database)
        try:
            knowledge = KnowledgeService(store, LocalBlobStore(root / "blobs"))
            project_a = store.create_project("benchmark A")["project_id"]
            project_b = store.create_project("benchmark B")["project_id"]
            session_a = store.create_session(project_id=project_a)
            session_b = store.create_session(project_id=project_b)
            owners = {
                "session_a": session_a,
                "session_b": session_b,
                "project_a": project_a,
                "project_b": project_b,
            }
            documents: dict[str, Any] = {}
            attachments: list[str] = []
            for spec in corpus["documents"]:
                owner = spec["owner"]
                upload = (
                    knowledge.attach_project(owners[owner], spec["name"], spec["text"].encode())
                    if owner.startswith("project_")
                    else knowledge.attach(owners[owner], spec["name"], spec["text"].encode())
                )
                documents[spec["key"]] = upload
                if owner == "session_a":
                    attachments.append(upload.attachment_id)
            scope = _scope(session_a, tuple(attachments), project_a)
            deleted = {
                spec["key"] for spec in corpus["documents"] if spec.get("delete_before_queries")
            }
            for key in deleted:
                knowledge.delete(documents[key].document.document_id, scope)
            allowed = {
                spec["key"]
                for spec in corpus["documents"]
                if spec["owner"] in {"session_a", "project_a"} and spec["key"] not in deleted
            }
            index = SemanticIndexService(store, embeddings)
            production_hybrid = KnowledgeService(
                store, LocalBlobStore(root / "blobs"), semantic_retriever_factory=lambda: index
            )
            store._connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            before_bytes = database.stat().st_size
            indexing_started = time.perf_counter()
            progress = index.reconcile_missing(max_documents=100)
            indexing_seconds = time.perf_counter() - indexing_started
            store._connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            after_bytes = database.stat().st_size
            window_count = store._connection.execute(
                "SELECT COUNT(*) FROM segment_embeddings"
            ).fetchone()[0]
            segment_count = store._connection.execute(
                "SELECT COUNT(*) FROM document_segments"
            ).fetchone()[0]
            segment_to_document = {
                str(row["segment_id"]): str(row["document_id"])
                for upload in documents.values()
                for row in store.document_segments(upload.document.document_id)
            }
            document_to_key = {
                upload.document.document_id: key for key, upload in documents.items()
            }
            names = {spec["key"]: spec["name"] for spec in corpus["documents"]}
            dense_cases: list[dict[str, Any]] = []
            fusion_cases: list[dict[str, Any]] = []
            query_latencies: list[float] = []
            for spec in corpus["queries"]:
                start = time.perf_counter()
                dense = index.search(scope, spec["query"], HYBRID_CANDIDATE_DEPTH)
                query_latencies.append((time.perf_counter() - start) * 1000)
                lexical = knowledge.search(scope, spec["query"], HYBRID_CANDIDATE_DEPTH)
                dense_ids = [hit.segment_id for hit in dense]
                lexical_ids = [hit.segment_id for hit in lexical]
                exact_filename_ids = {
                    segment_id
                    for segment_id in (*dense_ids, *lexical_ids)
                    if spec["query"].casefold().strip()
                    == names[document_to_key[segment_to_document[segment_id]]].casefold()
                }
                scores = fuse_hybrid_ranks(lexical_ids, dense_ids, exact_filename_ids)
                fused_ids = sorted(scores, key=lambda item: (-scores[item], item))
                production_ids = [
                    hit.segment_id
                    for hit in production_hybrid.search(scope, spec["query"], HYBRID_CANDIDATE_DEPTH)
                ]
                if production_ids != fused_ids[:HYBRID_CANDIDATE_DEPTH]:
                    raise AssertionError(f"Production hybrid rank differs for {spec['key']}")
                for target, ids in ((dense_cases, dense_ids), (fusion_cases, fused_ids)):
                    keys = _ranked_documents(ids, segment_to_document, document_to_key)
                    target.append(
                        {
                            "key": spec["key"],
                            "category": spec["category"],
                            "segment_ids": ids[:HYBRID_CANDIDATE_DEPTH],
                            "retrieved": keys,
                            "relevant": list(spec["relevant"]),
                            "first_relevant_rank": min(
                                (keys.index(key) + 1 for key in spec["relevant"] if key in keys),
                                default=None,
                            ),
                        }
                    )
            # Warm repeated query sample after model and indexes have loaded.
            warm: list[float] = []
            for _ in range(30):
                start = time.perf_counter()
                embeddings.embed_queries(("phục hồi dữ liệu",))
                warm.append((time.perf_counter() - start) * 1000)
            passage_sample = tuple(
                "Representative Vietnamese và English passage." for _ in range(64)
            )
            passage_started = time.perf_counter()
            for offset in range(0, len(passage_sample), 16):
                embeddings.embed_passages(passage_sample[offset : offset + 16])
            passage_seconds = time.perf_counter() - passage_started
            model_bytes = sum(
                path.stat().st_size for path in model_directory().iterdir() if path.is_file()
            )
            return {
                "corpus_version": corpus["version"],
                "baseline": baseline,
                "dense": _summarize(
                    dense_cases, allowed, "e5_dense_only", set(segment_to_document)
                ),
                "fusion": _summarize(
                    fusion_cases,
                    allowed,
                    "rrf_60_lexical_dense_filename",
                    set(segment_to_document),
                ),
                "production_hybrid_matches_fusion": True,
                "performance": {
                    "model_cache_bytes": model_bytes,
                    "cold_load_seconds": cold_load_seconds,
                    "warm_query_p50_ms": statistics.median(warm),
                    "warm_query_p95_ms": sorted(warm)[int(0.95 * (len(warm) - 1))],
                    "first_query_latencies_ms": query_latencies,
                    "backfill_seconds": indexing_seconds,
                    "passage_throughput_per_second": len(passage_sample) / passage_seconds,
                    "passage_sample_count": len(passage_sample),
                    "backfilled_documents": progress.reindexed,
                    "windows": window_count,
                    "segments": segment_count,
                    "sqlite_growth_bytes": after_bytes - before_bytes,
                    "bytes_per_vector_payload": embeddings.dimension * 4,
                    "peak_rss_kb": _peak_rss_kb(),
                    "batch_size": 16,
                },
            }
        finally:
            store.close()


if __name__ == "__main__":
    print(json.dumps(run_experiment(), ensure_ascii=False, indent=2, sort_keys=True))
