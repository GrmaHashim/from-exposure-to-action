"""
Fetch the OECD AI Exposure Measure (2026) report, and check for its
associated occupation-level data file.

Source:   OECD (2026), "The OECD AI exposure measure: Mapping the OECD AI
          Capability Indicators to occupations", OECD Artificial
          Intelligence Papers, No. 59, OECD Publishing, Paris.
Page:     https://doi.org/10.1787/f3da0f0a-en (permanent DOI; resolves to
          https://www.oecd.org/en/publications/the-oecd-ai-exposure-measure_f3da0f0a-en.html)
PDF:      https://www.oecd.org/content/dam/oecd/en/publications/reports/2026/05/the-oecd-ai-exposure-measure_489cfd42/f3da0f0a-en.pdf
License:  OECD content is published under a Creative Commons Attribution
          4.0 International licence (CC BY 4.0) -- see
          https://creativecommons.org/licenses/by/4.0/. Cite "OECD (2026),
          The OECD AI exposure measure, OECD Artificial Intelligence
          Papers No. 59" whenever this data is used.

Occupational classification: O*NET-SOC (the US Department of Labor's
detailed occupation taxonomy), NOT ISCO-08. The paper explicitly maps its
nine OECD AI Capability Indicators onto "occupational requirements in
O*NET" (p.11) and extends the ratings to "the full O*NET occupational
space" (Annex 1, p.42/43) -- on the order of ~879 O*NET-SOC occupations
per third-party summaries of the paper. This means that, once real
occupation-level scores are available, this source joins onto this
project's master table via src/crosswalks/soc_onet_crosswalk.py's
O*NET-SOC <-> SOC 2018 mapping directly -- it does NOT need the ISCO-08 <->
SOC chain that fetch_bls_crosswalks.py / fetch_ilo_genai.py require.

*** IMPORTANT -- NO MACHINE-READABLE OCCUPATION-LEVEL DATA FILE IS
    CURRENTLY PUBLISHED (checked 2026-09-23). ***
The paper itself states (p.9): "the OECD has made the full dataset
available at Introducing the OECD AI Capability Indicators - OECD.AI."
That referenced page
(https://oecd.ai/en/ai-publications/introducing-the-oecd-ai-capability-indicators,
WordPress post id 19444 on wp.oecd.ai) was checked directly via its public
wp-json REST API (https://wp.oecd.ai/wp-json/wp/v2/ai-publications/19444)
and carries exactly three linked resources in its ACF fields: the PDF
report itself (link1), an "AI Wonk" blog post (link2), and a link to the
AI Capability Indicators Webtool at aicapabilityindicators.oecd.org
(link3) -- all ten "fileN" attachment slots on that post are empty/null.
The webtool itself is a static capability-level explainer (levels 1-5 per
domain) with no per-occupation export. No xlsx/csv with the promised full
occupation-level AI Capability Gap index was found there, on the
oecd.org publication landing page (no StatLink, no sibling file at any of
the obvious /content/dam/.../f3da0f0a-en-{data,annex}.xlsx guesses -- all
404), on oecd-ilibrary.org (iLibrary was retired in July 2024), on OECD's
new Data Explorer, on OECD.AI's other post types (documents / ai-resources
/ visualizations), or in any GitHub repo. This looks like either a
not-yet-published companion dataset or a stale citation in the paper.

Given that, this script downloads the one real, citable artifact that IS
actually published right now -- the PDF report -- and validates it by
content (%PDF magic bytes), the same way the other fetch_*.py scripts in
this project validate their downloads by content rather than by HTTP
status alone. It does NOT produce occupation-level tabular data. See the
printout at the bottom of `if __name__ == "__main__":` for what to do once
OECD actually publishes the dataset file.

For reference, the paper's Annex 2 (Table A2.1, "Initial OECD mean
ratings") does print a small sample table in the PDF text itself -- 40
O*NET-SOC occupations (e.g. "Anesthesiologists", "Dentists, General",
"Firefighters", "Nursing Assistants", "Retail Salespersons") used for the
initial manual-rating benchmark, each with mean levels (0-5 scale) across
the nine capability domains (Language, Social Interaction, Problem
Solving, Creativity, Metacognition and Critical Thinking, Knowledge,
Vision, Manipulation, Robotic Intelligence). That is a benchmark subsample
embedded in running PDF text (not a clean table export), not the full
~879-occupation dataset, so it is not extracted here.

Usage:
    python fetch_oecd_exposure.py

Requires internet access to oecd.org (and, for the DOI-resolution
fallback, doi.org) -- run this from your own machine, Colab, or inside the
Kaggle notebook (with internet enabled in notebook settings). It will not
reach the source from a network-restricted sandbox.
"""
import re
import sys
from pathlib import Path

import requests

RAW_DIR = Path(__file__).resolve().parents[2] / "data" / "raw"
OUT_FILE = RAW_DIR / "OECD_AI_Exposure_Measure_f3da0f0a-en.pdf"

# The report's PDF has already moved once (its /content/dam/ path picked up
# a "/2026/05/..._489cfd42/" segment once the paper was formally numbered
# "No. 59" in the AI Papers series) -- so don't hard-code a single URL.
# Try the last-known-good direct link first, then fall back to resolving
# the permanent DOI landing page and scraping whatever PDF link it
# currently advertises.
DOI_LANDING_PAGE = "https://doi.org/10.1787/f3da0f0a-en"
CANDIDATE_URLS = [
    "https://www.oecd.org/content/dam/oecd/en/publications/reports/2026/05/the-oecd-ai-exposure-measure_489cfd42/f3da0f0a-en.pdf",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
}

PDF_MAGIC = b"%PDF"


def _looks_like_pdf(content: bytes) -> bool:
    return content[:4] == PDF_MAGIC


def _discover_pdf_url_from_landing_page() -> str | None:
    """Fallback: resolve the DOI and scrape the landing page's own PDF link,
    in case OECD moves the /content/dam/ path again."""
    try:
        resp = requests.get(DOI_LANDING_PAGE, headers=HEADERS, timeout=60)
        if resp.status_code != 200:
            return None
        m = re.search(r'href="(/content/dam/oecd/[^"]+\.pdf)"', resp.text)
        if m:
            return "https://www.oecd.org" + m.group(1)
    except requests.RequestException:
        pass
    return None


def fetch() -> Path:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    last_error = None
    for url in CANDIDATE_URLS:
        try:
            resp = requests.get(url, headers=HEADERS, timeout=60)
            if resp.status_code == 200 and _looks_like_pdf(resp.content):
                OUT_FILE.write_bytes(resp.content)
                print(f"Saved: {OUT_FILE}  ({len(resp.content):,} bytes)  from {url}")
                return OUT_FILE
            last_error = f"HTTP {resp.status_code} from {url}"
        except requests.RequestException as exc:
            last_error = f"{exc} ({url})"

    print("Direct candidate URL(s) failed; falling back to DOI resolution ...", file=sys.stderr)
    discovered = _discover_pdf_url_from_landing_page()
    if discovered:
        try:
            resp = requests.get(discovered, headers=HEADERS, timeout=60)
            if resp.status_code == 200 and _looks_like_pdf(resp.content):
                OUT_FILE.write_bytes(resp.content)
                print(
                    f"Saved: {OUT_FILE}  ({len(resp.content):,} bytes)  "
                    f"from {discovered} (discovered via DOI)"
                )
                return OUT_FILE
            last_error = f"HTTP {resp.status_code} from {discovered}"
        except requests.RequestException as exc:
            last_error = f"{exc} ({discovered})"

    raise RuntimeError(
        "Could not download the OECD AI Exposure Measure PDF from any "
        f"candidate URL or via DOI discovery. Last error: {last_error}. "
        f"Check {DOI_LANDING_PAGE} manually -- it resolves to the OECD "
        "publication landing page, which links the current PDF under "
        "'Download'."
    )


if __name__ == "__main__":
    out = fetch()
    print(
        "\nDone. This is the OECD's PDF report, not a structured data file. "
        "As of 2026-09, OECD has NOT published a machine-readable xlsx/csv "
        "of the full occupation-level AI Capability Gap index, despite the "
        "paper (p.9) saying the 'full dataset' is available on OECD.AI -- "
        "checked and found nothing there (see module docstring for exactly "
        "what was checked). If OECD later publishes the real data file, "
        "update CANDIDATE_URLS above and change the content-validation "
        "check from PDF magic bytes (%PDF) to xlsx (PK) / csv as "
        "appropriate.\n"
        "\nClassification used by this measure: O*NET-SOC (not ISCO-08) -- "
        "once/if real occupation-level scores are published, this source "
        "joins onto the master table via "
        "src/crosswalks/soc_onet_crosswalk.py directly."
    )
