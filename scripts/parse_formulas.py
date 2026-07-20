"""
parse_formulas.py

Parses a raw-text extraction of the Arabic orientation guide (produced by
extract_guide_pages.py / extract_all_pdfs.py) and pulls out
(program_code_3digit, bac_type, formula) rows into a CSV.

Run from the project root (the folder containing data/ and scripts/):

    (.venv) PS orientation> python scripts/parse_formulas.py

Requirements: none beyond the standard library.

IMPORTANT LIMITATIONS (read before trusting the output):
- Output columns are just program_code_3digit, formula, bac_type. Names
  aren't extracted here -- the Arabic filiere/institution text on each line
  is frequently split across multiple lines and reordered by pdfplumber's
  RTL handling, so it isn't reliable to reconstruct automatically. Pull
  names from programs.csv (join on program_code) if you need them.
- The table layout only prints each program's 5-digit code once, on the
  first of five bac-type rows (order: Lettres, Mathématiques, Sciences
  Expérimentales, Économie et Gestion, Sciences de l'Informatique) -- the
  other four rows for the same program have no code in the flattened text
  (it was a rowspan in the original table). This script tracks the most
  recently seen code as running state and carries it onto code-less rows.
  CAVEAT: if a page break falls in the middle of a program's five rows,
  the carried-forward code is still correct as long as PAGE markers don't
  reset state (they don't, by design) -- but if a page is missing/skipped
  from the extraction, rows immediately after the gap could silently
  inherit the wrong code. Spot-check the first few rows after any gap in
  your page range.
- Arabic word order coming out of pdfplumber's RTL handling is not always
  consistent across the document -- the same bac-type label can appear
  with its words in a different order on different pages. To handle this,
  bac-type tokens are matched as an unordered, normalized set of words
  (see normalize_word / BAC_TYPE_WORDSETS) rather than an exact phrase.
- Most rows carry trailing text after the bac-type words -- things like
  "(ADMA) 3 years", parenthetical university/campus names, "male-only" /
  "female-only" markers, or a following specialization name. That text is
  NOT part of the bac-type label. Matching is therefore done by finding
  the longest known bac-type word-set as a *prefix* of the captured
  words, and simply ignoring anything after it (see match_bactype below).
  Do not try to match the captured blob as a whole -- that was the
  earlier bug that sent ~99% of otherwise-fine rows to the unmatched pile.
"""

import csv
import re
import sys
from pathlib import Path

# --- paths -------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
EXTRACTED_DIR = PROJECT_ROOT / "data" / "extracted"
OUTPUT_DIR = PROJECT_ROOT / "data" / "final"

INPUT_TXT = EXTRACTED_DIR / "guide2025_p40-176.txt"   # edit to match your filename
OUTPUT_CSV = OUTPUT_DIR / "formulas_extracted.csv"
UNMATCHED_TXT = OUTPUT_DIR / "formulas_unmatched_lines.txt"

# --- known bac-type tokens, as space-separated Arabic words. Word ORDER
# --- doesn't matter for matching (see normalize_word/word-set logic
# --- below) -- only which words are present. Extend this as you discover
# --- new variants by checking UNMATCHED_TXT after a run.
BAC_TYPE_TOKENS = {
    "بادآ": "Lettres",
    "تايضاير": "Mathematiques",
    "ةيبيرجت مولع": "Sciences Experimentales",
    "فرصتو داصتقإ": "Économie et Gestion",
    "داصتقإ": "Économie et Gestion",  # occasionally extracted without "فرصتو"
    "ةيملاعلإا مولع": "Informatique",
    "ةينقتلا مولعلا": "Sciences Techniques",
    "ةضاير": "Sport",  # was previously missing entirely -- see UNMATCHED_TXT
}


def normalize_word(word: str) -> str:
    """Strip anything that isn't an Arabic letter, then fold common
    letter-shape variants (alef/hamza forms, ta marbuta, alef maksura)
    so minor spelling/typography differences don't break matching."""
    word = re.sub(r"[^\u0600-\u06FF]", "", word)
    for a, b in (("أ", "ا"), ("إ", "ا"), ("آ", "ا"), ("ى", "ي"), ("ة", "ه")):
        word = word.replace(a, b)
    return word


def to_wordset(text: str) -> frozenset:
    words = [normalize_word(w) for w in text.split()]
    return frozenset(w for w in words if w)


# --- build normalized word-set -> label lookup --------------------------
BAC_TYPE_WORDSETS = {to_wordset(token): label for token, label in BAC_TYPE_TOKENS.items()}

# distinct word-counts among known tokens, longest first, so that when we
# try to match a prefix of the captured words we prefer the most specific
# (longest) known token rather than accidentally stopping short.
_KNOWN_LENGTHS = sorted({len(ws) for ws in BAC_TYPE_WORDSETS}, reverse=True)


def match_bactype(text: str):
    """Return the bac-type label matching the START of `text`, ignoring
    any trailing words (years/campus/gender markers/specialization names
    etc. that regularly follow the bac-type on these rows). Returns None
    if no known token matches as a prefix."""
    words = [normalize_word(w) for w in text.split()]
    words = [w for w in words if w]

    for length in _KNOWN_LENGTHS:
        if length > len(words):
            continue
        candidate = frozenset(words[:length])
        label = BAC_TYPE_WORDSETS.get(candidate)
        if label:
            return label
    return None


# --- regex: FORMULA, then capture everything up to the 5-digit code
# --- (lazily, so we don't run past it), then the code itself, then
# --- whatever's left on the line. The bac-type words are pulled out of
# --- the captured middle text afterwards by match_bactype(), which
# --- tolerates -- and ignores -- trailing junk instead of requiring the
# --- whole captured blob to equal a known token exactly.
LINE_PATTERN = re.compile(r"(FG\S+)[()\*\s]+(.+?)(?<!\d)(\d{5})(?!\d)\s*(.*)")

# --- fallback for the 4 out of every 5 bac-type rows that DON'T repeat
# --- the code (the code is only printed once per program, on the first
# --- of its five bac-type rows, in the flattened text). No code or end
# --- anchor required here -- match_bactype() ignores trailing junk after
# --- the recognized bactype words on its own.
LINE_PATTERN_NOCODE = re.compile(r"(FG\S+)[()\*\s]+(.*)")


def parse_file(input_path: Path):
    text = input_path.read_text(encoding="utf-8")
    lines = text.splitlines()

    # rows[(code_3digit, bac_type)] = formula
    rows = {}
    conflicts = []
    unmatched = []

    current_code = None  # most recent 5-digit code seen, carried onto
                          # code-less continuation rows (see module docstring)

    for line in lines:
        line = line.strip()
        if not line or not line.startswith("FG"):
            continue

        # --- try the "has its own code" pattern first ---
        match = LINE_PATTERN.search(line)
        if match:
            formula, bactype_middle, code5, _rest = match.groups()
            current_code = code5  # update state regardless of recognition below
        else:
            # --- fall back to "inherits the last-seen code" pattern ---
            match = LINE_PATTERN_NOCODE.search(line)
            if not match:
                unmatched.append(line)
                continue
            formula, bactype_middle = match.groups()
            if current_code is None:
                unmatched.append(f"[no code context yet -- likely first line(s) of file/page] {line}")
                continue
            code5 = current_code

        bactype = match_bactype(bactype_middle)
        if bactype is None:
            unmatched.append(f"[unrecognized bac-type words: {bactype_middle!r}] {line}")
            continue

        code3 = code5[-3:]
        key = (code3, bactype)
        if key in rows and rows[key] != formula:
            conflicts.append((key, rows[key], formula, line))
        else:
            rows[key] = formula

    return rows, conflicts, unmatched


def write_csv(rows: dict, output_path: Path):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["program_code_3digit", "formula", "bac_type"])
        for (code3, bactype), formula in sorted(rows.items()):
            writer.writerow([code3, formula, bactype])


def write_unmatched(unmatched: list, output_path: Path):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(f"{len(unmatched)} unmatched candidate lines "
                f"(contain 'FG' + a 5-digit number, but no recognized bac-type word-set)\n")
        f.write("Extend BAC_TYPE_TOKENS in parse_formulas.py if these reveal new token variants.\n\n")
        for line in unmatched:
            f.write(line + "\n")


def main() -> int:
    if not INPUT_TXT.exists():
        print(f"ERROR: input file not found: {INPUT_TXT.relative_to(PROJECT_ROOT)}")
        print("Edit INPUT_TXT at the top of this script to match your extracted filename.")
        return 1

    rows, conflicts, unmatched = parse_file(INPUT_TXT)

    write_csv(rows, OUTPUT_CSV)
    write_unmatched(unmatched, UNMATCHED_TXT)

    print(f"Parsed {len(rows)} (code, bac_type) -> formula rows.")
    print(f"  -> saved to {OUTPUT_CSV.relative_to(PROJECT_ROOT)}")
    print(f"{len(unmatched)} unmatched lines written to "
          f"{UNMATCHED_TXT.relative_to(PROJECT_ROOT)} for manual review.")

    if conflicts:
        print(f"\nWARNING: {len(conflicts)} conflicting formula(s) found for the same "
              f"(code, bac_type) -- first occurrence was kept:")
        for (key, old, new, line) in conflicts:
            print(f"  code={key[0]} bac_type={key[1]}: kept '{old}', saw '{new}' in line:\n    {line}")

    return 0


if __name__ == "__main__":
    sys.exit(main())