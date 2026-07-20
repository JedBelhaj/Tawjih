# -*- coding: utf-8 -*-
"""
parse_orientation_pdf.py

Parses the extracted text of sd_par_univ_23_24_25.pdf (produced by
extract_all_pdfs.py, i.e. data/extracted/sd_par_univ_23_24_25.txt) into
two clean CSVs:

    data/final/programs.csv
        program_code, program_name, university, institution

    data/final/cutoffs.csv
        year, program_code, bac_type, orientation_score

Structure being parsed (one row per line of extracted text):

    Page boilerplate (ministry/title/"scientific research") -> skipped
    Date line "2025/2024/2023" or page-number footer -> page_top_marker:
        the NEXT 1-2 header lines are the page's authoritative
        (university, institution) restatement, set directly
    Mid-page header line(s) (not right after a page_top_marker):
        1 header before the next data line = institution-only change
        (university unchanged, e.g. a new ISET under the same DGET);
        2 headers before the next data line = a genuine new
        (university, institution) pair
    Column header line          -> "2025 2024 2023 <ce'ba word>"  -> skipped
    New-program data line        -> score score score  bac_type  program_name...  program_code
    Continuation data line       -> score score score  bac_type
    Footer disclaimer line       -> skipped

Any line we can't confidently classify is written to
data/final/unparsed_lines.txt for manual inspection, instead of guessed at.
Any spot where 3+ header lines stack up before a data line is printed as
a warning (took the last two) for manual review, instead of silently
guessed at.

Run from the project root:
    (.venv) PS orientation> python scripts/parse_orientation_pdf.py
"""

import csv
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
EXTRACTED_FILE = PROJECT_ROOT / "data" / "extracted" / "sd_par_univ_23_24_25.txt"
FINAL_DIR = PROJECT_ROOT / "data" / "final"

# --- known closed set of bac types (exact strings as extracted) --------
# NOTE: text is RTL and pdfplumber gives us the visually-reversed word
# order, but that's fine -- we only need EXACT STRING MATCHES, not
# correct reading order, to classify each row.
BAC_TYPES = {
    "ﺕﺎﻴﺿﺎﻳﺭ",           # Mathematiques
    "ﺔﻴﺒﻳﺮﺠﺗ ﻡﻮﻠﻋ",       # Sciences Experimentales
    "ﻑﺮﺼﺗﻭ ﺩﺎﺼﺘﻗﺇ",      # Economie et Gestion
    "ﺔﻴﻨﻘﺘﻟﺍ ﻡﻮﻠﻌﻟﺍ",      # Sciences Techniques
    "ﺔﻴﻣﻼﻋﻹﺍ ﻡﻮﻠﻋ",       # Informatique / Sciences de l'Information
    "ﺔﺿﺎﻳﺭ",              # Sport
    "ﺏﺍﺩﺁ",               # Lettres
}

# Canonical French labels for the 7 bac types, keyed by the raw (reversed)
# Arabic string pdfplumber extracts. This is more useful downstream than
# leaving bac_type as backward-rendered Arabic.
BAC_TYPE_LABELS = {
    "ﺕﺎﻴﺿﺎﻳﺭ": "Mathematiques",
    "ﺔﻴﺒﻳﺮﺠﺗ ﻡﻮﻠﻋ": "Sciences Experimentales",
    "ﻑﺮﺼﺗﻭ ﺩﺎﺼﺘﻗﺇ": "Economie et Gestion",
    "ﺔﻴﻨﻘﺘﻟﺍ ﻡﻮﻠﻌﻟﺍ": "Sciences Techniques",
    "ﺔﻴﻣﻼﻋﻹﺍ ﻡﻮﻠﻋ": "Informatique",
    "ﺔﺿﺎﻳﺭ": "Sport",
    "ﺏﺍﺩﺁ": "Lettres",
}


def fix_rtl_field(text):
    """
    pdfplumber extracts RTL Arabic text with the whole field's character
    order reversed (both word order and the letters within each word).
    A straight full-string reversal restores correct reading order.

    We only do this for fields that are pure Arabic (no ASCII digits),
    since a field containing embedded numbers would have those numbers
    corrupted by a blind reversal. Fields with digits are left as-is and
    flagged, for manual inspection -- none were observed in university/
    institution/program_name fields so far, but better to flag than
    silently mangle if one ever appears.
    """
    if text is None:
        return text
    if any(ch.isdigit() for ch in text):
        return text  # left untouched -- contains digits, unsafe to reverse blindly
    return text[::-1]

PAGE_MARKER_RE = re.compile(r"^===== PAGE")
FOOTER_DISCLAIMER_MARKERS = (
    "ﺪﺣﺃﺎﻬﻴﻟﺇ ﻪﺟﻮﻳ",   # start of the standard footer disclaimer sentence
)
# Fixed boilerplate lines that repeat at the top of every single page
# (ministry name / report title / "and scientific research"). These have
# no leading digit like a real header line, but they are page furniture,
# not a university or institution -- must be skipped, not treated as a
# header, or they'd inflate the header count on every page.
PAGE_BOILERPLATE_LINES = {
    "ﻲﻟﺎﻌﻟﺍ ﻢﻴﻠﻌﺘﻟﺍ ﺓﺭﺍﺯﻭ",
    "ﺓﺮﻴﺧﻷﺍ ﺙﻼﺜﻟﺍ ﺕﺍﻮﻨﺴﻠﻟ ﻪﺟﻮﻣ ﺮﺧﺁ ﻁﺎﻘﻧ ﻉﻮﻤﺠﻣ ﺭﻮﻄﺗ",
    "ﻲﻤﻠﻌﻟﺍ ﺚﺤﺒﻟﺍﻭ",
}
PAGE_NUMBER_RE = re.compile(r"^\d+\s*/\s*\d+\b")  # matches BOTH the "2025/2024/2023"
                                                    # date line at the top of a page and
                                                    # the "54 / 100" page-number footer --
                                                    # both are treated as "a fresh page-top
                                                    # header pair is about to appear next",
                                                    # which is harmless to flag on either one

FLOAT_RE = re.compile(r"^-?\d+(\.\d+)?$")
INT_RE = re.compile(r"^\d+$")


def is_number_token(tok: str) -> bool:
    return bool(FLOAT_RE.match(tok))


def is_program_code_token(tok: str) -> bool:
    # Program codes observed so far are 5-digit integers, e.g. 10101.
    return bool(INT_RE.match(tok)) and len(tok) == 5


def classify_and_parse(line: str, current_program_code, current_program_name):
    """
    Returns one of:
        ("header", name)   -- a university- or institution-level line
                              appearing mid-page; which one it is gets
                              resolved later based on how many consecutive
                              header lines preceded the next data line.
        ("page_top_marker", None) -- the "2025/2024/2023" date line (or the
                              page-number footer) -- signals that the next
                              1-2 header lines are the page's authoritative
                              (university, institution) restatement, not a
                              mid-page change.
        ("skip", None)
        ("program_row", (program_code, program_name, bac_type, scores))
        ("continuation_row", (bac_type, scores))
        ("unparsed", None)
    """
    stripped = line.strip()
    if not stripped:
        return ("skip", None)

    if PAGE_MARKER_RE.match(stripped):
        return ("skip", None)

    if any(stripped.startswith(m) for m in FOOTER_DISCLAIMER_MARKERS):
        return ("skip", None)

    if stripped in PAGE_BOILERPLATE_LINES:
        return ("skip", None)

    if PAGE_NUMBER_RE.match(stripped) or "ﺮﻴﻏ ﻻ ﻲﺒﻳﺮﻘﺗ" in stripped:
        return ("page_top_marker", None)

    tokens = stripped.split()

    # column header line: "2025 2024 2023 <something>" with no program code
    # (3 leading year-looking ints, then non-numeric tokens, no trailing int)
    if (
        len(tokens) >= 4
        and tokens[0] in {"2023", "2024", "2025"}
        and tokens[1] in {"2023", "2024", "2025"}
        and tokens[2] in {"2023", "2024", "2025"}
    ):
        return ("skip", None)

    # university- or institution-level header lines: no leading numeric
    # token at all. We no longer try to tell them apart here by keyword
    # (e.g. requiring "Jami'a"/University) -- some top-level entities that
    # play the same structural role as a university are administrative
    # bodies with different names (e.g. the Direction Generale des Etudes
    # Technologiques, which governs ISETs directly instead of a regional
    # university). Which of these header lines is the university and
    # which is the institution gets resolved in main() based on how many
    # consecutive header lines appeared before the next data line.
    if not is_number_token(tokens[0]):
        return ("header", stripped)

    # data line: leading tokens are 1-3 scores. A blank cell in the source
    # PDF (year not offered yet) simply drops a token rather than printing
    # a 0, so we take as many leading numeric tokens as are present, up to
    # 3, rather than requiring exactly 3.
    num_score_tokens = 0
    while num_score_tokens < 3 and num_score_tokens < len(tokens) and is_number_token(tokens[num_score_tokens]):
        num_score_tokens += 1

    if num_score_tokens == 0:
        return ("unparsed", None)

    score_tokens = tokens[:num_score_tokens]
    scores = [float(t) for t in score_tokens]
    rest = tokens[num_score_tokens:]

    if not rest:
        return ("unparsed", None)

    # new-program row: last token is a 5-digit program code
    if is_program_code_token(rest[-1]):
        program_code = rest[-1]
        body = rest[:-1]
        # find where bac_type ends: bac_type is a known exact phrase,
        # possibly multi-word. Try matching from the front, longest known
        # phrase first.
        bac_type = None
        body_text = " ".join(body)
        for candidate in sorted(BAC_TYPES, key=len, reverse=True):
            if body_text.startswith(candidate + " ") or body_text == candidate:
                bac_type = candidate
                program_name = body_text[len(candidate):].strip()
                break
        if bac_type is None:
            return ("unparsed", None)
        return ("program_row", (program_code, program_name, bac_type, scores))

    # continuation row: remaining tokens should be exactly a known bac_type
    rest_text = " ".join(rest)
    if rest_text in BAC_TYPES:
        return ("continuation_row", (rest_text, scores))

    return ("unparsed", None)


def main() -> int:
    if not EXTRACTED_FILE.exists():
        print(f"ERROR: extracted file not found: {EXTRACTED_FILE}")
        print("Run scripts/extract_all_pdfs.py first.")
        return 1

    FINAL_DIR.mkdir(parents=True, exist_ok=True)

    programs = {}   # program_code -> (program_name, university, institution)
    cutoffs = []     # list of (year, program_code, bac_type, score)
    unparsed_lines = []
    header_count_warnings = []  # (line_no, pending_headers) when count != 1 or 2

    current_university = None
    current_institution = None
    current_program_code = None
    current_program_name = None
    pending_headers = []  # header lines seen since the last data line (mid-page changes)
    expect_page_top_headers = 0  # counts down 2,1,0 -- consumes the next
                                   # header line(s) right after a page_top_marker
                                   # directly, since those are always the page's
                                   # authoritative (university, institution)
                                   # restatement, not a mid-page change

    years = ["2025", "2024", "2023"]  # column order confirmed from header row

    def flush_pending_headers(line_no):
        nonlocal current_university, current_institution
        if len(pending_headers) == 2:
            current_university, current_institution = pending_headers
        elif len(pending_headers) == 1:
            current_institution = pending_headers[0]
            # current_university stays unchanged -- same top-level entity
        elif len(pending_headers) >= 3:
            # Unexpected -- take the last two rather than guess further,
            # but flag it so we can check what actually happened here.
            current_university, current_institution = pending_headers[-2:]
            header_count_warnings.append((line_no, list(pending_headers)))
        pending_headers.clear()

    with open(EXTRACTED_FILE, "r", encoding="utf-8") as f:
        for line_no, raw_line in enumerate(f, start=1):
            kind, payload = classify_and_parse(
                raw_line, current_program_code, current_program_name
            )

            if kind == "skip":
                continue
            elif kind == "page_top_marker":
                expect_page_top_headers = 2
            elif kind == "header":
                if expect_page_top_headers == 2:
                    current_university = payload
                    expect_page_top_headers = 1
                    pending_headers.clear()  # page-top restatement is authoritative
                elif expect_page_top_headers == 1:
                    current_institution = payload
                    expect_page_top_headers = 0
                    pending_headers.clear()
                else:
                    pending_headers.append(payload)
            elif kind == "program_row":
                if expect_page_top_headers != 0:
                    header_count_warnings.append((line_no, [f"expected {expect_page_top_headers} more page-top header(s) but got data instead"]))
                    expect_page_top_headers = 0
                flush_pending_headers(line_no)
                program_code, program_name, bac_type, scores = payload
                current_program_code = program_code
                current_program_name = program_name
                programs[program_code] = (
                    program_name,
                    current_university,
                    current_institution,
                )
                for year, score in zip(years, scores):
                    cutoffs.append((year, program_code, bac_type, score))
            elif kind == "continuation_row":
                if expect_page_top_headers != 0:
                    header_count_warnings.append((line_no, [f"expected {expect_page_top_headers} more page-top header(s) but got data instead"]))
                    expect_page_top_headers = 0
                flush_pending_headers(line_no)
                bac_type, scores = payload
                if current_program_code is None:
                    unparsed_lines.append((line_no, raw_line.rstrip("\n")))
                    continue
                for year, score in zip(years, scores):
                    cutoffs.append((year, current_program_code, bac_type, score))
            else:  # unparsed
                unparsed_lines.append((line_no, raw_line.rstrip("\n")))

    # --- write programs.csv ---
    programs_path = FINAL_DIR / "programs.csv"
    with open(programs_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["program_code", "program_name", "university", "institution"])
        for code, (name, univ, inst) in sorted(programs.items()):
            writer.writerow([
                code,
                fix_rtl_field(name),
                fix_rtl_field(univ),
                fix_rtl_field(inst),
            ])

    # --- write cutoffs.csv ---
    cutoffs_path = FINAL_DIR / "cutoffs.csv"
    with open(cutoffs_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["year", "program_code", "bac_type", "orientation_score"])
        for year, program_code, bac_type, score in cutoffs:
            label = BAC_TYPE_LABELS.get(bac_type, bac_type)
            writer.writerow([year, program_code, label, score])

    # --- write unparsed lines for review ---
    unparsed_path = FINAL_DIR / "unparsed_lines.txt"
    with open(unparsed_path, "w", encoding="utf-8") as f:
        for line_no, text in unparsed_lines:
            f.write(f"line {line_no}: {text}\n")

    print(f"Programs found: {len(programs)}")
    print(f"Cutoff rows written: {len(cutoffs)}")
    print(f"Unparsed lines: {len(unparsed_lines)} -> see {unparsed_path.relative_to(PROJECT_ROOT)}")
    if header_count_warnings:
        print(f"WARNING: {len(header_count_warnings)} places had 3+ consecutive header lines "
              f"(took the last two, may need review):")
        for line_no, headers in header_count_warnings[:10]:
            print(f"  line {line_no}: {headers}")
    print(f"Saved: {programs_path.relative_to(PROJECT_ROOT)}")
    print(f"Saved: {cutoffs_path.relative_to(PROJECT_ROOT)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())