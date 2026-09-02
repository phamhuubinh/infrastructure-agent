"""Small deterministic local implementations of the knowledge ports."""

from __future__ import annotations

import hashlib
import math
import re

from orion.knowledge.ports import Chunk, IndexedSegment, ParsedDocument, ParsedSection

_WORD = re.compile(r"[a-z0-9]+")
_SYNONYMS = {
    "automobile": "car",
    "vehicle": "car",
    "feline": "cat",
    "canine": "dog",
    "retention": "retain",
    "retaining": "retain",
    "backup": "backups",
}


def _terms(text: str) -> list[str]:
    return [_SYNONYMS.get(term, term) for term in _WORD.findall(text.lower())]


class PlainTextParser:
    """Parses safe local text/Markdown."""

    _supported = {"text/plain", "text/markdown", "text/x-markdown", None}

    def parse(self, content: bytes, media_type: str | None) -> ParsedDocument:
        if media_type not in self._supported:
            raise ValueError(f"Unsupported document media type: {media_type}")
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError as error:
            raise ValueError("Document is not valid UTF-8 text") from error
        text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
        if not text:
            raise ValueError("Document has no readable text")
        sections: list[ParsedSection] = []
        current_title: str | None = None
        current_lines: list[str] = []
        for line in text.splitlines():
            if line.startswith("#") and line.lstrip("#").startswith(" "):
                if current_lines:
                    section_text = "\n".join(current_lines).strip()
                    if section_text:
                        sections.append(ParsedSection(section_text, current_title))
                current_title = line.lstrip("#").strip()
                current_lines = []
            else:
                current_lines.append(line)
        if current_lines:
            section_text = "\n".join(current_lines).strip()
            if section_text:
                sections.append(ParsedSection(section_text, current_title))
        if not sections:
            sections.append(ParsedSection(text, current_title))
        return ParsedDocument(text=text, sections=tuple(sections))


class ParagraphChunker:
    def __init__(self, maximum_characters: int = 900) -> None:
        self._maximum_characters = maximum_characters

    def chunk(self, parsed: ParsedDocument) -> tuple[Chunk, ...]:
        chunks: list[Chunk] = []
        ordinal = 0
        for source in parsed.sections:
            current = ""
            for paragraph in (part.strip() for part in source.text.split("\n\n") if part.strip()):
                if current and len(current) + len(paragraph) + 2 > self._maximum_characters:
                    chunks.append(Chunk(ordinal, current, source.page, source.section))
                    ordinal += 1
                    current = ""
                while len(paragraph) > self._maximum_characters:
                    if current:
                        chunks.append(Chunk(ordinal, current, source.page, source.section))
                        ordinal += 1
                        current = ""
                    chunks.append(
                        Chunk(
                            ordinal,
                            paragraph[: self._maximum_characters],
                            source.page,
                            source.section,
                        )
                    )
                    ordinal += 1
                    paragraph = paragraph[self._maximum_characters :]
                current = f"{current}\n\n{paragraph}".strip() if current else paragraph
            if current:
                chunks.append(Chunk(ordinal, current, source.page, source.section))
                ordinal += 1
        return tuple(chunks)


class HashingEmbedding:
    """A dependency-free local vector representation with a small semantic normalizer."""

    def embed(self, text: str) -> dict[str, float]:
        vector: dict[str, float] = {}
        for term in _terms(text):
            bucket = hashlib.sha256(term.encode()).hexdigest()[:8]
            vector[bucket] = vector.get(bucket, 0.0) + 1.0
        return vector


class LocalLexicalIndex:
    def search(self, query: str, segments: tuple[IndexedSegment, ...]) -> dict[str, float]:
        query_terms = set(_terms(query))
        if not query_terms:
            return {}
        scores: dict[str, float] = {}
        for segment in segments:
            terms = _terms(segment.text)
            if terms:
                overlap = sum(terms.count(term) for term in query_terms)
                if overlap:
                    scores[segment.segment_id] = overlap / math.sqrt(len(terms))
        return scores


class LocalVectorIndex:
    def __init__(self, embeddings: HashingEmbedding) -> None:
        self._embeddings = embeddings

    def search(self, query: str, segments: tuple[IndexedSegment, ...]) -> dict[str, float]:
        query_vector = self._embeddings.embed(query)
        query_norm = math.sqrt(sum(value * value for value in query_vector.values()))
        if not query_norm:
            return {}
        scores: dict[str, float] = {}
        for segment in segments:
            vector = self._embeddings.embed(segment.text)
            denominator = query_norm * math.sqrt(sum(value * value for value in vector.values()))
            if denominator:
                score = sum(query_vector.get(key, 0.0) * value for key, value in vector.items())
                if score:
                    scores[segment.segment_id] = score / denominator
        return scores
