# -*- coding: utf-8 -*-
"""
list_domains.py

Prints every distinct `domain` value found in data/final/programs.csv,
along with how many programs fall under each one -- useful for a quick
sanity check that the domain text reads correctly and to see the full
category list at a glance.

Run from the project root:
    (.venv) PS orientation> python scripts/list_domains.py
"""

import csv
import sys
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROGRAMS_CSV = PROJECT_ROOT / "data" / "final" / "programs.csv"


def main() -> int:
    if not PROGRAMS_CSV.exists():
        print(f"ERROR: {PROGRAMS_CSV} not found.")
        return 1

    with open(PROGRAMS_CSV, "r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        counts = Counter(row["domain"] for row in reader)

    print(f"{len(counts)} distinct domains, {sum(counts.values())} total programs\n")
    for domain, count in sorted(counts.items(), key=lambda kv: kv[0]):
        print(f"{count:4d}  {domain}")

    return 0


if __name__ == "__main__":
    sys.exit(main())