from __future__ import annotations

import io
import re
from dataclasses import dataclass
from pathlib import Path

from docx import Document
from pypdf import PdfReader


SUPPORTED_EXTENSIONS = {".pdf", ".txt", ".md", ".docx"}


class DocumentExtractionError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ExtractedSection:
    text: str
    page_number: int | None = None


def _decode_text(content: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "utf-16", "cp1252"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise DocumentExtractionError("The text encoding could not be detected")


def extract_sections(filename: str, content: bytes) -> list[ExtractedSection]:
    extension = Path(filename).suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        raise DocumentExtractionError(
            f"Unsupported file type: {extension or 'unknown'}"
        )

    try:
        if extension in {".txt", ".md"}:
            sections = [ExtractedSection(_decode_text(content))]
        elif extension == ".pdf":
            reader = PdfReader(io.BytesIO(content))
            sections = [
                ExtractedSection(page.extract_text() or "", index + 1)
                for index, page in enumerate(reader.pages)
            ]
        else:
            document = Document(io.BytesIO(content))
            text = "\n".join(
                paragraph.text for paragraph in document.paragraphs
                if paragraph.text.strip()
            )
            sections = [ExtractedSection(text)]
    except DocumentExtractionError:
        raise
    except Exception as exc:
        raise DocumentExtractionError(
            f"Could not extract text from {filename}"
        ) from exc

    cleaned = [
        ExtractedSection(
            text=re.sub(r"\n{3,}", "\n\n", section.text).strip(),
            page_number=section.page_number,
        )
        for section in sections
        if section.text and section.text.strip()
    ]
    if not cleaned:
        raise DocumentExtractionError(
            "No readable text was found. Scanned PDFs require OCR, which is not enabled."
        )
    return cleaned


def chunk_sections(
    sections: list[ExtractedSection],
    *,
    chunk_words: int = 700,
    overlap_words: int = 100,
) -> list[dict]:
    if chunk_words <= overlap_words:
        raise ValueError("chunk_words must be greater than overlap_words")

    chunks: list[dict] = []
    step = chunk_words - overlap_words
    for section in sections:
        words = section.text.split()
        for start in range(0, len(words), step):
            group = words[start : start + chunk_words]
            if not group:
                continue
            chunks.append(
                {
                    "chunk_index": len(chunks),
                    "text": " ".join(group),
                    "page_number": section.page_number,
                    "word_count": len(group),
                }
            )
            if start + chunk_words >= len(words):
                break
    return chunks

