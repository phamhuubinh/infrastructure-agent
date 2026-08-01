from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.project_store import ProjectStore


def test_projects_persist_and_remain_isolated(tmp_path: Path) -> None:
    store = ProjectStore(tmp_path)
    alpha = store.create("Alpha", "first corpus")
    beta = store.create("Beta", "second corpus")

    store.add_document(alpha["id"], {"id": "doc-a", "chunk_ids": ["a-1"]})
    store.add_document(beta["id"], {"id": "doc-b", "chunk_ids": ["b-1"]})
    store.add_analysis(
        alpha["id"],
        {"id": "analysis-a", "query": "alpha", "retrieved": []},
    )

    reloaded = ProjectStore(tmp_path)
    assert [doc["id"] for doc in reloaded.get(alpha["id"])["documents"]] == ["doc-a"]
    assert [doc["id"] for doc in reloaded.get(beta["id"])["documents"]] == ["doc-b"]
    assert reloaded.get(beta["id"])["analyses"] == []
    assert reloaded.get("default")["documents"] == []


def test_analysis_history_is_bounded(tmp_path: Path) -> None:
    store = ProjectStore(tmp_path)
    project = store.create("Bounded")
    for index in range(105):
        store.add_analysis(
            project["id"],
            {"id": str(index), "query": str(index), "retrieved": []},
        )

    analyses = store.get(project["id"])["analyses"]
    assert len(analyses) == 100
    assert analyses[0]["id"] == "104"
    assert analyses[-1]["id"] == "5"


def test_delete_removes_only_selected_project_documents(tmp_path: Path) -> None:
    store = ProjectStore(tmp_path)
    alpha = store.create("Alpha")
    beta = store.create("Beta")
    alpha_dir = store.project_documents_dir(alpha["id"])
    beta_dir = store.project_documents_dir(beta["id"])
    (alpha_dir / "a.txt").write_text("a")
    (beta_dir / "b.txt").write_text("b")

    assert store.delete(alpha["id"])
    assert not alpha_dir.exists()
    assert beta_dir.exists()
    assert store.get(beta["id"])["name"] == "Beta"
