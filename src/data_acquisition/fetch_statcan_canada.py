"""
Fetch the Statistics Canada "Potential AI Occupational Exposure in Canada"
data table -- the source for this project's APPENDIX-ONLY Canada comparison
chart (one chart, not a parallel pipeline).

Source:   Mehdi, T., & Morissette, R. (2024). Experimental Estimates of
          Potential Artificial Intelligence Occupational Exposure in Canada.
          Analytical Studies Branch Research Paper Series, no. 478.
          Statistics Canada Catalogue no. 11F0019M2024005.
Page:     https://www150.statcan.gc.ca/n1/pub/11f0019m/11f0019m2024005-eng.htm
          Released September 3, 2024. This is the foundational C-AIOE
          (complementarity-adjusted AI occupational exposure) paper for
          Canada and is cited as the primary source by StatCan's later
          (2026) follow-on articles on journeypersons, cultural industries,
          and generative-AI employment trends -- those are narrower spinoffs
          of the same index, not updates to this dataset.
License:  Statistics Canada Open Licence. Free to use, reproduce, and
          redistribute with attribution: "Source: Statistics Canada,
          [title], [date]." Keep this citation in any notebook, report, or
          app that uses this data.

There is no separate downloadable CSV/XLSX -- both tables below are HTML
<table> elements embedded directly in the article page, so this script
saves the article page itself; parsing happens downstream, not here. Two
occupation-level tables exist on the page, at different levels of detail:

    - "Data table for Chart 1" (a simple <details> section): 28 aggregated
      NOC (National Occupational Classification 2016 v1.3) occupation
      groups x 3 columns -- percentage of employees in each of "high
      exposure/low complementarity", "high exposure/high complementarity",
      and "low exposure".

    - Appendix Table A.2 ("...employees aged 18 to 64, May 2021" -- the
      MORE RECENT of two appendix tables on the page; Table A.1 is the same
      structure for May 2016, kept only as a 2016-vs-2021 trend option, not
      needed for the single comparison chart) -- RICHER and RECOMMENDED
      over the Chart-1 table above: the same 28 NOC occupation groups, but
      with Employment (number), AIOE (average index score), Potential
      complementarity, and Complementarity-adjusted AIOE, PLUS the same 3
      exposure-percentage columns as Chart 1. This is the one to parse for
      the project's Canada comparison chart.

      CAUTION: Table A.2 is one HTML <table> that bundles many demographic
      breakdowns together (Occupation, then Industry, Highest level of
      education, Employment income decile, Selected census metropolitan
      area, Field of study, Age, Gender, disability status, immigrant
      status, racialized group, hours worked, union membership, enterprise
      size, work-from-home ability, risk of automation -- each introduced
      by its own sub-header row within the SAME table). Downstream parsing
      must isolate only the rows between the "Occupation" sub-header row
      and the next sub-header ("Industry") -- the other sections are
      out of scope for this project's appendix-only guardrail (one Canada
      comparison chart, not a parallel demographic pipeline).

NOC codes are used as-is in both tables (no crosswalk needed for this
appendix chart).

Usage:
    python fetch_statcan_canada.py

Requires internet access to www150.statcan.gc.ca -- run this from your own
machine, Colab, or inside the Kaggle notebook (with internet enabled in
notebook settings). It will not reach the source from a network-restricted
sandbox.
"""
from pathlib import Path

import requests

RAW_DIR = Path(__file__).resolve().parents[2] / "data" / "raw"
OUT_FILE = RAW_DIR / "StatCan_11F0019M2024005_AI_Occupational_Exposure.html"

# Canonical article URL first, DOI resolver (redirects to the same page) as
# a fallback in case the direct path ever moves.
CANDIDATE_URLS = [
    "https://www150.statcan.gc.ca/n1/pub/11f0019m/11f0019m2024005-eng.htm",
    "https://doi.org/10.25318/11f0019m2024005-eng",
]

# Markers that must be present to confirm we got the real article page with
# its embedded occupation-exposure table, not an error page or a generic
# "page not found" redirect.
REQUIRED_MARKERS = [
    b"Data table for Chart 1",
    b"National Occupational Classification",
]


def _looks_like_article_page(content: bytes) -> bool:
    lowered = content.lower()
    if b"<html" not in lowered and b"<!doctype html" not in lowered:
        return False
    return all(marker in content for marker in REQUIRED_MARKERS)


def fetch() -> Path:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    last_error = None
    for url in CANDIDATE_URLS:
        try:
            resp = requests.get(url, timeout=60, headers={"User-Agent": "Mozilla/5.0"})
            if resp.status_code == 200 and _looks_like_article_page(resp.content):
                OUT_FILE.write_bytes(resp.content)
                print(f"Saved: {OUT_FILE}  ({len(resp.content):,} bytes)  from {url}")
                return OUT_FILE
            last_error = f"HTTP {resp.status_code} from {url} (or missing expected table markers)"
        except requests.RequestException as exc:
            last_error = f"{exc} ({url})"
    raise RuntimeError(
        "Could not download the StatCan AI occupational exposure article from "
        f"any candidate URL. Last error: {last_error}. Check "
        "https://www150.statcan.gc.ca/n1/pub/11f0019m/11f0019m2024005-eng.htm "
        "in case the page moved, or search Statistics Canada's site for "
        "'Experimental Estimates of Potential Artificial Intelligence "
        "Occupational Exposure in Canada'."
    )


if __name__ == "__main__":
    out = fetch()
    print(
        f"\nDone. {out.name} contains two occupation-level tables (see module "
        "docstring): the simple 'Data table for Chart 1' (28 NOC groups x 3 "
        "exposure-percentage columns), and the richer, RECOMMENDED Appendix "
        "Table A.2 (May 2021 -- same 28 NOC groups plus Employment/AIOE/"
        "Potential complementarity/Complementarity-adjusted AIOE). NOC codes "
        "appear in parentheses after each occupation-group label, e.g. "
        "'Management occupations (0)'. Table A.2 is embedded within a much "
        "larger demographic-breakdown table -- isolate only the 'Occupation' "
        "section (between the 'Occupation' and 'Industry' sub-header rows) "
        "when parsing downstream. No crosswalk conversion is needed since "
        "NOC codes are used as-is."
    )
