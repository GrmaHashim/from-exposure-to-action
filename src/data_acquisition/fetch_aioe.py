"""
Fetch the AIOE (AI Occupational Exposure) dataset.

Source:   Felten, E., Raj, M., & Seamans, R. (2021). Occupational, industry, and
          geographic exposure to artificial intelligence: A novel dataset and its
          potential uses. Strategic Management Journal, 42(12), 2195-2217.
Repo:     https://github.com/AIOE-Data/AIOE
License:  No explicit license stated by the authors; they request the citation
          above whenever this data is used. Keep that citation in any notebook,
          report, or app that uses this data.

The repo hosts a single Excel workbook (AIOE_DataAppendix.xlsx) with five
appendices. The one used in this project is Appendix A: AIOE scores indexed
by 6-digit SOC occupation code.

Usage:
    python fetch_aioe.py

Requires internet access to raw.githubusercontent.com — run this from your
own machine, Colab, or inside the Kaggle notebook (with internet enabled in
notebook settings). It will not reach the source from a network-restricted
sandbox.
"""
import sys
from pathlib import Path

import requests

RAW_DIR = Path(__file__).resolve().parents[2] / "data" / "raw"
OUT_FILE = RAW_DIR / "AIOE_DataAppendix.xlsx"

# Try both common default-branch names; GitHub repos vary between the two.
CANDIDATE_URLS = [
    "https://raw.githubusercontent.com/AIOE-Data/AIOE/main/AIOE_DataAppendix.xlsx",
    "https://raw.githubusercontent.com/AIOE-Data/AIOE/master/AIOE_DataAppendix.xlsx",
]


def fetch() -> Path:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    last_error = None
    for url in CANDIDATE_URLS:
        try:
            resp = requests.get(url, timeout=60)
            if resp.status_code == 200 and resp.content[:2] == b"PK":  # xlsx = zip magic bytes
                OUT_FILE.write_bytes(resp.content)
                print(f"Saved: {OUT_FILE}  ({len(resp.content):,} bytes)  from {url}")
                return OUT_FILE
            last_error = f"HTTP {resp.status_code} from {url}"
        except requests.RequestException as exc:
            last_error = f"{exc} ({url})"
    raise RuntimeError(
        "Could not download AIOE_DataAppendix.xlsx from either branch. "
        f"Last error: {last_error}. Check https://github.com/AIOE-Data/AIOE "
        "in case the filename or branch changed."
    )


def list_sheets(path: Path) -> None:
    import openpyxl

    wb = openpyxl.load_workbook(path, read_only=True)
    print("Sheets found:")
    for name in wb.sheetnames:
        print(f"  - {name}")
    print(
        "\nLook for the sheet holding Appendix A (AIOE scores by 6-digit SOC code) "
        "and load it with pandas.read_excel(path, sheet_name=<name>)."
    )


if __name__ == "__main__":
    out = fetch()
    try:
        list_sheets(out)
    except Exception as exc:  # pragma: no cover
        print(f"Downloaded the file but could not list sheets automatically: {exc}", file=sys.stderr)
