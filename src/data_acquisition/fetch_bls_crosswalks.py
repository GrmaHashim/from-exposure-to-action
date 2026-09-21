"""
Fetch the official BLS reference crosswalks needed to join ISCO-08-coded
sources (ILO, OECD) onto this project's SOC-2018-keyed master table.

There is no single official ISCO-08 <-> SOC 2018 crosswalk. BLS publishes
two separate pieces that chain together:

    1. ISCO-08 <-> SOC 2010   (BLS's own crosswalk, built by matching ISCO
       unit groups to SOC 2010 detailed occupations)
    2. SOC 2010 -> SOC 2018   (BLS's own crosswalk for the classification
       revision)

Chaining (1) through (2) gives ISCO-08 -> SOC 2018. See
src/crosswalks/soc_onet_crosswalk.py for the functions that do the chaining
and the lookup.

Source:   U.S. Bureau of Labor Statistics, Standard Occupational
          Classification (SOC) program.
Pages:    https://www.bls.gov/soc/2018/crosswalks.htm
          https://www.bls.gov/soc/isco_soc_crosswalk_process.pdf (methodology)
License:  U.S. government work, public domain. No attribution legally
          required, but cite "U.S. Bureau of Labor Statistics, SOC program"
          as the source in any notebook, report, or app that uses this data.

Usage:
    python fetch_bls_crosswalks.py

Requires internet access to bls.gov -- run this from your own machine,
Colab, or inside the Kaggle notebook (with internet enabled in notebook
settings). It will not reach the source from a network-restricted sandbox.
"""
import sys
from pathlib import Path

import requests

RAW_DIR = Path(__file__).resolve().parents[2] / "data" / "raw"

# (output filename, candidate URLs to try in order)
FILES = {
    "isco_soc2010": (
        "ISCO_SOC_2010_Crosswalk.xls",
        [
            "https://www.bls.gov/soc/ISCO_SOC_Crosswalk.xls",
            "https://www.bls.gov/soc/isco_soc_crosswalk.xls",
        ],
    ),
    "soc2010_soc2018": (
        "SOC_2010_to_2018_Crosswalk.xlsx",
        [
            "https://www.bls.gov/soc/2018/soc_2010_to_2018_crosswalk.xlsx",
        ],
    ),
}

# BLS serves both legacy .xls (OLE/CFB format) and modern .xlsx (zip format).
# Accept either magic-byte signature as a valid download.
XLS_MAGIC = b"\xd0\xcf\x11\xe0"  # legacy .xls (Compound File Binary)
XLSX_MAGIC = b"PK"              # modern .xlsx (zip)


def _looks_like_excel(content: bytes) -> bool:
    return content[:4] == XLS_MAGIC or content[:2] == XLSX_MAGIC


def fetch_one(out_name: str, candidate_urls: list[str]) -> Path:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RAW_DIR / out_name
    last_error = None
    for url in candidate_urls:
        try:
            resp = requests.get(url, timeout=60)
            if resp.status_code == 200 and _looks_like_excel(resp.content):
                out_path.write_bytes(resp.content)
                print(f"Saved: {out_path}  ({len(resp.content):,} bytes)  from {url}")
                return out_path
            last_error = f"HTTP {resp.status_code} from {url}"
        except requests.RequestException as exc:
            last_error = f"{exc} ({url})"
    raise RuntimeError(
        f"Could not download {out_name} from any candidate URL. "
        f"Last error: {last_error}. Check "
        "https://www.bls.gov/soc/2018/crosswalks.htm in case a filename changed."
    )


def fetch() -> list[Path]:
    saved = []
    for key, (out_name, urls) in FILES.items():
        print(f"Downloading BLS crosswalk: {key} ...")
        saved.append(fetch_one(out_name, urls))
    return saved


if __name__ == "__main__":
    paths = fetch()
    print(f"\nDone. {len(paths)} crosswalk file(s) saved under {RAW_DIR}.")
    print(
        "Next: src/crosswalks/soc_onet_crosswalk.py's build_isco_to_soc2018() "
        "chains these two files into a single ISCO-08 -> SOC 2018 lookup table."
    )
