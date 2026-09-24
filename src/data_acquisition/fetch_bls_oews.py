"""
Fetch BLS OEWS (Occupational Employment and Wage Statistics) national,
cross-industry "All Data" tables for multiple recent reference years, to
build a multi-year employment/wage trend panel by 6-digit SOC code.

Source:   U.S. Bureau of Labor Statistics, Occupational Employment and Wage
          Statistics (OEWS) program.
Page:     https://www.bls.gov/oes/tables.htm  (see "All data" links under
          each year's "National" tables)
License:  U.S. government work, public domain. No attribution legally
          required, but cite "U.S. Bureau of Labor Statistics, OEWS program"
          as the source in any notebook, report, or app that uses this data.

Each year's national all-industries workbook (oesmYYnat.zip) is a zip
archive containing a single Excel file (national_MYYYY_dl.xlsx / similar)
with one row per detailed (6-digit) SOC occupation: OCC_CODE, OCC_TITLE,
TOT_EMP, employment percent relative standard error, mean/median hourly and
annual wage, and percentile wages (10th/25th/75th/90th).

Usage:
    python fetch_bls_oews.py

Requires internet access to bls.gov -- run this from your own machine,
Colab, or inside the Kaggle notebook (with internet enabled in notebook
settings). It will not reach the source from a network-restricted sandbox.

KNOWN ISSUE (as of 2026-09): bls.gov blocks automated requests at the WAF
level with HTTP 403 "Access Denied", even with a full browser-like
User-Agent, Accept, Accept-Language and Referer headers -- and even on the
plain HTML landing pages (oes/tables.htm, download.bls.gov directory
listings), not just the zip files themselves. This is the same block hit by
fetch_bls_crosswalks.py. If this still fails, download the files manually
in your own browser and place them at the paths below; the sheet layout
inside is stable across recent years so no code changes should be needed
downstream.
"""
import sys
import zipfile
from pathlib import Path

import requests

RAW_DIR = Path(__file__).resolve().parents[2] / "data" / "raw"

# BLS's national "All Data" OEWS workbook is a zip archive named
# oesm<YY>nat.zip, historically served under a directory named either
# "special-requests" (hyphen, current) or "special.requests" (dot, older
# archived pages still link to this spelling) -- try both. Most recent
# three published reference years as of 2026-09: May 2025, May 2024, May 2023.
FILES = {
    "2025": (
        "oesm25nat.zip",
        [
            "https://www.bls.gov/oes/special-requests/oesm25nat.zip",
            "https://www.bls.gov/oes/special.requests/oesm25nat.zip",
        ],
    ),
    "2024": (
        "oesm24nat.zip",
        [
            "https://www.bls.gov/oes/special-requests/oesm24nat.zip",
            "https://www.bls.gov/oes/special.requests/oesm24nat.zip",
        ],
    ),
    "2023": (
        "oesm23nat.zip",
        [
            "https://www.bls.gov/oes/special-requests/oesm23nat.zip",
            "https://www.bls.gov/oes/special.requests/oesm23nat.zip",
        ],
    ),
}

ZIP_MAGIC = b"PK"

# A full browser-like User-Agent, matching fetch_bls_crosswalks.py's
# approach -- bls.gov's WAF has blocked plain `requests` default headers
# in the past for this project.
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.bls.gov/oes/tables.htm",
}


def _looks_like_zip(content: bytes) -> bool:
    return content[:2] == ZIP_MAGIC


def fetch_one(out_name: str, candidate_urls: list[str]) -> Path:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RAW_DIR / out_name
    last_error = None
    for url in candidate_urls:
        try:
            resp = requests.get(url, headers=HEADERS, timeout=60)
            if resp.status_code == 200 and _looks_like_zip(resp.content):
                out_path.write_bytes(resp.content)
                print(f"Saved: {out_path}  ({len(resp.content):,} bytes)  from {url}")
                return out_path
            last_error = f"HTTP {resp.status_code} from {url}"
        except requests.RequestException as exc:
            last_error = f"{exc} ({url})"
    raise RuntimeError(
        f"Could not download {out_name} from any candidate URL. "
        f"Last error: {last_error}. bls.gov is known to WAF-block automated "
        "requests for this project (see fetch_bls_crosswalks.py) -- if this "
        "persists, download the file manually from "
        "https://www.bls.gov/oes/tables.htm (National, All Data) and save it "
        f"as {out_path}."
    )


def fetch() -> list[Path]:
    saved = []
    for year, (out_name, urls) in FILES.items():
        print(f"Downloading BLS OEWS national all-data table for {year} ...")
        saved.append(fetch_one(out_name, urls))
    return saved


def list_zip_contents(path: Path) -> None:
    with zipfile.ZipFile(path) as zf:
        print(f"Contents of {path.name}:")
        for name in zf.namelist():
            print(f"  - {name}")


if __name__ == "__main__":
    paths = fetch()
    for path in paths:
        try:
            list_zip_contents(path)
        except Exception as exc:  # pragma: no cover
            print(f"Downloaded {path.name} but could not list zip contents: {exc}", file=sys.stderr)
    print(
        f"\nDone. {len(paths)} OEWS national all-data workbook(s) saved under {RAW_DIR}. "
        "Each is a zip containing one national_M<YYYY>_dl.xlsx with one row per "
        "6-digit SOC occupation (OCC_CODE, OCC_TITLE, TOT_EMP, wage percentiles)."
    )
