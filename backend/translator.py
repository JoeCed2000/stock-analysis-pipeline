"""Document translation through the local Codex CLI provider.

Parallel by default: paragraphs translated concurrently for speed.
"""
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

from backend import codex_provider

logger = logging.getLogger(__name__)

MAX_CHUNK_CHARS = 2000
MAX_PARALLEL_CHUNKS = 6  # parallel paragraph translations


class TranslationUnavailableError(RuntimeError):
    """Raised when a required local Codex translation cannot be produced."""


def _target_language_name(target_lang: str) -> str:
    names = {
        "jp": "Japanese",
        "ja": "Japanese",  # ISO 639-1 alias — public API accepts ?lang=ja
        "fr": "French", "zh": "Chinese",
        "ko": "Korean", "de": "German",
        "en": "English",
    }
    return names.get(target_lang, target_lang)


def _estimate_max_tokens(text: str, target_lang: str) -> int:
    if target_lang in {"jp", "ja", "zh", "ko"}:
        return min(int(len(text) * 1.5) + 200, 4000)
    return min(len(text) * 2 + 200, 4000)


def _translate_chunk(text: str, target_lang: str, *, strict: bool = False) -> str:
    language_name = _target_language_name(target_lang)
    system = (
        f"You are a professional financial translator translating to {language_name}. "
        "Preserve all numbers, tickers, URLs, dates, percentages, markdown structure, "
        "tables, file paths, and financial units exactly. Return only the translation."
    )
    prompt = (
        f"Translate the following text to {language_name}.\n\n"
        "Do not add commentary. Do not remove source citations. Keep headings and lists structurally identical.\n\n"
        f"{text}"
    )
    translated = codex_provider._codex_chat(
        prompt,
        system=system,
        max_tokens=_estimate_max_tokens(text, target_lang),
    )
    if translated and translated.strip():
        return translated.strip()
    if strict:
        raise TranslationUnavailableError(f"Codex translation unavailable for target language: {target_lang}")
    return text


def translate_text(text: str, target_lang: str = "jp", *, strict: bool = False) -> str:
    """Translate text using local Codex. Falls back to original text if Codex is unavailable.
    
    Paragraphs are translated in parallel (up to 6 concurrent) for speed.
    """
    if not text or not text.strip() or target_lang == "en":
        return text

    if len(text) <= MAX_CHUNK_CHARS:
        return _translate_chunk(text, target_lang, strict=strict)

    # Split by paragraph, translate in parallel
    paragraphs = text.split("\n\n")
    # Group short paragraphs to minimize API calls
    chunks = []
    buf = ""
    for para in paragraphs:
        if len(buf) + len(para) < MAX_CHUNK_CHARS:
            buf = f"{buf}\n\n{para}" if buf else para
        else:
            if buf:
                chunks.append(buf)
            buf = para
    if buf:
        chunks.append(buf)

    # Translate concurrently
    results: dict[int, str] = {}
    with ThreadPoolExecutor(max_workers=min(len(chunks), MAX_PARALLEL_CHUNKS)) as ex:
        futures = {
            ex.submit(_translate_chunk, chunk, target_lang, strict=True): idx
            for idx, chunk in enumerate(chunks)
        }
        for future in as_completed(futures):
            idx = futures[future]
            try:
                results[idx] = future.result()
            except Exception as e:
                logger.warning(f"Parallel chunk {idx} translation failed: {e}")
                results[idx] = chunks[idx]  # fallback to original

    # Reassemble in order
    return "\n\n".join(results[i] for i in range(len(chunks)))


def translate_file(filepath: str, target_lang: str = "jp", *, strict: bool = False) -> bool:
    """Translate a text file in place through local Codex. Returns True when content changed."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()

        translated = translate_text(content, target_lang, strict=strict)

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(translated)

        logger.info("Translated %s -> %s (%d -> %d chars)", filepath, target_lang, len(content), len(translated))
        return translated != content
    except Exception as e:
        logger.warning("Translation failed for %s: %s", filepath, e)
        return False
