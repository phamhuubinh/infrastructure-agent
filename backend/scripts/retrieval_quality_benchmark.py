"""Offline, model-free retrieval benchmark for Orion's production knowledge.search path."""

from __future__ import annotations

import json
import math
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from orion.contracts import RuntimeScope
from orion.knowledge.blob_store import LocalBlobStore
from orion.knowledge.service import KnowledgeService
from orion.persistence.sqlite import SQLiteStore

CORPUS = Path(__file__).parents[1] / "benchmarks" / "retrieval_v2_corpus.json"


def _scope(session_id: str, attachments: tuple[str, ...], project_id: str) -> RuntimeScope:
    return RuntimeScope(
        session_id=session_id,
        attachment_ids=attachments,
        project_id=project_id,
        principal_id="local",
        workspace_id="local",
    )


def _metrics(ranks: list[list[int]]) -> dict[str, float]:
    if not ranks:
        return {"recall@1": 0.0, "recall@5": 0.0, "recall@10": 0.0, "mrr@10": 0.0, "ndcg@10": 0.0}
    count = len(ranks)
    return {
        f"recall@{k}": sum(sum(rank <= k for rank in case) / len(case) for case in ranks) / count
        for k in (1, 5, 10)
    } | {
        "mrr@10": sum(
            1 / min((rank for rank in case if rank <= 10), default=math.inf) for case in ranks
        )
        / count,
        "ndcg@10": sum(
            sum(1 / math.log2(rank + 1) for rank in case if rank <= 10)
            / sum(1 / math.log2(i + 1) for i in range(1, len(case) + 1))
            for case in ranks
        )
        / count,
    }


def run_baseline(corpus_path: Path = CORPUS) -> dict[str, Any]:
    corpus = json.loads(corpus_path.read_text(encoding="utf-8"))
    with TemporaryDirectory(prefix="orion-retrieval-benchmark-") as temporary:
        root = Path(temporary)
        store = SQLiteStore(root / "benchmark.db")
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
            attachments_a: list[str] = []
            for spec in corpus["documents"]:
                owner = spec["owner"]
                upload = (
                    knowledge.attach_project(owners[owner], spec["name"], spec["text"].encode())
                    if owner.startswith("project_")
                    else knowledge.attach(owners[owner], spec["name"], spec["text"].encode())
                )
                assert upload.status == "ready"
                documents[spec["key"]] = upload
                if owner == "session_a":
                    attachments_a.append(upload.attachment_id)
            runtime_scope = _scope(session_a, tuple(attachments_a), project_a)
            deleted = {
                spec["key"] for spec in corpus["documents"] if spec.get("delete_before_queries")
            }
            for key in deleted:
                assert knowledge.delete(documents[key].document.document_id, runtime_scope)
            by_document_id = {upload.document.document_id: key for key, upload in documents.items()}
            expected_segments = {
                key: {
                    str(row["segment_id"])
                    for row in store.document_segments(upload.document.document_id)
                }
                for key, upload in documents.items()
            }
            allowed = {
                spec["key"]
                for spec in corpus["documents"]
                if spec["owner"] in {"session_a", "project_a"} and spec["key"] not in deleted
            }
            cases: list[dict[str, Any]] = []
            relevant_ranks: list[list[int]] = []
            leakage_count = 0
            provenance_checks = 0
            provenance_correct = 0
            filename_total = 0
            filename_top_one = 0
            for spec in corpus["queries"]:
                hits = knowledge.search(runtime_scope, spec["query"], 10)
                keys = [by_document_id.get(hit.document.document_id, "<unknown>") for hit in hits]
                leakage_count += sum(key not in allowed for key in keys)
                for hit in hits:
                    source = knowledge.source_for_segment(hit)
                    key = by_document_id.get(hit.document.document_id)
                    provenance_checks += 1
                    if (
                        key is not None
                        and source.document_id == documents[key].document.document_id
                        and source.segment_id in expected_segments[key]
                        and source.source_kind == documents[key].document.source.kind
                        and source.source_id == documents[key].document.source.source_id
                        and source.page == hit.page
                        and source.section == hit.section
                    ):
                        provenance_correct += 1
                relevant = list(spec["relevant"])
                if relevant:
                    relevant_ranks.append(
                        [keys.index(key) + 1 if key in keys else 11 for key in relevant]
                    )
                if spec["category"] == "filename":
                    filename_total += 1
                    filename_top_one += int(bool(keys) and keys[0] in relevant)
                cases.append(
                    {
                        "key": spec["key"],
                        "category": spec["category"],
                        "retrieved": keys,
                        "relevant": relevant,
                        "first_relevant_rank": min(
                            (keys.index(key) + 1 for key in relevant if key in keys), default=None
                        ),
                    }
                )
            return {
                "corpus_version": corpus["version"],
                "ranker": "production_lexical_plus_hash",
                "query_count": len(cases),
                "metrics": _metrics(relevant_ranks),
                "filename_top1_rate": filename_top_one / filename_total,
                "provenance_accuracy": provenance_correct / provenance_checks
                if provenance_checks
                else 1.0,
                "leakage_count": leakage_count,
                "cases": cases,
            }
        finally:
            store.close()


if __name__ == "__main__":
    print(json.dumps(run_baseline(), ensure_ascii=False, indent=2, sort_keys=True))
