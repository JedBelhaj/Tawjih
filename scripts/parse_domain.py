# -*- coding: utf-8 -*-
"""
parse_domains.py

Extracts a program_code -> domain mapping from the extracted text of
sd_par_dom_23_24_25.pdf, and merges a `domain` column into the existing
data/final/programs.csv (produced by parse_orientation_pdf.py).

Why this script ignores university/institution/scores from the dom file:
institution names in this file can wrap onto a line that appears AFTER
a data row has already started (observed e.g. "Institut Superieur des
Etudes Appliquees en Humanites a Sbeitla", where "a Sbeitla" lands on
its own line between two data rows). That makes a full structural
re-parse of university/institution unreliable here. We don't need to:
programs.csv already has correct university/institution from the
_univ file. All we need from the _dom file is which domain each
program_code belongs to.

How the domain is detected:
Every page repeats the same header block, and the domain name always
appears immediately after the literal line "2025/2024/2023" (this
repeats even on pages where the domain hasn't changed from the
previous page -- that's fine, it just re-confirms the same value).

Run from the project root, after parse_orientation_pdf.py has already
produced data/final/programs.csv:
    (.venv) PS orientation> python scripts/parse_domains.py
"""

import csv
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
EXTRACTED_FILE = PROJECT_ROOT / "data" / "extracted" / "sd_par_dom_23_24_25.txt"
FINAL_DIR = PROJECT_ROOT / "data" / "final"
PROGRAMS_CSV = FINAL_DIR / "programs.csv"

DATE_MARKER = "2025/2024/2023"
FLOAT_RE = re.compile(r"^-?\d+(\.\d+)?$")
INT_RE = re.compile(r"^\d+$")


def is_number_token(tok: str) -> bool:
    return bool(FLOAT_RE.match(tok))


def is_program_code_token(tok: str) -> bool:
    return bool(INT_RE.match(tok)) and len(tok) == 5


def fix_rtl_field(text):
    """Same fix as parse_orientation_pdf.py: full-string reversal restores
    correct Arabic reading order, skipped for fields containing digits."""
    if text is None:
        return text
    if any(ch.isdigit() for ch in text):
        return text
    return text[::-1]


def extract_program_code_from_line(stripped_line):
    """
    Returns a program_code (str) if this line is a 'new program' data row
    (leading 1-3 numeric score tokens, then non-numeric tokens, ending in
    a bare 5-digit program code), else None. We don't care about the
    bac_type/university/name content here, only whether this line
    introduces a program_code.
    """
    tokens = stripped_line.split()
    if len(tokens) < 3:
        return None

    num_score_tokens = 0
    while num_score_tokens < 3 and num_score_tokens < len(tokens) and is_number_token(tokens[num_score_tokens]):
        num_score_tokens += 1

    if num_score_tokens == 0:
        return None

    rest = tokens[num_score_tokens:]
    if not rest:
        return None

    if is_program_code_token(rest[-1]):
        return rest[-1]

    return None


def main() -> int:
    if not EXTRACTED_FILE.exists():
        print(f"ERROR: extracted file not found: {EXTRACTED_FILE}")
        print("Run scripts/extract_all_pdfs.py first.")
        return 1

    if not PROGRAMS_CSV.exists():
        print(f"ERROR: {PROGRAMS_CSV} not found. Run parse_orientation_pdf.py first.")
        return 1

    code_to_domain = {}       # program_code -> domain (first one seen)
    code_domain_conflicts = []  # (program_code, old_domain, new_domain) if it ever changes
    current_domain = None
    expect_domain_next = False

    with open(EXTRACTED_FILE, "r", encoding="utf-8") as f:
        for raw_line in f:
            stripped = raw_line.strip()
            if not stripped:
                continue

            if stripped == DATE_MARKER:
                expect_domain_next = True
                continue

            if expect_domain_next:
                current_domain = stripped
                expect_domain_next = False
                continue

            program_code = extract_program_code_from_line(stripped)
            if program_code is not None:
                if program_code in code_to_domain and code_to_domain[program_code] != current_domain:
                    code_domain_conflicts.append(
                        (program_code, code_to_domain[program_code], current_domain)
                    )
                else:
                    code_to_domain.setdefault(program_code, current_domain)

    # --- merge into programs.csv ---
    with open(PROGRAMS_CSV, "r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        fieldnames = reader.fieldnames

    if "domain" not in fieldnames:
        fieldnames = fieldnames + ["domain"]

    missing_domain = []
    for row in rows:
        code = row["program_code"]
        domain = code_to_domain.get(code)
        row["domain"] = fix_rtl_field(domain) if domain else ""
        if not domain:
            missing_domain.append(code)

    with open(PROGRAMS_CSV, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Domains found in dom file for {len(code_to_domain)} distinct program codes")
    print(f"programs.csv rows updated: {len(rows)}")
    print(f"programs.csv rows with NO domain match: {len(missing_domain)}")
    if missing_domain:
        print(f"  e.g.: {missing_domain[:10]}")
    if code_domain_conflicts:
        print(f"WARNING: {len(code_domain_conflicts)} program codes had conflicting domains across the file:")
        for code, old, new in code_domain_conflicts[:10]:
            print(f"  {code}: first saw '{fix_rtl_field(old)}', later saw '{fix_rtl_field(new)}'")

    return 0


if __name__ == "__main__":
    sys.exit(main())