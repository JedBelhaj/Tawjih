# -*- coding: utf-8 -*-
"""
fetch_formulas.py

Scrapes the "guide des specialites" table from orientini.com's score
calculator page, which lists, for each generic (3-digit) program code:
    - the program name (Arabic + French)
    - the score formula (e.g. "FG+(M+SP)/2", "FG+SVT", "FG+M")

This table appears to be the general specialization catalog (not
filtered to one bac type) -- the SAME table should render regardless of
which bac-type variant of the page you load, since eligibility differs
by bac type but the underlying formula per program does not.

Saves to data/final/formulas.csv with columns:
    program_code_3digit, program_name_ar, program_name_fr, formula

NOTE: program_code_3digit is the GENERIC code (e.g. "301" for Droit),
which is the last 3 digits of the 5-digit program_code already in
programs.csv (e.g. 10301, 70301 both map to generic code 301). Joining
this against programs.csv requires matching on that suffix.

Requires: pip install requests beautifulsoup4

Run from the project root:
    (.venv) PS orientation> python scripts/fetch_formulas.py
"""

import csv
import re
import sys
from pathlib import Path

import requests
from bs4 import BeautifulSoup

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FINAL_DIR = PROJECT_ROOT / "data" / "final"
OUTPUT_CSV = FINAL_DIR / "formulas.csv"

URL = "https://orientini.com/sms/"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
}

# A formula always starts with "FG" (Formule Generale) and is made up of
# uppercase letters, digits, and the symbols + - * / ( ) , used to
# combine subject codes (M, SP, SVT, AR, ANG, F, PH, Info, Spt, All, ...).
FORMULA_RE = re.compile(r"FG[A-Za-z0-9+\-*/(),.]*")

# Generic program code: 2-3 digits at the very start of the row's first cell.
CODE_RE = re.compile(r"^\s*(\d{2,3})\b")


def find_catalog_table(soup):
    """
    Find the table whose header row mentions both a code column and a
    "Formule"/specializations-style column. We don't assume a fixed
    table index, since the page has many small tables (menus etc.).
    """
    for table in soup.find_all("table"):
        header_text = table.get_text(" ", strip=True)
        if "الرمز" in header_text and ("Formule" in header_text or "التخصّصات" in header_text or "التخصصات" in header_text):
            return table
    return None


def parse_row(tr):
    cells = tr.find_all(["td", "th"])
    if len(cells) < 3:
        return None

    cell_texts = [c.get_text(" ", strip=True) for c in cells]
    first_cell = cell_texts[0]

    code_match = CODE_RE.match(first_cell)
    if not code_match:
        return None
    program_code = code_match.group(1)

    # name cell: usually the 2nd cell, contains Arabic then French name
    name_cell = cell_texts[1] if len(cell_texts) > 1 else ""
    name_ar, name_fr = split_ar_fr(name_cell)

    # formula: search all remaining cells for something matching FORMULA_RE
    formula = None
    for text in cell_texts[2:]:
        m = FORMULA_RE.search(text)
        if m:
            formula = m.group(0)
            break

    if formula is None:
        return None

    return program_code, name_ar, name_fr, formula


def split_ar_fr(name_cell):
    """
    Name cells look like "الإجازة في القانون   LICENCE EN DROIT" -- Arabic
    followed by the French/uppercase name. Split on the first run of
    Latin letters.
    """
    match = re.search(r"[A-Za-zÀ-ÿ]", name_cell)
    if not match:
        return name_cell.strip(), ""
    idx = match.start()
    return name_cell[:idx].strip(), name_cell[idx:].strip()


def main() -> int:
    print(f"Fetching {URL} ...")
    resp = requests.get(URL, headers=HEADERS, timeout=30)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    table = find_catalog_table(soup)
    if table is None:
        print("ERROR: could not find the catalog table on the page. "
              "The page structure may have changed -- inspect the saved "
              "raw HTML (written to data/extracted/orientini_sms_raw.html) "
              "and adjust find_catalog_table().")
        FINAL_DIR.mkdir(parents=True, exist_ok=True)
        (PROJECT_ROOT / "data" / "extracted" / "orientini_sms_raw.html").write_text(
            resp.text, encoding="utf-8"
        )
        return 1

    rows = []
    unparsed_rows = 0
    for tr in table.find_all("tr"):
        parsed = parse_row(tr)
        if parsed:
            rows.append(parsed)
        else:
            # header rows and rows without a real code are expected here;
            # only worth investigating if this count is surprisingly high
            unparsed_rows += 1

    FINAL_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["program_code_3digit", "program_name_ar", "program_name_fr", "formula"])
        for code, name_ar, name_fr, formula in rows:
            writer.writerow([code, name_ar, name_fr, formula])

    print(f"Parsed {len(rows)} program formulas")
    print(f"Rows skipped (likely headers/non-data rows): {unparsed_rows}")
    print(f"Saved: {OUTPUT_CSV.relative_to(PROJECT_ROOT)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())