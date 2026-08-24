# Projects, RAG, and memory

## Purpose

Project knowledge helps Orion reason with runbooks, architecture documents, incident notes, and other operator-provided material. Retrieval is evidence/context, not execution authority.

## Separation

- Project storage owns documents and metadata.
- Retrieval/index service owns chunks/embeddings/search.
- Session runtime requests project search through explicit tools.
- Authority engine never accepts a target/source merely because a document mentioned it.

## Retrieval tools

Recommended model-facing capabilities:

- `project.search` — retrieve bounded relevant snippets with document IDs;
- `project.document.read` — read a bounded region of an exact selected document.

Results include project/document IDs and provenance.

## Ingestion

Ingestion must be recoverable across file storage, metadata storage, and vector index. Use staging/journaling/tombstones so partial uploads/deletes do not appear healthy.

## Prompt injection

Retrieved text is untrusted. It cannot override system policy, tool authority, permissions, or approvals. The model prompt should clearly delimit retrieved data.

## Memory

Do not implement implicit personal memory as hidden execution state. Product memory should be explicit, scoped, inspectable, deletable, and never a source of infrastructure authority by itself.
