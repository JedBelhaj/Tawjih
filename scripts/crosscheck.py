"""
cross_check_scraped.py

Cross-checks tawjih_scraped.csv against formulas_extracted.csv to answer:
"for every program+bac_type combination that actually exists, do I have
a formula to compute its orientation score?"

The tricky bit: tawjih_scraped.csv lists EVERY program under EVERY
bac_type you queried, using orientation_score = 0.00 as a placeholder
when that bac_type doesn't actually apply to that program (nobody can
realistically enroll in "Faculty of Arabic" via a "Sciences Techniques"
bac, for instance -- the site still includes the row, just with 0.00).
So a raw diff against formulas_extracted.csv would report hundreds of
false "missing formula" pairs that were never real combinations to begin
with.

This script splits the check into two tiers:
  - CRITICAL: (program, bac_type) pairs with a NONZERO score anywhere in
    the scrape (i.e. someone was actually admitted that way at least
    once) that have NO matching formula. These are real gaps -- you
    cannot compute these programs' cutoffs, full stop.
  - INFO: (program, bac_type) pairs that only ever show 0.00 and have no
    formula. Probably genuinely inapplicable combinations, not gaps --
    but listed so you can spot-check a sample instead of assuming.

Also reports formulas that were never observed in the scrape at all
(could mean the scrape didn't run for that bac_type/year, or the formula
is stale/wrong).

Run:
    pip install pandas --break-system-packages
    python cross_check_scraped.py
"""

import sys
from pathlib import Path

import pandas as pd

# --- paths -------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
FINAL_DIR = PROJECT_ROOT / "data" / "final"

SCRAPED_CSV = FINAL_DIR / "tawjih_scraped.csv"
FORMULAS_CSV = FINAL_DIR / "formulas_extracted.csv"
OUTPUT_MISSING_CRITICAL = FINAL_DIR / "missing_formulas_critical.csv"
OUTPUT_MISSING_INFO = FINAL_DIR / "missing_formulas_zero_only.csv"
OUTPUT_UNOBSERVED_FORMULAS = FINAL_DIR / "formulas_never_observed.csv"

# Arabic bac_type label (as used by the scraper / tawjih.tn) -> the label
# used in formulas_extracted.csv (must match BAC_TYPE_TOKENS values in
# parse_formulas.py exactly).
BAC_TYPE_MAP = {
    "رياضيات": "Mathematiques",
    "علوم تجريبية": "Sciences Experimentales",
    "العلوم التقنية": "Sciences Techniques",
    "علوم الإعلامية": "Informatique",
    "اقتصاد وتصرف": "Economie et Gestion",
    "آداب": "Lettres",
    "رياضة": "Sport",
}


def main() -> int:
    if not SCRAPED_CSV.exists():
        print(f"ERROR: file not found: {SCRAPED_CSV.relative_to(PROJECT_ROOT)}")
        return 1
    if not FORMULAS_CSV.exists():
        print(f"ERROR: file not found: {FORMULAS_CSV.relative_to(PROJECT_ROOT)}")
        return 1

    scraped = pd.read_csv(SCRAPED_CSV, dtype={"program_code": str})
    formulas = pd.read_csv(FORMULAS_CSV, dtype={"program_code_3digit": str})

    print(f"Loaded {len(scraped)} scraped rows, {len(formulas)} formula rows.\n")

    # --- map Arabic bac_type -> formula label ------------------------------
    unmapped = sorted(set(scraped["bac_type"]) - set(BAC_TYPE_MAP))
    if unmapped:
        print(f"ERROR: these bac_type values in the scrape have no mapping "
              f"in BAC_TYPE_MAP -- add them before trusting any results below: {unmapped}")
        return 1

    scraped["bac_type_label"] = scraped["bac_type"].map(BAC_TYPE_MAP)
    scraped["code3"] = scraped["program_code"].str[-3:]

    # numeric score, coercing anything unparsable to NaN so it doesn't
    # masquerade as a real nonzero score
    scraped["score_num"] = pd.to_numeric(scraped["orientation_score"], errors="coerce")

    # --- build pair sets -----------------------------------------------
    scraped_pairs_all = set(zip(scraped["code3"], scraped["bac_type_label"]))

    nonzero = scraped[scraped["score_num"] > 0]
    scraped_pairs_nonzero = set(zip(nonzero["code3"], nonzero["bac_type_label"]))

    formula_pairs = set(zip(formulas["program_code_3digit"], formulas["bac_type"]))

    # --- CRITICAL: real (nonzero) pairs with no formula -----------------
    critical_missing = scraped_pairs_nonzero - formula_pairs
    print(f"=== CRITICAL: {len(critical_missing)} (code3, bac_type) pairs have a REAL "
          f"nonzero score somewhere but NO matching formula ===")
    if critical_missing:
        detail_rows = nonzero[
            nonzero.apply(lambda r: (r["code3"], r["bac_type_label"]) in critical_missing, axis=1)
        ].drop_duplicates(subset=["code3", "bac_type_label"])
        detail_rows = detail_rows[["code3", "bac_type_label", "program_code", "program_name",
                                    "institution", "university", "year", "orientation_score"]]
        detail_rows.to_csv(OUTPUT_MISSING_CRITICAL, index=False)
        print(f"  -> details written to {OUTPUT_MISSING_CRITICAL}")
        print(detail_rows.head(20).to_string(index=False))
    print()

    # --- INFO: zero-only pairs with no formula ---------------------------
    zero_only_missing = (scraped_pairs_all - formula_pairs) - critical_missing
    print(f"[INFO] {len(zero_only_missing)} additional (code3, bac_type) pairs appear "
          f"only with score 0.00 and have no formula -- likely genuinely inapplicable "
          f"combinations, but worth a spot-check rather than assuming.")
    if zero_only_missing:
        zero_rows = scraped[
            scraped.apply(lambda r: (r["code3"], r["bac_type_label"]) in zero_only_missing, axis=1)
        ].drop_duplicates(subset=["code3", "bac_type_label"])
        zero_rows = zero_rows[["code3", "bac_type_label", "program_code", "program_name",
                                "institution", "university"]]
        zero_rows.to_csv(OUTPUT_MISSING_INFO, index=False)
        print(f"  -> details written to {OUTPUT_MISSING_INFO}")
    print()

    # --- INFO: formulas never seen in the scrape at all -------------------
    unobserved = formula_pairs - scraped_pairs_all
    print(f"[INFO] {len(unobserved)} formula rows were never observed in the scrape "
          f"at all (could mean the scrape missed a bac_type/year, or the formula's "
          f"code3/bac_type is wrong).")
    if unobserved:
        unobs_df = formulas[
            formulas.apply(lambda r: (r["program_code_3digit"], r["bac_type"]) in unobserved, axis=1)
        ]
        unobs_df.to_csv(OUTPUT_UNOBSERVED_FORMULAS, index=False)
        print(f"  -> details written to {OUTPUT_UNOBSERVED_FORMULAS}")
    print()

    # --- summary ----------------------------------------------------------
    total_real_pairs = len(scraped_pairs_nonzero)
    covered = total_real_pairs - len(critical_missing)
    pct = (covered / total_real_pairs * 100) if total_real_pairs else 0
    print("=== SUMMARY ===")
    print(f"Real (nonzero-score) program+bac_type combinations observed: {total_real_pairs}")
    print(f"Of those, covered by a formula: {covered} ({pct:.1f}%)")
    print(f"Missing a formula (CRITICAL, see {OUTPUT_MISSING_CRITICAL}): {len(critical_missing)}")

    return 1 if critical_missing else 0


if __name__ == "__main__":
    sys.exit(main())