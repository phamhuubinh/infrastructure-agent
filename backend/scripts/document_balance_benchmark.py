"""Offline Phase 3C measurement of bounded document-balanced evidence selection."""

from __future__ import annotations

import argparse
import json
import math
import uuid
from collections import Counter
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from unittest.mock import patch

from orion.contracts import RetrievedSegment, RuntimeScope
from orion.knowledge.blob_store import LocalBlobStore
from orion.knowledge.evidence_selection import select_document_balanced
from orion.knowledge.local_embeddings import LocalE5Embeddings, model_status
from orion.knowledge.ranking import HYBRID_CANDIDATE_DEPTH
from orion.knowledge.semantic import SemanticIndexService
from orion.knowledge.service import KnowledgeService
from orion.persistence.sqlite import SQLiteStore

CORPUS = (
    Path(__file__).parents[1] / "benchmarks" / "retrieval_v2_document_balance_phase3c_corpus.json"
)


def _ids() -> Any:
    ordinal = 0
    while True:
        yield uuid.uuid5(uuid.NAMESPACE_URL, f"orion:phase3c:fixture:{ordinal}")
        ordinal += 1


def _text(spec: dict[str, Any]) -> bytes:
    sections = [
        f"# {section['title']}\n\n" + "\n\n".join([section["paragraph"]] * section["repeat"])
        for section in spec["sections"]
    ]
    return "\n\n".join(sections).encode("utf-8")


def _scope(session: str, project: str, attachments: list[str]) -> RuntimeScope:
    return RuntimeScope(
        session_id=session,
        project_id=project,
        attachment_ids=tuple(attachments),
        principal_id="local",
        workspace_id="local",
    )


def _case(
    hits: tuple[RetrievedSegment, ...],
    spec: dict[str, Any],
    keys_by_document: dict[str, str],
    labels_by_segment: dict[str, str],
    canonical: dict[str, dict[str, Any]],
    allowed: set[str],
    knowledge: KnowledgeService,
) -> dict[str, Any]:
    limit = int(spec["limit"])
    shown = hits[:limit]
    keys = [keys_by_document.get(hit.document.document_id, "<unknown>") for hit in shown]
    relevant = set(spec["relevant"])
    first_by_document = {key: keys.index(key) + 1 for key in relevant if key in keys}
    first_rank = min(first_by_document.values(), default=None)
    ideal = sum(1 / math.log2(rank + 1) for rank in range(1, min(len(relevant), limit) + 1))
    dcg = sum(1 / math.log2(rank + 1) for rank in first_by_document.values())
    counts = Counter(keys)
    provenance_correct = 0
    for hit in shown:
        row = canonical.get(hit.segment_id)
        source = knowledge.source_for_segment(hit)
        if (
            row is not None
            and hit.document.document_id == row["document_id"]
            and hit.text == row["text"]
            and hit.page == row["page"]
            and hit.section == row["section"]
            and source.document_id == row["document_id"]
            and source.segment_id == hit.segment_id
            and source.source_kind == hit.document.source.kind
            and source.source_id == hit.document.source.source_id
            and source.page == hit.page
            and source.section == hit.section
        ):
            provenance_correct += 1
    return {
        "ranked_segments": [labels_by_segment.get(hit.segment_id, "<unknown>") for hit in shown],
        "scores": [hit.score for hit in shown],
        "documents": keys,
        "result_count": len(shown),
        "first_relevant_rank": first_rank,
        "recall@1": sum(rank <= 1 for rank in first_by_document.values()) / len(relevant)
        if relevant
        else None,
        "recall@k": len(first_by_document) / len(relevant) if relevant else None,
        "mrr@k": 1 / first_rank if first_rank is not None else (0.0 if relevant else None),
        "ndcg@k": dcg / ideal if ideal else None,
        "relevant_documents_represented@k": len(first_by_document),
        "expected_relevant_documents": len(relevant),
        "unique_documents@k": len(counts),
        "max_segments_from_one_document@k": max(counts.values(), default=0),
        "exact_filename_top_one": keys[0] in relevant
        if spec["category"] == "filename" and keys
        else None,
        "provenance_accuracy": provenance_correct / len(shown) if shown else 1.0,
        "leakage_count": sum(key not in allowed for key in keys),
    }


def _measure(
    knowledge: KnowledgeService,
    scope: RuntimeScope,
    corpus: dict[str, Any],
    keys_by_document: dict[str, str],
    labels_by_segment: dict[str, str],
    canonical: dict[str, dict[str, Any]],
    allowed: set[str],
    documents: dict[str, Any],
) -> dict[str, Any]:
    cases: list[dict[str, Any]] = []
    for spec in corpus["queries"]:
        document_ids = tuple(
            documents[key].document.document_id for key in spec.get("document_filter", [])
        )
        raw = knowledge.search(scope, spec["query"], HYBRID_CANDIDATE_DEPTH, document_ids)
        selected = select_document_balanced(raw, int(spec["limit"]))
        assert all(any(hit is candidate for candidate in raw) for hit in selected)
        cases.append(
            {
                "key": spec["key"],
                "category": spec["category"],
                "limit": spec["limit"],
                "relevant": spec["relevant"],
                "document_filter": spec.get("document_filter", []),
                "candidate_count": len(raw),
                "candidate_documents": [keys_by_document[hit.document.document_id] for hit in raw],
                "raw": _case(
                    raw, spec, keys_by_document, labels_by_segment, canonical, allowed, knowledge
                ),
                "selected": _case(
                    selected,
                    spec,
                    keys_by_document,
                    labels_by_segment,
                    canonical,
                    allowed,
                    knowledge,
                ),
            }
        )
    summaries: dict[str, Any] = {}
    for mode in ("raw", "selected"):
        relevant_cases = [case[mode] for case in cases if case["relevant"]]
        multi_cases = [case[mode] for case in cases if len(case["relevant"]) > 1]
        all_cases = [case[mode] for case in cases]
        summaries[mode] = {
            metric: sum(case[metric] for case in relevant_cases) / len(relevant_cases)
            for metric in ("recall@1", "recall@k", "mrr@k", "ndcg@k")
        } | {
            "multi_document_coverage@k": sum(
                case["relevant_documents_represented@k"] / case["expected_relevant_documents"]
                for case in multi_cases
            )
            / len(multi_cases),
            "multi_document_represented_count@k": sum(
                case["relevant_documents_represented@k"] for case in multi_cases
            ),
            "mean_unique_documents@k": sum(case["unique_documents@k"] for case in all_cases)
            / len(all_cases),
            "max_segments_from_one_document@k": max(
                case["max_segments_from_one_document@k"] for case in all_cases
            ),
            "exact_filename_top_one": next(
                case[mode]["exact_filename_top_one"]
                for case in cases
                if case["category"] == "filename"
            ),
            "provenance_accuracy": sum(
                case["provenance_accuracy"] * case["result_count"] for case in all_cases
            )
            / max(1, sum(case["result_count"] for case in all_cases)),
            "leakage_count": sum(case["leakage_count"] for case in all_cases),
        }
    return {"summary": summaries, "cases": cases}


def run_experiment(corpus_path: Path = CORPUS, *, include_hybrid: bool = False) -> dict[str, Any]:
    """Run on real ingestion; optional E5 indexing is explicit and local-only."""
    corpus = json.loads(corpus_path.read_text(encoding="utf-8"))
    assert corpus["candidate_depth"] == HYBRID_CANDIDATE_DEPTH
    if include_hybrid and model_status() != "installed":
        raise RuntimeError("Optional local E5 model is not installed")
    with TemporaryDirectory(prefix="orion-phase3c-benchmark-") as temporary:
        with patch("uuid.uuid4", side_effect=_ids()):
            root = Path(temporary)
            store = SQLiteStore(root / "benchmark.db")
            try:
                blobs = LocalBlobStore(root / "blobs")
                knowledge = KnowledgeService(store, blobs)
                project_a = str(store.create_project("Phase 3C A")["project_id"])
                project_b = str(store.create_project("Phase 3C B")["project_id"])
                session_a = store.create_session(project_id=project_a)
                session_b = store.create_session(project_id=project_b)
                owners = {
                    "project_a": project_a,
                    "project_b": project_b,
                    "session_a": session_a,
                    "session_b": session_b,
                }
                documents: dict[str, Any] = {}
                attachments: list[str] = []
                for spec in corpus["documents"]:
                    owner = spec["owner"]
                    content = _text(spec)
                    upload = (
                        knowledge.attach_project(
                            owners[owner], spec["name"], content, "text/markdown"
                        )
                        if owner.startswith("project_")
                        else knowledge.attach(owners[owner], spec["name"], content, "text/markdown")
                    )
                    assert upload.status == "ready", (spec["key"], upload.error_message)
                    documents[spec["key"]] = upload
                    if owner == "session_a":
                        attachments.append(upload.attachment_id)
                scope = _scope(session_a, project_a, attachments)
                deleted = {
                    spec["key"] for spec in corpus["documents"] if spec.get("delete_before_queries")
                }
                for key in deleted:
                    assert knowledge.delete(documents[key].document.document_id, scope)
                keys_by_document = {
                    upload.document.document_id: key for key, upload in documents.items()
                }
                canonical: dict[str, dict[str, Any]] = {}
                labels_by_segment: dict[str, str] = {}
                segment_counts: dict[str, int] = {}
                for key, upload in documents.items():
                    rows = store.document_segments(upload.document.document_id)
                    segment_counts[key] = len(rows)
                    for row in rows:
                        segment_id = str(row["segment_id"])
                        canonical[segment_id] = row
                        labels_by_segment[segment_id] = f"{key}#{row['ordinal']}"
                allowed = {
                    spec["key"]
                    for spec in corpus["documents"]
                    if spec["owner"] in {"session_a", "project_a"} and spec["key"] not in deleted
                }
                modes = {
                    "baseline": _measure(
                        knowledge,
                        scope,
                        corpus,
                        keys_by_document,
                        labels_by_segment,
                        canonical,
                        allowed,
                        documents,
                    )
                }
                if include_hybrid:
                    index = SemanticIndexService(store, LocalE5Embeddings())
                    index.reconcile_missing(max_documents=len(corpus["documents"]))
                    hybrid = KnowledgeService(
                        store, blobs, semantic_retriever_factory=lambda: index
                    )
                    modes["hybrid"] = _measure(
                        hybrid,
                        scope,
                        corpus,
                        keys_by_document,
                        labels_by_segment,
                        canonical,
                        allowed,
                        documents,
                    )
                return {
                    "corpus_version": corpus["version"],
                    "candidate_depth": HYBRID_CANDIDATE_DEPTH,
                    "document_segment_counts": segment_counts,
                    "modes": modes,
                }
            finally:
                store.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--with-hybrid", action="store_true")
    args = parser.parse_args()
    print(
        json.dumps(
            run_experiment(include_hybrid=args.with_hybrid),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
