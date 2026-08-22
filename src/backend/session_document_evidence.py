"""Deterministic, session-scoped evidence for Chat attachments.

This deliberately does not call the Project RAG API.  Chat attachments are
read only through the active server-owned session id, extracted lazily, and
discarded after the request.  The returned payload is model context, never
execution authority.
"""

from __future__ import annotations

import io
import json
import re
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass

from src.backend.document_service import get_file, list_files, read_file_content
from src.shared.attachment_evidence import ATTACHMENT_EVIDENCE_MAX_BYTES

_DIRECT_TEXT_CHARS = 3_000
MAX_ATTACHMENTS_PER_REQUEST = 8
MAX_ATTACHMENT_RAW_BYTES = 8 * 1024 * 1024
MAX_ATTACHMENT_EXTRACTED_CHARS = 24_000
_CHUNK_CHARS = 900
_CHUNK_OVERLAP_CHARS = 120
_MAX_RETRIEVED_CHUNKS = 4
_MAX_RETRIEVED_CHUNK_CHARS = 750
_TOKEN_RE = re.compile(r"[\wÀ-ỹ]+", re.UNICODE)
_TEXT_SUFFIXES = frozenset(
    {
        ".bash",
        ".c",
        ".cfg",
        ".conf",
        ".cpp",
        ".css",
        ".csv",
        ".env.example",
        ".go",
        ".html",
        ".ini",
        ".java",
        ".js",
        ".json",
        ".log",
        ".md",
        ".markdown",
        ".py",
        ".rb",
        ".rs",
        ".sh",
        ".sql",
        ".toml",
        ".ts",
        ".txt",
        ".xml",
        ".yaml",
        ".yml",
    }
)
_IMAGE_SUFFIXES = frozenset(
    {".bmp", ".gif", ".jpeg", ".jpg", ".png", ".tif", ".tiff", ".webp"}
)


@dataclass(frozen=True, slots=True)
class _ExtractedDocument:
    filename: str
    text: str | None
    limitation: str | None = None


class SessionDocumentEvidenceService:
    """Build bounded attachment evidence for exactly one active chat session."""

    def __init__(self, dsn: str | None) -> None:
        self._dsn = dsn

    def build(
        self, *, session_id: str, question: str
    ) -> tuple[Mapping[str, object], ...]:
        """Return untrusted evidence without exposing ids or storage paths.

        Indexing is intentionally lazy and request-local.  Consequently a
        deleted attachment has no stale chunks that can survive into a future
        request.
        """

        if not isinstance(session_id, str) or not session_id:
            raise ValueError("session_id must be non-empty.")
        documents = list_files(self._dsn, session_id=session_id, limit=10_000)
        extracted: list[_ExtractedDocument] = []
        limitations: list[dict[str, object]] = []
        if len(documents) > MAX_ATTACHMENTS_PER_REQUEST:
            limitations.append(
                {
                    "status": "limitation",
                    "reason": "attachment_budget_exceeded",
                    "attachment_count": len(documents),
                    "skipped_count": len(documents) - MAX_ATTACHMENTS_PER_REQUEST,
                }
            )
        raw_bytes = 0
        extracted_chars = 0
        for index, listed in enumerate(documents[:MAX_ATTACHMENTS_PER_REQUEST]):
            doc_id = listed.get("id")
            if not isinstance(doc_id, str):
                continue
            document = get_file(self._dsn, doc_id)
            # A list result is untrusted storage metadata.  Recheck the
            # authority scope before each read, including source-mode storage.
            if (
                not isinstance(document, dict)
                or document.get("session_id") != session_id
            ):
                continue
            size_bytes = listed.get("size_bytes", document.get("size_bytes", 0))
            if not isinstance(size_bytes, int) or size_bytes < 0:
                size_bytes = 0
            if raw_bytes + size_bytes > MAX_ATTACHMENT_RAW_BYTES:
                limitations.append(
                    {
                        "status": "limitation",
                        "reason": "attachment_budget_exceeded",
                        "attachment": _safe_name(document),
                        "remaining_count": len(documents) - index,
                    }
                )
                break
            content = read_file_content(str(document.get("storage_path", "")))
            if content is None:
                extracted.append(
                    _ExtractedDocument(_safe_name(document), None, "file_unavailable")
                )
                continue
            raw_bytes += len(content)
            remaining_chars = MAX_ATTACHMENT_EXTRACTED_CHARS - extracted_chars
            if remaining_chars <= 0:
                limitations.append(
                    {
                        "status": "limitation",
                        "reason": "attachment_budget_exceeded",
                        "attachment": _safe_name(document),
                    }
                )
                break
            item = self._extract(document, content, remaining_chars)
            extracted.append(item)
            extracted_chars += len(item.text or "")

        usable = [item for item in extracted if item.text]
        limitations.extend(
            [
                {
                    "attachment": item.filename,
                    "status": "limitation",
                    "reason": item.limitation,
                }
                for item in extracted
                if item.limitation is not None
            ]
        )
        if not usable and not limitations:
            return ()

        total_chars = sum(len(item.text or "") for item in usable)
        if total_chars <= _DIRECT_TEXT_CHARS:
            evidence: dict[str, object] = {
                "scope": "current_session_attachments",
                "mode": "direct_context",
                "untrusted": True,
                "documents": [
                    {"attachment": item.filename, "text": item.text} for item in usable
                ],
            }
        else:
            evidence = {
                "scope": "current_session_attachments",
                "mode": "retrieval",
                "untrusted": True,
                "chunks": self._retrieve(usable, question),
            }
        if limitations:
            evidence["limitations"] = limitations
        return (self._fit_payload(evidence),)

    @staticmethod
    def _fit_payload(payload: dict[str, object]) -> dict[str, object]:
        """Keep the serialized evidence within the controller contract."""

        def encoded() -> bytes:
            return json.dumps(
                payload, ensure_ascii=False, separators=(",", ":")
            ).encode("utf-8")

        if len(encoded()) <= ATTACHMENT_EVIDENCE_MAX_BYTES:
            return payload
        limitations = payload.setdefault("limitations", [])
        if isinstance(limitations, list) and not any(
            isinstance(item, dict) and item.get("evidence_truncated") is True
            for item in limitations
        ):
            limitations.append(
                {
                    "status": "limitation",
                    "reason": "attachment_budget_exceeded",
                    "evidence_truncated": True,
                }
            )
        entries = payload.get("documents") or payload.get("chunks") or []
        if isinstance(entries, list):
            for entry in entries:
                if isinstance(entry, dict) and isinstance(entry.get("text"), str):
                    entry["text"] = entry["text"][: max(80, len(entry["text"]) // 2)]
                    if len(encoded()) <= ATTACHMENT_EVIDENCE_MAX_BYTES:
                        return payload
            while len(entries) > 1 and len(encoded()) > ATTACHMENT_EVIDENCE_MAX_BYTES:
                entries.pop()
        if len(encoded()) > ATTACHMENT_EVIDENCE_MAX_BYTES:
            entries = payload.get("documents") or payload.get("chunks") or []
            if isinstance(entries, list):
                while (
                    len(entries) > 1 and len(encoded()) > ATTACHMENT_EVIDENCE_MAX_BYTES
                ):
                    entries.pop()
        if len(encoded()) > ATTACHMENT_EVIDENCE_MAX_BYTES:
            # Fixed metadata is small enough to fit; omit content rather than
            # violating the hard contract or leaking an unbounded payload.
            payload.pop("documents", None)
            payload.pop("chunks", None)
        if len(encoded()) > ATTACHMENT_EVIDENCE_MAX_BYTES:
            return {
                "scope": "current_session_attachments",
                "mode": "limitation",
                "untrusted": True,
                "limitations": [
                    {
                        "status": "limitation",
                        "reason": "attachment_budget_exceeded",
                        "evidence_truncated": True,
                    }
                ],
            }
        return payload

    def _extract(
        self,
        document: Mapping[str, object],
        content: bytes,
        remaining_chars: int,
    ) -> _ExtractedDocument:
        filename = _safe_name(document)
        suffix = _suffix(filename)
        content_type = str(document.get("content_type", "")).lower()
        if suffix == ".pdf" or content_type == "application/pdf":
            return self._extract_pdf(filename, content, remaining_chars)
        if suffix in _IMAGE_SUFFIXES or content_type.startswith("image/"):
            return _ExtractedDocument(filename, None, "ocr_unavailable_visual_content")
        if (
            suffix not in _TEXT_SUFFIXES
            and not content_type.startswith("text/")
            and content_type
            not in {"application/json", "application/x-yaml", "text/yaml"}
        ):
            return _ExtractedDocument(filename, None, "unsupported_file_type")
        try:
            byte_limit = max(remaining_chars * 4, remaining_chars)
            raw_truncated = len(content) > byte_limit
            prefix = content[:byte_limit]
            try:
                text = prefix.decode("utf-8")
            except UnicodeDecodeError as exc:
                if exc.reason == "unexpected end of data" and exc.end == len(prefix):
                    text = prefix[: exc.start].decode("utf-8")
                else:
                    text = prefix.decode("latin-1")
        except UnicodeDecodeError:
            return _ExtractedDocument(filename, None, "unreadable_text")
        normalized, text_truncated = _normalize_bounded(text, remaining_chars)
        limitation = (
            "attachment_budget_exceeded"
            if raw_truncated or text_truncated
            else "no_usable_text"
            if not normalized
            else None
        )
        return _ExtractedDocument(
            filename,
            normalized or None,
            limitation,
        )

    @staticmethod
    def _extract_pdf(
        filename: str, content: bytes, remaining_chars: int
    ) -> _ExtractedDocument:
        try:
            from pypdf import PdfReader
        except ImportError:
            return _ExtractedDocument(filename, None, "pdf_text_extractor_unavailable")
        try:
            reader = PdfReader(io.BytesIO(content))
            parts: list[str] = []
            collected = 0
            truncated = False
            for page in reader.pages:
                page_source = page.extract_text() or ""
                page_budget = remaining_chars - collected
                page_text, page_truncated = _normalize_bounded(
                    page_source, max(page_budget, 0)
                )
                if page_text:
                    separator = 1 if parts else 0
                    if len(page_text) + separator > page_budget:
                        page_text, _ = _normalize_bounded(
                            page_source, max(page_budget - separator, 0)
                        )
                        page_truncated = True
                    if page_text:
                        collected += separator
                        collected += len(page_text)
                        parts.append(page_text)
                if page_truncated:
                    truncated = True
                    break
            text = "\n".join(parts)
        except Exception:
            return _ExtractedDocument(filename, None, "unparseable_pdf")
        if not text:
            return _ExtractedDocument(filename, None, "ocr_unavailable_scanned_pdf")
        return _ExtractedDocument(
            filename,
            text,
            "attachment_budget_exceeded" if truncated else None,
        )

    @staticmethod
    def _retrieve(
        documents: list[_ExtractedDocument], question: str
    ) -> list[dict[str, object]]:
        query_terms = Counter(_tokens(question))
        candidates: list[tuple[int, int, str, str]] = []
        order = 0
        for document in documents:
            for chunk in _chunks(document.text or ""):
                score = sum(
                    query_terms[term] * count
                    for term, count in Counter(_tokens(chunk)).items()
                )
                candidates.append((score, -order, document.filename, chunk))
                order += 1
        candidates.sort(reverse=True)
        selected = candidates[:_MAX_RETRIEVED_CHUNKS]
        return [
            {
                "attachment": filename,
                "text": chunk[:_MAX_RETRIEVED_CHUNK_CHARS],
                "score": score,
            }
            for score, _order, filename, chunk in selected
        ]


def _safe_name(document: Mapping[str, object]) -> str:
    name = str(document.get("filename", "attachment"))
    return name.replace("\r", " ").replace("\n", " ")[:160] or "attachment"


def _suffix(filename: str) -> str:
    lower = filename.lower()
    return (
        ".env.example"
        if lower.endswith(".env.example")
        else "." + lower.rsplit(".", 1)[-1]
        if "." in lower
        else ""
    )


def _normalize(text: str) -> str:
    return _normalize_bounded(text, None)[0]


def _normalize_bounded(text: str, max_chars: int | None) -> tuple[str, bool]:
    lines: list[str] = []
    used = 0
    for raw_line in text.replace("\x00", "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        separator = 1 if lines else 0
        if max_chars is not None and used + separator + len(line) > max_chars:
            remaining = max_chars - used - separator
            if remaining > 0:
                lines.append(line[:remaining])
            return "\n".join(lines), True
        lines.append(line)
        used += separator + len(line)
    return "\n".join(lines), False


def _tokens(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


def _chunks(text: str) -> list[str]:
    if len(text) <= _CHUNK_CHARS:
        return [text]
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + _CHUNK_CHARS)
        chunks.append(text[start:end])
        if end == len(text):
            break
        start = end - _CHUNK_OVERLAP_CHARS
    return chunks
