# -*- coding: utf-8 -*-
"""
validate_formulas.py

Checks:
1. Does any program_code_3digit in formulas.csv appear more than once
   with a DIFFERENT formula? (Appearing twice with the SAME formula is
   harmless -- the source page likely lists some programs in more than
   one table.)
2. Cross-check against programs.csv: for every 5-digit program_code,
   take its last 3 digits as the generic code and check whether
   formulas.csv has a matching row. Reports:
     - how many of the 688 programs have a matching formula
     - which distinct 3-digit codes are missing (so we know what's
       left to source, e.g. from another bac-type page or the
       official guide)

Run from the project root:
    (.venv) PS orientation> python scripts/validate_formulas.py
"""

import csv
import sys
from collections import defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FORMULAS_CSV = PROJECT_ROOT / "data" / "final" / "formulas.csv"
PROGRAMS_CSV = PROJECT_ROOT / "data" / "final" / "programs.csv"


def main() -> int:
    if not FORMULAS_CSV.exists():
        print(f"ERROR: {FORMULAS_CSV} not found.")
        return 1

    with open(FORMULAS_CSV, "r", newline="", encoding="utf-8-sig") as f:
        formula_rows = list(csv.DictReader(f))

    print(f"=== formulas.csv ===")
    print(f"total rows: {len(formula_rows)}")

    formulas_by_code = defaultdict(set)
    for row in formula_rows:
        formulas_by_code[row["program_code_3digit"]].add(row["formula"])

    print(f"distinct program_code_3digit values: {len(formulas_by_code)}")

    conflicts = {code: fs for code, fs in formulas_by_code.items() if len(fs) > 1}
    print(f"\n=== codes with conflicting formulas ===")
    if conflicts:
        for code, fs in sorted(conflicts.items()):
            print(f"  {code}: {sorted(fs)}")
    else:
        print("  (none -- all duplicate rows agree)")

    if not PROGRAMS_CSV.exists():
        print(f"\n(programs.csv not found at {PROGRAMS_CSV}, skipping coverage check)")
        return 0

    with open(PROGRAMS_CSV, "r", newline="", encoding="utf-8-sig") as f:
        program_rows = list(csv.DictReader(f))

    suffix_to_full_codes = defaultdict(list)
    for row in program_rows:
        code = row["program_code"]
        suffix = code[-3:]
        suffix_to_full_codes[suffix].append(code)

    covered = {s: codes for s, codes in suffix_to_full_codes.items() if s in formulas_by_code}
    missing = {s: codes for s, codes in suffix_to_full_codes.items() if s not in formulas_by_code}

    covered_program_count = sum(len(v) for v in covered.values())
    missing_program_count = sum(len(v) for v in missing.values())

    print(f"\n=== coverage against programs.csv ({len(program_rows)} programs) ===")
    print(f"distinct generic (3-digit) codes in programs.csv: {len(suffix_to_full_codes)}")
    print(f"covered by formulas.csv: {len(covered)} distinct codes / {covered_program_count} programs")
    print(f"missing: {len(missing)} distinct codes / {missing_program_count} programs")
    if missing:
        print(f"\nmissing 3-digit codes (with one example 5-digit program_code each):")
        for suffix, codes in sorted(missing.items()):
            print(f"  {suffix}  (e.g. {codes[0]})")

    return 0


if __name__ == "__main__":
    sys.exit(main())