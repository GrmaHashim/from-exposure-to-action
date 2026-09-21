"""
Fetch the O*NET database (core files: Task Ratings, Skills, Abilities, Job Zones).

Source:   O*NET Resource Center, sponsored by the US Department of Labor,
          Employment and Training Administration.
Page:     https://www.onetcenter.org/database.html
License:  O*NET data is released under a Creative Commons Attribution 4.0
          International License. Attribution required: "This [product]
          incorporates information from O*NET Web Services / O*NET Resource
          Center. Sponsored by the U.S. Department of Labor, Employment and
          Training Administration." Keep this attribution in any notebook,
          report, or app that uses this data.

O*NET publishes a new numbered version periodically (e.g. 31.0). This script
targets a specific version so results are reproducible; update ONET_VERSION
if a newer release is available at https://www.onetcenter.org/database.html
when you run this.

Usage:
    python fetch_onet.py

Requires internet access to onetcenter.org — run this from your own machine,
Colab, or inside the Kaggle notebook (with internet enabled in notebook
settings). It will not reach the source from a network-restricted sandbox.
"""
import zipfile
from pathlib import Path

import requests

ONET_VERSION = "31_0"  # verify against onetcenter.org/database.html before a fresh run
BASE_URL = f"https://www.onetcenter.org/dl_files/database/db_{ONET_VERSION}_excel.zip"

RAW_DIR = Path(__file__).resolve().parents[2] / "data" / "raw"
ZIP_PATH = RAW_DIR / f"onet_db_{ONET_VERSION}_excel.zip"
EXTRACT_DIR = RAW_DIR / f"onet_db_{ONET_VERSION}"

# The core files this project actually needs (others in the zip are ignored to
# keep data/raw small). Filenames match O*NET's Excel release naming.
#
# NOTE (v31.0): O*NET restructured a couple of files compared to older
# versions. "Skills.xlsx" was split into "Essential Skills.xlsx" and
# "Transferable Skills.xlsx", and "Alternate Titles.xlsx" was renamed to
# "Sample of Reported Titles.xlsx". If a future O*NET version renames files
# again, re-run with FILES_OF_INTEREST = [] temporarily (see the "Warning"
# branch in extract()) to print every filename in the archive and update
# this list.
FILES_OF_INTEREST = [
    "Task Ratings.xlsx",
    "Essential Skills.xlsx",
    "Transferable Skills.xlsx",
    "Abilities.xlsx",
    "Knowledge.xlsx",
    "Work Activities.xlsx",
    "Work Context.xlsx",
    "Job Zones.xlsx",
    "Job Zone Reference.xlsx",
    "Occupation Data.xlsx",
    "Sample of Reported Titles.xlsx",
]


def fetch() -> Path:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Downloading O*NET {ONET_VERSION.replace('_', '.')} database ... ({BASE_URL})")
    resp = requests.get(BASE_URL, timeout=120, stream=True)
    resp.raise_for_status()
    with open(ZIP_PATH, "wb") as f:
        for chunk in resp.iter_content(chunk_size=1 << 20):
            f.write(chunk)
    print(f"Saved zip: {ZIP_PATH}")
    return ZIP_PATH


def extract(zip_path: Path) -> None:
    EXTRACT_DIR.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
        wanted = [n for n in names if Path(n).name in FILES_OF_INTEREST]
        if not wanted:
            print("Warning: none of the expected filenames matched. Extracting everything instead.")
            print("Files in archive:")
            for n in names:
                print(f"  - {n}")
            zf.extractall(EXTRACT_DIR)
            return
        for n in wanted:
            # Extract by basename only (flattened into EXTRACT_DIR), since the
            # zip's internal folder (e.g. "db_31_0_excel/") is not something
            # downstream code should need to know about.
            dest = EXTRACT_DIR / Path(n).name
            with zf.open(n) as src, open(dest, "wb") as out:
                out.write(src.read())
            print(f"Extracted: {n} -> {dest.name}")

        found_names = {Path(n).name for n in wanted}
        missing = [f for f in FILES_OF_INTEREST if f not in found_names]
        if missing:
            print(f"\nWarning: {len(missing)} expected file(s) were NOT found in this archive:")
            for f in missing:
                print(f"  - {f}")
            print("This usually means O*NET renamed a file in this version. Full archive listing:")
            for n in names:
                print(f"  - {n}")


if __name__ == "__main__":
    zip_path = fetch()
    extract(zip_path)
    print(f"\nDone. Core files are under: {EXTRACT_DIR}")
    print("Key join columns: 'O*NET-SOC Code' (occupation) — see src/crosswalks/ for mapping to US SOC / NOC / ISCO-08.")
