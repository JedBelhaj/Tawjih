# -*- coding: utf-8 -*-
"""
validate_programs.py

Runs a set of sanity checks on data/final/programs.csv and prints a
summary, instead of us eyeballing rows one at a time. Checks:

1. Row count and how many distinct universities / institutions / domains.
2. How many institutions each university has (sorted) -- a university
   with a suspiciously huge or tiny institution count is worth a look.
3. Any institution name that's unusually SHORT (word count <= 2) -- a
   likely sign of a wrapped/truncated name rather than a real short name.
4. Any (university, institution) pair where the institution appears
   under more than one university -- could be legitimate (some ISETs
   really are shared/reassigned) or could be a leftover parsing bug;
   printed either way so we can eyeball it.
5. A specific spot-check on the codes we already debugged by hand
   (86209, 86391, 86394, 86396, 86566, 86568, 86570, 86571), so we can
   confirm the DGET fix actually landed for all of them, not just one.
6. Cross-check against cutoffs.csv: every program_code in cutoffs.csv
   should exist in programs.csv, and vice versa.

Run from the project root:
    (.venv) PS orientation> python scripts/validate_programs.py
"""

import csv
import sys
from collections import Counter, defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROGRAMS_CSV = PROJECT_ROOT / "data" / "final" / "programs.csv"
CUTOFFS_CSV = PROJECT_ROOT / "data" / "final" / "cutoffs.csv"

SPOT_CHECK_CODES = ["86209", "86391", "86394", "86396", "86566", "86568", "86570", "86571"]


def main() -> int:
    if not PROGRAMS_CSV.exists():
        print(f"ERROR: {PROGRAMS_CSV} not found.")
        return 1

    with open(PROGRAMS_CSV, "r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        fieldnames = reader.fieldnames

    print(f"=== programs.csv ===")
    print(f"columns: {fieldnames}")
    print(f"rows: {len(rows)}")

    universities = Counter(r["university"] for r in rows)
    institutions = Counter(r["institution"] for r in rows)
    print(f"distinct universities: {len(universities)}")
    print(f"distinct institutions: {len(institutions)}")
    if "domain" in fieldnames:
        domains = Counter(r["domain"] for r in rows)
        print(f"distinct domains: {len(domains)}")

    # --- institutions per university ---
    inst_by_univ = defaultdict(set)
    for r in rows:
        inst_by_univ[r["university"]].add(r["institution"])
    print("\n=== institutions per university (sorted by count) ===")
    for univ, insts in sorted(inst_by_univ.items(), key=lambda kv: -len(kv[1])):
        print(f"{len(insts):3d}  {univ}")

    # --- suspiciously short institution names ---
    print("\n=== institution names with <= 2 words (possible truncation) ===")
    short_found = False
    for inst in sorted(institutions):
        if inst and len(inst.split()) <= 2:
            short_found = True
            print(f"  \"{inst}\"  ({institutions[inst]} programs)")
    if not short_found:
        print("  (none found)")

    # --- institutions appearing under more than one university ---
    univ_by_inst = defaultdict(set)
    for r in rows:
        univ_by_inst[r["institution"]].add(r["university"])
    print("\n=== institutions appearing under more than one university ===")
    multi_found = False
    for inst, univs in sorted(univ_by_inst.items()):
        if len(univs) > 1:
            multi_found = True
            print(f"  \"{inst}\" -> {sorted(univs)}")
    if not multi_found:
        print("  (none found)")

    # --- spot check known codes ---
    print("\n=== spot check ===")
    by_code = {r["program_code"]: r for r in rows}
    for code in SPOT_CHECK_CODES:
        r = by_code.get(code)
        if r is None:
            print(f"  {code}: NOT FOUND in programs.csv")
        else:
            print(f"  {code}: university=\"{r['university']}\"  institution=\"{r['institution']}\"")

    # --- cross-check against cutoffs.csv ---
    if CUTOFFS_CSV.exists():
        with open(CUTOFFS_CSV, "r", newline="", encoding="utf-8-sig") as f:
            cutoff_rows = list(csv.DictReader(f))
        cutoff_codes = set(r["program_code"] for r in cutoff_rows)
        program_codes = set(r["program_code"] for r in rows)

        only_in_cutoffs = cutoff_codes - program_codes
        only_in_programs = program_codes - cutoff_codes

        print(f"\n=== cross-check with cutoffs.csv ({len(cutoff_rows)} rows) ===")
        print(f"program_codes only in cutoffs.csv (missing from programs.csv): {len(only_in_cutoffs)}")
        if only_in_cutoffs:
            print(f"  e.g.: {sorted(only_in_cutoffs)[:10]}")
        print(f"program_codes only in programs.csv (missing from cutoffs.csv): {len(only_in_programs)}")
        if only_in_programs:
            print(f"  e.g.: {sorted(only_in_programs)[:10]}")
    else:
        print(f"\n(cutoffs.csv not found at {CUTOFFS_CSV}, skipping cross-check)")

    return 0


if __name__ == "__main__":
    sys.exit(main())