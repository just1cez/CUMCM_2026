"""Render every PDF page and record structural/layout evidence for visual review."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

import pymupdf
from PIL import Image, ImageDraw


def audit(pdf_path: Path, prefix: str, dpi: int = 120):
    directory = Path(__file__).resolve().parent / "report" / "visual"
    directory.mkdir(parents=True, exist_ok=True)
    document = pymupdf.open(pdf_path)
    pages, outside, thin, replacements = [], [], [], 0
    for number, page in enumerate(document, 1):
        text = page.get_text()
        replacements += text.count("\ufffd")
        if len(text.strip()) < 15:
            thin.append(number)
        spans = [
            span
            for block in page.get_text("dict")["blocks"]
            if "lines" in block
            for line in block["lines"]
            for span in line["spans"]
            if span["text"].strip()
        ]
        for span in spans:
            rect = pymupdf.Rect(span["bbox"])
            if (
                rect.x0 < -0.5
                or rect.y0 < -0.5
                or rect.x1 > page.rect.width + 0.5
                or rect.y1 > page.rect.height + 0.5
            ):
                outside.append(
                    {"page": number, "text": span["text"], "bbox": list(rect)}
                )
        image = directory / f"{prefix}_{number:03d}.png"
        page.get_pixmap(dpi=dpi).save(image)
        pages.append(
            {
                "page": number,
                "characters": len(text),
                "image": image.name,
                "smallest_text_pt": min((s["size"] for s in spans), default=None),
                "largest_text_pt": max((s["size"] for s in spans), default=None),
            }
        )
    sheets = []
    for start in range(0, len(pages), 6):
        width, height, gutter = 600, 880, 15
        sheet = Image.new(
            "RGB", (3 * width + 4 * gutter, 2 * height + 3 * gutter), "#d4d4d4"
        )
        draw = ImageDraw.Draw(sheet)
        for offset, record in enumerate(pages[start : start + 6]):
            picture = Image.open(directory / record["image"]).convert("RGB")
            picture.thumbnail((width, height - 28), Image.Resampling.LANCZOS)
            x = gutter + (offset % 3) * (width + gutter)
            y = gutter + (offset // 3) * (height + gutter)
            draw.text((x + 8, y + 4), f"Page {record['page']}", fill="black")
            sheet.paste(picture, (x + (width - picture.width) // 2, y + 27))
        name = f"{prefix}_sheet_{start // 6 + 1:02d}.png"
        sheet.save(directory / name)
        sheets.append(name)
    endbody = None
    auxiliary = pdf_path.with_suffix(".aux")
    if auxiliary.exists():
        match = re.search(
            r"\\newlabel\{endbody\}\{\{[^}]*\}\{(\d+)\}", auxiliary.read_text()
        )
        if match:
            endbody = int(match[1])
    result = {
        "pdf": str(pdf_path),
        "sha256": hashlib.sha256(pdf_path.read_bytes()).hexdigest(),
        "pages": len(document),
        "size_mib": pdf_path.stat().st_size / 2**20,
        "body_end_page": endbody,
        "body_pages_excluding_abstract": endbody - 1 if endbody else None,
        "abstract_keywords_on_first_page": "关键词" in document[0].get_text(),
        "out_of_page_spans": outside,
        "replacement_characters": replacements,
        "near_empty_pages": thin,
        "rendered_all_pages": True,
        "dpi": dpi,
        "contact_sheets": sheets,
        "page_records": pages,
        "visual_review_status": "rendered_for_inspection_not_automatically_approved",
    }
    output = directory / f"{prefix}_audit.json"
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    if outside or replacements:
        raise RuntimeError(f"PDF has structural text issues; inspect {output}")
    if prefix == "paper" and (
        endbody is None
        or endbody - 1 > 30
        or not result["abstract_keywords_on_first_page"]
    ):
        raise RuntimeError(
            f"Paper abstract/body page requirement failed; inspect {output}"
        )
    print(
        json.dumps(
            {k: v for k, v in result.items() if k != "page_records"},
            ensure_ascii=False,
            indent=2,
        )
    )
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--pdf", type=Path, default=Path("report/paper.pdf"))
    parser.add_argument("--prefix", default="paper")
    parser.add_argument("--dpi", type=int, default=120)
    args = parser.parse_args()
    audit(args.pdf, args.prefix, args.dpi)
