"""Extract text, metadata, and visual renders for PDF audit.

This script is intentionally read-only for source PDFs. It writes audit artifacts
under reports/pdf-visual-diff.
"""
from __future__ import annotations

import json
from pathlib import Path

import fitz
from PIL import Image, ImageChops, ImageStat


ROOT = Path(__file__).resolve().parents[1]
MODEL_PATH = ROOT / "docs/specs/modele.pdf"
GENERATED_PATH = ROOT / "docs/specs/genere.pdf"
FINAL_PATH = ROOT / "reports/generated/final-report-en.pdf"
OUT_DIR = ROOT / "reports/pdf-visual-diff"


def page_summary(page: fitz.Page) -> dict:
    page_dict = page.get_text("dict")
    fonts: dict[str, int] = {}
    colors: dict[str, int] = {}
    blocks: list[dict] = []

    for block in page_dict.get("blocks", []):
        if block.get("type") != 0:
            continue
        text_lines: list[str] = []
        for line in block.get("lines", []):
            line_text = "".join(span.get("text", "") for span in line.get("spans", []))
            if line_text.strip():
                text_lines.append(line_text.strip())
            for span in line.get("spans", []):
                text = span.get("text", "")
                font_key = f"{span.get('font')}|{round(span.get('size', 0), 2)}"
                fonts[font_key] = fonts.get(font_key, 0) + len(text)
                colors[str(span.get("color"))] = colors.get(str(span.get("color")), 0) + len(text)
        text = " ".join(text_lines).strip()
        if text:
            blocks.append({
                "bbox": [round(x, 2) for x in block.get("bbox", [])],
                "text": text[:300],
            })

    return {
        "size": [round(page.rect.width, 2), round(page.rect.height, 2)],
        "text_chars": len(page.get_text()),
        "fonts": fonts,
        "colors": colors,
        "blocks": blocks[:30],
    }


def analyze_pdf(path: Path, prefix: str) -> dict:
    doc = fitz.open(path)
    pages: list[dict] = []
    all_text: list[str] = []

    for index, page in enumerate(doc, start=1):
        text = page.get_text()
        all_text.append(f"\n--- PAGE {index} ---\n{text}")
        pages.append(page_summary(page))

        pix = page.get_pixmap(matrix=fitz.Matrix(150 / 72, 150 / 72), alpha=False)
        pix.save(OUT_DIR / f"{prefix}-page-{index}.png")

    (OUT_DIR / f"{prefix}-text.txt").write_text("\n".join(all_text), encoding="utf-8")
    return {
        "path": str(path),
        "bytes": path.stat().st_size,
        "page_count": len(doc),
        "metadata": doc.metadata,
        "pages": pages,
    }


def white_canvas(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    canvas = Image.new("RGB", size, "white")
    canvas.paste(image.convert("RGB"), (0, 0))
    return canvas


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    model = analyze_pdf(MODEL_PATH, "model")
    generated = analyze_pdf(GENERATED_PATH, "generated")
    final = analyze_pdf(FINAL_PATH, "final") if FINAL_PATH.exists() else None

    comparisons: list[dict] = []
    common_pages = min(model["page_count"], generated["page_count"])
    for page_no in range(1, common_pages + 1):
        model_image = Image.open(OUT_DIR / f"model-page-{page_no}.png")
        generated_image = Image.open(OUT_DIR / f"generated-page-{page_no}.png")
        size = (
            max(model_image.width, generated_image.width),
            max(model_image.height, generated_image.height),
        )
        model_canvas = white_canvas(model_image, size)
        generated_canvas = white_canvas(generated_image, size)
        diff = ImageChops.difference(model_canvas, generated_canvas)
        diff.save(OUT_DIR / f"diff-page-{page_no}.png")

        side = Image.new("RGB", (size[0] * 2 + 24, size[1]), "white")
        side.paste(model_canvas, (0, 0))
        side.paste(generated_canvas, (size[0] + 24, 0))
        side.save(OUT_DIR / f"side-by-side-page-{page_no}.png")

        stat = ImageStat.Stat(diff)
        mean_diff = sum(stat.mean) / len(stat.mean)
        comparisons.append({
            "page": page_no,
            "model_png": model_image.size,
            "generated_png": generated_image.size,
            "mean_pixel_diff": round(mean_diff, 3),
            "diff_bbox": diff.getbbox(),
        })

    final_comparisons: list[dict] = []
    if final:
        common_final_pages = min(model["page_count"], final["page_count"])
        for page_no in range(1, common_final_pages + 1):
            model_image = Image.open(OUT_DIR / f"model-page-{page_no}.png")
            final_image = Image.open(OUT_DIR / f"final-page-{page_no}.png")
            size = (
                max(model_image.width, final_image.width),
                max(model_image.height, final_image.height),
            )
            model_canvas = white_canvas(model_image, size)
            final_canvas = white_canvas(final_image, size)
            diff = ImageChops.difference(model_canvas, final_canvas)
            diff.save(OUT_DIR / f"diff-final-page-{page_no}.png")

            side = Image.new("RGB", (size[0] * 2 + 24, size[1]), "white")
            side.paste(model_canvas, (0, 0))
            side.paste(final_canvas, (size[0] + 24, 0))
            side.save(OUT_DIR / f"side-by-side-final-page-{page_no}.png")

            stat = ImageStat.Stat(diff)
            mean_diff = sum(stat.mean) / len(stat.mean)
            final_comparisons.append({
                "page": page_no,
                "model_png": model_image.size,
                "final_png": final_image.size,
                "mean_pixel_diff": round(mean_diff, 3),
                "diff_bbox": diff.getbbox(),
            })

    analysis = {
        "model": model,
        "generated": generated,
        "final": final,
        "comparisons": comparisons,
        "final_comparisons": final_comparisons,
    }
    (OUT_DIR / "pdf-analysis.json").write_text(
        json.dumps(analysis, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(json.dumps({
        "out_dir": str(OUT_DIR),
        "model_pages": model["page_count"],
        "generated_pages": generated["page_count"],
        "final_pages": final["page_count"] if final else None,
        "model_bytes": model["bytes"],
        "generated_bytes": generated["bytes"],
        "final_bytes": final["bytes"] if final else None,
        "comparisons": comparisons,
        "final_comparisons": final_comparisons,
    }, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
