import csv
import unicodedata
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent

PROGRAMS_CSV = (
    PROJECT_ROOT
    / "data"
    / "final"
    / "programs.csv"
)

NORMALIZED_CSV = (
    PROJECT_ROOT
    / "data"
    / "final"
    / "programs_normalized.csv"
)


def normalize_text(text: str) -> str:
    """
    Convert Arabic presentation-form characters into normal Unicode Arabic.

    Example:
        ﺍﻹﺟﺎﺯﺓ ﻓﻲ ﺍﻟﻌﺮﺑﻴﺔ
    becomes:
        الإجازة في العربية
    """
    if not text:
        return text

    return unicodedata.normalize("NFKC", text)


def normalize_csv(input_file: Path, output_file: Path) -> None:
    with input_file.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as infile:

        reader = csv.DictReader(infile)

        rows = []

        for row in reader:
            normalized_row = {
                column: normalize_text(value)
                for column, value in row.items()
            }

            rows.append(normalized_row)

        fieldnames = reader.fieldnames

    output_file.parent.mkdir(parents=True, exist_ok=True)

    with output_file.open(
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as outfile:

        writer = csv.DictWriter(
            outfile,
            fieldnames=fieldnames,
        )

        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    if not PROGRAMS_CSV.exists():
        raise FileNotFoundError(
            f"Input file not found: {PROGRAMS_CSV}"
        )

    normalize_csv(
        input_file=PROGRAMS_CSV,
        output_file=NORMALIZED_CSV,
    )

    print(
        f"Normalized CSV created at:\n"
        f"{NORMALIZED_CSV}"
    )


if __name__ == "__main__":
    main()