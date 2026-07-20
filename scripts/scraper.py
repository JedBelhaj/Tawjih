"""
scrape_tawjih.py

Scrapes https://www.tawjih.tn/ori_univ/search/index.php across every
bac_type x year combination, paginating through results, and writes a
single combined CSV of everything found.

The endpoint is plain server-rendered HTML driven by GET query params --
no JS execution or auth needed. Confirmed params (from browser devtools):

    section_bac         Arabic bac-type label (e.g. "رياضيات")
    ordre_resultats      "ordre_guide" (matches the guide's own ordering)
    domaine, universite, gouvernerat, code, mon_score, comparaison_score
                          left blank to get everything, unfiltered
    comparaison_annee    year, e.g. 2025 (site supports back to 2019)
    page, ipp             pagination -- ipp = results per page (max
                          explicit option seen in the UI is 200)

IMPORTANT -- before running this at any real volume:
  - Check https://www.tawjih.tn/robots.txt and the site's terms yourself.
  - This script is deliberately rate-limited (REQUEST_DELAY_SECONDS).
    Don't drop that just to go faster -- it's a small independent site,
    not a CDN-backed API.
  - A "مجموع نقاط آخر موجه" (score) of 0.00 does NOT necessarily mean
    "no one was admitted this year" -- it can also mean this program
    doesn't actually accept this bac_type at all (i.e. it's outside that
    program's formula). Cross-reference against formulas_extracted.csv
    before trusting a 0.00 row as a real cutoff.

Run:
    pip install requests beautifulsoup4 --break-system-packages
    python scrape_tawjih.py
"""

import csv
import re
import sys
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://www.tawjih.tn/ori_univ/search/index.php"

BAC_TYPES = [
    "رياضيات",
    "علوم تجريبية",
    "العلوم التقنية",
    "علوم الإعلامية",
    "اقتصاد وتصرف",
    "آداب",
    "رياضة",
]

# Edit this if you only want the latest year for now -- full history is
# more requests (7 bac_types x N years x ~4 pages each at ipp=200).
YEARS = [2025, 2024, 2023, 2022, 2021, 2020, 2019]

ITEMS_PER_PAGE = 200          # max explicit option in the site's own UI
REQUEST_DELAY_SECONDS = 1.0   # politeness delay between requests
REQUEST_TIMEOUT = 20
MAX_PAGES_SAFETY = 20         # hard stop per (bac_type, year) in case of a bug

OUTPUT_CSV = Path("tawjih_scraped.csv")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; research script; contact: <your email here>)",
}

FICHE_ID_RE = re.compile(r"id=(\d+)")


def fetch_page(section_bac: str, year: int, page: int) -> str:
    params = {
        "section_bac": section_bac,
        "ordre_resultats": "ordre_guide",
        "domaine": "",
        "universite": "",
        "gouvernerat": "",
        "code": "",
        "mon_score": "",
        "comparaison_score": "",
        "comparaison_annee": year,
        "irssal": "",
        "page": page,
        "ipp": ITEMS_PER_PAGE,
    }
    resp = requests.get(BASE_URL, params=params, headers=HEADERS, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return resp.text


def parse_rows(html: str):
    """Yield dicts for each result row on the page. Returns [] if the page
    has no results table (i.e. we've paginated past the last page)."""
    soup = BeautifulSoup(html, "html.parser")

    table = soup.find("table")
    if table is None:
        return []

    rows = []
    for tr in table.find_all("tr"):
        cells = tr.find_all("td")
        if len(cells) < 5:
            continue  # header row or malformed row

        code = cells[0].get_text(strip=True)
        name_cell = cells[1]
        name = name_cell.get_text(strip=True)
        link = name_cell.find("a")
        fiche_id = None
        if link and link.get("href"):
            m = FICHE_ID_RE.search(link["href"])
            if m:
                fiche_id = m.group(1)

        institution = cells[2].get_text(strip=True)
        university = cells[3].get_text(strip=True)
        score_text = cells[4].get_text(strip=True)

        # program codes should be numeric; skip anything that slipped
        # through that isn't a real data row
        if not code.isdigit():
            continue

        rows.append({
            "program_code": code,
            "program_name": name,
            "fiche_id": fiche_id,
            "institution": institution,
            "university": university,
            "orientation_score": score_text,
        })
    return rows


def scrape_all():
    all_rows = []
    seen_keys = set()  # (program_code, bac_type, year) -- guard against accidental dupes

    for bac_type in BAC_TYPES:
        for year in YEARS:
            page = 1
            while page <= MAX_PAGES_SAFETY:
                print(f"[{bac_type} / {year}] page {page} ...", end=" ", flush=True)
                try:
                    html = fetch_page(bac_type, year, page)
                except requests.RequestException as e:
                    print(f"ERROR: {e} -- skipping rest of this (bac_type, year)")
                    break

                rows = parse_rows(html)
                print(f"{len(rows)} rows")

                if not rows:
                    break  # past the last page

                for row in rows:
                    key = (row["program_code"], bac_type, year)
                    if key in seen_keys:
                        continue
                    seen_keys.add(key)
                    row["bac_type"] = bac_type
                    row["year"] = year
                    all_rows.append(row)

                if len(rows) < ITEMS_PER_PAGE:
                    break  # short page -- that was the last one

                page += 1
                time.sleep(REQUEST_DELAY_SECONDS)

            time.sleep(REQUEST_DELAY_SECONDS)

    return all_rows


def write_csv(rows, output_path: Path):
    fieldnames = ["year", "bac_type", "program_code", "program_name",
                  "fiche_id", "institution", "university", "orientation_score"]
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})


def main() -> int:
    rows = scrape_all()
    write_csv(rows, OUTPUT_CSV)
    print(f"\nDone. {len(rows)} total rows written to {OUTPUT_CSV}")
    return 0


if __name__ == "__main__":
    sys.exit(main())