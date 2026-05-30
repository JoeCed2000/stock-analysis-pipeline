"""PDF retrieval service for the chat widget.

Extracts text from PDFs, chunks them, indexes in SQLite FTS5,
and searches for relevant passages at query time.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Optional

import logging

logger = logging.getLogger(__name__)

# Approximate characters per page (for chunk sizing)
CHARS_PER_CHUNK = 1000
CHUNK_OVERLAP = 100


def _hash_file(path: str) -> str:
    """SHA256 of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(8192)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _extract_text(pdf_path: str) -> str:
    """Extract text from a PDF file. Uses pymupdf if available, otherwise pdftotext."""
    try:
        import fitz  # pymupdf
        doc = fitz.open(pdf_path)
        text_parts = []
        for page in doc:
            text_parts.append(page.get_text())
        doc.close()
        return "\n\n".join(text_parts)
    except ImportError:
        pass

    # Fallback to pdftotext
    import subprocess
    try:
        result = subprocess.run(
            ["pdftotext", "-layout", pdf_path, "-"],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            return result.stdout
        logger.warning(f"pdftotext failed: {result.stderr[:200]}")
    except (FileNotFoundError, subprocess.TimeoutExpired):
        logger.warning("pdftotext not available")
    return ""


def _chunk_text(text: str) -> list[dict]:
    """Split text into overlapping chunks. Returns list of {content, page_hint}."""
    paragraphs = text.split("\n\n")
    chunks = []
    current = ""
    for para in paragraphs:
        if len(current) + len(para) > CHARS_PER_CHUNK and current:
            chunks.append({"content": current.strip()})
            # Overlap: keep last bit
            overlap_start = max(0, len(current) - CHUNK_OVERLAP)
            current = current[overlap_start:] + "\n\n" + para
        else:
            if current:
                current += "\n\n" + para
            else:
                current = para
    if current.strip():
        chunks.append({"content": current.strip()})
    return chunks


def _detect_section_title(chunk: str) -> Optional[str]:
    """Try to detect a section title from the first line of a chunk."""
    first_line = chunk.split("\n")[0].strip()
    # Heuristic: short line, uppercase or title-like, ends with a known pattern
    if len(first_line) < 80 and (
        first_line.isupper()
        or first_line[0].isupper()
        or first_line.endswith("：")
        or first_line.endswith(":")
    ):
        return first_line
    return None


def ingest_pdf(
    pdf_path: str,
    ticker: str,
    title: Optional[str] = None,
    pdf_id: Optional[str] = None,
) -> Optional[str]:
    """Ingest a PDF into the chat system: extract text, chunk, index.

    Returns the pdf_id, or None on failure.
    """
    from . import chat_store

    path = Path(pdf_path)
    if not path.exists():
        logger.warning(f"PDF not found: {pdf_path}")
        return None

    if title is None:
        title = path.stem

    if pdf_id is None:
        pdf_id = f"pdf_{ticker}_{hashlib.md5(str(path).encode()).hexdigest()[:8]}"

    # Extract text
    text = _extract_text(str(path))
    if not text:
        logger.warning(f"No text extracted from {pdf_path}")
        return None

    # Hash
    sha = _hash_file(str(path))

    # Store document
    report_date = None
    try:
        mtime = os.path.getmtime(str(path))
        from datetime import datetime, timezone
        report_date = datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat()
    except OSError:
        pass

    chat_store.upsert_pdf_document(
        pdf_id, ticker, title,
        report_date=report_date,
        source_path=str(path),
        sha256=sha,
        summary=text[:500] if text else None,
    )

    # Clear old chunks and re-index
    chat_store.clear_pdf_chunks(pdf_id)

    # Chunk and store
    chunks = _chunk_text(text)
    for i, chunk in enumerate(chunks):
        section = _detect_section_title(chunk["content"])
        # Approximate page (rough heuristic: ~3000 chars per page)
        page_estimate = (i * CHARS_PER_CHUNK) // 3000 + 1
        chat_store.upsert_pdf_chunk(
            pdf_id, ticker, i, chunk["content"],
            page_start=page_estimate,
            page_end=page_estimate,
            section_title=section,
        )

    logger.info(f"Ingested PDF {pdf_id}: {len(chunks)} chunks from {pdf_path}")
    return pdf_id


def retrieve_pdf_context(
    query: str,
    ticker: Optional[str] = None,
    pdf_id: Optional[str] = None,
    limit: int = 5,
) -> list[dict]:
    """Search PDF chunks for relevant passages."""
    from . import chat_store

    # FTS5 requires specific query formatting: each term must be valid
    # Simple approach: use the user message directly; FTS5 handles basic queries
    # For multi-word queries, wrap in quotes or use AND
    fts_query = _prepare_fts_query(query)

    return chat_store.search_pdf_chunks(fts_query, ticker=ticker, pdf_id=pdf_id, limit=limit)


def _prepare_fts_query(text: str) -> str:
    """Prepare a user message for FTS5 search.
    Simple approach: wrap in quotes for exact phrase, or use individual terms with AND.
    """
    # For short queries, use exact phrase
    if len(text) < 50:
        return f'"{text}"'
    # For longer queries, use first 2-3 meaningful words
    words = [w for w in text.split() if len(w) > 2][:5]
    if words:
        return " AND ".join(words)
    return f'"{text[:100]}"'


def ingest_analyses_pdfs(ticker: Optional[str] = None, max_pdfs: int = 20) -> int:
    """Scan analyses/ directory and ingest key PDFs for chat retrieval.

    Only ingests final report PDFs (earnings_deep_dive, company_overview) and
    earnings news transcripts — not every PDF in the tree. Limits to max_pdfs
    to avoid blocking startup.

    Returns count of ingested PDFs.
    """
    from pathlib import Path

    analyses_dir = Path(__file__).resolve().parent.parent / "analyses"
    if not analyses_dir.exists():
        return 0

    # Only ingest these PDF types (most recent first)
    priority_patterns = [
        "07_final_report/earnings_deep_dive.pdf",
        "07_final_report/company_overview",
        "04_transcripts_and_management/earnings_news",
    ]

    candidates = []
    for pdf_file in analyses_dir.rglob("*.pdf"):
        path_str = str(pdf_file)
        for pat in priority_patterns:
            if pat in path_str:
                candidates.append(pdf_file)
                break

    # Sort by modification time (newest first), limit
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    candidates = candidates[:max_pdfs]

    count = 0
    for pdf_file in candidates:
        # Determine ticker from path
        detected_ticker = None
        for part in pdf_file.parts:
            for token in part.split("_"):
                token = token.strip()
                if token.isupper() and 2 <= len(token) <= 5 and token.isalpha():
                    if token in ("PDF", "API", "HTTP", "NEW", "OLD", "CORP", "INC", "LTD", "THE"):
                        continue
                    detected_ticker = token
                    if ticker and ticker.upper() != detected_ticker:
                        continue
                    break
            if detected_ticker:
                break

        if not detected_ticker:
            stem = pdf_file.stem
            for token in stem.split("_"):
                token = token.strip()
                if token.isupper() and 2 <= len(token) <= 5 and token.isalpha():
                    if token in ("PDF", "API", "HTTP", "NEW", "OLD", "CORP", "INC", "LTD", "THE"):
                        continue
                    detected_ticker = token
                    if ticker and ticker.upper() != detected_ticker:
                        continue
                    break

        if not detected_ticker:
            continue

        title = f"{detected_ticker} — {pdf_file.parent.name} — {pdf_file.stem}"
        try:
            result = ingest_pdf(str(pdf_file), detected_ticker, title=title)
            if result:
                count += 1
        except Exception as e:
            logger.warning(f"Failed to ingest {pdf_file}: {e}")

    return count
