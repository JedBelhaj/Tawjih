"""
list_subjects.py

Scans data/final/formulas_extracted.csv and pulls out every distinct
subject/discipline abbreviation used inside the `formula` column (e.g. A,
Ang, F, M, SP, Info, PH, EP, SB, HG, Ec, Ge, ESP, IT, ALL, TE, Algo, SVT...)
so you can build a legend / sanity-check the naming.

Formulas look like:
    FG+A                       -> subjects: {A}
    FG+(A+2Ang+F)/3             -> subjects: {A, Ang, F}   (leading digit "2"
                                    is a weight/multiplier, not part of the
                                    subject name -- stripped automatically)
    FG+Max((Ang-M)/2,0)         -> subjects: {Ang, M}      ("Max" is a
                                    function keyword, not a subject -- see
                                    FUNCTION_KEYWORDS below, reported
                                    separately)

"FG" itself is the formula marker (always present) and is excluded.

Run from the project root:

    (.venv) PS orientation> python scripts/list_subjects.py

Outputs to stdout:
  - every distinct subject code found, with how many formula rows use it
  - any function keywords found (e.g. Max) and how many rows use them
Also writes data/final/subjects_found.csv with the same subject/count data.
"""

import csv
import re
import sys
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FORMULAS_CSV = PROJECT_ROOT / "data" / "final" / "formulas_extracted.csv"
OUTPUT_CSV = PROJECT_ROOT / "data" / "final" / "subjects_found.csv"

# Known non-subject keywords that can appear as letter-runs inside a
# formula. Extend this if a run turns up something else that isn't a
# subject (check the printed list -- anything that's clearly a function
# name rather than a discipline belongs here, not in your subject legend).
FUNCTION_KEYWORDS = {"FG", "Max", "Min"}

LETTER_RUN = re.compile(r"[A-Za-z]+")


def main() -> int:
    if not FORMULAS_CSV.exists():
        print(f"ERROR: file not found: {FORMULAS_CSV}")
        return 1

    with open(FORMULAS_CSV, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))

    subject_counts = Counter()
    function_counts = Counter()
    # keep one example formula per subject, handy for eyeballing context
    example_formula = {}

    for row in rows:
        formula = row["formula"].strip()
        for token in LETTER_RUN.findall(formula):
            if token in FUNCTION_KEYWORDS:
                function_counts[token] += 1
            else:
                subject_counts[token] += 1
                example_formula.setdefault(token, formula)

    print(f"Scanned {len(rows)} formula rows.\n")

    print(f"=== {len(subject_counts)} distinct subject codes found ===")
    for subject, count in sorted(subject_counts.items(), key=lambda kv: (-kv[1], kv[0])):
        print(f"  {subject:<8} used in {count:>4} row(s)   e.g. {example_formula[subject]}")

    if function_counts:
        print(f"\n=== function keywords found (excluded from subject list above) ===")
        for kw, count in sorted(function_counts.items(), key=lambda kv: (-kv[1], kv[0])):
            print(f"  {kw:<8} used in {count:>4} row(s)")

    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["subject_code", "row_count", "example_formula"])
        for subject, count in sorted(subject_counts.items(), key=lambda kv: (-kv[1], kv[0])):
            writer.writerow([subject, count, example_formula[subject]])

    print(f"\n-> saved to {OUTPUT_CSV.relative_to(PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())