"""
Scrapes tawjih.tn's fiche_formation page for every fiche_id found in the
programs CSV, and writes the results to a new CSV.

Usage:
    python scrape_fiche_details.py
    python scrape_fiche_details.py --input data/final/tawjih_scraped.csv --output data/final/fiche_details.csv
    python scrape_fiche_details.py --delay 1 --limit 50   # test run on the first 50

Resumable: if the output CSV already exists, fiche_ids already in it are
skipped, so you can stop (Ctrl+C) and rerun without losing progress or
re-hitting the server for rows you already have.
"""

import argparse
import sys
import time
from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup

FICHE_LABELS = [
    "نوع الشهادة الجامعية",
    "مدة الدراسة",
    "المجال",
    "التخصصات",
    "صيغة حساب مجموع النقاط",
    "التنفيل الجغرافي 7%",
    "تتطلب اجتياز اختبارات مسبقة",
    "لها شروط خاصة",
    "آفاق جامعية",
    "آفاق مهنية",
]

FICHE_URL = "https://www.tawjih.tn/ori_univ/search/fiche_formation.php?id={id}"


def fetch_fiche_info(fiche_id: int, timeout: int = 10) -> dict:
    info = {"fiche_id": fiche_id}
    try:
        resp = requests.get(FICHE_URL.format(id=fiche_id), timeout=timeout)
        resp.raise_for_status()
    except Exception as e:
        info["error"] = str(e)
        return info

    soup = BeautifulSoup(resp.text, "html.parser")
    lines = [l.strip() for l in soup.get_text(separator="\n").split("\n") if l.strip()]

    for i, line in enumerate(lines):
        for label in FICHE_LABELS:
            if line == label or line.startswith(label):
                if i + 1 < len(lines):
                    info[label] = lines[i + 1]
                break

    return info


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input", default="data/final/tawjih_scraped.csv",
        help="Path to the programs CSV containing a fiche_id column (default: %(default)s)",
    )
    parser.add_argument(
        "--output", default="data/final/fiche_details.csv",
        help="Path to write the scraped details CSV (default: %(default)s)",
    )
    parser.add_argument(
        "--delay", type=float, default=0.5,
        help="Seconds to wait between requests (default: %(default)s)",
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Only scrape the first N fiche_ids (useful for a test run)",
    )
    parser.add_argument(
        "--save-every", type=int, default=25,
        help="Write progress to disk every N new rows (default: %(default)s)",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)

    programs = pd.read_csv(input_path, encoding="utf-8-sig")
    fiche_ids = sorted(programs["fiche_id"].dropna().astype(int).unique())
    if args.limit:
        fiche_ids = fiche_ids[: args.limit]

    if output_path.exists():
        existing = pd.read_csv(output_path, encoding="utf-8-sig")
        done = set(existing["fiche_id"].astype(int))
        rows = existing.to_dict("records")
    else:
        existing = None
        done = set()
        rows = []

    todo = [f for f in fiche_ids if f not in done]
    print(f"{len(fiche_ids)} unique fiche_ids total, {len(done)} already scraped, {len(todo)} to go.")

    since_last_save = 0
    try:
        for i, fid in enumerate(todo, 1):
            rows.append(fetch_fiche_info(fid))
            since_last_save += 1

            print(f"[{i}/{len(todo)}] fiche_id={fid}")

            if since_last_save >= args.save_every:
                pd.DataFrame(rows).to_csv(output_path, index=False, encoding="utf-8-sig")
                since_last_save = 0

            time.sleep(args.delay)
    except KeyboardInterrupt:
        print("\nInterrupted -- saving progress before exiting.")
    finally:
        pd.DataFrame(rows).to_csv(output_path, index=False, encoding="utf-8-sig")
        print(f"Saved {len(rows)} rows to {output_path}")


if __name__ == "__main__":
    sys.exit(main())