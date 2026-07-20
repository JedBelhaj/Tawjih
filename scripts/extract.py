"""
extract_all_pdfs.py

Extracts raw text from every PDF in data/raw/ and writes one .txt file
per PDF into data/extracted/, preserving page boundaries so we can later
inspect year/section structure.

Run from the project root (the folder containing data/ and scripts/):

    (.venv) PS orientation> python scripts/extract_all_pdfs.py

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

# --- the four known files (edit if you add more later) -----------------
PDF_FILENAMES = [
    "SD_TN_2025.pdf",
    "sd_par_typbac_23_24_25.pdf",
    "sd_par_univ_23_24_25.pdf",
    "sd_par_dom_23_24_25.pdf",
]


def extract_pdf_to_txt(pdf_path: Path, out_path: Path) -> None:
    """Extract all pages of a PDF into a single .txt file, with clear
    page-break markers so we can inspect where years/sections change."""
    print(f"  -> extracting {pdf_path.name} ...")
    with pdfplumber.open(pdf_path) as pdf:
        total_pages = len(pdf.pages)
        with open(out_path, "w", encoding="utf-8") as out_file:
            for i, page in enumerate(pdf.pages, start=1):
                text = page.extract_text() or ""
                out_file.write(f"\n\n===== PAGE {i}/{total_pages} "
                                f"({pdf_path.name}) =====\n\n")
                out_file.write(text)
    print(f"     saved -> {out_path.relative_to(PROJECT_ROOT)} "
          f"({total_pages} pages)")


def main() -> int:
    if not RAW_DIR.exists():
        print(f"ERROR: raw data folder not found: {RAW_DIR}")
        return 1

    EXTRACTED_DIR.mkdir(parents=True, exist_ok=True)

    found_any = False
    for filename in PDF_FILENAMES:
        pdf_path = RAW_DIR / filename
        if not pdf_path.exists():
            print(f"WARNING: not found, skipping: {pdf_path.relative_to(PROJECT_ROOT)}")
            continue

        found_any = True
        out_path = EXTRACTED_DIR / (pdf_path.stem + ".txt")
        try:
            extract_pdf_to_txt(pdf_path, out_path)
        except Exception as exc:  # keep going even if one PDF fails
            print(f"ERROR extracting {pdf_path.name}: {exc}")

    if not found_any:
        print(f"No known PDFs found in {RAW_DIR}. "
              f"Expected one of: {PDF_FILENAMES}")
        return 1

    print("\nDone. Extracted text files are in data/extracted/.")
    return 0


if __name__ == "__main__":
    sys.exit(main())