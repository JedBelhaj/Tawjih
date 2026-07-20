"""
extract_guide_pages.py

Extracts raw text from a specific page range of the orientation guide PDF
(data/raw/guide2026.pdf) and writes it to data/extracted/, preserving page
boundaries so we can later parse program codes and score formulas.

Run from the project root (the folder containing data/ and scripts/):

    (.venv) PS orientation> python scripts/extract_guide_pages.py

Requirements:
    pip install pdfplumber
"""

import sys
from pathlib import Path

import pdfplumber

# --- paths -------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = PROJECT_ROOT / "data" / "raw"
EXTRACTED_DIR = PROJECT_ROOT / "data" / "extracted"

# --- the file + page range to extract (edit if needed) -----------------
PDF_FILENAME = "guide2025.pdf"
START_PAGE = 40   # 1-indexed, inclusive (as seen in a PDF viewer)
END_PAGE = 176    # 1-indexed, inclusive


def extract_page_range_to_txt(pdf_path: Path, out_path: Path,
                               start_page: int, end_page: int) -> None:
    """Extract pages [start_page, end_page] (1-indexed, inclusive) of a PDF
    into a single .txt file, with clear page-break markers so we can
    inspect where filière/domain sections change."""
    print(f"  -> extracting {pdf_path.name} pages {start_page}-{end_page} ...")
    with pdfplumber.open(pdf_path) as pdf:
        total_pages = len(pdf.pages)
        if start_page < 1 or end_page > total_pages:
            raise ValueError(
                f"Requested pages {start_page}-{end_page} out of range "
                f"(document has {total_pages} pages)."
            )

        with open(out_path, "w", encoding="utf-8") as out_file:
            for page_num in range(start_page, end_page + 1):
                page = pdf.pages[page_num - 1]
                text = page.extract_text() or ""
                out_file.write(f"\n\n===== PAGE {page_num}/{total_pages} "
                                f"({pdf_path.name}) =====\n\n")
                out_file.write(text)

    print(f"     saved -> {out_path.relative_to(PROJECT_ROOT)} "
          f"(pages {start_page}-{end_page})")


def main() -> int:
    if not RAW_DIR.exists():
        print(f"ERROR: raw data folder not found: {RAW_DIR}")
        return 1

    EXTRACTED_DIR.mkdir(parents=True, exist_ok=True)

    pdf_path = RAW_DIR / PDF_FILENAME
    if not pdf_path.exists():
        print(f"ERROR: not found: {pdf_path.relative_to(PROJECT_ROOT)}")
        return 1

    out_path = EXTRACTED_DIR / f"{pdf_path.stem}_p{START_PAGE}-{END_PAGE}.txt"
    try:
        extract_page_range_to_txt(pdf_path, out_path, START_PAGE, END_PAGE)
    except Exception as exc:
        print(f"ERROR extracting {pdf_path.name}: {exc}")
        return 1

    print("\nDone. Extracted text file is in data/extracted/.")
    return 0


if __name__ == "__main__":
    sys.exit(main())