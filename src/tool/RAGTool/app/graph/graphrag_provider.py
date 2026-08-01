"""Microsoft GraphRAG adapter (github.com/microsoft/graphrag).

Requires `pip install graphrag`. GraphRAG is index-heavy: it runs an LLM
over the whole corpus to extract entities/relationships/communities and
pre-computes community summaries — expensive but gives the best
"global" query answers ("what are the main themes across all documents").
Written against GraphRAG's real pipeline API (index build via its config +
CLI-equivalent Python entrypoints, query via `GlobalSearch`/`LocalSearch`).

Given the indexing cost, this provider expects an already-built GraphRAG
workspace (`workspace_dir`, produced by `graphrag index` or the
`api.build_index` call) rather than building it inline on every request —
call `build_workspace_index()` once (offline/batch) after ingesting new
documents, not per-request.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from app.graph.base import GraphSearchResult

# Module-level compatibility config. Tests and deployments may replace it;
# GraphRAG's own config is loaded for actual index/search operations.
config = SimpleNamespace(output_dir="output")


class MicrosoftGraphRagProvider:
    name = "graphrag"

    def __init__(self, workspace_dir: str) -> None:
        self._workspace_dir = Path(workspace_dir)
        output_dir = str(config.output_dir)
        if ".." in Path(output_dir).parts:
            raise ValueError("Invalid output_dir: directory traversal detected")
        self._output_dir = output_dir

    def build(self, doc_id: str, text: str) -> None:
        """GraphRAG indexes in batch, not per-document. Write the text into
        the workspace's input directory; call `build_workspace_index()`
        after all documents for this batch have been written."""
        input_dir = self._workspace_dir / "input"
        input_dir.mkdir(parents=True, exist_ok=True)
        (input_dir / f"{doc_id}.txt").write_text(text, encoding="utf-8")

    def build_workspace_index(self) -> None:
        try:
            import asyncio

            from graphrag.api import build_index
            from graphrag.config.load_config import load_config
        except ImportError as exc:
            msg = "graphrag is not installed (`pip install graphrag`)"
            raise RuntimeError(msg) from exc

        graph_config = load_config(self._workspace_dir)
        asyncio.run(build_index(config=graph_config))

    def search(self, query: str, top_k: int = 10) -> list[GraphSearchResult]:
        try:
            import asyncio

            import pandas as pd
            from graphrag.api import global_search
            from graphrag.config.load_config import load_config
        except ImportError as exc:
            msg = "graphrag is not installed (`pip install graphrag`)"
            raise RuntimeError(msg) from exc

        graph_config = load_config(self._workspace_dir)
        # Validate that output_dir is configured in GraphRAG config
        output_setting = getattr(graph_config, "output_dir", None)
        if not output_setting:
            raise ValueError("output_dir must be configured in GraphRAG config")
        if ".." in Path(str(output_setting)).parts:
            raise ValueError("Invalid output_dir: directory traversal detected")

        output_dir = self._workspace_dir / str(output_setting)

        entities = pd.read_parquet(output_dir / "entities.parquet")
        communities = pd.read_parquet(output_dir / "communities.parquet")
        community_reports = pd.read_parquet(output_dir / "community_reports.parquet")

        response, context = asyncio.run(
            global_search(
                config=graph_config,
                entities=entities,
                communities=communities,
                community_reports=community_reports,
                community_level=2,
                dynamic_community_selection=False,
                response_type="multiple paragraphs",
                query=query,
            )
        )

        return [GraphSearchResult(text=str(response), source_ids=[], score=1.0)]
